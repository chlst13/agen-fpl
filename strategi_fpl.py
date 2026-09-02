#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mesin proyeksi dan strategi multi-gameweek untuk Agen FPL.

Modul ini sengaja deterministik: seluruh angka berasal dari data resmi FPL
yang sudah tersedia di ``agen_fpl.py``. AI hanya menjelaskan hasilnya, bukan
menentukan transfer tanpa dasar angka.
"""

from collections import Counter, defaultdict

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


def _baseline(pemain):
    """Estimasi poin netral sebelum lawan/venue diterapkan."""
    ppg = _angka(pemain.get("PPG"))
    form = _angka(pemain.get("Form"))
    xgi90 = _angka(pemain.get("xGI/90"))
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

    gabung = df.merge(
        proyeksi[["_id", *[c for c in proyeksi if c.startswith("GW")], kolom_total, "Risiko"]],
        on="_id",
        how="left",
        suffixes=("", "_proyeksi"),
    )
    milik = set(skuad["_id"])
    klub_awal = Counter(int(x) for x in skuad["_klub"])
    skuad_p = gabung[gabung["_id"].isin(milik)]
    kandidat_p = gabung[(~gabung["_id"].isin(milik)) & gabung["Siap"]]
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
                "Risiko Masuk": masuk.get("Risiko", ""),
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


def kandidat_kapten(skuad, proyeksi, gw_awal, batas=3):
    if skuad.empty or proyeksi.empty:
        return []
    kolom = f"GW{gw_awal}"
    gabung = skuad[["_id", "Nama", "Klub", "Form", "xGI/90"]].merge(
        proyeksi[["_id", kolom, "Risiko"]], on="_id", how="left"
    )
    # Ceiling memberi sedikit bobot ekstra pada form dan xGI untuk kapten.
    gabung["Ceiling"] = (
        gabung[kolom].fillna(0)
        + gabung["Form"].map(_angka) * 0.12
        + gabung["xGI/90"].map(_angka) * 0.8
    )
    return gabung.nlargest(batas, "Ceiling").to_dict("records")


def rencana_jangka_panjang(transfer, gw_awal, horizon=5):
    """Susun satu keputusan kini dan watchlist tanpa menjanjikan kepastian palsu."""
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


def teks_telegram(kapten, transfer, rencana, horizon=5):
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
        utama = transfer.iloc[0]
        gain_col = f"Gain {horizon}GW"
        baris.append(
            f"↔️ Prioritas: <b>{utama['Keluar']} → {utama['Masuk']}</b> "
            f"({utama[gain_col]:+.1f} poin/{horizon}GW, bank tersisa {utama['Sisa Bank']:.1f}jt)"
        )
        if utama["Net jika -4"] <= 0:
            baris.append("🟡 Jangan ambil hit -4; idealnya gunakan free transfer.")
        else:
            baris.append(f"🟢 Hit -4 masih punya estimasi net {utama['Net jika -4']:+.1f} poin.")

        alternatif = transfer.iloc[1:3]
        if not alternatif.empty:
            baris.append("Alternatif: " + "; ".join(
                f"{r['Keluar']}→{r['Masuk']} ({r[gain_col]:+.1f})"
                for r in alternatif.to_dict("records")
            ))

    if rencana:
        baris.append("📅 Rencana: " + " | ".join(f"GW{x['GW']} {x['Aksi']}" for x in rencana[:3]))
    baris.append("<i>Proyeksi adalah alat keputusan, bukan jaminan poin. Cek berita tim menjelang deadline.</i>")
    return "\n".join(baris)


def rakit_strategi(df, skuad, fixtures, gw_awal, bank, horizon=5, biaya_hit=4):
    horizon = max(1, min(8, int(horizon)))
    proyeksi = proyeksi_pemain(df, fixtures, gw_awal, horizon)
    transfer = analisis_transfer(df, skuad, proyeksi, bank, horizon, biaya_hit)
    kapten = kandidat_kapten(skuad, proyeksi, gw_awal)
    rencana = rencana_jangka_panjang(transfer, gw_awal, horizon)
    return {
        "horizon": horizon,
        "proyeksi": proyeksi,
        "transfer": transfer,
        "kapten": kapten,
        "rencana": rencana,
        "teks": teks_telegram(kapten, transfer, rencana, horizon),
    }
