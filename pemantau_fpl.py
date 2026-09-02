#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================
  PEMANTAU FPL  —  penjaga menjelang deadline
=============================================================
Dijalankan tiap 15 menit. Tugasnya bukan menganalisis, tapi MENJAGA:

  1. Bandingkan status semua pemain dengan snapshot sebelumnya
  2. Kirim peringatan SAAT ITU JUGA kalau ada yang berubah:
     cedera baru, keraguan main, pulih, harga berubah, kabar baru
  3. Nilai risiko rotasi skuadmu dari tren menit bermain (data nyata)
  4. Menjelang deadline, cek berita konferensi pers (opsional, butuh API key)
  5. Hitung mundur deadline dan ingatkan kalau masih ada bendera merah

Berbagi konfigurasi dan fungsi dengan agen_fpl.py — taruh di folder yang sama.
"""

import json
import sys
import datetime as dt
from pathlib import Path

import requests

import agen_fpl as inti

try:
    import keputusan_transfer as keputusan
except ImportError:
    keputusan = None

try:
    import fitur_lanjutan as lanjut
except ImportError:
    lanjut = None

try:
    import laporan_gw as lapgw
except ImportError:
    lapgw = None

AKAR = Path(__file__).resolve().parent
BERKAS_STATE = AKAR / "state_pantau.json"

# Ambang: pemantauan penuh untuk skuad & pantauan, pemain lain hanya kalau populer
MILIK_MINIMAL = 5.0          # persen kepemilikan
JAM_SIAGA = 6                # jendela siaga tetap: cek mendalam saat deadline < 6 jam


# ------------------------------------------------------------------
# SNAPSHOT & PERBANDINGAN
# ------------------------------------------------------------------

def potret(bootstrap):
    """Rekam kondisi tiap pemain yang layak dipantau."""
    klub = {t["id"]: t["short_name"] for t in bootstrap.get("teams", [])}
    return {
        str(p["id"]): {
            "nama": p["web_name"],
            "status": p.get("status", "a"),
            "peluang": p.get("chance_of_playing_next_round"),
            "kabar": (p.get("news") or "").strip(),
            "harga": p.get("now_cost", 0),
            "milik": inti.angka(p.get("selected_by_percent")),
            "klub": klub.get(p["team"], "?"),
            "bolamati": list(lanjut.peran_bola_mati(p)) if lanjut else [],
        }
        for p in bootstrap["elements"]
    }


ARTI_STATUS = {
    "a": "fit",
    "d": "diragukan",
    "i": "cedera",
    "s": "sanksi",
    "u": "tidak terdaftar",
    "n": "tidak memenuhi syarat",
}


def bandingkan(lama, baru, penting):
    """
    Cari perubahan yang layak diberitahukan.
    `penting` = himpunan id pemain di skuad/pantauan (selalu dilaporkan).
    """
    kabar = []
    for pid, kini in baru.items():
        dulu = lama.get(pid)
        if dulu is None:
            continue

        prioritas = pid in penting or kini["milik"] >= MILIK_MINIMAL
        if not prioritas:
            continue

        tanda = "🔴" if pid in penting else "⚪"
        # Nama pendek FPL sering ambigu — "Bruno G." (NEW) vs "B.Fernandes" (MUN).
        # Klub ditempelkan supaya tidak salah orang.
        nama = f"{kini['nama']} ({kini['klub']})" if kini.get("klub") else kini["nama"]

        # 1. status berubah
        if dulu["status"] != kini["status"]:
            arah = "❗" if kini["status"] != "a" else "✅"
            kabar.append({
                "berat": 3 if pid in penting else 2,
                "teks": f"{arah} {tanda} <b>{nama}</b>: {ARTI_STATUS.get(dulu['status'], dulu['status'])}"
                        f" → <b>{ARTI_STATUS.get(kini['status'], kini['status'])}</b>"
                        + (f"\n   {kini['kabar']}" if kini["kabar"] else ""),
            })
            continue

        # 2. peluang bermain berubah (75% → 25% itu sinyal besar)
        pl_lama = 100 if dulu["peluang"] is None else dulu["peluang"]
        pl_kini = 100 if kini["peluang"] is None else kini["peluang"]
        if pl_lama != pl_kini:
            arah = "⬇️" if pl_kini < pl_lama else "⬆️"
            kabar.append({
                "berat": 3 if pid in penting else 2,
                "teks": f"{arah} {tanda} <b>{nama}</b>: peluang main {pl_lama}% → <b>{pl_kini}%</b>"
                        + (f"\n   {kini['kabar']}" if kini["kabar"] else ""),
            })
            continue

        # 3. teks kabar berubah walau status tetap
        if dulu["kabar"] != kini["kabar"] and kini["kabar"]:
            kabar.append({
                "berat": 2 if pid in penting else 1,
                "teks": f"📰 {tanda} <b>{nama}</b>: {kini['kabar']}",
            })
            continue

        # 4. peran bola mati berubah — jarang diumumkan, dampaknya besar
        if lanjut and dulu.get("bolamati") and dulu["bolamati"] != kini.get("bolamati"):
            pesan = lanjut.perubahan_bola_mati(
                tuple(dulu["bolamati"]), tuple(kini["bolamati"]), nama)
            if pesan:
                kabar.append({"berat": 3 if pid in penting else 2, "teks": f"{tanda} {pesan}"})
                continue

        # 5. harga berubah
        if dulu["harga"] != kini["harga"]:
            arah = "📈" if kini["harga"] > dulu["harga"] else "📉"
            kabar.append({
                "berat": 2 if pid in penting else 0,
                "teks": f"{arah} {tanda} <b>{nama}</b>: harga {dulu['harga']/10:.1f} → "
                        f"<b>{kini['harga']/10:.1f}</b> juta",
            })

    kabar.sort(key=lambda k: -k["berat"])
    return [k for k in kabar if k["berat"] >= 1]


# ------------------------------------------------------------------
# RISIKO ROTASI — dari data nyata, bukan tebakan
# ------------------------------------------------------------------

def klasifikasi_rotasi(riwayat, jumlah=5):
    """
    Baca menit bermain di beberapa laga terakhir.
    Ini fakta historis, bukan ramalan susunan pemain.
    """
    laga = [h for h in riwayat if h.get("minutes") is not None][-jumlah:]
    if not laga:
        return {"label": "belum ada data", "skor": 50, "detail": "—"}

    menit = [h["minutes"] for h in laga]
    rata = sum(menit) / len(menit)
    penuh = sum(1 for m in menit if m >= 60)
    kosong = sum(1 for m in menit if m == 0)

    if kosong >= len(menit) * 0.6:
        label, skor = "cadangan", 90
    elif rata >= 80 and kosong == 0:
        label, skor = "aman (nailed)", 10
    elif rata >= 60 and kosong <= 1:
        label, skor = "hampir aman", 25
    elif rata >= 35:
        label, skor = "dirotasi", 60
    else:
        label, skor = "risiko tinggi", 75

    # Tren dua laga terakhir. Menit yang anjlok lebih penting daripada
    # rata-rata bagus dari laga lama — jadi tren boleh menimpa label.
    if len(menit) >= 4:
        akhir = sum(menit[-2:]) / 2
        awal = sum(menit[:-2]) / len(menit[:-2])
        if akhir < awal - 25:
            label = "menit anjlok"
            skor = max(skor, 70)
        elif akhir > awal + 25:
            label += " · menit menanjak"
            skor = max(0, skor - 15)

    return {
        "label": label,
        "skor": skor,
        "detail": "-".join(str(m) for m in menit) + " menit",
        "rata": round(rata, 1),
    }


def periksa_rotasi(ids, potret_kini):
    hasil = []
    for pid in ids:
        ringkas = inti.ambil(f"element-summary/{pid}/", wajib=False)
        if not ringkas:
            continue
        r = klasifikasi_rotasi(ringkas.get("history", []))
        info = potret_kini.get(str(pid), {})
        r["nama"] = info.get("nama", str(pid))
        if info.get("klub"):
            r["nama"] += f" ({info['klub']})"
        hasil.append(r)
    hasil.sort(key=lambda x: -x["skor"])
    return hasil


# ------------------------------------------------------------------
# CEK BERITA KONFERENSI PERS (opsional)
# ------------------------------------------------------------------

def cek_berita(cfg, nama_pemain):
    """
    Minta Claude mencari berita terbaru soal kebugaran & kemungkinan
    dimainkannya seorang pemain. Best effort — jawabannya bisa saja
    ketinggalan atau salah, jadi selalu diberi label "belum resmi".
    """
    kunci = cfg.get("anthropic_api_key", "")
    if not kunci or not nama_pemain:
        return ""
    daftar = ", ".join(nama_pemain[:6])
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            timeout=90,
            headers={"x-api-key": kunci, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 1000,
                "system": (
                    "Kamu pemantau berita Fantasy Premier League. Cari berita 48 jam terakhir "
                    "tentang kebugaran dan kemungkinan bermain pemain yang disebutkan — "
                    "terutama hasil konferensi pers pelatih. "
                    "Format tiap pemain satu baris: NAMA — ringkasan singkat — [RESMI/RUMOR/TIDAK ADA BERITA]. "
                    "Jangan mengarang. Kalau tidak menemukan apa pun, tulis TIDAK ADA BERITA. "
                    "Bahasa Indonesia, maksimal 200 kata total."
                ),
                "messages": [{"role": "user",
                              "content": f"Kabar terbaru pemain Premier League berikut: {daftar}"}],
                "tools": [{"type": "web_search_20250305", "name": "web_search"}],
            },
        )
        data = r.json()
        if "error" in data:
            return ""
        return "".join(b.get("text", "") for b in data.get("content", [])).strip()
    except requests.RequestException:
        return ""


# ------------------------------------------------------------------
# DEADLINE
# ------------------------------------------------------------------

def jam_ke_deadline(bootstrap):
    for e in bootstrap.get("events", []):
        if e.get("is_next") or not e.get("finished"):
            waktu = e.get("deadline_time")
            if not waktu:
                continue
            batas = dt.datetime.fromisoformat(waktu.replace("Z", "+00:00"))
            sisa = (batas - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600
            if sisa > -3:
                return e["id"], sisa, batas
    return None, None, None


def label_tahap(jam):
    """24 -> '1 hari', 3 -> '3 jam'."""
    if jam >= 24 and jam % 24 == 0:
        hari = jam // 24
        return f"{hari} hari"
    return f"{jam} jam"


def tahap_laporan(catatan, gw, sisa_jam, ambang):
    """
    Tentukan apakah laporan pra-deadline perlu dikirim sekarang.
    Sepenuhnya mengikuti deadline asli dari API — tidak peduli hari apa.
    `ambang` misalnya [6, 2] artinya: kirim saat sisa 6 jam, lalu saat sisa 2 jam.
    """
    if gw is None or sisa_jam is None or sisa_jam <= 0:
        return None
    sudah = set(catatan.get("tahap", [])) if catatan.get("gw") == gw else set()
    for t in sorted(ambang, reverse=True):
        if sisa_jam <= t and t not in sudah:
            return t
    return None


def fixtures_semua():
    """Tarik jadwal hanya saat benar-benar diperlukan, bukan tiap 20 menit."""
    return inti.ambil("fixtures/", wajib=False) or []


def simpan_state(potret_kini, catatan):
    BERKAS_STATE.write_text(
        json.dumps(
            {"waktu": dt.datetime.now().isoformat(), "potret": potret_kini, "laporan": catatan},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


# ------------------------------------------------------------------
# ALUR UTAMA
# ------------------------------------------------------------------

def jalankan():
    cfg = inti.muat_config()
    bootstrap = inti.ambil("bootstrap-static/")
    gw, sisa_jam, batas = jam_ke_deadline(bootstrap)
    gw_berjalan, gw_depan = inti.gw_aktif(bootstrap)
    # Klik Setujui/Tolak/Tunda diproses di awal agar tetap tercatat walaupun
    # tidak ada perubahan pemain dan pemantau kemudian memilih diam.
    if keputusan:
        keputusan.proses_callback(cfg, bootstrap, gw_aktif=gw or gw_depan)
    kini = potret(bootstrap)

    # --- tentukan siapa yang dipantau ketat ---
    penting = set()
    sumber = "daftar manual"
    if cfg.get("entry_id"):
        ids = inti.skuad_terkini(cfg["entry_id"], gw_berjalan, gw or gw_depan)
        if ids:
            penting = {str(i) for i in ids}
            sumber = "akun FPL"
    if not penting and cfg.get("skuad_manual"):
        kandidat = [{"id": pid, "nama": v["nama"], "klub": v.get("klub", "")}
                    for pid, v in kini.items()]
        ids, catatan = inti.cocok_manual(cfg["skuad_manual"], kandidat)
        penting = {str(i) for i in ids}
        for c in catatan:
            print(f"⚠ Daftar manual: {c}")
    for n in cfg.get("pantau_tambahan", []):
        for pid, v in kini.items():
            if v["nama"].lower() == n.lower().strip():
                penting.add(pid)
    print(f"→ Memantau {len(penting)} pemain (skuad dari {sumber})")
    if sumber == "daftar manual" and len(penting) < 15:
        print(f"⚠ Hanya {len(penting)} pemain terpantau. Sebelum deadline pertama "
              f"musim, akun FPL belum bisa dibaca — lengkapi FPL_SKUAD_MANUAL "
              f"dengan 15 nama supaya tidak ada pemain yang lolos pantauan.")

    # --- bandingkan dengan snapshot lalu ---
    lama, catatan = {}, {}
    if BERKAS_STATE.exists():
        try:
            simpanan = json.loads(BERKAS_STATE.read_text(encoding="utf-8"))
            lama = simpanan.get("potret", {})
            catatan = simpanan.get("laporan", {})
        except json.JSONDecodeError:
            lama, catatan = {}, {}

    perubahan = bandingkan(lama, kini, penting) if lama else []
    simpan_state(kini, catatan)

    if not lama:
        print("→ Snapshot awal dibuat. Perbandingan mulai berjalan pada eksekusi berikutnya.")
        return 0

    # --- mode siaga menjelang deadline ---
    tahap = tahap_laporan(catatan, gw, sisa_jam, cfg.get("tahap_laporan_jam", [24, 3, 1]))
    siaga = (tahap is not None) or (sisa_jam is not None and 0 < sisa_jam <= JAM_SIAGA)
    blok_rotasi, blok_berita, bendera = "", "", []

    if siaga and penting:
        rotasi = periksa_rotasi(sorted(penting, key=int), kini)
        rawan = [r for r in rotasi if r["skor"] >= 55]
        if rawan:
            blok_rotasi = "\n<b>Risiko rotasi (dari menit bermain terakhir):</b>\n" + "\n".join(
                f"• {r['nama']} — {r['label']} ({r['detail']})" for r in rawan[:6]
            )

        bendera = [
            f"{v['nama']} ({v['klub']})" if v.get("klub") else v["nama"]
            for pid, v in kini.items()
            if pid in penting and (v["status"] != "a" or (v["peluang"] is not None and v["peluang"] < 100))
        ]
        nama_dicek = list(dict.fromkeys(bendera + [r["nama"] for r in rawan[:3]]))
        if lanjut and cfg.get("entry_id") and gw_berjalan:
            picks = inti.ambil(f"entry/{cfg['entry_id']}/event/{gw_berjalan}/picks/", wajib=False)
            layak = lanjut.cek_kelayakan(picks, kini)
            if layak and layak["catatan"]:
                blok_rotasi += "\n<b>Pemeriksaan skuad:</b>\n" + "\n".join(
                    "• " + c for c in layak["catatan"])

        berita = cek_berita(cfg, nama_dicek)
        if berita:
            blok_berita = f"\n<b>Pantauan berita (belum resmi):</b>\n{berita}"

    # --- susun pesan ---
    gw_perlu_dibedah = None
    if lapgw is not None and cfg.get("entry_id"):
        try:
            gw_perlu_dibedah = lapgw.gw_baru_selesai(
                lapgw.peta_event(bootstrap), catatan.get("gw_dibedah"))
        except Exception:
            gw_perlu_dibedah = None

    if not perubahan and not siaga and tahap is None and gw_perlu_dibedah is None:
        print("→ Tidak ada perubahan. Diam.")
        return 0

    baris = []
    if sisa_jam is not None and sisa_jam > 0:
        baris.append(f"<b>PEMANTAU FPL — GW{gw}</b>")
        baris.append(f"⏳ Deadline {sisa_jam:.1f} jam lagi ({batas.astimezone():%a %d %b %H:%M})")
        if tahap is not None:
            baris.append(f"🚨 <b>PENGINGAT — {label_tahap(tahap)} sebelum deadline</b>")
    else:
        baris.append("<b>PEMANTAU FPL</b>")

    if perubahan:
        baris.append("")
        baris += [k["teks"] for k in perubahan[:14]]
        if len(perubahan) > 14:
            baris.append(f"…dan {len(perubahan)-14} perubahan lain.")
    elif siaga:
        baris.append("\nTidak ada perubahan status sejak pengecekan terakhir.")

    if bendera:
        baris.append(f"\n⚠️ Bendera aktif di skuadmu: {', '.join(bendera)}")

    if blok_rotasi:
        baris.append(blok_rotasi)
    if blok_berita:
        baris.append(blok_berita)

    pesan = "\n".join(baris)
    # Pada tahap pengingat, laporan lengkap dipanggil di bawah. Pesan pemantau
    # dimasukkan sebagai pengantar ke laporan itu agar pengguna menerima satu
    # chat, bukan ringkasan pemantau lalu laporan kedua yang isinya tumpang tindih.
    kirim_pemantau = tahap is None and bool(perubahan or siaga)
    if kirim_pemantau:
        terkirim = inti.kirim_telegram(cfg, pesan, satu_pesan=True)
        print(pesan.replace("<b>", "").replace("</b>", ""))
        print(f"\n✓ Telegram: {'terkirim' if terkirim else 'dilewati'}")
    elif tahap is not None:
        print("→ Ringkasan pemantau akan digabung ke laporan deadline.")
    else:
        print("→ Tidak mengirim pesan pemantau kosong; lanjut ke pembedahan GW.")

    # --- pembedahan otomatis begitu gameweek rampung ---
    if lapgw is not None and cfg.get("entry_id"):
        try:
            events = lapgw.peta_event(bootstrap)
            selesai = lapgw.gw_baru_selesai(events, catatan.get("gw_dibedah"))
            if selesai:
                print(f"\n→ GW{selesai} rampung dan bonus sudah final. Membedah…")
                hasil = inti.bedah_gw_lengkap(cfg, bootstrap, fixtures_semua(), selesai)
                if hasil.get("teks"):
                    inti.kirim_telegram(cfg, hasil["teks"])
                    catatan["gw_dibedah"] = selesai
                    simpan_state(kini, catatan)
                    print(f"✓ Pembedahan GW{selesai} terkirim.")
        except Exception as e:
            print(f"⚠ Pembedahan gameweek dilewati: {e}")

    # --- laporan lengkap otomatis menjelang deadline ---
    if tahap is not None:
        print(f"\n→ Deadline tinggal {sisa_jam:.1f} jam. Menyusun laporan lengkap…")
        try:
            inti.jalankan(pengantar_telegram=pesan)
            if catatan.get("gw") != gw:
                catatan = {"gw": gw, "tahap": []}
            catatan["tahap"] = sorted(set(catatan.get("tahap", [])) | {tahap}, reverse=True)
            simpan_state(kini, catatan)
            print(f"✓ Laporan pengingat {label_tahap(tahap)} terkirim.")
        except Exception as e:
            print(f"⚠ Laporan pra-deadline gagal, akan dicoba lagi: {e}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(jalankan())
    except Exception as galat:
        print(f"✗ Pemantau berhenti: {galat}")
        sys.exit(1)
