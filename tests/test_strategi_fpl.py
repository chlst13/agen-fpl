import unittest

import pandas as pd

import strategi_fpl as strategi


class TestStrategiFPL(unittest.TestCase):
    def test_proyeksi_mengenali_double_dan_blank_gameweek(self):
        pemain = pd.DataFrame([{
            "_id": 1, "_klub": 1, "Nama": "Alpha", "Klub": "AAA", "Pos": "MID",
            "Harga": 7.0, "PPG": 5.0, "Form": 6.0, "xGI/90": 0.5,
            "Keandalan": 90, "Siap": True, "Bola Mati": "penalti",
        }])
        fixtures = [
            {"event": 4, "team_h": 1, "team_a": 2,
             "team_h_difficulty": 2, "team_a_difficulty": 4},
            {"event": 4, "team_h": 3, "team_a": 1,
             "team_h_difficulty": 3, "team_a_difficulty": 2},
        ]

        hasil = strategi.proyeksi_pemain(pemain, fixtures, 4, horizon=2).iloc[0]

        self.assertGreater(hasil["GW4"], 0)
        self.assertEqual(hasil["GW5"], 0)
        self.assertEqual(hasil["Total 2GW"], hasil["GW4"])

    def test_transfer_mematuhi_batas_tiga_pemain_per_klub(self):
        data = [
            {"_id": 1, "_klub": 1, "Nama": "Keluar", "Klub": "AAA", "Pos": "MID",
             "Harga": 7.0, "Siap": True},
            {"_id": 2, "_klub": 2, "Nama": "Rekan 1", "Klub": "BBB", "Pos": "DEF",
             "Harga": 5.0, "Siap": True},
            {"_id": 3, "_klub": 2, "Nama": "Rekan 2", "Klub": "BBB", "Pos": "FWD",
             "Harga": 6.0, "Siap": True},
            {"_id": 4, "_klub": 2, "Nama": "Rekan 3", "Klub": "BBB", "Pos": "GKP",
             "Harga": 4.5, "Siap": True},
            {"_id": 5, "_klub": 2, "Nama": "Kandidat Terlarang", "Klub": "BBB", "Pos": "MID",
             "Harga": 7.5, "Siap": True},
            {"_id": 6, "_klub": 3, "Nama": "Kandidat Aman", "Klub": "CCC", "Pos": "MID",
             "Harga": 7.4, "Siap": True},
        ]
        df = pd.DataFrame(data)
        skuad = df[df["_id"].isin([1, 2, 3, 4])].copy()
        proyeksi = pd.DataFrame([
            {"_id": 1, "GW4": 3, "Total 5GW": 15, "Risiko": "Rendah"},
            {"_id": 2, "GW4": 2, "Total 5GW": 10, "Risiko": "Rendah"},
            {"_id": 3, "GW4": 2, "Total 5GW": 10, "Risiko": "Rendah"},
            {"_id": 4, "GW4": 2, "Total 5GW": 10, "Risiko": "Rendah"},
            {"_id": 5, "GW4": 8, "Total 5GW": 40, "Risiko": "Rendah"},
            {"_id": 6, "GW4": 7, "Total 5GW": 35, "Risiko": "Rendah"},
        ])

        hasil = strategi.analisis_transfer(df, skuad, proyeksi, bank=1.0, horizon=5)

        self.assertNotIn("Kandidat Terlarang", set(hasil["Masuk"]))
        self.assertIn("Kandidat Aman", set(hasil["Masuk"]))


if __name__ == "__main__":
    unittest.main()
