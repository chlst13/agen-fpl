#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================
  AGEN FPL  —  pemantau otomatis Fantasy Premier League
=============================================================
Jalan sendiri di background. Setiap kali dieksekusi dia akan:

  1. Tarik data terbaru dari API resmi FPL
  2. Hitung skor tiap pemain (form, xGI, menit, jadwal, harga)
  3. Bedah skuad kamu: siapa yang layak jadi kapten, siapa yang
     sebaiknya dijual, siapa kandidat pengganti sesuai budget
  4. Deteksi pemain yang harganya berpotensi naik/turun malam ini
  5. Tulis laporan HTML + Excel
  6. Kirim ringkasan ke Telegram
  7. (opsional) Minta Claude menulis komentar analitis

Semua pengaturan ada di config.json — script ini tidak perlu diubah.
"""

import json
import os
import sys
import time
import datetime as dt
from pathlib import Path

import requests
import pandas as pd

try:
    import fitur_lanjutan as lanjut
except ImportError:      # agen tetap jalan walau modul lanjutan belum diunggah
    lanjut = None

try:
    import laporan_gw as lapgw
except ImportError:
    lapgw = None

# ------------------------------------------------------------------
# KONFIGURASI
# ------------------------------------------------------------------

AKAR = Path(__file__).resolve().parent
BERKAS_CONFIG = AKAR / "config.json"

BAWAAN = {
    "entry_id": 0,
    "folder_laporan": "laporan",
    "jumlah_gw_dipantau": 5,
    "budget_bank": 0.0,
    "skuad_manual": [],
    "telegram_token": "",
    "telegram_chat_id": "",
    "anthropic_api_key": "",
    "pakai_komentar_ai": True,
    "ambang_harga": 0.75,
    "kirim_berkas": True,
    "tahap_laporan_jam": [24, 3, 1],
    "liga_id": 0,
}

API = "https://fantasy.premierleague.com/api"
JEDA = 0.6  # jeda antar request, jangan bombardir server FPL


def muat_config():
    """Urutan prioritas: environment variable > config.json > bawaan."""
    cfg = dict(BAWAAN)
    if BERKAS_CONFIG.exists():
        cfg.update(json.loads(BERKAS_CONFIG.read_text(encoding="utf-8")))

    def daftar(s):
        return [x.strip() for x in s.split(",") if x.strip()]

    def boolean(s):
        return s.strip().lower() in ("1", "true", "ya", "yes", "on")

    def jam(s):
        """'24,3,1' -> [24, 3, 1]"""
        return sorted({int(float(x)) for x in s.split(",") if x.strip()}, reverse=True)

    peta = {
        "FPL_ENTRY_ID": ("entry_id", int),
        "TELEGRAM_TOKEN": ("telegram_token", str),
        "TELEGRAM_CHAT_ID": ("telegram_chat_id", str),
        "ANTHROPIC_API_KEY": ("anthropic_api_key", str),
        "FPL_SKUAD_MANUAL": ("skuad_manual", daftar),
        "FPL_PANTAU_TAMBAHAN": ("pantau_tambahan", daftar),
        "FPL_PAKAI_AI": ("pakai_komentar_ai", boolean),
        "FPL_BANK": ("budget_bank", float),
        "FPL_TAHAP_LAPORAN": ("tahap_laporan_jam", jam),
        "FPL_LIGA_ID": ("liga_id", int),
    }
    for env, (kunci, ubah) in peta.items():
        nilai = os.environ.get(env, "").strip()
        if nilai:
            try:
                cfg[kunci] = ubah(nilai)
            except (ValueError, TypeError):
                print(f"⚠ {env} diabaikan, formatnya tidak terbaca")

    di_cloud = bool(os.environ.get("GITHUB_ACTIONS") or os.environ.get("TELEGRAM_TOKEN"))
    if not BERKAS_CONFIG.exists() and not di_cloud:
        BERKAS_CONFIG.write_text(json.dumps(BAWAAN, indent=2), encoding="utf-8")
        print(f"config.json dibuat di {BERKAS_CONFIG}. Isi entry_id kamu dulu, lalu jalankan lagi.")
        sys.exit(0)
    return cfg


# ------------------------------------------------------------------
# PENGAMBILAN DATA
# ------------------------------------------------------------------

def ambil(jalur, wajib=True):
    """GET ke API FPL dengan percobaan ulang."""
    url = f"{API}/{jalur.lstrip('/')}"
    for percobaan in range(3):
        try:
            r = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                time.sleep(JEDA)
                return r.json()
            if r.status_code == 404 and not wajib:
                return None
        except requests.RequestException as e:
            if percobaan == 2 and wajib:
                raise RuntimeError(f"Gagal menghubungi FPL ({jalur}): {e}")
        time.sleep(2 * (percobaan + 1))
    if wajib:
        raise RuntimeError(f"FPL menolak permintaan: {jalur}")
    return None


def gw_aktif(bootstrap):
    """Kembalikan (gw_berjalan, gw_berikutnya)."""
    berjalan, berikutnya = None, None
    for e in bootstrap.get("events", []):
        if e.get("is_current"):
            berjalan = e["id"]
        if e.get("is_next"):
            berikutnya = e["id"]
    if berikutnya is None:
        belum = [e["id"] for e in bootstrap.get("events", []) if not e.get("finished")]
        berikutnya = min(belum) if belum else 38
    return berjalan, berikutnya


# ------------------------------------------------------------------
# MESIN PENILAIAN
# ------------------------------------------------------------------

def peta_jadwal(fixtures, gw_awal, jumlah_gw):
    """
    Rata-rata FDR tiap klub untuk beberapa GW ke depan.
    Sekaligus hitung berapa kali klub itu main (deteksi blank/double GW).
    """
    kumpul = {}
    for f in fixtures:
        gw = f.get("event")
        if gw is None or gw < gw_awal or gw >= gw_awal + jumlah_gw:
            continue
        for sisi, lawan, fdr in (
            ("team_h", "team_a", "team_h_difficulty"),
            ("team_a", "team_h", "team_a_difficulty"),
        ):
            klub = f[sisi]
            kumpul.setdefault(klub, []).append(
                {"fdr": f.get(fdr) or 3, "kandang": sisi == "team_h", "gw": gw}
            )
    hasil = {}
    for klub, laga in kumpul.items():
        fdr_rata = sum(l["fdr"] for l in laga) / len(laga)
        hasil[klub] = {
            "fdr": round(fdr_rata, 2),
            "jumlah_laga": len(laga),
            # skor 0-100: FDR 2 itu bagus, FDR 5 itu berat
            "skor": max(0.0, min(100.0, (5.0 - fdr_rata) / 3.0 * 100)),
            "bonus_laga": len(laga) - jumlah_gw,  # positif = ada double GW
        }
    return hasil


def angka(x, bawaan=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return bawaan


def bangun_tabel(bootstrap, jadwal):
    """Ubah data mentah FPL jadi tabel pemain lengkap dengan skor agen."""
    posisi = {p["id"]: p["singular_name_short"] for p in bootstrap["element_types"]}
    klub = {t["id"]: t["short_name"] for t in bootstrap["teams"]}
    total_manajer = max(1, bootstrap.get("total_players", 1))

    baris = []
    for p in bootstrap["elements"]:
        menit = angka(p.get("minutes"))
        per90 = menit / 90.0 if menit > 0 else 0.0

        xgi = angka(p.get("expected_goal_involvements"))
        xgi90 = round(xgi / per90, 3) if per90 > 0 else 0.0
        harga = angka(p.get("now_cost")) / 10.0
        form = angka(p.get("form"))
        milik = angka(p.get("selected_by_percent"))

        j = jadwal.get(p["team"], {"skor": 50.0, "fdr": 3.0, "jumlah_laga": 0, "bonus_laga": 0})

        # keandalan menit: 90 menit x jumlah GW berjalan = ideal
        gw_lewat = max(1, angka(p.get("starts"), 1))
        andal = min(100.0, (menit / (gw_lewat * 90.0)) * 100) if gw_lewat else 0.0

        # form relatif terhadap harga — inti dari "value pick"
        nilai = (form / harga * 100) if harga > 0 else 0.0

        # tekanan transfer: indikator arah harga, bukan ramalan pasti
        masuk = angka(p.get("transfers_in_event"))
        keluar = angka(p.get("transfers_out_event"))
        neto = masuk - keluar
        tekanan = neto / total_manajer * 100

        # bendera ketersediaan
        peluang = p.get("chance_of_playing_next_round")
        peluang = 100 if peluang is None else peluang
        siap = angka(p.get("status") == "a" and peluang >= 75)

        skor = (
            min(100, nilai * 1.2) * 0.30
            + min(100, xgi90 * 120) * 0.25
            + j["skor"] * 0.20
            + andal * 0.15
            + min(100, angka(p.get("points_per_game")) * 12) * 0.10
        ) * (1.0 if siap else 0.45)
        if p.get("penalties_order") == 1:
            skor *= 1.08

        peran = lanjut.peran_bola_mati(p) if lanjut else None
        baris.append({
            "Nama": p["web_name"],
            "Bola Mati": (lanjut.jelaskan_bola_mati(peran) if peran else "") or "",
            "Klub": klub.get(p["team"], "?"),
            "Pos": posisi.get(p["element_type"], "?"),
            "Harga": harga,
            "Poin": p.get("total_points", 0),
            "Form": form,
            "PPG": angka(p.get("points_per_game")),
            "Menit": int(menit),
            "xGI/90": xgi90,
            "Milik%": milik,
            "FDR": j["fdr"],
            "Laga": j["jumlah_laga"],
            "Keandalan": round(andal, 1),
            "Nilai": round(nilai, 1),
            "Tekanan": round(tekanan, 3),
            "Siap": bool(siap),
            "Kabar": (p.get("news") or "").strip(),
            "Skor": round(skor, 1),
            "_id": p["id"],
            "_klub": p["team"],
        })

    df = pd.DataFrame(baris)
    return df.sort_values("Skor", ascending=False).reset_index(drop=True)


def sinyal_harga(df, ambang):
    """Pemain dengan tekanan transfer ekstrem — kandidat naik/turun harga."""
    naik = df[df["Tekanan"] >= ambang].nlargest(8, "Tekanan")
    turun = df[df["Tekanan"] <= -ambang].nsmallest(8, "Tekanan")
    return naik, turun


# ------------------------------------------------------------------
# ANALISIS SKUAD
# ------------------------------------------------------------------

def skuad_terkini(entry_id, gw_berjalan, gw_next):
    """
    Baca skuad dari akun FPL, lalu TERAPKAN transfer yang sudah kamu lakukan
    untuk gameweek berikutnya.

    Kenapa perlu: endpoint picks/ hanya menampilkan susunan gameweek berjalan.
    Kalau kamu menjual A dan membeli B hari Rabu untuk GW berikutnya, picks/
    masih menampilkan A sampai gameweek berganti. Padahal justru B yang perlu
    dipantau. Jadi transfernya kita tempelkan sendiri.
    """
    if not entry_id or not gw_berjalan:
        return []
    picks = ambil(f"entry/{entry_id}/event/{gw_berjalan}/picks/", wajib=False)
    if not picks or not picks.get("picks"):
        return []
    ids = [p["element"] for p in picks["picks"]]

    transfers = ambil(f"entry/{entry_id}/transfers/", wajib=False) or []
    tertunda = [t for t in transfers if t.get("event") == gw_next]
    tertunda.sort(key=lambda t: t.get("time", ""))  # urut waktu, agar transfer berantai benar

    for t in tertunda:
        keluar, masuk = t.get("element_out"), t.get("element_in")
        if keluar in ids:
            ids[ids.index(keluar)] = masuk
        elif masuk not in ids:
            ids.append(masuk)
    return ids


def ambil_skuad(cfg, gw_berjalan, df, gw_next=None):
    """Ambil skuad dari akun FPL. Kalau belum bisa, pakai daftar manual."""
    entry = cfg.get("entry_id") or 0
    nama_tim, bank = "Skuad kamu", cfg.get("budget_bank", 0.0)
    sumber = "daftar manual"
    ids = []

    if entry:
        info = ambil(f"entry/{entry}/", wajib=False)
        if info:
            nama_tim = info.get("name", nama_tim)
            bank = angka(info.get("last_deadline_bank"), bank * 10) / 10.0
        ids = skuad_terkini(entry, gw_berjalan, gw_next or (gw_berjalan or 0) + 1)
        if ids:
            sumber = "akun FPL (transfer terbaru sudah ikut)"

    if not ids and cfg.get("skuad_manual"):
        cari = {n.lower().strip() for n in cfg["skuad_manual"]}
        ids = df[df["Nama"].str.lower().isin(cari)]["_id"].tolist()

    skuad = df[df["_id"].isin(ids)].copy() if ids else pd.DataFrame(columns=df.columns)
    return nama_tim, bank, skuad, sumber


def rekomendasi(df, skuad, bank):
    """Kapten, kandidat jual, dan pengganti yang muat di budget."""
    hasil = {"kapten": [], "jual": [], "beli": {}}
    if skuad.empty:
        return hasil

    layak = skuad[skuad["Siap"]]
    hasil["kapten"] = layak.nlargest(3, "Skor")[
        ["Nama", "Klub", "Pos", "Skor", "xGI/90", "FDR", "Laga"]
    ].to_dict("records")

    lemah = skuad.nsmallest(3, "Skor")[["Nama", "Klub", "Pos", "Harga", "Skor", "Kabar"]]
    hasil["jual"] = lemah.to_dict("records")

    dimiliki = set(skuad["_id"])
    for _, keluar in lemah.iterrows():
        plafon = keluar["Harga"] + bank
        kandidat = df[
            (df["Pos"] == keluar["Pos"])
            & (df["Harga"] <= plafon)
            & (df["Siap"])
            & (~df["_id"].isin(dimiliki))
        ].nlargest(4, "Skor")
        hasil["beli"][keluar["Nama"]] = kandidat[
            ["Nama", "Klub", "Harga", "Skor", "Form", "FDR", "Milik%"]
        ].to_dict("records")
    return hasil


# ------------------------------------------------------------------
# KOMENTAR AI (opsional)
# ------------------------------------------------------------------

def komentar_ai(cfg, ringkasan):
    kunci = cfg.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
    if not cfg.get("pakai_komentar_ai") or not kunci:
        return ""
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            timeout=60,
            headers={
                "x-api-key": kunci,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 900,
                "system": (
                    "Kamu analis Fantasy Premier League. Bahasa Indonesia, langsung ke inti. "
                    "Kamu diberi data yang SUDAH dihitung — jangan mengarang angka di luar data itu. "
                    "Berikan: 1 pilihan kapten dengan alasannya, 1 transfer prioritas, "
                    "dan 1 peringatan risiko. Maksimal 250 kata."
                ),
                "messages": [{"role": "user", "content": ringkasan}],
            },
        )
        data = r.json()
        if "error" in data:
            return f"(Komentar AI gagal: {data['error'].get('message', '')})"
        return "".join(b.get("text", "") for b in data.get("content", [])).strip()
    except Exception as e:
        return f"(Komentar AI gagal: {e})"


# ------------------------------------------------------------------
# FITUR LANJUTAN
# ------------------------------------------------------------------

def rakit_lanjutan(cfg, bootstrap, fixtures, df, skuad, gw_next):
    """Kumpulkan semua analisis lanjutan. Kegagalan di sini tidak boleh
    menjatuhkan laporan utama, jadi seluruhnya dibungkus try."""
    kosong = {"riwayat": None, "liga": None, "chip": [], "differ": [],
              "khusus": {}, "ticker": [], "teks": "", "nama_klub": {}}
    if lanjut is None:
        return kosong
    try:
        nama_klub = {t["id"]: t["short_name"] for t in bootstrap["teams"]}
        klub_ids = set(nama_klub)

        khusus = lanjut.deteksi_gw_khusus(fixtures, klub_ids, gw_next, 8)
        ticker = lanjut.ticker_jadwal(fixtures, nama_klub, klub_ids, gw_next, 6)
        differ = lanjut.cari_differential(df)
        riwayat = riwayat_aman(cfg)
        liga = lanjut.papan_liga(ambil, cfg.get("liga_id"), cfg.get("entry_id"))

        klub_skuad = []
        if not skuad.empty:
            balik = {v: k for k, v in nama_klub.items()}
            klub_skuad = [balik.get(k) for k in skuad["Klub"] if balik.get(k)]
        chip = lanjut.saran_chip(
            riwayat["chip_terpakai"] if riwayat else set(), khusus, klub_skuad, nama_klub)

        teks = lanjut.ringkas_telegram(riwayat, liga, chip, differ, khusus, nama_klub)
        return {"riwayat": riwayat, "liga": liga, "chip": chip, "differ": differ,
                "khusus": khusus, "ticker": ticker, "teks": teks, "nama_klub": nama_klub}
    except Exception as e:
        print(f"⚠ Fitur lanjutan dilewati: {e}")
        return kosong


def riwayat_aman(cfg):
    try:
        return lanjut.riwayat_tim(ambil, cfg.get("entry_id"))
    except Exception:
        return None


def bedah_gw_lengkap(cfg, bootstrap, fixtures, gw):
    """Kumpulkan poin, skor pertandingan, dan pembedahan untuk satu gameweek."""
    kosong = {"poin": {}, "laga": [], "bedah": None, "teks": ""}
    if lapgw is None or not cfg.get("entry_id"):
        return kosong
    try:
        entry = cfg["entry_id"]
        events = lapgw.peta_event(bootstrap)
        nama_klub = {t["id"]: t["short_name"] for t in bootstrap["teams"]}
        nama_pemain = {p["id"]: p["web_name"] for p in bootstrap["elements"]}
        posisi = {p["id"]: p["element_type"] for p in bootstrap["elements"]}
        singkat = {p["id"]: p["singular_name_short"] for p in bootstrap["element_types"]}
        posisi = {k: singkat.get(v, "?") for k, v in posisi.items()}
        klub_pemain = {p["id"]: p["team"] for p in bootstrap["elements"]}

        hist = ambil(f"entry/{entry}/history/", wajib=False)
        picks = ambil(f"entry/{entry}/event/{gw}/picks/", wajib=False)
        live = ambil(f"event/{gw}/live/", wajib=False)

        poin = lapgw.tabel_poin(hist, events)
        baris_hist = next((g for g in (hist or {}).get("current", []) if g["event"] == gw), None)

        pengali, ids = {}, []
        if picks and picks.get("picks"):
            pengali = {p["element"]: p.get("multiplier", 1) for p in picks["picks"]}
            ids = [p["element"] for p in picks["picks"]]

        laga = lapgw.skor_pertandingan(fixtures, gw, nama_klub, klub_pemain,
                                       nama_pemain, ids, live, pengali)
        bedah = lapgw.bedah_gameweek(picks, live, nama_pemain, posisi, baris_hist, events, gw)
        teks = lapgw.teks_gw_telegram(gw, bedah, laga, poin)
        return {"poin": poin, "laga": laga, "bedah": bedah, "teks": teks}
    except Exception as e:
        print(f"⚠ Pembedahan gameweek dilewati: {e}")
        return kosong


# ------------------------------------------------------------------
# KELUARAN
# ------------------------------------------------------------------

def tulis_excel(folder, gw, df, skuad, naik, turun):
    berkas = folder / f"FPL_GW{gw}_data.xlsx"
    kolom = [c for c in df.columns if not c.startswith("_")]
    with pd.ExcelWriter(berkas, engine="openpyxl") as w:
        df[kolom].head(250).to_excel(w, sheet_name="Peringkat", index=False)
        if not skuad.empty:
            skuad[kolom].to_excel(w, sheet_name="Skuad Saya", index=False)
        naik[kolom].to_excel(w, sheet_name="Calon Naik Harga", index=False)
        turun[kolom].to_excel(w, sheet_name="Calon Turun Harga", index=False)
        for pos in ("GKP", "DEF", "MID", "FWD"):
            sub = df[df["Pos"] == pos].head(40)
            if not sub.empty:
                sub[kolom].to_excel(w, sheet_name=pos, index=False)
    return berkas


def tabel_html(judul, records, kolom):
    if not records:
        return ""
    th = "".join(f"<th>{k}</th>" for k in kolom)
    tr = ""
    for r in records:
        sel = "".join(f"<td>{r.get(k, '')}</td>" for k in kolom)
        tr += f"<tr>{sel}</tr>"
    return f"<h3>{judul}</h3><table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>"


def tulis_html(folder, gw, nama_tim, bank, df, skuad, rek, naik, turun, ai, sumber="", ekstra=None, gwr=None):
    kol = ["Nama", "Klub", "Pos", "Harga", "Form", "xGI/90", "FDR", "Milik%", "Bola Mati", "Skor"]
    bagian = ""

    if rek["kapten"]:
        bagian += tabel_html("Kandidat kapten", rek["kapten"],
                             ["Nama", "Klub", "Pos", "Skor", "xGI/90", "FDR", "Laga"])
    if rek["jual"]:
        bagian += tabel_html("Titik lemah skuad", rek["jual"],
                             ["Nama", "Klub", "Pos", "Harga", "Skor", "Kabar"])
    for keluar, masuk in rek["beli"].items():
        bagian += tabel_html(f"Pengganti untuk {keluar}", masuk,
                             ["Nama", "Klub", "Harga", "Skor", "Form", "FDR", "Milik%"])

    gwr = gwr or {}
    if gwr.get("poin", {}).get("baris") and lapgw:
        bagian += lapgw.batang_html(gwr["poin"]["baris"])
        bagian += tabel_html("Rincian poin per gameweek", gwr["poin"]["baris"],
                             ["GW", "Poin", "Rata dunia", "Selisih", "Bangku", "Hit", "Peringkat"])
    if gwr.get("laga"):
        rows = []
        for m in gwr["laga"]:
            rows.append({"Pertandingan": m["laga"], "Status": m["status"],
                         "Poin dari laga ini": m["poin_laga"],
                         "Pemainmu": ", ".join(
                             f"{p['nama']} {p['poin']}" + ("©" if p["kali"] > 1 else "")
                             + (" (bangku)" if p["bangku"] else "")
                             for p in m["pemainku"])})
        bagian += tabel_html("Hasil pertandingan klub pemainmu", rows,
                             ["Pertandingan", "Status", "Poin dari laga ini", "Pemainmu"])
    if gwr.get("bedah") and gwr["bedah"].get("catatan"):
        isi = "<br>".join(gwr["bedah"]["catatan"])
        bagian += f"<h3>Pembedahan gameweek</h3><div class='ai'><p>{isi}</p></div>"
        if gwr["bedah"].get("starter"):
            bagian += tabel_html("Perolehan tiap pemain", gwr["bedah"]["starter"],
                                 ["nama", "pos", "menit", "mentah", "kali", "efektif", "rincian"])

    ekstra = ekstra or {}

    if ekstra.get("chip"):
        bagian += tabel_html(
            "Saran chip", 
            [{"GW": c["gw"], "Chip": c["chip"], "Kekuatan": c["kekuatan"], "Alasan": c["alasan"]}
             for c in ekstra["chip"]],
            ["GW", "Chip", "Kekuatan", "Alasan"])

    if ekstra.get("khusus"):
        bagian += tabel_html(
            "Blank & double gameweek",
            [{"GW": g,
              "Main dua kali": ", ".join(ekstra["nama_klub"].get(k, "?") for k in i["double"]) or "—",
              "Tidak main": ", ".join(ekstra["nama_klub"].get(k, "?") for k in i["blank"]) or "—"}
             for g, i in sorted(ekstra["khusus"].items())],
            ["GW", "Main dua kali", "Tidak main"])

    if ekstra.get("differ"):
        bagian += tabel_html("Differential — bagus tapi belum ramai dimiliki",
                             ekstra["differ"],
                             ["Nama", "Klub", "Pos", "Harga", "Milik%", "Form", "xGI/90", "FDR", "Skor"])

    if ekstra.get("ticker"):
        tk = ekstra["ticker"][:10]
        kolom_tk = [k for k in tk[0].keys()] if tk else []
        bagian += tabel_html("Ticker jadwal 6 gameweek (huruf besar = kandang)", tk, kolom_tk)

    if ekstra.get("liga") and ekstra["liga"].get("saya"):
        lg = ekstra["liga"]
        bagian += tabel_html(f"{lg['liga']} — 3 teratas", lg["puncak"],
                             ["rank", "tim", "manajer", "total", "gw"])

    bagian += tabel_html("Peringkat 25 teratas", df.head(25)[kol].to_dict("records"), kol)
    bagian += tabel_html("Tekanan beli tertinggi", naik.head(8)[kol + ["Tekanan"]].to_dict("records"),
                         kol + ["Tekanan"])
    bagian += tabel_html("Tekanan jual tertinggi", turun.head(8)[kol + ["Tekanan"]].to_dict("records"),
                         kol + ["Tekanan"])

    blok_ai = f"<div class='ai'><h3>Catatan analis</h3><p>{ai.replace(chr(10), '<br>')}</p></div>" if ai else ""

    html = f"""<!doctype html><html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agen FPL — GW{gw}</title><style>
