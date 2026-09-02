import datetime as dt
import sys
import unittest
from unittest.mock import Mock

sys.modules.setdefault("requests", Mock())

import berita


class TestBerita(unittest.TestCase):
    def test_berita_resmi_menyertakan_estimasi_menit_dan_confidence(self):
        bootstrap = {
            "teams": [{"id": 1, "short_name": "AAA"}],
            "element_types": [{"id": 3, "singular_name_short": "MID"}],
            "elements": [{
                "id": 10, "web_name": "Pemain", "team": 1, "element_type": 3,
                "now_cost": 75, "selected_by_percent": "12.5", "status": "d",
                "chance_of_playing_next_round": 25, "news": "Hamstring injury",
                "news_added": dt.datetime.now(dt.timezone.utc).isoformat(),
            }],
        }

        hasil = berita.kumpulkan_berita(bootstrap, ids_skuad=[10])

        self.assertEqual(len(hasil), 1)
        self.assertEqual(hasil[0]["sumber"], "FPL resmi")
        self.assertIn("0–30", hasil[0]["estimasi_menit"])
        self.assertIn("Tinggi", hasil[0]["confidence"])


if __name__ == "__main__":
    unittest.main()
