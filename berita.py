#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================
  RINGKASAN BERITA FPL
=============================================================
Berita cedera itu banyak. Yang sedikit adalah berita yang benar-benar
mengubah keputusanmu. Modul ini menyaringnya.

Dua lapis:

  LAPIS 1 (gratis, tanpa API key)
  Menyaring seluruh berita resmi FPL 72 jam terakhir, lalu menerjemahkan
  tiap berita jadi satu tindakan: JUAL, TAHAN, PANTAU, atau PELUANG BELI.
  Termasuk membaca dampaknya terhadap peringkatmu — pemain populer yang
  cedera dan TIDAK kamu miliki justru kabar baik.

  LAPIS 2 (opsional, butuh anthropic_api_key)
  Menelusuri berita konferensi pers di web untuk pemain paling genting,
  lalu menandai tiap temuan RESMI / RUMOR / TIDAK ADA BERITA.

Semua fungsi aman gagal.
"""

import re
import datetime as dt

import requests


# ==================================================================
# PENYARINGAN BERITA
# ==================================================================

ARTI_STATUS = {
    "a": "fit", "d": "diragukan", "i": "cedera",
    "s": "sanksi", "u": "tidak terdaftar", "n": "tidak memenuhi syarat",
}


def _umur_jam(stempel):
    """Berapa jam lalu berita ini ditambahkan."""
    if not stempel:
        return None
    try:
        waktu = dt.datetime.fromisoformat(str(stempel).replace("Z", "+00:00"))
        return (dt.datetime.now(dt.timezone.utc) - waktu).total_seconds() / 3600
    except (ValueError, TypeError):
        return None


def _perkiraan_kembali(kabar):
    """Tarik tanggal perkiraan pulih dari teks berita FPL, kalau ada."""
    if not kabar:
        return None
    cocok = re.search(r"[Ee]xpected back\s+([0-9]{1,2}\s+\w+)", str(kabar))
    if cocok:
        return cocok.group(1)
    if re.search(r"[Uu]nknown return", str(kabar)):
        return "belum diketahui"
    return None


def _bobot(status, peluang):
    """Seberapa berat kabarnya. Angka besar = makin genting."""
    if status in ("i", "u", "n"):
        return 100
    if status == "s":
        return 90
    if status == "d":
        if peluang is not None and peluang <= 25:
            return 85
        if peluang is not None and peluang <= 50:
            return 70
        return 50
    return 10


def saran_tindakan(item):
    """
    Terjemahkan satu berita jadi keputusan. Inilah bagian yang menentukan
    apakah ringkasan ini berguna atau cuma tumpukan informasi.
    """
    dimiliki = item["dimiliki"]
    bobot = item["bobot"]
    peluang = item["peluang"]
    milik = item["milik"]
    pulih = item["pulih"]

    if pulih:
        if dimiliki:
            return ("TAHAN", "Sudah fit kembali — tidak perlu tindakan")
        if milik <= 15 and item["harga"] <= 8.0:
            return ("PELUANG BELI", f"Baru pulih dan baru dimiliki {milik}% — "
                                    f"harganya biasanya naik beberapa hari setelah kabar ini")
        return ("PANTAU", "Baru pulih, tunggu konfirmasi menit bermain")

    if dimiliki:
        if bobot >= 90:
            sisa = f", perkiraan kembali {item['kembali']}" if item["kembali"] else ""
            return ("JUAL", f"Tidak bisa dimainkan{sisa} — kursi di XI-mu terbuang percuma")
        if bobot >= 70:
            return ("PANTAU", f"Peluang main {peluang}% — putuskan 1 jam sebelum deadline, "
                              f"jangan buru-buru buang transfer")
        return ("TAHAN", f"Peluang main {peluang}% — risikonya kecil, biasanya tetap main")

    # tidak dimiliki
    if bobot >= 85 and milik >= 25:
        return ("KABAR BAIK", f"{milik}% manajer memilikinya dan kamu tidak — "
                              f"peringkatmu naik tanpa melakukan apa pun")
    if bobot >= 85 and milik >= 10:
        return ("PANTAU", f"Dimiliki {milik}% — pesaingmu akan sibuk mencari pengganti, "
                          f"perhatikan siapa yang mereka beli")
    return ("ABAIKAN", "Tidak menyentuh skuadmu maupun pesaing dekat")


def kumpulkan_berita(bootstrap, ids_skuad, ids_incaran=None, jam=72, milik_minimal=5.0):
    """
    Saring semua berita resmi FPL dalam rentang waktu tertentu.
    Yang lolos: pemain di skuadmu, pemain incaranmu, atau pemain populer.
    """
    nama_klub = {t["id"]: t["short_name"] for t in bootstrap.get("teams", [])}
    posisi = {p["id"]: p["singular_name_short"] for p in bootstrap.get("element_types", [])}
    milikku = {int(i) for i in (ids_skuad or [])}
    incaran = {int(i) for i in (ids_incaran or [])}

    hasil = []
    for p in bootstrap.get("elements", []):
        kabar = (p.get("news") or "").strip()
        umur = _umur_jam(p.get("news_added"))
        status = p.get("status", "a")
        peluang = p.get("chance_of_playing_next_round")
        milik = float(p.get("selected_by_percent") or 0)
        pid = p["id"]

        # Berita dianggap relevan kalau masih baru, atau kalau pemainnya
        # sedang bermasalah — kabar lama yang belum selesai tetap penting.
        baru = umur is not None and umur <= jam
        bermasalah = status != "a" or (peluang is not None and peluang < 100)
        if not kabar or not (baru or bermasalah):
            continue

        penting = pid in milikku or pid in incaran or milik >= milik_minimal
        if not penting:
            continue

        # "Pulih" = statusnya sudah fit tapi masih ada catatan berita,
        # biasanya kalimat seperti "returned to training".
        pulih = status == "a"

        item = {
            "id": pid,
            "nama": p["web_name"],
            "klub": nama_klub.get(p["team"], "?"),
            "pos": posisi.get(p["element_type"], "?"),
            "harga": (p.get("now_cost") or 0) / 10.0,
            "milik": round(milik, 1),
            "status": ARTI_STATUS.get(status, status),
            "peluang": 100 if peluang is None else peluang,
            "kabar": kabar,
            "kembali": _perkiraan_kembali(kabar),
            "umur_jam": round(umur, 1) if umur is not None else None,
            "dimiliki": pid in milikku,
            "incaran": pid in incaran,
            "pulih": pulih,
            "bobot": _bobot(status, peluang),
        }
        item["tindakan"], item["alasan"] = saran_tindakan(item)
        hasil.append(item)

    # Skuadmu selalu di atas, lalu incaran, lalu yang paling genting,
    # lalu yang paling banyak dimiliki orang.
    hasil.sort(key=lambda x: (not x["dimiliki"], not x["incaran"],
                              -x["bobot"], -x["milik"]))
    return hasil


# ==================================================================
# DAMPAK KE PERINGKAT
# ==================================================================

def dampak_peringkat(berita):
    """
    Hitung untung-rugi bersih terhadap peringkatmu. Di FPL kamu tidak
    bersaing melawan poin absolut, tapi melawan manajer lain — jadi
    cedera pemain populer yang tidak kamu miliki adalah keuntungan.
    """
    rugi = [b for b in berita if b["dimiliki"] and b["bobot"] >= 70 and not b["pulih"]]
    untung = [b for b in berita if not b["dimiliki"] and b["bobot"] >= 85
              and b["milik"] >= 20 and not b["pulih"]]

    skor_rugi = sum(b["milik"] for b in rugi)
    skor_untung = sum(b["milik"] for b in untung)
    bersih = skor_untung - skor_rugi

    if bersih > 15:
        nada = "menguntungkan"
    elif bersih < -15:
        nada = "merugikan"
    else:
        nada = "netral"

    return {
        "rugi": rugi, "untung": untung, "bersih": round(bersih, 1), "nada": nada,
        "kalimat": _kalimat_dampak(rugi, untung, nada, bersih),
    }


def _kalimat_dampak(rugi, untung, nada, bersih):
    if not rugi and not untung:
        return "Tidak ada berita yang menggeser posisimu relatif terhadap manajer lain."
    bagian = []
    if rugi:
        bagian.append(f"{len(rugi)} pemainmu bermasalah")
    if untung:
        nama = ", ".join(f"{b['nama']} ({b['milik']}%)" for b in untung[:3])
        bagian.append(f"pemain populer yang tidak kamu miliki juga kena: {nama}")
    inti = " — sementara ".join(bagian)
    return f"Dampak bersih pekan ini {nada} ({bersih:+.1f}). {inti}."


# ==================================================================
# BRIEFING AI (OPSIONAL)
# ==================================================================

def briefing_ai(cfg, berita, batas=6):
    """
    Telusuri berita web untuk pemain paling genting. Hasilnya selalu
    diberi label sumber, karena keputusan transfer tidak boleh berdiri
    di atas rumor yang disamarkan jadi fakta.
    """
    kunci = cfg.get("anthropic_api_key", "")
    if not kunci or not berita:
        return ""

    penting = [b for b in berita if b["dimiliki"] or b["bobot"] >= 85][:batas]
    if not penting:
        return ""

    konteks = "\n".join(
        f"- {b['nama']} ({b['klub']}, {b['pos']}, {b['harga']}jt, dimiliki {b['milik']}%): "
        f"{b['kabar']} | status FPL: {b['status']}, peluang main {b['peluang']}%"
        + (" | ADA DI SKUAD SAYA" if b["dimiliki"] else "")
        for b in penting
    )

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            timeout=120,
            headers={"x-api-key": kunci, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 1000,
                "system": (
                    "Kamu analis berita Fantasy Premier League. Kamu diberi daftar pemain "
                    "bermasalah beserta keterangan resmi FPL. Cari berita 72 jam terakhir "
                    "untuk melengkapinya, terutama hasil konferensi pers pelatih.\n\n"
                    "Format tiap pemain SATU baris:\n"
                    "NAMA — temuan singkat — [RESMI/RUMOR/TIDAK ADA BERITA] — tindakan yang disarankan\n\n"
                    "Aturan keras: jangan mengarang. Kalau tidak menemukan apa pun, tulis "
                    "TIDAK ADA BERITA dan jangan menebak. Bedakan ucapan pelatih (RESMI) "
                    "dari laporan wartawan (RUMOR). Utamakan pemain yang ada di skuad pengguna. "
                    "Tutup dengan satu baris 'PRIORITAS:' berisi satu keputusan paling mendesak. "
                    "Bahasa Indonesia, maksimal 250 kata."
                ),
                "messages": [{"role": "user", "content":
                              f"Pemain yang perlu ditelusuri:\n{konteks}"}],
                "tools": [{"type": "web_search_20250305", "name": "web_search"}],
            },
        )
        data = r.json()
        if "error" in data:
            return f"(Briefing AI gagal: {data['error'].get('message', '')[:120]})"
        return "".join(b.get("text", "") for b in data.get("content", [])).strip()
    except requests.RequestException as e:
        return f"(Briefing AI gagal: {e})"


# ==================================================================
# PERAKIT KELUARAN
# ==================================================================

IKON = {
    "JUAL": "🔴", "PANTAU": "🟡", "TAHAN": "🟢",
    "PELUANG BELI": "💎", "KABAR BAIK": "😀", "ABAIKAN": "⚪",
}


def ringkas_telegram(berita, dampak, ai="", batas=10):
    """Ringkasan berita untuk Telegram, sudah diurutkan menurut kepentingan."""
    if not berita:
        return ""

    baris = ["\n<b>📰 RINGKASAN BERITA</b>"]
    if dampak:
        baris.append(f"<i>{dampak['kalimat']}</i>")

    ditampilkan = [b for b in berita if b["tindakan"] != "ABAIKAN"][:batas]
    if not ditampilkan:
        baris.append("Tidak ada berita yang memengaruhi keputusanmu.")
        return "\n".join(baris)

    for b in ditampilkan:
        tanda = "🔴" if b["dimiliki"] else ("🎯" if b["incaran"] else "⚪")
        baris.append(
            f"\n{tanda} <b>{b['nama']} ({b['klub']})</b> — {b['status']}"
            + (f", peluang {b['peluang']}%" if b["peluang"] < 100 else "")
            + f"\n   {b['kabar']}"
            + f"\n   {IKON.get(b['tindakan'], '·')} <b>{b['tindakan']}</b> — {b['alasan']}"
        )

    if ai:
        baris.append(f"\n<b>Pantauan berita web:</b>\n{ai[:900]}")
    return "\n".join(baris)


def tabel_html(berita, batas=20):
    """Baris siap pakai untuk tabel laporan HTML."""
    return [
        {
            "Pemain": f"{b['nama']} ({b['klub']})",
            "Pos": b["pos"],
            "Harga": b["harga"],
            "Milik%": b["milik"],
            "Status": b["status"],
            "Peluang": f"{b['peluang']}%",
            "Kabar": b["kabar"],
            "Tindakan": b["tindakan"],
            "Alasan": b["alasan"],
        }
        for b in berita[:batas] if b["tindakan"] != "ABAIKAN"
    ]