:root{{--bg:#14181B;--pnl:#1E2427;--gar:#333D42;--tks:#D9D3C4;--kbt:#8C9196;--acc:#C88A2E}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--tks);font:15px/1.55 system-ui,sans-serif;padding:22px}}
h1{{font-size:24px;letter-spacing:.1em;margin:0}}
.meta{{color:var(--kbt);font-size:12px;letter-spacing:.1em;text-transform:uppercase;margin:6px 0 26px}}
h3{{font-size:15px;margin:26px 0 9px;color:var(--acc);letter-spacing:.04em}}
table{{width:100%;border-collapse:collapse;font-size:13px;background:var(--pnl)}}
th{{text-align:left;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--kbt);
padding:8px 9px;border-bottom:1px solid var(--gar)}}
td{{padding:7px 9px;border-bottom:1px solid var(--gar)}}
tr:last-child td{{border-bottom:0}}
.ai{{background:var(--pnl);border-left:3px solid var(--acc);padding:14px 16px;margin:26px 0}}
.ai h3{{margin-top:0}}
.kaki{{color:var(--kbt);font-size:11px;margin-top:32px;border-top:1px solid var(--gar);padding-top:12px}}
@media(max-width:640px){{body{{padding:14px}}table{{font-size:12px}}td,th{{padding:6px}}}}
</style></head><body>
<h1>AGEN FPL</h1>
<div class="meta">{nama_tim} &nbsp;·&nbsp; Gameweek {gw} &nbsp;·&nbsp; Bank {bank:.1f}jt &nbsp;·&nbsp; {dt.datetime.now():%d %b %Y %H:%M}{f' &nbsp;·&nbsp; skuad dari {sumber}' if sumber else ''}</div>
{blok_ai}{bagian}
<div class="kaki">Skor agen = gabungan nilai per harga (30%), xGI per 90 menit (25%),
kemudahan jadwal (20%), keandalan menit (15%), dan poin per laga (10%),
dikali faktor ketersediaan. Tekanan transfer adalah indikator arah harga, bukan kepastian.
Data: API resmi Fantasy Premier League.</div>
</body></html>"""
    berkas = folder / f"FPL_GW{gw}_laporan.html"
    berkas.write_text(html, encoding="utf-8")
    return berkas


def kirim_telegram(cfg, pesan):
    token, chat = cfg.get("telegram_token"), cfg.get("telegram_chat_id")
    if not token or not chat:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            timeout=20,
            json={"chat_id": chat, "text": pesan[:4000], "parse_mode": "HTML"},
        )
        return r.status_code == 200
    except requests.RequestException:
        return False


def kirim_dokumen(cfg, berkas, judul=""):
    """Kirim file laporan langsung ke Telegram — dipakai saat jalan di cloud."""
    token, chat = cfg.get("telegram_token"), cfg.get("telegram_chat_id")
    berkas = Path(berkas)
    if not token or not chat or not berkas.exists():
        return False
    try:
        with berkas.open("rb") as f:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendDocument",
                timeout=90,
                data={"chat_id": chat, "caption": judul[:1000]},
                files={"document": (berkas.name, f)},
            )
        return r.status_code == 200
    except requests.RequestException:
        return False


# ------------------------------------------------------------------
# ALUR UTAMA
# ------------------------------------------------------------------

def jalankan():
    cfg = muat_config()
    folder = AKAR / cfg["folder_laporan"]
    folder.mkdir(exist_ok=True)

    print("→ Menarik data FPL…")
    bootstrap = ambil("bootstrap-static/")
    fixtures = ambil("fixtures/")

    gw_berjalan, gw_next = gw_aktif(bootstrap)
    print(f"→ GW berjalan: {gw_berjalan} | GW berikutnya: {gw_next}")

    jadwal = peta_jadwal(fixtures, gw_next, cfg["jumlah_gw_dipantau"])
    df = bangun_tabel(bootstrap, jadwal)
    naik, turun = sinyal_harga(df, cfg["ambang_harga"])

    nama_tim, bank, skuad, sumber = ambil_skuad(cfg, gw_berjalan, df, gw_next)
    ekstra = rakit_lanjutan(cfg, bootstrap, fixtures, df, skuad, gw_next)
    gwr = bedah_gw_lengkap(cfg, bootstrap, fixtures, gw_berjalan) if gw_berjalan else {"teks": ""}
    ekstra["nama_klub"] = {tm["id"]: tm["short_name"] for tm in bootstrap["teams"]}
    if ekstra.get("khusus"):
        print(f"→ Gameweek khusus: {sorted(ekstra['khusus'])}")
    if ekstra.get("chip"):
        print(f"→ Saran chip: {[c['chip'] + ' GW' + str(c['gw']) for c in ekstra['chip']]}")
    print(f"→ Skuad dibaca dari: {sumber} ({len(skuad)} pemain)")
    rek = rekomendasi(df, skuad, bank)

    # ringkasan padat untuk dikirim ke Claude
    def ringkas(sub, n=8):
        return "; ".join(
            f"{r['Nama']} ({r['Klub']} {r['Pos']}, {r['Harga']}jt, form {r['Form']}, "
            f"xGI90 {r['xGI/90']}, FDR {r['FDR']}, skor {r['Skor']})"
            for r in sub.head(n).to_dict("records")
        )

    ringkasan = (
        f"Gameweek {gw_next}. Tim: {nama_tim}. Bank: {bank:.1f} juta.\n\n"
        f"SKUAD SAYA: {ringkas(skuad, 15) or 'belum terbaca'}\n\n"
        f"PEMAIN SKOR TERTINGGI LIGA: {ringkas(df, 12)}\n\n"
        f"TEKANAN BELI: {', '.join(naik['Nama'].head(6))}\n"
        f"TEKANAN JUAL: {', '.join(turun['Nama'].head(6))}"
    )
    ai = komentar_ai(cfg, ringkasan)

    berkas_html = tulis_html(folder, gw_next, nama_tim, bank, df, skuad, rek, naik, turun, ai, sumber, ekstra, gwr)
    berkas_xlsx = tulis_excel(folder, gw_next, df, skuad, naik, turun)

    # pesan Telegram
    baris = [f"<b>AGEN FPL — GW{gw_next}</b>", f"{nama_tim} · bank {bank:.1f}jt"]
    if sumber.startswith("daftar manual"):
        baris.append("⚠️ <i>Skuad dibaca dari daftar manual, bukan akun FPL. "
                     "Transfer terbarumu belum tentu ikut terbaca.</i>")
    baris.append("")
    if rek["kapten"]:
        k = rek["kapten"][0]
        baris.append(f"⭐ Kapten: <b>{k['Nama']}</b> ({k['Klub']}) — skor {k['Skor']}, FDR {k['FDR']}")
    if rek["jual"]:
        j = rek["jual"][0]
        baris.append(f"⚠️ Titik lemah: {j['Nama']} ({j['Klub']}) — skor {j['Skor']}")
        gnt = rek["beli"].get(j["Nama"], [])
        if gnt:
            baris.append(f"↔️ Ganti ke: {gnt[0]['Nama']} ({gnt[0]['Klub']}, "
                         f"{gnt[0]['Harga']}jt, skor {gnt[0]['Skor']})")
    def dengan_klub(sub, n=4):
        return ", ".join(f"{r['Nama']} ({r['Klub']})" for r in sub.head(n).to_dict("records"))

    if len(naik):
        baris.append(f"📈 Berpotensi naik: {dengan_klub(naik)}")
    if len(turun):
        baris.append(f"📉 Berpotensi turun: {dengan_klub(turun)}")
    if gwr.get("teks"):
        baris.append("\n" + gwr["teks"])
    if ekstra.get("teks"):
        baris.append(ekstra["teks"])
    if ai:
        baris += ["", ai[:900]]
    if gwr.get("teks"):
        baris.append("\n" + gwr["teks"])
    if ekstra.get("teks"):
        baris.append(ekstra["teks"])
    pesan = "\n".join(baris)

    terkirim = kirim_telegram(cfg, pesan)
    if terkirim and cfg.get("kirim_berkas", True):
        kirim_dokumen(cfg, berkas_html, f"Laporan lengkap GW{gw_next} — buka di browser HP")
        kirim_dokumen(cfg, berkas_xlsx, f"Data mentah GW{gw_next}")

    print(f"✓ Laporan  : {berkas_html}")
    print(f"✓ Data     : {berkas_xlsx}")
    print(f"✓ Telegram : {'terkirim' if terkirim else 'dilewati (token/chat_id kosong)'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(jalankan())
    except Exception as galat:
        print(f"✗ Agen berhenti: {galat}")
        sys.exit(1)
