import unittest
import sys
from unittest.mock import Mock, patch

# Unit test ini tidak melakukan jaringan; sediakan stub jika dependency belum
# dipasang pada mesin pengembang. Di GitHub Actions requests tetap dipasang.
sys.modules.setdefault("requests", Mock())

import agen_fpl


class FakeRequestException(Exception):
    pass


class FakeReadTimeout(FakeRequestException):
    pass


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

    def test_koneksi_gagal_dicoba_lagi_lalu_berhasil(self):
        cfg = {"telegram_token": "token", "telegram_chat_id": "123"}
        respons = Mock(status_code=200, text="ok")

        with patch(
            "agen_fpl.requests.post",
            side_effect=[FakeRequestException("putus"), respons],
        ) as post, patch.object(
            agen_fpl.requests, "RequestException", FakeRequestException
        ), patch.object(
            agen_fpl.requests, "ReadTimeout", FakeReadTimeout
        ), patch("agen_fpl.time.sleep") as tidur:
            berhasil = agen_fpl.kirim_telegram(cfg, "Laporan", satu_pesan=True)

        self.assertTrue(berhasil)
        self.assertEqual(post.call_count, 2)
        tidur.assert_called_once_with(agen_fpl.JEDA_RETRY_TELEGRAM)

    def test_read_timeout_tidak_diulang_agar_tidak_duplikat(self):
        cfg = {"telegram_token": "token", "telegram_chat_id": "123"}

        with patch(
            "agen_fpl.requests.post",
            side_effect=FakeReadTimeout("terlambat"),
        ) as post, patch.object(
            agen_fpl.requests, "RequestException", FakeRequestException
        ), patch.object(
            agen_fpl.requests, "ReadTimeout", FakeReadTimeout
        ), patch("agen_fpl.time.sleep") as tidur:
            berhasil = agen_fpl.kirim_telegram(cfg, "Laporan", satu_pesan=True)

        self.assertFalse(berhasil)
        self.assertEqual(post.call_count, 1)
        tidur.assert_not_called()

    def test_error_server_dicoba_tiga_kali(self):
        cfg = {"telegram_token": "token", "telegram_chat_id": "123"}
        respons = Mock(status_code=503, text="service unavailable")

        with patch("agen_fpl.requests.post", return_value=respons) as post, patch(
            "agen_fpl.time.sleep"
        ) as tidur:
            berhasil = agen_fpl.kirim_telegram(cfg, "Laporan", satu_pesan=True)

        self.assertFalse(berhasil)
        self.assertEqual(post.call_count, agen_fpl.PERCOBAAN_TELEGRAM)
        self.assertEqual(tidur.call_count, agen_fpl.PERCOBAAN_TELEGRAM - 1)

    def test_tombol_keputusan_dikirim_sebagai_reply_markup(self):
        cfg = {"telegram_token": "token", "telegram_chat_id": "123"}
        respons = Mock(status_code=200, text="ok")
        tombol = {"inline_keyboard": [[{"text": "Setujui", "callback_data": "fpl|a|4|1|2"}]]}

        with patch("agen_fpl.requests.post", return_value=respons) as post:
            berhasil = agen_fpl.kirim_telegram(
                cfg, "Laporan", satu_pesan=True, reply_markup=tombol)

        self.assertTrue(berhasil)
        self.assertEqual(post.call_args.kwargs["json"]["reply_markup"], tombol)


if __name__ == "__main__":
    unittest.main()
