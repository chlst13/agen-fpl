import json
import sys
import tempfile
import unittest
import datetime as dt
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

sys.modules.setdefault("requests", Mock())

import keputusan_transfer as keputusan


class Respons:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data


class TestKeputusanTransfer(unittest.TestCase):
    def test_keyboard_memuat_tiga_keputusan_dan_callback_ringkas(self):
        transfer = pd.DataFrame([{
            "Keluar": "Nama Panjang Keluar", "Masuk": "Nama Panjang Masuk",
            "_keluar_id": 123, "_masuk_id": 456, "Status Om": "BELUM DIPUTUSKAN",
            "Keputusan": "LAYAK", "Kesiapan": "HIJAU",
        }])

        keyboard = keputusan.keyboard(transfer, 4)

        self.assertEqual(len(keyboard["inline_keyboard"]), 1)
        self.assertEqual(len(keyboard["inline_keyboard"][0]), 3)
        for tombol in keyboard["inline_keyboard"][0]:
            self.assertLessEqual(len(tombol["callback_data"].encode()), 64)

    def test_callback_disetujui_tersimpan_dengan_nama_pemain(self):
        update = {
            "ok": True,
            "result": [{
                "update_id": 10,
                "callback_query": {
                    "id": "cb-1",
                    "data": "fpl2|a|4|1|2",
                    "from": {"username": "om"},
                    "message": {"chat": {"id": 123}},
                },
            }],
        }
        bootstrap = {"elements": [
            {"id": 1, "web_name": "Keluar", "status": "a"},
            {"id": 2, "web_name": "Masuk", "status": "a"},
        ]}
        cfg = {"telegram_token": "token", "telegram_chat_id": "123"}

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "keputusan.json"
            keputusan.catat_penawaran(pd.DataFrame([{
                "Keluar": "Keluar", "Masuk": "Masuk", "_keluar_id": 1,
                "_masuk_id": 2, "Keputusan": "LAYAK", "Kesiapan": "HIJAU",
                "Gain 5GW": 6.0,
            }]), 4, dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2), path)
            with patch("keputusan_transfer.requests.get", return_value=Respons(update)), patch(
                "keputusan_transfer.requests.post", return_value=Respons({"ok": True})
            ):
                hasil = keputusan.proses_callback(cfg, bootstrap, path)

            state = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(len(hasil), 1)
        self.assertEqual(state["offset"], 11)
        self.assertEqual(state["keputusan"][0]["status"], "DISETUJUI")
        self.assertEqual(state["keputusan"][0]["keluar"], "Keluar")
        self.assertEqual(state["keputusan"][0]["masuk"], "Masuk")

    def test_tombol_lama_ditolak_dan_tidak_mencatat_keputusan(self):
        update = {
            "result": [{
                "update_id": 20,
                "callback_query": {
                    "id": "cb-old", "data": "fpl|a|3|1|2",
                    "message": {"chat": {"id": 123}},
                },
            }],
        }
        cfg = {"telegram_token": "token", "telegram_chat_id": "123"}
        bootstrap = {"elements": [
            {"id": 1, "web_name": "Keluar", "status": "a"},
            {"id": 2, "web_name": "Masuk", "status": "a"},
        ]}

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "keputusan.json"
            with patch("keputusan_transfer.requests.get", return_value=Respons(update)), patch(
                "keputusan_transfer.requests.post", return_value=Respons({"ok": True})
            ) as jawab:
                hasil = keputusan.proses_callback(cfg, bootstrap, path, gw_aktif=4)
            state = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(hasil, [])
        self.assertEqual(state["keputusan"], [])
        self.assertIn("lama", jawab.call_args.kwargs["json"]["text"].lower())

    def test_persetujuan_pemain_yang_kini_cedera_dibatalkan(self):
        update = {
            "result": [{
                "update_id": 30,
                "callback_query": {
                    "id": "cb-injury", "data": "fpl2|a|4|1|2",
                    "message": {"chat": {"id": 123}},
                },
            }],
        }
        cfg = {"telegram_token": "token", "telegram_chat_id": "123"}
        bootstrap = {"elements": [
            {"id": 1, "web_name": "Keluar", "status": "a"},
            {"id": 2, "web_name": "Masuk", "status": "i",
             "chance_of_playing_next_round": 0},
        ]}

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "keputusan.json"
            keputusan.catat_penawaran(pd.DataFrame([{
                "Keluar": "Keluar", "Masuk": "Masuk", "_keluar_id": 1,
                "_masuk_id": 2, "Keputusan": "LAYAK", "Kesiapan": "HIJAU",
            }]), 4, dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2), path)
            with patch("keputusan_transfer.requests.get", return_value=Respons(update)), patch(
                "keputusan_transfer.requests.post", return_value=Respons({"ok": True})
            ):
                hasil = keputusan.proses_callback(cfg, bootstrap, path, gw_aktif=4)
            state = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(hasil, [])
        self.assertEqual(state["keputusan"], [])

    def test_keyboard_tidak_menawarkan_opsi_merah_atau_tahan(self):
        transfer = pd.DataFrame([
            {"Keluar": "A", "Masuk": "B", "_keluar_id": 1, "_masuk_id": 2,
             "Keputusan": "LAYAK", "Kesiapan": "MERAH"},
            {"Keluar": "C", "Masuk": "D", "_keluar_id": 3, "_masuk_id": 4,
             "Keputusan": "TAHAN", "Kesiapan": "KUNING"},
        ])

        self.assertIsNone(keputusan.keyboard(transfer, 4))


if __name__ == "__main__":
    unittest.main()
