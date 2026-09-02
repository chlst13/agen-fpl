import json
import sys
import tempfile
import unittest
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
                    "data": "fpl|a|4|1|2",
                    "from": {"username": "om"},
                    "message": {"chat": {"id": 123}},
                },
            }],
        }
        bootstrap = {"elements": [
            {"id": 1, "web_name": "Keluar"}, {"id": 2, "web_name": "Masuk"}
        ]}
        cfg = {"telegram_token": "token", "telegram_chat_id": "123"}

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "keputusan.json"
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


if __name__ == "__main__":
    unittest.main()
