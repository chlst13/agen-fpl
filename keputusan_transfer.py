#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Persetujuan transfer semi-otomatis melalui tombol Telegram.

Modul ini tidak pernah login atau melakukan transfer ke akun FPL. Tombol
Telegram hanya menyimpan keputusan pengguna agar rekomendasi berikutnya tahu
opsi mana yang disetujui, ditolak, atau ditunda.
"""

import datetime as dt
import json
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


def proses_callback(cfg, bootstrap, path=BERKAS_KEPUTUSAN, gw_aktif=None, sekarang=None):
    """Ambil klik tombol Telegram dan simpan sebagai catatan keputusan."""
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
                "allowed_updates": json.dumps(["callback_query"]),
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
