#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mesin proyeksi dan strategi multi-gameweek untuk Agen FPL.

Modul ini sengaja deterministik: seluruh angka berasal dari data resmi FPL
yang sudah tersedia di ``agen_fpl.py``. AI hanya menjelaskan hasilnya, bukan
menentukan transfer tanpa dasar angka.
"""

from collections import Counter, defaultdict
import datetime as dt
import json
import random
from pathlib import Path

import pandas as pd


def _angka(nilai, bawaan=0.0):
    try:
        return float(nilai)
    except (TypeError, ValueError):
        return bawaan


def _peta_fixture(fixtures, gw_awal, horizon):
    """Petakan fixture per klub per GW, termasuk blank dan double GW."""
    hasil = defaultdict(lambda: defaultdict(list))
    akhir = gw_awal + horizon
    for laga in fixtures:
        gw = laga.get("event")
        if gw is None or not (gw_awal <= gw < akhir):
            continue
        hasil[laga["team_h"]][gw].append({
            "fdr": _angka(laga.get("team_h_difficulty"), 3),
            "kandang": True,
            "lawan": laga.get("team_a"),
        })
        hasil[laga["team_a"]][gw].append({
            "fdr": _angka(laga.get("team_a_difficulty"), 3),
            "kandang": False,
            "lawan": laga.get("team_h"),
        })
    return hasil


def _faktor_fixture(fdr, kandang):
    # FDR 1..5 menjadi kira-kira 1.30..0.78, lalu diberi koreksi venue kecil.
    faktor = 1.43 - 0.13 * max(1.0, min(5.0, fdr))
    faktor *= 1.05 if kandang else 0.98
    return max(0.55, min(1.40, faktor))


def expected_minutes(df):
    """Estimasi menit, peluang starter, dan 60+ menit dari data resmi FPL.

    Ini bukan klaim susunan pemain. Model menggabungkan start rate musim ini,
    menit per start, availability resmi, dan ukuran sampel. Data yang belum
    cukup selalu mendapat confidence lebih rendah.
    """
    hasil = []
    for p in df.to_dict("records"):
        gw = max(1.0, _angka(p.get("GW Selesai"), 1))
        starts = max(0.0, _angka(p.get("Starts")))
        menit = max(0.0, _angka(p.get("Menit")))
        start_rate = min(1.0, starts / gw)
        rata_gw = min(90.0, menit / gw)

        peluang = _angka(p.get("Peluang"), 100 if p.get("Siap") else 35)
        availability = max(0.0, min(1.0, peluang / 100.0))
        if str(p.get("Status", "a")) in ("i", "s", "u", "n"):
            availability *= 0.15
        elif not bool(p.get("Siap", True)):
            availability *= 0.65

        peluang_starter = max(0.02, min(0.99, start_rate * availability))
        # Menit agregat FPL termasuk cameo dari bangku. Membagi menit dengan
        # jumlah start akan melebihkan pemain rotasi, jadi rata-rata per GW
        # harus tetap menjadi komponen terbesar.
        peran = 0.55 * rata_gw + 0.45 * (90.0 * start_rate)
        xmins = max(0.0, min(90.0, peran * availability))
        peluang_60 = max(0.0, min(0.99, peluang_starter * min(1.0, xmins / 70.0)))

        sample = min(1.0, gw / 8.0)
        confidence = 45 + 45 * sample
        if p.get("Kabar"):
            confidence -= 12
        if availability < 0.75:
            confidence -= 18
        confidence = int(max(20, min(95, round(confidence))))

        label = "nailed" if xmins >= 75 else (
            "cukup aman" if xmins >= 60 else (
                "rawan rotasi" if xmins >= 35 else "menit rendah"
            )
        )
        hasil.append({
            "_id": p.get("_id"),
            "Nama": p.get("Nama"),
            "Klub": p.get("Klub"),
            "Pos": p.get("Pos"),
            "xMins": round(xmins, 1),
            "Peluang Starter%": round(peluang_starter * 100, 1),
            "Peluang 60+%": round(peluang_60 * 100, 1),
            "Confidence%": confidence,
            "Label Menit": label,
        })
    return pd.DataFrame(hasil)


def _baseline(pemain):
    """Estimasi poin netral sebelum lawan/venue diterapkan."""
    ppg = _angka(pemain.get("PPG"))
    form = _angka(pemain.get("Form"))
    xgi90 = _angka(pemain.get("xGI/90"))
    if pemain.get("xMins") is not None:
        andal = max(0.08, min(1.0, _angka(pemain.get("xMins")) / 82.0))
    else:
        andal = max(0.35, min(1.0, _angka(pemain.get("Keandalan"), 50) / 85.0))
    tersedia = 1.0 if bool(pemain.get("Siap")) else 0.35

    # PPG menjaga kontribusi clean sheet/bonus tetap terbaca; form memberi
    # bobot pada tren terbaru; xGI/90 memberi sinyal proses, bukan hasil saja.
    proses = 2.0 + xgi90 * 4.0
    dasar = (0.45 * ppg) + (0.30 * form) + (0.25 * proses)
    if pemain.get("Bola Mati"):
        dasar *= 1.04
    return max(0.0, dasar * andal * tersedia)


def proyeksi_pemain(df, fixtures, gw_awal, horizon=5):
    """Hitung expected points setiap pemain untuk ``horizon`` gameweek."""
    horizon = max(1, min(8, int(horizon)))
    peta = _peta_fixture(fixtures, gw_awal, horizon)
    baris = []

    for pemain in df.to_dict("records"):
        dasar = _baseline(pemain)
        proyeksi = {}
        for gw in range(gw_awal, gw_awal + horizon):
            laga = peta[pemain["_klub"]].get(gw, [])
            poin = sum(dasar * _faktor_fixture(x["fdr"], x["kandang"]) for x in laga)
            proyeksi[f"GW{gw}"] = round(poin, 2)

        total = round(sum(proyeksi.values()), 2)
        risiko = "Rendah"
        if not bool(pemain.get("Siap")):
            risiko = "Tinggi"
        elif _angka(pemain.get("xMins"), 90) < 40:
            risiko = "Tinggi"
        elif _angka(pemain.get("xMins"), 90) < 65:
            risiko = "Sedang"
        elif _angka(pemain.get("Keandalan")) < 65:
            risiko = "Sedang"

        baris.append({
            "_id": pemain["_id"],
            "_klub": pemain["_klub"],
            "Nama": pemain["Nama"],
            "Klub": pemain["Klub"],
            "Pos": pemain["Pos"],
            "Harga": _angka(pemain["Harga"]),
            "Keandalan": _angka(pemain.get("Keandalan")),
            "xMins": round(_angka(pemain.get("xMins")), 1),
            "Confidence%": int(_angka(pemain.get("Confidence%"), 50)),
            "Risiko": risiko,
            **proyeksi,
            f"Total {horizon}GW": total,
            "Rata-rata": round(total / horizon, 2),
        })

    hasil = pd.DataFrame(baris)
    if hasil.empty:
        return hasil
    return hasil.sort_values(f"Total {horizon}GW", ascending=False).reset_index(drop=True)


def analisis_transfer(df, skuad, proyeksi, bank, horizon=5, biaya_hit=4, batas=12):
    """Nilai transfer satu-langkah dengan budget dan batas 3 pemain per klub."""
    kolom_total = f"Total {horizon}GW"
    if skuad.empty or proyeksi.empty:
        return pd.DataFrame()

    kolom_proyeksi = [
        "_id", *[c for c in proyeksi if c.startswith("GW")], kolom_total, "Risiko",
        *[c for c in ("xMins", "Confidence%") if c in proyeksi],
    ]
    gabung = df.merge(
        proyeksi[kolom_proyeksi],
        on="_id",
        how="left",
        suffixes=("", "_proyeksi"),
    )
    milik = set(skuad["_id"])
    klub_awal = Counter(int(x) for x in skuad["_klub"])
    skuad_p = gabung[gabung["_id"].isin(milik)]
    kandidat_p = gabung[(~gabung["_id"].isin(milik)) & gabung["Siap"]]
    if "xMins" in kandidat_p and kandidat_p["xMins"].map(_angka).max() > 0:
        kandidat_p = kandidat_p[kandidat_p["xMins"].map(_angka) >= 35]
    hasil = []
    gw_pertama = next((c for c in proyeksi if c.startswith("GW")), None)

    for keluar in skuad_p.to_dict("records"):
        plafon = _angka(keluar["Harga"]) + _angka(bank)
        kandidat = kandidat_p[
            (kandidat_p["Pos"] == keluar["Pos"])
            & (kandidat_p["Harga"] <= plafon + 1e-9)
        ]
        for masuk in kandidat.to_dict("records"):
            jumlah_klub = klub_awal[int(masuk["_klub"])]
            if int(keluar["_klub"]) != int(masuk["_klub"]) and jumlah_klub >= 3:
                continue

            gain = _angka(masuk.get(kolom_total)) - _angka(keluar.get(kolom_total))
            gain_gw = _angka(masuk.get(gw_pertama)) - _angka(keluar.get(gw_pertama))
            net_hit = gain - _angka(biaya_hit, 4)
            if gain >= 4:
                keputusan = "LAYAK"
            elif gain >= 1.5:
                keputusan = "OPSIONAL"
            else:
                keputusan = "TAHAN"

            confidence = int(round(_angka(masuk.get("Confidence%"), 50)))
            xmins = round(_angka(masuk.get("xMins"), 0), 1)
            risiko = masuk.get("Risiko", "")
            if (
                keputusan == "LAYAK" and risiko == "Rendah"
                and confidence >= 70 and xmins >= 60 and gain_gw > 0
            ):
                kesiapan = "HIJAU"
            elif (
                keputusan in ("LAYAK", "OPSIONAL") and risiko != "Tinggi"
                and confidence >= 50 and xmins >= 45
            ):
                kesiapan = "KUNING"
            else:
                kesiapan = "MERAH"

            hasil.append({
                "Keluar": keluar["Nama"],
                "Klub Keluar": keluar["Klub"],
                "Masuk": masuk["Nama"],
                "Klub Masuk": masuk["Klub"],
                "Pos": keluar["Pos"],
                "Harga Masuk": round(_angka(masuk["Harga"]), 1),
                "Sisa Bank": round(plafon - _angka(masuk["Harga"]), 1),
                "Gain GW Depan": round(gain_gw, 2),
                f"Gain {horizon}GW": round(gain, 2),
                "Net jika -4": round(net_hit, 2),
                "Risiko Masuk": risiko,
                "Confidence Masuk%": confidence,
                "xMins Masuk": xmins,
                "Kesiapan": kesiapan,
                "Keputusan": keputusan,
                "_keluar_id": keluar["_id"],
                "_masuk_id": masuk["_id"],
            })

    if not hasil:
        return pd.DataFrame()
    return (
        pd.DataFrame(hasil)
        .sort_values([f"Gain {horizon}GW", "Gain GW Depan"], ascending=False)
        .head(max(1, int(batas)))
        .reset_index(drop=True)
    )


def terapkan_keputusan(transfer, keputusan, gw):
    """Tempel status persetujuan pengguna dan turunkan opsi yang ditolak."""
    if transfer.empty:
        return transfer
    status = {
        (int(x.get("keluar_id", 0)), int(x.get("masuk_id", 0))): x.get("status", "")
        for x in (keputusan or [])
        if int(x.get("gw", 0)) == int(gw)
    }
    hasil = transfer.copy()
    hasil["Status Om"] = [
        status.get((int(r["_keluar_id"]), int(r["_masuk_id"])), "BELUM DIPUTUSKAN")
        for _, r in hasil.iterrows()
    ]
    prioritas = {"DISETUJUI": 0, "BELUM DIPUTUSKAN": 1, "DITUNDA": 2, "DITOLAK": 3}
    hasil["_status_urut"] = hasil["Status Om"].map(prioritas).fillna(4)
    gain_col = next((c for c in hasil if c.startswith("Gain ") and c.endswith("GW")), None)
    kolom = ["_status_urut", gain_col] if gain_col else ["_status_urut"]
    naik = [True, False] if gain_col else [True]
    return hasil.sort_values(kolom, ascending=naik).drop(columns="_status_urut").reset_index(drop=True)


def analisis_rute_transfer(df, skuad, proyeksi, bank, horizon=5, biaya_hit=4,
                           free_transfer=1, batas=10):
    """Cari rute satu atau dua transfer dengan budget dan batas klub tetap sah."""
    awal = analisis_transfer(df, skuad, proyeksi, bank, horizon, biaya_hit, batas=18)
    if awal.empty:
        return pd.DataFrame()
    gain_col = f"Gain {horizon}GW"
    rute = []
    free_transfer = max(0, int(free_transfer))

    for _, pertama in awal.head(12).iterrows():
        biaya_satu = max(0, 1 - free_transfer) * _angka(biaya_hit, 4)
        rute.append({
            "Langkah 1": f"{pertama['Keluar']} → {pertama['Masuk']}",
            "Langkah 2": "—",
            "Gain Kotor": round(_angka(pertama[gain_col]), 2),
            "Biaya Hit": biaya_satu,
            "Gain Bersih": round(_angka(pertama[gain_col]) - biaya_satu, 2),
            "Sisa Bank": pertama["Sisa Bank"],
            "Risiko": pertama.get("Risiko Masuk", ""),
            "Rencana": "Eksekusi sekarang" if biaya_satu == 0 else "Hanya jika mendesak",
        })

        keluar_id, masuk_id = int(pertama["_keluar_id"]), int(pertama["_masuk_id"])
        skuad_baru = skuad[skuad["_id"] != keluar_id].copy()
        pemain_masuk = df[df["_id"] == masuk_id]
        if pemain_masuk.empty:
            continue
        skuad_baru = pd.concat([skuad_baru, pemain_masuk.iloc[[0]]], ignore_index=True)
        kedua = analisis_transfer(
            df, skuad_baru, proyeksi, pertama["Sisa Bank"], horizon, biaya_hit, batas=10)
        if kedua.empty:
            continue
        kedua = kedua[
            (kedua["_keluar_id"] != masuk_id)
            & (kedua["_masuk_id"] != keluar_id)
        ]
        if kedua.empty:
            continue
        terbaik = kedua.iloc[0]
        # Langkah kedua diasumsikan terjadi satu GW kemudian; 80% dari gain
        # horizon dipakai agar rute tidak melebihkan manfaat yang datang terlambat.
        gain = _angka(pertama[gain_col]) + 0.8 * _angka(terbaik[gain_col])
        biaya_dua = max(0, 2 - free_transfer) * _angka(biaya_hit, 4)
        rute.append({
            "Langkah 1": f"{pertama['Keluar']} → {pertama['Masuk']}",
            "Langkah 2": f"{terbaik['Keluar']} → {terbaik['Masuk']}",
            "Gain Kotor": round(gain, 2),
            "Biaya Hit": biaya_dua,
            "Gain Bersih": round(gain - biaya_dua, 2),
            "Sisa Bank": terbaik["Sisa Bank"],
            "Risiko": "Tinggi" if "Tinggi" in (pertama.get("Risiko Masuk"), terbaik.get("Risiko Masuk")) else "Sedang",
            "Rencana": "Bertahap dua GW" if biaya_dua else "Dua free transfer",
        })

    return (
        pd.DataFrame(rute)
        .drop_duplicates(["Langkah 1", "Langkah 2"])
        .sort_values("Gain Bersih", ascending=False)
        .head(max(1, int(batas)))
        .reset_index(drop=True)
    )


def optimasi_lineup(skuad, proyeksi, gw, kapten=None):
    """Pilih XI legal dengan formasi terbaik serta urutan bangku."""
    if skuad.empty or proyeksi.empty or f"GW{gw}" not in proyeksi:
        return {"starter": [], "bench": [], "formasi": "", "proyeksi": 0.0}
    data = skuad[["_id", "Nama", "Klub", "Pos"]].merge(
        proyeksi[["_id", f"GW{gw}", "xMins", "Risiko"]], on="_id", how="left"
    ).fillna({f"GW{gw}": 0, "xMins": 0, "Risiko": "Tinggi"})

    terbaik = None
    for d in range(3, 6):
        for m in range(2, 6):
            f = 10 - d - m
            if not (1 <= f <= 3):
                continue
            pilihan = []
            sah = True
            for pos, jumlah in (("GKP", 1), ("DEF", d), ("MID", m), ("FWD", f)):
                sub = data[data["Pos"] == pos].nlargest(jumlah, f"GW{gw}")
                if len(sub) < jumlah:
                    sah = False
                    break
                pilihan.append(sub)
            if not sah:
                continue
            xi = pd.concat(pilihan)
            skor = float(xi[f"GW{gw}"].sum())
            if terbaik is None or skor > terbaik[0]:
                terbaik = (skor, d, m, f, xi)
    if terbaik is None:
        return {"starter": [], "bench": [], "formasi": "", "proyeksi": 0.0}

    skor, d, m, f, xi = terbaik
    kapten = kapten or []
    cap_id = int(kapten[0]["_id"]) if kapten and kapten[0].get("_id") else None
    vc_id = int(kapten[1]["_id"]) if len(kapten) > 1 and kapten[1].get("_id") else None
    starter = []
    for _, r in xi.sort_values(f"GW{gw}", ascending=False).iterrows():
        peran = "C" if int(r["_id"]) == cap_id else ("VC" if int(r["_id"]) == vc_id else "XI")
        starter.append({
            "Peran": peran, "Nama": r["Nama"], "Klub": r["Klub"], "Pos": r["Pos"],
            "xPts": round(_angka(r[f"GW{gw}"]), 2), "xMins": round(_angka(r["xMins"]), 1),
            "Risiko": r["Risiko"],
        })
    bench_df = data[~data["_id"].isin(set(xi["_id"]))].copy()
    gkp = bench_df[bench_df["Pos"] == "GKP"]
    out = bench_df[bench_df["Pos"] != "GKP"].sort_values(f"GW{gw}", ascending=False)
    bench = []
    for nomor, (_, r) in enumerate(pd.concat([out, gkp]).iterrows(), 1):
        bench.append({
            "Urutan": nomor, "Nama": r["Nama"], "Klub": r["Klub"], "Pos": r["Pos"],
            "xPts": round(_angka(r[f"GW{gw}"]), 2), "xMins": round(_angka(r["xMins"]), 1),
        })
    return {
        "starter": starter, "bench": bench, "formasi": f"{d}-{m}-{f}",
        "proyeksi": round(skor, 2),
    }


def simulasi_transfer(transfer, horizon=5, jumlah=1500, seed=2026):
    """Monte Carlo deterministik untuk rentang hasil rekomendasi transfer."""
    if transfer.empty:
        return pd.DataFrame()
    rng = random.Random(seed)
    gain_col = f"Gain {horizon}GW"
    hasil = []
    for _, r in transfer.head(8).iterrows():
        mean = _angka(r.get(gain_col))
        risiko = r.get("Risiko Masuk", "Sedang")
        sigma = max(1.5, abs(mean) * {"Rendah": 0.35, "Sedang": 0.55, "Tinggi": 0.8}.get(risiko, 0.55))
        sampel = sorted(rng.gauss(mean, sigma) for _ in range(max(200, int(jumlah))))
        n = len(sampel)
        hasil.append({
            "Transfer": f"{r['Keluar']} → {r['Masuk']}",
            "Rata-rata": round(sum(sampel) / n, 2),
            "P10": round(sampel[int(n * 0.10)], 2),
            "Median": round(sampel[int(n * 0.50)], 2),
            "P90": round(sampel[min(n - 1, int(n * 0.90))], 2),
            "Peluang Untung%": round(sum(x > 0 for x in sampel) / n * 100, 1),
            "Profil": "Aman" if risiko == "Rendah" else ("Agresif" if risiko == "Tinggi" else "Seimbang"),
        })
    return pd.DataFrame(hasil).sort_values("Peluang Untung%", ascending=False).reset_index(drop=True)


def kandidat_kapten(skuad, proyeksi, gw_awal, batas=3):
    if skuad.empty or proyeksi.empty:
        return []
    kolom = f"GW{gw_awal}"
    gabung = skuad[["_id", "Nama", "Klub", "Form", "xGI/90"]].merge(
        proyeksi[["_id", kolom, "Risiko", "xMins", "Confidence%"]], on="_id", how="left"
    )
    # Ceiling memberi sedikit bobot ekstra pada form dan xGI untuk kapten.
    gabung["Ceiling"] = (
        gabung[kolom].fillna(0)
        + gabung["Form"].map(_angka) * 0.12
        + gabung["xGI/90"].map(_angka) * 0.8
        + gabung["xMins"].map(_angka) * 0.012
    )
    return gabung.nlargest(batas, "Ceiling").to_dict("records")


def strategi_liga(liga, differ):
    """Tentukan profil risiko berdasarkan jarak di mini-league."""
    if not liga or not liga.get("saya"):
        return {
            "Mode": "Seimbang", "Alasan": "Liga mini belum dikonfigurasi.",
            "Differential": [],
        }
    atas = liga.get("atas") or []
    bawah = liga.get("bawah") or []
    gap_atas = atas[-1].get("selisih", 0) if atas else 0
    gap_bawah = bawah[0].get("selisih", 999) if bawah else 999
    if not atas:
        mode = "Proteksi"
        alasan = "Sedang memimpin; prioritaskan pemain berlantai poin tinggi."
    elif gap_atas >= 30:
        mode = "Agresif"
        alasan = f"Tertinggal {gap_atas} poin dari rival terdekat; butuh 2–3 differential terukur."
    elif gap_bawah <= 10:
        mode = "Proteksi"
        alasan = f"Rival di bawah hanya berjarak {gap_bawah} poin; hindari hit spekulatif."
    else:
        mode = "Seimbang"
        alasan = f"Jarak ke rival di atas {gap_atas} poin; satu differential cukup."
    return {
        "Mode": mode,
        "Alasan": alasan,
        "Differential": [f"{x['Nama']} ({x['Klub']}, {x['Milik%']}%)" for x in (differ or [])[:3]],
    }


def rencana_chip_pro(skuad, proyeksi, khusus, chip_lama, gw_awal, horizon=5):
    """Papan chip per GW berdasarkan xPts skuad, bench, blank, dan double."""
    if skuad.empty or proyeksi.empty:
        return pd.DataFrame()
    milik = proyeksi[proyeksi["_id"].isin(set(skuad["_id"]))]
    klub_skuad = Counter(int(x) for x in skuad["_klub"])
    saran_lama = {(int(x["gw"]), x["chip"]): x for x in (chip_lama or [])}
    rows = []
    for gw in range(gw_awal, gw_awal + horizon):
        kolom = f"GW{gw}"
        if kolom not in milik:
            continue
        nilai = sorted((_angka(x) for x in milik[kolom]), reverse=True)
        total15 = sum(nilai)
        xi = sum(nilai[:11])
        bench = total15 - xi
        kapten = nilai[0] if nilai else 0
        info = (khusus or {}).get(gw, {})
        blank = sum(klub_skuad[k] for k in info.get("blank", []))
        double = sum(klub_skuad[k] for k in info.get("double", []))
        kandidat = "Simpan"
        skor = 0.0
        alasan = "Tidak ada kondisi chip yang cukup kuat."
        if blank >= 5:
            kandidat, skor, alasan = "Free Hit", blank * 12, f"{blank} pemain skuad blank."
        if bench >= 14 and double >= 4 and bench + double * 2 > skor:
            kandidat, skor, alasan = "Bench Boost", bench + double * 2, f"Bench xPts {bench:.1f}; {double} pemain double."
        if kapten >= 8 and double >= 1 and kapten * 2 > skor:
            kandidat, skor, alasan = "Triple Captain", kapten * 2, f"Kandidat kapten xPts {kapten:.1f}."
        for (g, chip), lama in saran_lama.items():
            if g == gw and skor < 20:
                kandidat, skor, alasan = chip, 20, lama.get("alasan", alasan)
        rows.append({
            "GW": gw, "Chip Kandidat": kandidat, "Skor Sinyal": round(skor, 1),
            "xPts XI": round(xi, 1), "xPts Bench": round(bench, 1),
            "Pemain Blank": blank, "Pemain Double": double, "Alasan": alasan,
        })
    return pd.DataFrame(rows).sort_values(["Skor Sinyal", "GW"], ascending=[False, True]).reset_index(drop=True)


def kalibrasi_proyeksi(df, proyeksi, gw_awal, path):
    """Nilai prediksi GW lalu dan kalibrasi skala proyeksi berikutnya."""
    path = Path(path)
    try:
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (json.JSONDecodeError, OSError):
        state = {}
    factor = max(0.75, min(1.25, _angka(state.get("factor"), 1.0)))
    evaluasi = None
    lama = state.get("prediksi") or {}
    if lama and int(lama.get("gw", gw_awal)) < int(gw_awal):
        kini = {int(r["_id"]): _angka(r.get("Poin")) for r in df.to_dict("records")}
        aktual, prediksi, galat = [], [], []
        for pid, p in (lama.get("pemain") or {}).items():
            pid = int(pid)
            if pid not in kini:
                continue
            a = max(0.0, kini[pid] - _angka(p.get("poin_awal")))
            y = max(0.0, _angka(p.get("xpts")))
            aktual.append(a)
            prediksi.append(y)
            galat.append(abs(a - y))
        if len(galat) >= 20 and sum(prediksi) > 0:
            ratio = sum(aktual) / sum(prediksi)
            factor = max(0.75, min(1.25, 0.7 * factor + 0.3 * ratio))
            evaluasi = {
                "GW": lama.get("gw"), "Pemain": len(galat),
                "MAE": round(sum(galat) / len(galat), 2),
                "Bias": round((sum(prediksi) - sum(aktual)) / len(galat), 2),
                "Faktor Baru": round(factor, 3),
            }
            riwayat = state.get("riwayat", [])
            riwayat.append(evaluasi)
            state["riwayat"] = riwayat[-12:]

    gw_cols = [c for c in proyeksi if c.startswith("GW")]
    hasil = proyeksi.copy()
    for col in gw_cols:
        hasil[col] = (hasil[col].map(_angka) * factor).round(2)
    horizon_cols = [c for c in hasil if c.startswith("Total ") and c.endswith("GW")]
    for col in horizon_cols:
        hasil[col] = hasil[gw_cols].sum(axis=1).round(2)
    if "Rata-rata" in hasil and gw_cols:
        hasil["Rata-rata"] = (hasil[gw_cols].sum(axis=1) / len(gw_cols)).round(2)

    if not lama or int(lama.get("gw", -1)) != int(gw_awal):
        poin_awal = {int(r["_id"]): _angka(r.get("Poin")) for r in df.to_dict("records")}
        state["prediksi"] = {
            "gw": int(gw_awal),
            "dibuat": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "pemain": {
                str(int(r["_id"])): {
                    "xpts": _angka(r.get(f"GW{gw_awal}")),
                    "poin_awal": poin_awal.get(int(r["_id"]), 0),
                }
                for r in hasil.to_dict("records")
            },
        }
    state["factor"] = round(factor, 4)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return hasil, {
        "Faktor": round(factor, 3),
        "Evaluasi Terakhir": evaluasi,
        "Riwayat": state.get("riwayat", []),
    }


def rencana_jangka_panjang(transfer, gw_awal, horizon=5):
    """Susun satu keputusan kini dan watchlist tanpa menjanjikan kepastian palsu."""
    if not transfer.empty and "Status Om" in transfer:
        transfer = transfer[transfer["Status Om"] != "DITOLAK"]
    if not transfer.empty and "Kesiapan" in transfer:
        transfer = transfer[transfer["Kesiapan"] != "MERAH"]
    if not transfer.empty and "Keputusan" in transfer:
        transfer = transfer[transfer["Keputusan"] != "TAHAN"]
    if transfer.empty:
        return [{
            "GW": gw_awal,
            "Aksi": "Simpan transfer",
            "Alasan": "Belum ada upgrade yang memberi kenaikan proyeksi berarti.",
            "Pemicu": "Berubah jika ada cedera, rotasi, atau jadwal baru.",
        }]

    gain_col = f"Gain {horizon}GW"
    rencana = []
    terpakai_keluar, terpakai_masuk = set(), set()
    for row in transfer.to_dict("records"):
        if row["Keluar"] in terpakai_keluar or row["Masuk"] in terpakai_masuk:
            continue
        if not rencana:
            aksi = f"{row['Keluar']} → {row['Masuk']}"
            alasan = f"Estimasi keuntungan {row[gain_col]:+.1f} poin/{horizon}GW."
            pemicu = "Eksekusi jika tetap fit dan tidak ada kabar rotasi sebelum deadline."
            gw = gw_awal
        else:
            aksi = f"Pantau {row['Keluar']} → {row['Masuk']}"
            alasan = f"Opsi tahap berikutnya, potensi {row[gain_col]:+.1f} poin."
            pemicu = "Jalankan hanya jika transfer utama selesai dan budget masih cukup."
            gw = min(gw_awal + len(rencana), gw_awal + horizon - 1)
        rencana.append({"GW": gw, "Aksi": aksi, "Alasan": alasan, "Pemicu": pemicu})
        terpakai_keluar.add(row["Keluar"])
        terpakai_masuk.add(row["Masuk"])
        if len(rencana) >= 3:
            break
    return rencana


def teks_telegram(kapten, transfer, rencana, horizon=5, lineup=None, liga_mode=None,
                  rute=None, kalibrasi=None):
    """Decision brief; rincian angka lengkap tetap berada di HTML/Excel."""
    baris = [f"<b>🧠 STRATEGI {horizon} GAMEWEEK</b>"]
    if kapten:
        utama = kapten[0]
        wakil = kapten[1] if len(kapten) > 1 else None
        teks = f"© <b>{utama['Nama']}</b> ({utama['Klub']}) — proyeksi {utama[next(k for k in utama if str(k).startswith('GW'))]:.1f}"
        if wakil:
            teks += f" · VC {wakil['Nama']}"
        baris.append(teks)

    if transfer.empty:
        baris.append("🔒 <b>Simpan transfer</b> — belum ada upgrade yang cukup kuat.")
    else:
        layak = transfer[transfer.get("Status Om", "") != "DITOLAK"] if "Status Om" in transfer else transfer
        if "Kesiapan" in layak:
            layak = layak[layak["Kesiapan"] != "MERAH"]
        if "Keputusan" in layak:
            layak = layak[layak["Keputusan"] != "TAHAN"]
        if layak.empty:
            baris.append("🔒 Semua opsi saat ini sudah ditolak Om — simpan transfer sambil menunggu data baru.")
            utama = None
        else:
            utama = layak.iloc[0]
        gain_col = f"Gain {horizon}GW"
        if utama is not None:
            baris.append(
                f"↔️ Prioritas: <b>{utama['Keluar']} → {utama['Masuk']}</b> "
                f"({utama[gain_col]:+.1f} poin/{horizon}GW, bank tersisa {utama['Sisa Bank']:.1f}jt)"
            )
            warna = "🟢" if utama.get("Kesiapan") == "HIJAU" else "🟡"
            baris.append(
                f"{warna} Pagar keputusan: <b>{utama.get('Kesiapan', 'BELUM DINILAI')}</b> · "
                f"confidence {utama.get('Confidence Masuk%', 0):.0f}% · "
                f"estimasi {utama.get('xMins Masuk', 0):.0f} menit."
            )
            if utama.get("Status Om") and utama.get("Status Om") != "BELUM DIPUTUSKAN":
                baris.append(f"📝 Status keputusan Om: <b>{utama['Status Om']}</b>")
            if utama["Net jika -4"] <= 0:
                baris.append("🟡 Jangan ambil hit -4; idealnya gunakan free transfer.")
            else:
                baris.append(f"🟢 Hit -4 masih punya estimasi net {utama['Net jika -4']:+.1f} poin.")

        alternatif = layak.iloc[1:3]
        if not alternatif.empty:
            baris.append("Alternatif: " + "; ".join(
                f"{r['Keluar']}→{r['Masuk']} ({r[gain_col]:+.1f})"
                for r in alternatif.to_dict("records")
            ))

    if rencana:
        baris.append("📅 Rencana: " + " | ".join(f"GW{x['GW']} {x['Aksi']}" for x in rencana[:3]))
    if lineup and lineup.get("starter"):
        baris.append(
            f"🧩 XI terbaik: formasi {lineup['formasi']} · proyeksi {lineup['proyeksi']:.1f} poin."
        )
    if liga_mode:
        baris.append(f"🏆 Mode liga: <b>{liga_mode['Mode']}</b> — {liga_mode['Alasan']}")
    if rute is not None and not rute.empty:
        rr = rute.iloc[0]
        if rr["Langkah 2"] != "—":
            baris.append(f"🗺️ Rute terbaik: {rr['Langkah 1']} lalu {rr['Langkah 2']} ({rr['Gain Bersih']:+.1f} net).")
    if kalibrasi:
        baris.append(f"📐 Faktor kalibrasi model: {kalibrasi.get('Faktor', 1.0):.3f}")
    baris.append("<i>Proyeksi adalah alat keputusan, bukan jaminan poin. Cek berita tim menjelang deadline.</i>")
    return "\n".join(baris)


def rakit_strategi(df, skuad, fixtures, gw_awal, bank, horizon=5, biaya_hit=4,
                   free_transfer=1, keputusan=None, liga=None, differ=None,
                   khusus=None, chip_lama=None, state_path=None):
    horizon = max(1, min(8, int(horizon)))
    xmins = expected_minutes(df)
    kaya = df.merge(
        xmins[["_id", "xMins", "Peluang Starter%", "Peluang 60+%", "Confidence%", "Label Menit"]],
        on="_id", how="left",
    )
    proyeksi = proyeksi_pemain(kaya, fixtures, gw_awal, horizon)
    kalibrasi = {"Faktor": 1.0, "Evaluasi Terakhir": None, "Riwayat": []}
    if state_path:
        proyeksi, kalibrasi = kalibrasi_proyeksi(df, proyeksi, gw_awal, state_path)
    transfer = analisis_transfer(kaya, skuad, proyeksi, bank, horizon, biaya_hit)
    transfer = terapkan_keputusan(transfer, keputusan, gw_awal)
    rute = analisis_rute_transfer(
        kaya, skuad, proyeksi, bank, horizon, biaya_hit, free_transfer=free_transfer)
    kapten = kandidat_kapten(skuad, proyeksi, gw_awal)
    lineup = optimasi_lineup(skuad, proyeksi, gw_awal, kapten)
    skenario = simulasi_transfer(transfer, horizon)
    liga_mode = strategi_liga(liga, differ)
    chip_plan = rencana_chip_pro(skuad, proyeksi, khusus, chip_lama, gw_awal, horizon)
    rencana = rencana_jangka_panjang(transfer, gw_awal, horizon)
    return {
        "horizon": horizon,
        "expected_minutes": xmins,
        "proyeksi": proyeksi,
        "transfer": transfer,
        "rute": rute,
        "skenario": skenario,
        "kapten": kapten,
        "lineup": lineup,
        "chip_plan": chip_plan,
        "liga_mode": liga_mode,
        "kalibrasi": kalibrasi,
        "rencana": rencana,
        "teks": teks_telegram(
            kapten, transfer, rencana, horizon, lineup, liga_mode, rute, kalibrasi),
    }
