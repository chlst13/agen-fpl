#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================
  LAPORAN GAMEWEEK
=============================================================
Modul yang menjawab tiga pertanyaan setelah bola berhenti bergulir:

  1. Berapa poin saya gameweek ini, dan bagaimana dibanding manajer lain?
  2. Apa hasil pertandingan klub-klub pemain saya?
  3. Kenapa poin saya segitu — apa yang berhasil, apa yang gagal?

Bagian ketiga adalah yang paling berharga. Skor akhir hanya memberitahu
hasil; pembedahan memberitahu sebabnya — kapten salah pilih, bangku yang
mubazir, transfer yang tidak balik modal, atau sekadar nasib buruk saat
peluang bagus tidak jadi gol.

Semua fungsi aman gagal: data tidak lengkap menghasilkan bagian kosong,
bukan agen yang berhenti.
"""

# ==================================================================
# UTILITAS
# ==================================================================

def angka(x, bawaan=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return bawaan


def peta_event(bootstrap):
    """id gameweek -> rata-rata & skor tertinggi seluruh dunia."""
    return {
        e["id"]: {
            "rata": e.get("average_entry_score", 0),
            "tertinggi": e.get("highest_score") or 0,
            "selesai": bool(e.get("finished")),
            "diperiksa": bool(e.get("data_checked")),
            "nama": e.get("name", f"GW{e['id']}"),
        }
        for e in bootstrap.get("events", [])
    }


def gw_baru_selesai(events, sudah_dibedah):
    """
    Cari gameweek yang baru saja rampung dan belum pernah dilaporkan.
    `data_checked` menandai bonus resmi sudah masuk — sebelum itu angkanya
    masih bisa berubah, jadi kita tunggu.
    """
    calon = [
        gw for gw, e in events.items()
        if e["selesai"] and e["diperiksa"] and gw != sudah_dibedah
    ]
    if not calon:
        return None
    terbaru = max(calon)
    if sudah_dibedah and terbaru <= sudah_dibedah:
        return None
    return terbaru


# ==================================================================
# 1. POIN PER GAMEWEEK
# ==================================================================

def tabel_poin(hist, events, jumlah=10):
    """
    Riwayat poin per gameweek beserta pembandingnya. Poin mentah tidak
    banyak artinya — 60 poin bisa hebat atau biasa saja tergantung
    rata-rata dunia pekan itu.
    """
    if not hist or not hist.get("current"):
        return {"baris": [], "ringkas": {}}

    baris = []
    for g in hist["current"]:
        gw = g["event"]
        e = events.get(gw, {})
        rata = e.get("rata", 0)
        poin = g.get("points", 0)
        ongkos = g.get("event_transfers_cost", 0)
        baris.append({
            "GW": gw,
            "Poin": poin,
            "Bersih": poin - ongkos,
            "Rata dunia": rata,
            "Selisih": poin - rata,
            "Tertinggi": e.get("tertinggi", 0),
            "Bangku": g.get("points_on_bench", 0),
            "Hit": -ongkos if ongkos else 0,
            "Transfer": g.get("event_transfers", 0),
            "Peringkat": g.get("overall_rank"),
        })

    if not baris:
        return {"baris": [], "ringkas": {}}

    # Gameweek yang datanya belum lengkap punya rata-rata 0. Kalau ikut
    # dihitung, pembandingnya jadi menyesatkan — jadi disaring.
    banding = [b for b in baris if b["Rata dunia"]]
    di_atas = sum(1 for b in banding if b["Selisih"] > 0)
    terbaik = max(baris, key=lambda b: b["Poin"])
    terburuk = min(baris, key=lambda b: b["Poin"])
    total_hit = sum(-b["Hit"] for b in baris)
    n = max(1, len(banding))

    ringkas = {
        "jumlah_gw": len(banding),
        "rata_saya": round(sum(b["Poin"] for b in banding) / n, 1),
        "rata_dunia": round(sum(b["Rata dunia"] for b in banding) / n, 1),
        "di_atas_rata": di_atas,
        "persen_di_atas": round(di_atas / n * 100),
        "terbaik": {"gw": terbaik["GW"], "poin": terbaik["Poin"]},
        "terburuk": {"gw": terburuk["GW"], "poin": terburuk["Poin"]},
        "total_bangku": sum(b["Bangku"] for b in baris),
        "total_hit": total_hit,
        "gw_terakhir": baris[-1],
    }
    return {"baris": baris[-jumlah:], "ringkas": ringkas}


# ==================================================================
# 2. SKOR PERTANDINGAN KLUB PEMAINMU
# ==================================================================

def rincian_poin(stat):
    """Ubah statistik mentah jadi kalimat pendek: '1 gol, 1 asis, +3 bonus'."""
    bagian = []
    peta = [
        ("goals_scored", "gol"), ("assists", "asis"),
        ("penalties_saved", "penalti diselamatkan"),
        ("saves", "penyelamatan"), ("own_goals", "gol bunuh diri"),
        ("penalties_missed", "penalti gagal"),
        ("yellow_cards", "kartu kuning"), ("red_cards", "kartu merah"),
    ]
    for kunci, label in peta:
        n = int(angka(stat.get(kunci)))
        if n > 0:
            bagian.append(f"{n} {label}" if n > 1 or label.endswith("gol") else label)
    if int(angka(stat.get("clean_sheets"))) > 0:
        bagian.append("nirbobol")
    bonus = int(angka(stat.get("bonus")))
    if bonus > 0:
        bagian.append(f"+{bonus} bonus")
    return ", ".join(bagian) or "tanpa kontribusi"


def skor_pertandingan(fixtures, gw, nama_klub, klub_pemain, nama_pemain,
                      ids_skuad, live, pengali=None):
    """
    Hasil pertandingan setiap klub yang punya pemainmu, lengkap dengan
    daftar pemainmu di laga itu dan perolehan poinnya.
    """
    pengali = pengali or {}
    stat_live = {}
    if live and live.get("elements"):
        stat_live = {e["id"]: e.get("stats", {}) for e in live["elements"]}

    milikku = set(ids_skuad or [])
    hasil = []

    for f in fixtures:
        if f.get("event") != gw:
            continue
        klub = {f.get("team_h"), f.get("team_a")}
        pemainku = [pid for pid in milikku if klub_pemain.get(pid) in klub]
        if not pemainku:
            continue

        gh, ga = f.get("team_h_score"), f.get("team_a_score")
        if f.get("finished"):
            status, skor = "selesai", f"{gh}-{ga}"
        elif f.get("started"):
            status = f"babak berjalan ({f.get('minutes', 0)}')"
            skor = f"{gh if gh is not None else 0}-{ga if ga is not None else 0}"
        else:
            status, skor = "belum main", "vs"

        daftar = []
        for pid in pemainku:
            s = stat_live.get(pid, {})
            kali = pengali.get(pid, 1)
            poin = int(angka(s.get("total_points")))
            daftar.append({
                "nama": nama_pemain.get(pid, str(pid)),
                "menit": int(angka(s.get("minutes"))),
                "poin": poin * kali,
                "kali": kali,
                "rincian": rincian_poin(s) if s else "—",
                "bps": int(angka(s.get("bps"))),
                "bangku": kali == 0,
            })
        daftar.sort(key=lambda d: -d["poin"])

        hasil.append({
            "laga": f"{nama_klub.get(f.get('team_h'), '?')} {skor} {nama_klub.get(f.get('team_a'), '?')}",
            "status": status,
            "selesai": bool(f.get("finished")),
            "pemainku": daftar,
            "poin_laga": sum(d["poin"] for d in daftar),
        })

    hasil.sort(key=lambda h: -h["poin_laga"])
    return hasil


# ==================================================================
# 3. PEMBEDAHAN MENDALAM
# ==================================================================

def bedah_gameweek(picks, live, nama_pemain, posisi_pemain, baris_hist, events, gw):
    """
    Pembedahan menyeluruh satu gameweek: kapten, bangku, transfer,
    dan seberapa jauh hasil menyimpang dari kualitas peluang.
    """
    if not picks or not picks.get("picks") or not live:
        return None

    stat = {e["id"]: e.get("stats", {}) for e in live.get("elements", [])}
    e_gw = events.get(gw, {})

    starter, bangku, kapten, wakil = [], [], None, None
    for p in picks["picks"]:
        pid = p["element"]
        s = stat.get(pid, {})
        mentah = int(angka(s.get("total_points")))
        item = {
            "id": pid,
            "nama": nama_pemain.get(pid, str(pid)),
            "pos": posisi_pemain.get(pid, "?"),
            "menit": int(angka(s.get("minutes"))),
            "mentah": mentah,
            "kali": p.get("multiplier", 1),
            "efektif": mentah * p.get("multiplier", 1),
            "xgi": angka(s.get("expected_goal_involvements")),
            "gi": int(angka(s.get("goals_scored"))) + int(angka(s.get("assists"))),
            "rincian": rincian_poin(s),
        }
        if p.get("is_captain"):
            kapten = item
        if p.get("is_vice_captain"):
            wakil = item
        (starter if p["position"] <= 11 else bangku).append(item)

    otomatis = [
        {"masuk": nama_pemain.get(a["element_in"], a["element_in"]),
         "keluar": nama_pemain.get(a["element_out"], a["element_out"])}
        for a in picks.get("automatic_subs", [])
    ]

    # --- kapten: apa yang terjadi vs apa yang seharusnya ---
    analisa_kapten = None
    if kapten:
        terbaik = max(starter, key=lambda x: x["mentah"]) if starter else None
        rugi = 0
        if terbaik and terbaik["id"] != kapten["id"]:
            rugi = (terbaik["mentah"] - kapten["mentah"]) * max(1, kapten["kali"] - 1)
        analisa_kapten = {
            "nama": kapten["nama"],
            "mentah": kapten["mentah"],
            "efektif": kapten["efektif"],
            "terbaik": terbaik["nama"] if terbaik else "-",
            "poin_terbaik": terbaik["mentah"] if terbaik else 0,
            "tepat": bool(terbaik and terbaik["id"] == kapten["id"]),
            "kehilangan": max(0, rugi),
            "wakil": wakil["nama"] if wakil else "-",
            "kapten_main": kapten["menit"] > 0,
        }

    # --- bangku: berapa yang mubazir ---
    poin_bangku = sum(b["mentah"] for b in bangku)
    bangku_terbaik = max(bangku, key=lambda b: b["mentah"]) if bangku else None

    # --- transfer: balik modal atau tidak ---
    ongkos = (baris_hist or {}).get("event_transfers_cost", 0)
    jumlah_tf = (baris_hist or {}).get("event_transfers", 0)

    # --- keberuntungan: hasil vs kualitas peluang ---
    total_xgi = sum(x["xgi"] for x in starter)
    total_gi = sum(x["gi"] for x in starter)
    selisih_xgi = round(total_gi - total_xgi, 2)

    poin_gw = (baris_hist or {}).get("points", sum(x["efektif"] for x in starter))
    rata = e_gw.get("rata", 0)

    # --- penyumbang dan pengecewa ---
    urut = sorted(starter, key=lambda x: -x["efektif"])
    penyumbang = urut[:3]
    pengecewa = [x for x in urut if x["menit"] > 0][-3:][::-1]

    # --- kontribusi per posisi ---
    per_pos = {}
    for x in starter:
        per_pos[x["pos"]] = per_pos.get(x["pos"], 0) + x["efektif"]

    catatan = []
    if analisa_kapten and not analisa_kapten["kapten_main"]:
        catatan.append(
            f"⛔ Kaptenmu ({analisa_kapten['nama']}) tidak bermain sama sekali. "
            f"Ban kapten pindah ke {analisa_kapten['wakil']}."
        )
    elif analisa_kapten and analisa_kapten["kehilangan"] >= 6:
        catatan.append(
            f"😖 Salah pilih kapten memakan {analisa_kapten['kehilangan']} poin — "
            f"{analisa_kapten['terbaik']} mengumpulkan {analisa_kapten['poin_terbaik']}."
        )
    elif analisa_kapten and analisa_kapten["tepat"]:
        catatan.append(f"🎯 Pilihan kapten tepat sasaran ({analisa_kapten['nama']}).")

    if poin_bangku >= 12:
        catatan.append(
            f"🪑 {poin_bangku} poin tertinggal di bangku"
            + (f", terbesar dari {bangku_terbaik['nama']} ({bangku_terbaik['mentah']})" if bangku_terbaik else "")
            + ". Periksa lagi urutan bangkumu."
        )
    if ongkos > 0:
        catatan.append(
            f"💸 Kamu bayar {ongkos} poin untuk {jumlah_tf} transfer. "
            f"Transfer itu perlu menghasilkan lebih dari {ongkos} poin ekstra untuk balik modal."
        )
    if otomatis:
        daftar = ", ".join(f"{a['masuk']} menggantikan {a['keluar']}" for a in otomatis)
        catatan.append(f"🔄 Pergantian otomatis: {daftar}.")
    if selisih_xgi <= -1.5:
        catatan.append(
            f"🎲 Skuadmu menciptakan peluang senilai {total_xgi:.1f} gol/asis tapi hanya "
            f"menghasilkan {total_gi}. Prosesnya benar, hasilnya belum datang — biasanya menyusul."
        )
    elif selisih_xgi >= 1.5:
        catatan.append(
            f"🍀 Hasil {total_gi} gol/asis melampaui kualitas peluang ({total_xgi:.1f}). "
            f"Nikmati, tapi jangan jadikan dasar keputusan transfer."
        )
    if rata:
        beda = poin_gw - rata
        kata = "di atas" if beda >= 0 else "di bawah"
        catatan.append(f"📊 {poin_gw} poin — {abs(beda)} {kata} rata-rata dunia ({rata}).")

    return {
        "poin_gw": poin_gw,
        "rata_dunia": rata,
        "tertinggi_dunia": e_gw.get("tertinggi", 0),
        "kapten": analisa_kapten,
        "poin_bangku": poin_bangku,
        "bangku_terbaik": bangku_terbaik,
        "auto_sub": otomatis,
        "ongkos_transfer": ongkos,
        "xgi_skuad": round(total_xgi, 2),
        "gi_skuad": total_gi,
        "selisih_xgi": selisih_xgi,
        "penyumbang": penyumbang,
        "pengecewa": pengecewa,
        "per_posisi": per_pos,
        "starter": starter,
        "bangku": bangku,
        "catatan": catatan,
    }


# ==================================================================
# 4. PERAKIT PESAN
# ==================================================================

def teks_gw_telegram(gw, bedah, laga, poin):
    """Pesan Telegram untuk pembedahan gameweek. Ringkas — layar HP sempit."""
    baris = [f"<b>📋 PEMBEDAHAN GAMEWEEK {gw}</b>"]

    if bedah:
        b = bedah
        baris.append(
            f"\n<b>{b['poin_gw']} poin</b> · rata dunia {b['rata_dunia']} · "
            f"tertinggi {b['tertinggi_dunia']}"
        )
        if b["kapten"]:
            k = b["kapten"]
            tanda = "🎯" if k["tepat"] else "·"
            baris.append(f"{tanda} Kapten {k['nama']}: {k['efektif']} poin")
        baris.append(f"🪑 Bangku: {b['poin_bangku']} poin terbuang")

        if b["penyumbang"]:
            isi = ", ".join(f"{p['nama']} {p['efektif']}" for p in b["penyumbang"])
            baris.append(f"⭐ Penyumbang: {isi}")

    if laga:
        baris.append("\n<b>Hasil klub pemainmu:</b>")
        for m in laga[:8]:
            baris.append(f"   {m['laga']} — {m['poin_laga']} poin")
            for p in m["pemainku"][:3]:
                if p["bangku"]:
                    continue          # pemain bangku tidak menyumbang poin
                tanda = "©" if p["kali"] > 1 else " "
                baris.append(f"      {tanda}{p['nama']}: {p['poin']} ({p['rincian']})")

    if bedah and bedah["catatan"]:
        baris.append("\n<b>Catatan:</b>")
        baris += [f"   {c}" for c in bedah["catatan"][:5]]

    if poin and poin.get("ringkas"):
        r = poin["ringkas"]
        baris.append(
            f"\n📈 Musim ini: rata {r['rata_saya']} vs dunia {r['rata_dunia']} · "
            f"unggul di {r['di_atas_rata']}/{r['jumlah_gw']} gameweek ({r['persen_di_atas']}%)"
            f"\n   Terbaik GW{r['terbaik']['gw']} ({r['terbaik']['poin']}) · "
            f"terburuk GW{r['terburuk']['gw']} ({r['terburuk']['poin']})"
            f"\n   Total terbuang di bangku: {r['total_bangku']} · ongkos transfer: {r['total_hit']}"
        )

    return "\n".join(baris)


def batang_html(baris_poin):
    """Grafik batang sederhana poin per gameweek, murni HTML — tanpa pustaka."""
    if not baris_poin:
        return ""
    puncak = max(max(b["Poin"] for b in baris_poin), 1)
    sel = ""
    for b in baris_poin:
        tinggi = int(b["Poin"] / puncak * 100)
        warna = "#4E8C6E" if b["Selisih"] >= 0 else "#A0503C"
        sel += (
            f"<div style='flex:1;display:flex;flex-direction:column;justify-content:flex-end;"
            f"align-items:center;gap:4px'>"
            f"<span style='font-size:10px;color:#8C9196'>{b['Poin']}</span>"
            f"<div style='width:70%;height:{tinggi}px;background:{warna};border-radius:1px'></div>"
            f"<span style='font-size:9px;color:#8C9196'>{b['GW']}</span></div>"
        )
    return (
        "<h3>Poin per gameweek</h3>"
        "<div style='display:flex;align-items:flex-end;gap:5px;height:150px;"
        "background:#1E2427;padding:12px;border:1px solid #333D42'>" + sel + "</div>"
        "<div style='font-size:11px;color:#8C9196;margin-top:6px'>"
        "Hijau = di atas rata-rata dunia, merah = di bawah.</div>"
    )
