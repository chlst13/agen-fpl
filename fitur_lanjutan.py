#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================
  FITUR LANJUTAN FPL
=============================================================
Modul tambahan untuk agen_fpl.py dan pemantau_fpl.py.

Isinya hal-hal yang biasanya cuma dilakukan manajer FPL serius:

  · Deteksi blank & double gameweek beberapa pekan ke depan
  · Saran pemakaian chip (Wildcard, Free Hit, Bench Boost, Triple Captain)
  · Pencari differential — pemain bagus yang jarang dimiliki orang
  · Pemantau algojo penalti & bola mati (perubahannya sering luput)
  · Papan liga mini: siapa menyalip siapa
  · Proyeksi bonus BPS saat pertandingan berlangsung
  · Ticker jadwal 6 gameweek dalam bentuk tabel
  · Pemeriksa kelayakan skuad sebelum deadline
  · Riwayat nilai tim, peringkat, dan poin terbuang di bangku

Semua fungsi di sini dibuat "aman gagal": kalau data tidak lengkap,
mereka mengembalikan hasil kosong, bukan menghentikan agen.
"""

import datetime as dt


# ==================================================================
# 1. BLANK & DOUBLE GAMEWEEK
# ==================================================================

def deteksi_gw_khusus(fixtures, klub_ids, gw_awal, jumlah=8):
    """
    Cari gameweek di mana ada klub yang tidak bermain (blank) atau
    bermain dua kali (double). Ini informasi paling berharga di FPL —
    dan satu-satunya yang benar-benar bisa direncanakan dari jauh hari.
    """
    hitung = {}
    total_per_gw = {}
    for f in fixtures:
        gw = f.get("event")
        if gw is None or not (gw_awal <= gw < gw_awal + jumlah):
            continue
        total_per_gw[gw] = total_per_gw.get(gw, 0) + 1
        for sisi in ("team_h", "team_a"):
            kunci = (f[sisi], gw)
            hitung[kunci] = hitung.get(kunci, 0) + 1

    hasil = {}
    for gw in range(gw_awal, gw_awal + jumlah):
        # Gameweek yang jadwalnya belum dirilis akan terlihat seperti blank
        # untuk semua klub. Itu bukan blank — itu cuma belum dijadwalkan.
        # Ambang 5 laga membedakan keduanya.
        if total_per_gw.get(gw, 0) < 5:
            continue
        blank = sorted(k for k in klub_ids if hitung.get((k, gw), 0) == 0)
        double = sorted(k for k in klub_ids if hitung.get((k, gw), 0) >= 2)
        if blank or double:
            hasil[gw] = {"blank": blank, "double": double}
    return hasil


# ==================================================================
# 2. SARAN CHIP
# ==================================================================

NAMA_CHIP = {
    "wildcard": "Wildcard",
    "freehit": "Free Hit",
    "bboost": "Bench Boost",
    "3xc": "Triple Captain",
}


def saran_chip(chip_terpakai, gw_khusus, klub_skuad, nama_klub):
    """
    Sarankan chip berdasarkan blank/double gameweek yang akan datang
    dan komposisi klub di skuadmu.

    `chip_terpakai` : himpunan nama chip yang sudah dipakai musim ini
    `klub_skuad`    : daftar id klub dari 15 pemainmu (boleh berulang)
    """
    saran = []
    if not gw_khusus:
        return saran

    for gw, info in sorted(gw_khusus.items()):
        kena_blank = [k for k in klub_skuad if k in info["blank"]]
        kena_double = [k for k in klub_skuad if k in info["double"]]

        if len(kena_blank) >= 5 and "freehit" not in chip_terpakai:
            saran.append({
                "gw": gw, "chip": "Free Hit", "kekuatan": "kuat",
                "alasan": f"{len(kena_blank)} pemainmu tidak bermain di GW{gw} "
                          f"({', '.join(sorted({nama_klub.get(k, '?') for k in kena_blank}))})",
            })
        elif len(kena_blank) >= 3 and "wildcard" not in chip_terpakai:
            saran.append({
                "gw": gw, "chip": "Wildcard", "kekuatan": "sedang",
                "alasan": f"{len(kena_blank)} pemainmu blank di GW{gw} — "
                          f"pertimbangkan bongkar skuad sebelum itu",
            })

        if len(kena_double) >= 8 and "bboost" not in chip_terpakai:
            saran.append({
                "gw": gw, "chip": "Bench Boost", "kekuatan": "kuat",
                "alasan": f"{len(kena_double)} pemainmu main dua kali di GW{gw}, "
                          f"termasuk bangku cadangan",
            })
        if len(kena_double) >= 2 and "3xc" not in chip_terpakai:
            saran.append({
                "gw": gw, "chip": "Triple Captain", "kekuatan": "sedang",
                "alasan": f"ada {len(kena_double)} pemainmu dengan dua laga di GW{gw}",
            })

    urutan = {"kuat": 0, "sedang": 1}
    saran.sort(key=lambda s: (s["gw"], urutan.get(s["kekuatan"], 9)))
    return saran[:6]


# ==================================================================
# 3. DIFFERENTIAL
# ==================================================================

def cari_differential(df, batas_milik=8.0, skor_minimal=55.0, jumlah=10):
    """
    Pemain berskor tinggi yang dimiliki sedikit manajer. Ini alat naik
    peringkat: kalau kamu memiliki apa yang dimiliki semua orang, kamu
    hanya bisa bergerak searah dengan semua orang.
    """
    pilih = df[
        (df["Milik%"] <= batas_milik)
        & (df["Skor"] >= skor_minimal)
        & (df["Siap"])
        & (df["Menit"] > 0)
    ]
    kolom = ["Nama", "Klub", "Pos", "Harga", "Milik%", "Form", "xGI/90", "FDR", "Skor"]
    return pilih.nlargest(jumlah, "Skor")[kolom].to_dict("records")


# ==================================================================
# 4. ALGOJO PENALTI & BOLA MATI
# ==================================================================

def peran_bola_mati(p):
    """Ringkas peran bola mati seorang pemain jadi satu tuple kecil."""
    return (
        p.get("penalties_order"),
        p.get("direct_freekicks_order"),
        p.get("corners_and_indirect_freekicks_order"),
    )


def jelaskan_bola_mati(peran):
    bagian = []
    pen, fk, corner = peran
    if pen == 1:
        bagian.append("algojo penalti utama")
    elif pen == 2:
        bagian.append("algojo penalti kedua")
    if fk == 1:
        bagian.append("eksekutor tendangan bebas")
    if corner == 1:
        bagian.append("eksekutor sepak pojok")
    return ", ".join(bagian)


def perubahan_bola_mati(dulu, kini, nama):
    """
    Deteksi promosi peran bola mati. Perubahan ini nyaris tidak pernah
    diumumkan, tapi dampaknya ke perolehan poin besar sekali —
    algojo penalti utama di klub papan atas bisa bernilai 3-5 poin per laga.
    """
    if dulu == kini:
        return None
    lama = jelaskan_bola_mati(dulu)
    baru = jelaskan_bola_mati(kini)
    if not baru:
        return f"🎯 {nama}: kehilangan peran bola mati ({lama or 'sebelumnya ada'})"
    if kini[0] == 1 and dulu[0] != 1:
        return f"🎯 <b>{nama} kini algojo penalti utama</b> — sinyal beli kuat"
    if not lama:
        return f"🎯 {nama}: dapat peran baru — {baru}"
    return f"🎯 {nama}: peran bola mati berubah — {baru}"


# ==================================================================
# 5. LIGA MINI
# ==================================================================

def papan_liga(ambil, liga_id, entry_id):
    """Posisimu di liga mini, siapa yang menyalip, dan siapa yang bisa dikejar."""
    if not liga_id:
        return None
    data = ambil(f"leagues-classic/{liga_id}/standings/", wajib=False)
    if not data or not data.get("standings", {}).get("results"):
        return None

    hasil = data["standings"]["results"]
    nama_liga = data.get("league", {}).get("name", "Liga mini")

    saya, indeks = None, None
    for i, r in enumerate(hasil):
        if r.get("entry") == entry_id:
            saya, indeks = r, i
            break

    ringkas = {
        "liga": nama_liga,
        "jumlah": len(hasil),
        "puncak": [
            {"rank": r["rank"], "tim": r["entry_name"], "manajer": r["player_name"],
             "total": r["total"], "gw": r.get("event_total", 0)}
            for r in hasil[:3]
        ],
        "saya": None, "atas": [], "bawah": [], "gerak": "",
    }
    if saya is None:
        return ringkas

    ringkas["saya"] = {
        "rank": saya["rank"], "tim": saya["entry_name"],
        "total": saya["total"], "gw": saya.get("event_total", 0),
    }
    lalu = saya.get("last_rank") or saya["rank"]
    selisih = lalu - saya["rank"]
    if selisih > 0:
        ringkas["gerak"] = f"naik {selisih} posisi"
    elif selisih < 0:
        ringkas["gerak"] = f"turun {abs(selisih)} posisi"
    else:
        ringkas["gerak"] = "posisi tetap"

    for r in hasil[max(0, indeks - 2):indeks]:
        ringkas["atas"].append({"rank": r["rank"], "tim": r["entry_name"],
                                "selisih": r["total"] - saya["total"]})
    for r in hasil[indeks + 1:indeks + 3]:
        ringkas["bawah"].append({"rank": r["rank"], "tim": r["entry_name"],
                                 "selisih": saya["total"] - r["total"]})
    return ringkas


# ==================================================================
# 6. PROYEKSI BONUS SAAT LAGA BERLANGSUNG
# ==================================================================

def proyeksi_bonus(live, fixtures, klub_pemain, nama_pemain, gw):
    """
    Hitung siapa yang sedang memimpin BPS di tiap laga yang belum selesai.
    Bonus resmi baru masuk setelah pertandingan usai — ini bocorannya.
    """
    if not live or not live.get("elements"):
        return []

    bps = {e["id"]: e.get("stats", {}).get("bps", 0) for e in live["elements"]}
    menit = {e["id"]: e.get("stats", {}).get("minutes", 0) for e in live["elements"]}

    hasil = []
    for f in fixtures:
        if f.get("event") != gw or not f.get("started") or f.get("finished"):
            continue
        klub = {f["team_h"], f["team_a"]}
        peserta = [
            (pid, bps.get(pid, 0)) for pid, t in klub_pemain.items()
            if t in klub and menit.get(pid, 0) > 0
        ]
        if not peserta:
            continue
        peserta.sort(key=lambda x: -x[1])
        tiga = peserta[:3]
        hasil.append({
            "laga": f"{f['team_h']}-{f['team_a']}",
            "papan": [
                {"nama": nama_pemain.get(pid, "?"), "bps": nilai, "bonus": b}
                for (pid, nilai), b in zip(tiga, [3, 2, 1])
            ],
        })
    return hasil


# ==================================================================
# 7. TICKER JADWAL
# ==================================================================

def ticker_jadwal(fixtures, nama_klub, klub_ids, gw_awal, jumlah=6):
    """Tabel jadwal per klub, diurutkan dari yang paling ringan."""
    kotak = {k: {gw: [] for gw in range(gw_awal, gw_awal + jumlah)} for k in klub_ids}
    for f in fixtures:
        gw = f.get("event")
        if gw is None or not (gw_awal <= gw < gw_awal + jumlah):
            continue
        for sisi, lawan, kunci_fdr in (("team_h", "team_a", "team_h_difficulty"),
                                       ("team_a", "team_h", "team_a_difficulty")):
            if f[sisi] in kotak:
                kotak[f[sisi]][gw].append({
                    "lawan": nama_klub.get(f[lawan], "?"),
                    "fdr": f.get(kunci_fdr) or 3,
                    "kandang": sisi == "team_h",
                })

    baris = []
    for klub, jadwal in kotak.items():
        semua = [l for laga in jadwal.values() for l in laga]
        if not semua:
            continue
        rata = sum(l["fdr"] for l in semua) / len(semua)
        # Klub yang blank punya rata-rata FDR bagus secara semu karena
        # laganya sedikit. Skor di bawah menimbang jumlah laga juga, jadi
        # double gameweek naik dan blank gameweek turun.
        skor = (5.0 - rata) / 3.0 * 100 * (len(semua) / jumlah)
        baris.append({
            "Klub": nama_klub.get(klub, "?"),
            "Skor": round(max(0.0, skor), 1),
            "Rata FDR": round(rata, 2),
            "Laga": len(semua),
            **{
                f"GW{gw}": " + ".join(
                    f"{l['lawan'].upper() if l['kandang'] else l['lawan'].lower()}({l['fdr']})"
                    for l in laga
                ) or "—"
                for gw, laga in jadwal.items()
            },
        })
    baris.sort(key=lambda b: -b["Skor"])
    return baris


# ==================================================================
# 8. KELAYAKAN SKUAD SEBELUM DEADLINE
# ==================================================================

def cek_kelayakan(picks, potret):
    """
    Periksa hal-hal yang bikin manajer menyesal setelah deadline lewat:
    pemain bermasalah di starting XI, bangku yang tidak bisa menutupi,
    dan kapten yang statusnya meragukan.
    """
    if not picks or not picks.get("picks"):
        return None

    xi_bermasalah, bangku_aman, kapten, wakil = [], 0, None, None
    for p in picks["picks"]:
        pid = str(p["element"])
        info = potret.get(pid, {})
        nama = info.get("nama", pid)
        peluang = info.get("peluang")
        peluang = 100 if peluang is None else peluang
        bermasalah = info.get("status", "a") != "a" or peluang < 75

        if p.get("is_captain"):
            kapten = {"nama": nama, "bermasalah": bermasalah, "kabar": info.get("kabar", "")}
        if p.get("is_vice_captain"):
            wakil = {"nama": nama, "bermasalah": bermasalah}

        if p["position"] <= 11:
            if bermasalah:
                xi_bermasalah.append({"nama": nama, "peluang": peluang,
                                      "kabar": info.get("kabar", "")})
        else:
            if not bermasalah:
                bangku_aman += 1

    catatan = []
    if kapten and kapten["bermasalah"]:
        catatan.append(f"⛔ Kaptenmu ({kapten['nama']}) sedang bermasalah — pindahkan ban kapten")
    if kapten and wakil and wakil["bermasalah"]:
        if kapten["bermasalah"]:
            catatan.append(
                f"⛔ Kapten ({kapten['nama']}) DAN wakil kapten ({wakil['nama']}) "
                "dua-duanya bermasalah — kalau keduanya tidak main, ban kapten hangus")
        else:
            catatan.append(
                f"⚠️ Wakil kapten ({wakil['nama']}) meragukan — cadangan lapis dua kosong")
    if len(xi_bermasalah) > bangku_aman:
        catatan.append(
            f"⚠️ Ada {len(xi_bermasalah)} pemain bermasalah di XI tapi cuma "
            f"{bangku_aman} pemain bangku yang siap — auto-sub tidak akan menutupi semuanya"
        )
    return {"xi_bermasalah": xi_bermasalah, "bangku_aman": bangku_aman,
            "kapten": kapten, "catatan": catatan}


# ==================================================================
# 9. RIWAYAT TIM
# ==================================================================

def riwayat_tim(ambil, entry_id):
    """Nilai tim, peringkat, poin terbuang di bangku, dan ongkos transfer."""
    if not entry_id:
        return None
    data = ambil(f"entry/{entry_id}/history/", wajib=False)
    if not data or not data.get("current"):
        return None

    kini = data["current"]
    terakhir = kini[-1]
    chip_terpakai = {c.get("name") for c in data.get("chips", [])}

    gerak = ""
    if len(kini) >= 2 and kini[-2].get("overall_rank") and terakhir.get("overall_rank"):
        selisih = kini[-2]["overall_rank"] - terakhir["overall_rank"]
        gerak = f"naik {selisih:,}" if selisih > 0 else f"turun {abs(selisih):,}"

    return {
        "nilai_tim": terakhir.get("value", 0) / 10.0,
        "bank": terakhir.get("bank", 0) / 10.0,
        "peringkat": terakhir.get("overall_rank"),
        "gerak_peringkat": gerak,
        "poin_total": terakhir.get("total_points", 0),
        "poin_bangku": sum(g.get("points_on_bench", 0) for g in kini),
        "ongkos_transfer": sum(g.get("event_transfers_cost", 0) for g in kini),
        "chip_terpakai": chip_terpakai,
        "chip_tersisa": sorted(set(NAMA_CHIP) - chip_terpakai),
    }


# ==================================================================
# 10. PERAKIT RINGKASAN
# ==================================================================

def ringkas_telegram(riwayat, liga, chip, differ, khusus, nama_klub):
    """Susun potongan teks untuk pesan Telegram. Ringkas — layar HP itu sempit."""
    baris = []

    if riwayat:
        sisa = ", ".join(NAMA_CHIP[c] for c in riwayat["chip_tersisa"]) or "habis"
        baris.append(
            f"\n💰 Nilai tim {riwayat['nilai_tim']:.1f}jt · bank {riwayat['bank']:.1f}jt"
            + (f" · peringkat {riwayat['peringkat']:,}" if riwayat["peringkat"] else "")
            + (f" ({riwayat['gerak_peringkat']})" if riwayat["gerak_peringkat"] else "")
            + f"\n🎟️ Chip tersisa: {sisa}"
            + f"\n🪑 Poin terbuang di bangku musim ini: {riwayat['poin_bangku']}"
        )

    if liga and liga.get("saya"):
        s = liga["saya"]
        baris.append(f"\n🏆 {liga['liga']}: peringkat {s['rank']}/{liga['jumlah']} ({liga['gerak']})")
        if liga["atas"]:
            a = liga["atas"][-1]
            baris.append(f"   ↑ {a['tim']} unggul {a['selisih']} poin")
        if liga["bawah"]:
            b = liga["bawah"][0]
            baris.append(f"   ↓ {b['tim']} tertinggal {b['selisih']} poin")

    if chip:
        baris.append("\n🎟️ <b>Saran chip:</b>")
        for c in chip[:3]:
            baris.append(f"   GW{c['gw']} — {c['chip']} ({c['kekuatan']}): {c['alasan']}")

    if khusus:
        potongan = []
        for gw, info in sorted(khusus.items())[:4]:
            bagian = []
            if info["double"]:
                bagian.append(f"double: {', '.join(nama_klub.get(k, '?') for k in info['double'][:4])}")
            if info["blank"]:
                bagian.append(f"blank: {', '.join(nama_klub.get(k, '?') for k in info['blank'][:4])}")
            potongan.append(f"   GW{gw} — {' · '.join(bagian)}")
        if potongan:
            baris.append("\n📅 <b>Gameweek khusus:</b>")
            baris += potongan

    if differ:
        nama = ", ".join(f"{d['Nama']} ({d['Klub']}, {d['Milik%']}%)" for d in differ[:4])
        baris.append(f"\n💎 Differential: {nama}")

    return "\n".join(baris)
