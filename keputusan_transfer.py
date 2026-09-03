#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Persetujuan transfer semi-otomatis melalui tombol Telegram.

Modul ini tidak pernah login atau melakukan transfer ke akun FPL. Tombol
Telegram hanya menyimpan keputusan pengguna agar rekomendasi berikutnya tahu
opsi mana yang disetujui, ditolak, atau ditunda.
"""

import datetime as dt
import html
import json
import re
import unicodedata
from pathlib import Path

import requests


BERKAS_KEPUTUSAN = Path(__file__).resolve().parent / "keputusan_transfer.json"
STATUS = {"a": "DISETUJUI", "r": "DITOLAK", "d": "DITUNDA"}
IKON = {"DISETUJUI": "✅", "DITOLAK": "❌", "DITUNDA": "⏸️"}


def muat(path=BERKAS_KEPUTUSAN):
    path = Path(path)
    if not path.exists():
        return {"offset": 0, "keputusan": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"offset": 0, "keputusan": []}
    data.setdefault("offset", 0)
    data.setdefault("keputusan", [])
    return data


def simpan(data, path=BERKAS_KEPUTUSAN):
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _utc(nilai=None):
    """Normalisasi waktu menjadi UTC; nilai rusak dikembalikan sebagai None."""
    if nilai is None:
        return dt.datetime.now(dt.timezone.utc)
    if isinstance(nilai, dt.datetime):
        waktu = nilai
    else:
        try:
            waktu = dt.datetime.fromisoformat(str(nilai).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if waktu.tzinfo is None:
        waktu = waktu.replace(tzinfo=dt.timezone.utc)
    return waktu.astimezone(dt.timezone.utc)


def _normal_id(nilai):
    try:
        return int(float(nilai))
    except (TypeError, ValueError):
        return 0


def _normal_nama(nilai):
    teks = unicodedata.normalize("NFKD", str(nilai or ""))
    teks = "".join(c for c in teks if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", teks.lower()).strip()


def _cari_pemain(teks, bootstrap):
    """Cari satu pemain secara aman; dukung `Nama (KLUB)` bila ambigu."""
    mentah = str(teks or "").strip()
    cocok_klub = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", mentah)
    nama_cari = _normal_nama(cocok_klub.group(1) if cocok_klub else mentah)
    klub_cari = _normal_nama(cocok_klub.group(2)) if cocok_klub else ""
    klub = {int(t["id"]): t.get("short_name", "") for t in bootstrap.get("teams", [])}
    temuan = []
    for p in bootstrap.get("elements", []):
        alias = {
            _normal_nama(p.get("web_name")),
            _normal_nama(f"{p.get('first_name', '')} {p.get('second_name', '')}"),
        }
        if nama_cari not in alias:
            continue
        singkat = klub.get(int(p.get("team", 0)), "")
        if klub_cari and _normal_nama(singkat) != klub_cari:
            continue
        temuan.append({"id": int(p["id"]), "nama": p.get("web_name", mentah), "klub": singkat})
    if len(temuan) == 1:
        return temuan[0], ""
    if not temuan:
        return None, f"Pemain '{mentah}' tidak ditemukan. Gunakan nama yang tampil di FPL."
    daftar = ", ".join(f"{x['nama']} ({x['klub']})" for x in temuan)
    return None, f"Nama ambigu: {daftar}. Tambahkan klub, misalnya Nama (MUN)."


def transfer_manual_gw(data, gw):
    return [
        x for x in data.get("transfer_manual", [])
        if _normal_id(x.get("gw")) == _normal_id(gw)
    ]


def bank_manual_gw(data, gw):
    item = data.get("bank_manual") or {}
    if _normal_id(item.get("gw")) != _normal_id(gw):
        return None
    try:
        return float(item.get("nilai"))
    except (TypeError, ValueError):
        return None


def terapkan_transfer_manual(ids, data, gw):
    """Tempel transfer konfirmasi Telegram ke susunan publik pra-deadline."""
    hasil = list(ids or [])
    diterapkan = []
    for item in transfer_manual_gw(data or {}, gw):
        keluar = _normal_id(item.get("keluar_id"))
        masuk = _normal_id(item.get("masuk_id"))
        if keluar in hasil:
            hasil[hasil.index(keluar)] = masuk
            diterapkan.append(item)
        elif masuk in hasil:
            # FPL sudah membuka transfer tersebut; jangan menambah pemain ganda.
            diterapkan.append(item)
    return list(dict.fromkeys(hasil)), diterapkan


def teks_sinkronisasi(data, gw):
    baris = []
    for x in transfer_manual_gw(data or {}, gw):
        baris.append(f"{x.get('keluar', '?')} → {x.get('masuk', '?')}")
    bank = bank_manual_gw(data or {}, gw)
    if bank is not None:
        baris.append(f"bank {bank:.1f}jt")
    return "; ".join(baris)


def daftar_gw(data, gw):
    """Keputusan terbaru untuk setiap pasangan transfer pada satu GW."""
    terbaru = {}
    for item in data.get("keputusan", []):
        if _normal_id(item.get("gw")) != _normal_id(gw):
            continue
        kunci = (_normal_id(item.get("keluar_id")), _normal_id(item.get("masuk_id")))
        terbaru[kunci] = item
    return list(terbaru.values())


def peta_status(data, gw):
    return {
        (_normal_id(x.get("keluar_id")), _normal_id(x.get("masuk_id"))): x["status"]
        for x in daftar_gw(data, gw)
        if x.get("status")
    }


def ringkasan(data, gw):
    hasil = []
    for x in daftar_gw(data, gw):
        hasil.append({
            "GW": _normal_id(gw),
            "Transfer": f"{x.get('keluar', '?')} → {x.get('masuk', '?')}",
            "Status": x.get("status", ""),
            "Diputuskan": x.get("waktu", ""),
        })
    urutan = {"DISETUJUI": 0, "DITUNDA": 1, "DITOLAK": 2}
    return sorted(hasil, key=lambda x: (urutan.get(x["Status"], 9), x["Transfer"]))


def teks_ringkasan(data, gw, batas=4):
    rows = ringkasan(data, gw)
    if not rows:
        return ""
    baris = ["<b>📝 Keputusan Om</b>"]
    for x in rows[:batas]:
        baris.append(f"{IKON.get(x['Status'], '•')} {x['Transfer']} — {x['Status'].lower()}")
    return "\n".join(baris)


def _opsi_layak(transfer, batas=None):
    """Hanya tampilkan opsi yang lolos pagar kualitas mesin strategi."""
    if transfer is None or transfer.empty:
        return transfer
    kandidat = transfer.copy()
    if "Status Om" in kandidat:
        kandidat = kandidat[kandidat["Status Om"] != "DITOLAK"]
    if "Keputusan" in kandidat:
        kandidat = kandidat[kandidat["Keputusan"] != "TAHAN"]
    if "Kesiapan" in kandidat:
        kandidat = kandidat[kandidat["Kesiapan"] != "MERAH"]
    return kandidat.head(batas) if batas else kandidat


def catat_penawaran(transfer, gw, kedaluwarsa=None, path=BERKAS_KEPUTUSAN):
    """Simpan snapshot opsi yang benar-benar dikirim ke Telegram.

    Snapshot menjadi pagar pengaman: callback lama, opsi yang tidak pernah
    ditawarkan, dan klik setelah deadline tidak boleh dianggap persetujuan.
    """
    sekarang = _utc()
    batas = _utc(kedaluwarsa) if kedaluwarsa else sekarang + dt.timedelta(hours=36)
    opsi = []
    # Harus sama dengan jumlah tombol default agar opsi yang tidak terlihat
    # di pesan terbaru tidak dapat disetujui dari tombol laporan lama.
    for _, r in _opsi_layak(transfer, batas=3).iterrows():
        keluar, masuk = _normal_id(r.get("_keluar_id")), _normal_id(r.get("_masuk_id"))
        if not keluar or not masuk:
            continue
        gain_col = next(
            (c for c in r.index if str(c).startswith("Gain ") and str(c).endswith("GW")),
            None,
        )
        opsi.append({
            "keluar_id": keluar,
            "masuk_id": masuk,
            "keluar": str(r.get("Keluar", keluar)),
            "masuk": str(r.get("Masuk", masuk)),
            "kesiapan": str(r.get("Kesiapan", "BELUM DINILAI")),
            "confidence": float(r.get("Confidence Masuk%", 0) or 0),
            "xmins": float(r.get("xMins Masuk", 0) or 0),
            "gain": float(r.get(gain_col, 0) or 0) if gain_col else 0,
        })

    data = muat(path)
    data["penawaran"] = {
        "gw": _normal_id(gw),
        "dibuat": sekarang.isoformat(timespec="seconds"),
        "kedaluwarsa": batas.isoformat(timespec="seconds") if batas else "",
        "opsi": opsi,
    }
    simpan(data, path)
    return data["penawaran"]


def keyboard(transfer, gw, batas=3):
    """Tombol keputusan untuk maksimal tiga rekomendasi teratas."""
    if transfer is None or transfer.empty:
        return None
    rows = []
    kandidat = _opsi_layak(transfer, batas=batas)
    for _, r in kandidat.iterrows():
        keluar = _normal_id(r.get("_keluar_id"))
        masuk = _normal_id(r.get("_masuk_id"))
        if not keluar or not masuk:
            continue
        kode = f"{_normal_id(gw)}|{keluar}|{masuk}"
        warna = "🟢" if r.get("Kesiapan") == "HIJAU" else "🟡"
        label = f"{str(r.get('Keluar', '?'))[:10]}→{str(r.get('Masuk', '?'))[:10]}"
        rows.append([
            {"text": f"{warna} Setujui {label}", "callback_data": f"fpl2|a|{kode}"},
            {"text": "❌ Tolak", "callback_data": f"fpl2|r|{kode}"},
            {"text": "⏸ Tunda", "callback_data": f"fpl2|d|{kode}"},
        ])
    return {"inline_keyboard": rows} if rows else None


def _jawab_callback(token, callback_id, teks):
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            timeout=(10, 30),
            json={"callback_query_id": callback_id, "text": teks[:180]},
        )
    except requests.RequestException:
        pass


def _balas_pesan(token, chat_id, teks, message_id=None):
    payload = {"chat_id": chat_id, "text": teks}
    if message_id:
        payload["reply_parameters"] = {"message_id": message_id}
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            timeout=(10, 30),
            json=payload,
        )
    except requests.RequestException:
        pass


def _status_sinkronisasi(data, gw):
    transfer = transfer_manual_gw(data, gw)
    bank = bank_manual_gw(data, gw)
    if not transfer and bank is None:
        return f"Belum ada sinkronisasi manual untuk GW{gw}."
    baris = [f"Sinkronisasi sementara GW{gw}:"]
    baris += [f"• {x['keluar']} → {x['masuk']}" for x in transfer]
    baris.append(f"• Bank: {bank:.1f}jt" if bank is not None else "• Bank belum dikonfirmasi")
    return "\n".join(baris)


def _proses_perintah(teks, data, bootstrap, gw, skuad_ids=None):
    """Proses perintah sinkronisasi skuad; kembalikan balasan atau None."""
    bagian = str(teks or "").strip().split(maxsplit=1)
    if not bagian or not bagian[0].startswith("/"):
        return None
    perintah = bagian[0].lower().split("@", 1)[0]
    isi = bagian[1].strip() if len(bagian) > 1 else ""
    gw = _normal_id(gw)

    if perintah in ("/bantuanskuad", "/helpskuad"):
        return (
            "Perintah sinkronisasi skuad:\n"
            "/transfer Pemain Lama > Pemain Baru\n"
            "/bank 0.5\n"
            "/statusskuad\n"
            "/batalsync"
        )
    if perintah == "/statusskuad":
        return _status_sinkronisasi(data, gw)
    if perintah in ("/batalsync", "/bataltransfer"):
        data["transfer_manual"] = [
            x for x in data.get("transfer_manual", []) if _normal_id(x.get("gw")) != gw
        ]
        if _normal_id((data.get("bank_manual") or {}).get("gw")) == gw:
            data.pop("bank_manual", None)
        return f"Sinkronisasi manual GW{gw} dibatalkan. Bot kembali memakai data publik FPL."
    if perintah == "/bank":
        try:
            nilai = float(isi.replace(",", "."))
        except ValueError:
            return "Format salah. Contoh: /bank 0.5"
        if not 0 <= nilai <= 20:
            return "Bank harus antara 0 sampai 20 juta."
        data["bank_manual"] = {
            "gw": gw,
            "nilai": round(nilai, 1),
            "waktu": _utc().isoformat(timespec="seconds"),
        }
        return f"Bank sementara GW{gw} disimpan: {nilai:.1f}jt."
    if perintah != "/transfer":
        return None
    if not gw:
        return "GW berikutnya belum dapat ditentukan. Coba lagi setelah data FPL tersedia."

    cocok = re.match(r"^(.+?)\s*(?:->|→|>)\s*(.+?)$", isi)
    if not cocok:
        return "Format salah. Contoh: /transfer Davies > Ajayi"
    keluar, galat = _cari_pemain(cocok.group(1), bootstrap)
    if galat:
        return galat
    masuk, galat = _cari_pemain(cocok.group(2), bootstrap)
    if galat:
        return galat
    if keluar["id"] == masuk["id"]:
        return "Pemain keluar dan masuk tidak boleh sama."

    ids = set(int(x) for x in (skuad_ids or []))
    if ids and keluar["id"] not in ids:
        return f"{keluar['nama']} tidak ada di skuad sementara Om. Cek /statusskuad."
    if ids and masuk["id"] in ids:
        return f"{masuk['nama']} sudah ada di skuad sementara Om."

    item = {
        "gw": gw,
        "keluar_id": keluar["id"],
        "masuk_id": masuk["id"],
        "keluar": keluar["nama"],
        "masuk": masuk["nama"],
        "waktu": _utc().isoformat(timespec="seconds"),
    }
    data.setdefault("transfer_manual", []).append(item)
    data["transfer_manual"] = data["transfer_manual"][-30:]
    return (
        f"Transfer sementara GW{gw} disimpan: {keluar['nama']} → {masuk['nama']}.\n"
        "Agar perhitungan budget akurat, kirim juga bank terbaru, contoh: /bank 0.5"
    )


def proses_callback(cfg, bootstrap, path=BERKAS_KEPUTUSAN, gw_aktif=None, sekarang=None,
                    skuad_ids=None):
    """Ambil tombol keputusan dan perintah sinkronisasi skuad dari Telegram."""
    token = cfg.get("telegram_token")
    chat_id = str(cfg.get("telegram_chat_id") or "")
    if not token or not chat_id:
        return []

    data = muat(path)
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            timeout=(10, 35),
            params={
                "offset": int(data.get("offset", 0)),
                "timeout": 0,
                "allowed_updates": json.dumps(["callback_query", "message"]),
            },
        )
        if r.status_code != 200:
            print(f"⚠ Gagal membaca tombol Telegram (HTTP {r.status_code}).")
            return []
        updates = r.json().get("result", [])
    except (requests.RequestException, ValueError) as e:
        print(f"⚠ Gagal membaca tombol Telegram: {e}")
        return []

    detail_pemain = {int(p["id"]): p for p in bootstrap.get("elements", [])}
    pemain = {pid: p.get("web_name", str(pid)) for pid, p in detail_pemain.items()}
    diproses = []
    offset = int(data.get("offset", 0))

    for update in updates:
        offset = max(offset, int(update.get("update_id", -1)) + 1)
        pesan = update.get("message") or {}
        if pesan:
            pesan_chat = str(((pesan.get("chat") or {}).get("id") or ""))
            if pesan_chat != chat_id:
                continue
            ids_efektif, _ = terapkan_transfer_manual(skuad_ids, data, gw_aktif)
            balasan = _proses_perintah(
                pesan.get("text", ""), data, bootstrap, gw_aktif,
                skuad_ids=ids_efektif)
            if balasan:
                _balas_pesan(token, chat_id, balasan, pesan.get("message_id"))
                print(f"→ Perintah Telegram: {str(pesan.get('text', '')).split(maxsplit=1)[0]}")
            continue
        cb = update.get("callback_query") or {}
        mentah = str(cb.get("data") or "")
        bagian = mentah.split("|")
        if len(bagian) != 5 or bagian[0] not in ("fpl", "fpl2") or bagian[1] not in STATUS:
            continue
        pesan_chat = str((((cb.get("message") or {}).get("chat") or {}).get("id") or ""))
        if pesan_chat != chat_id:
            _jawab_callback(token, cb.get("id", ""), "Chat ini tidak diizinkan.")
            continue

        _, aksi, gw, keluar, masuk = bagian
        gw, keluar, masuk = map(_normal_id, (gw, keluar, masuk))

        penawaran = data.get("penawaran") or {}
        pasangan = {
            (_normal_id(x.get("keluar_id")), _normal_id(x.get("masuk_id")))
            for x in penawaran.get("opsi", [])
        }
        kini = _utc(sekarang) or _utc()
        batas = _utc(penawaran.get("kedaluwarsa"))
        alasan_batal = ""
        if _normal_id(penawaran.get("gw")) != gw or (keluar, masuk) not in pasangan:
            alasan_batal = "Tombol rekomendasi lama. Jalankan laporan terbaru."
        elif gw_aktif is not None and gw != _normal_id(gw_aktif):
            alasan_batal = f"Rekomendasi GW{gw} sudah tidak aktif."
        elif batas and kini >= batas:
            alasan_batal = "Deadline sudah lewat; keputusan tidak disimpan."

        calon = detail_pemain.get(masuk, {})
        peluang = calon.get("chance_of_playing_next_round")
        if not alasan_batal and aksi == "a" and (
            calon.get("status", "a") != "a" or (peluang is not None and peluang < 75)
        ):
            alasan_batal = (
                f"{pemain.get(masuk, masuk)} kini berisiko/tidak fit; "
                "persetujuan dibatalkan."
            )
        if alasan_batal:
            _jawab_callback(token, cb.get("id", ""), alasan_batal)
            print(f"⚠ Keputusan Telegram diabaikan: {alasan_batal}")
            continue

        status = STATUS[aksi]
        item = {
            "gw": gw,
            "keluar_id": keluar,
            "masuk_id": masuk,
            "keluar": pemain.get(keluar, str(keluar)),
            "masuk": pemain.get(masuk, str(masuk)),
            "status": status,
            "waktu": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        }
        data["keputusan"] = [
            x for x in data.get("keputusan", [])
            if not (
                _normal_id(x.get("gw")) == gw
                and _normal_id(x.get("keluar_id")) == keluar
                and _normal_id(x.get("masuk_id")) == masuk
            )
        ]
        data["keputusan"].append(item)
        diproses.append(item)
        _jawab_callback(
            token,
            cb.get("id", ""),
            f"{IKON[status]} {item['keluar']} → {item['masuk']}: {status.lower()}",
        )

    if offset != int(data.get("offset", 0)) or diproses:
        data["offset"] = offset
        # Simpan maksimal dua musim keputusan agar berkas state tetap kecil.
        data["keputusan"] = data.get("keputusan", [])[-300:]
        simpan(data, path)

    for x in diproses:
        print(f"→ Keputusan Telegram: {x['keluar']} → {x['masuk']} = {x['status']}")
    return diproses
