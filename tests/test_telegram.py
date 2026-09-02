import unittest
import sys
from unittest.mock import Mock, patch

# Unit test ini tidak melakukan jaringan; sediakan stub jika dependency belum
# dipasang pada mesin pengembang. Di GitHub Actions requests tetap dipasang.
sys.modules.setdefault("requests", Mock())

import agen_fpl


class TestTelegram(unittest.TestCase):
    def test_mode_satu_pesan_hanya_memanggil_telegram_sekali(self):
        cfg = {"telegram_token": "token", "telegram_chat_id": "123"}
        respons = Mock(status_code=200, text="ok")
        pesan = "Judul\n" + "\n".join(f"Baris analisis {i}: " + "x" * 80 for i in range(150))

        with patch("agen_fpl.requests.post", return_value=respons) as post:
            berhasil = agen_fpl.kirim_telegram(cfg, pesan, satu_pesan=True)

        self.assertTrue(berhasil)
        self.assertEqual(post.call_count, 1)
        teks = post.call_args.kwargs["json"]["text"]
        self.assertLessEqual(len(teks), agen_fpl.BATAS_RINGKASAN)
        self.assertIn("laporan HTML/Excel", teks)


if __name__ == "__main__":
    unittest.main()
