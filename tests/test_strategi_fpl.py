import unittest
import tempfile
from pathlib import Path

import pandas as pd

import strategi_fpl as strategi


class TestStrategiFPL(unittest.TestCase):
    def test_expected_minutes_membedakan_pemain_nagil_dan_rotasi(self):
        pemain = pd.DataFrame([
            {"_id": 1, "Nama": "Aman", "Klub": "AAA", "Pos": "MID", "Menit": 710,
             "Starts": 8, "GW Selesai": 8, "Peluang": 100, "Status": "a",
             "Siap": True, "Kabar": ""},
            {"_id": 2, "Nama": "Rotasi", "Klub": "BBB", "Pos": "MID", "Menit": 190,
             "Starts": 2, "GW Selesai": 8, "Peluang": 100, "Status": "a",
             "Siap": True, "Kabar": ""},
        ])

        hasil = strategi.expected_minutes(pemain).set_index("Nama")

        self.assertGreater(hasil.loc["Aman", "xMins"], 75)
        self.assertLess(hasil.loc["Rotasi", "xMins"], 40)
        self.assertGreater(
            hasil.loc["Aman", "Peluang Starter%"],
            hasil.loc["Rotasi", "Peluang Starter%"],
        )

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

    def test_pagar_keputusan_hanya_hijau_untuk_opsi_berkualitas(self):
        df = pd.DataFrame([
            {"_id": 1, "_klub": 1, "Nama": "Keluar", "Klub": "AAA",
             "Pos": "MID", "Harga": 7.0, "Siap": True},
            {"_id": 2, "_klub": 2, "Nama": "Aman", "Klub": "BBB",
             "Pos": "MID", "Harga": 7.0, "Siap": True},
            {"_id": 3, "_klub": 3, "Nama": "Rotasi", "Klub": "CCC",
             "Pos": "MID", "Harga": 7.0, "Siap": True},
        ])
        skuad = df[df["_id"] == 1]
        proyeksi = pd.DataFrame([
            {"_id": 1, "GW4": 2, "Total 5GW": 10, "Risiko": "Rendah",
             "xMins": 80, "Confidence%": 90},
            {"_id": 2, "GW4": 6, "Total 5GW": 30, "Risiko": "Rendah",
             "xMins": 78, "Confidence%": 88},
            {"_id": 3, "GW4": 7, "Total 5GW": 32, "Risiko": "Tinggi",
             "xMins": 35, "Confidence%": 45},
        ])

        hasil = strategi.analisis_transfer(df, skuad, proyeksi, bank=0, horizon=5)
        status = hasil.set_index("Masuk")["Kesiapan"].to_dict()

        self.assertEqual(status["Aman"], "HIJAU")
        self.assertEqual(status["Rotasi"], "MERAH")

    def test_lineup_selalu_memiliki_formasi_legal(self):
        posisi = ["GKP", "GKP"] + ["DEF"] * 5 + ["MID"] * 5 + ["FWD"] * 3
        skuad = pd.DataFrame([
            {"_id": i + 1, "Nama": f"P{i+1}", "Klub": "AAA", "Pos": pos,
             "Form": 5, "xGI/90": 0.3}
            for i, pos in enumerate(posisi)
        ])
        proyeksi = pd.DataFrame([
            {"_id": i + 1, "GW4": float(20 - i), "xMins": 80, "Risiko": "Rendah",
             "Confidence%": 90}
            for i in range(15)
        ])

        hasil = strategi.optimasi_lineup(skuad, proyeksi, 4)
        starter = pd.DataFrame(hasil["starter"])

        self.assertEqual(len(starter), 11)
        self.assertEqual((starter["Pos"] == "GKP").sum(), 1)
        self.assertGreaterEqual((starter["Pos"] == "DEF").sum(), 3)
        self.assertGreaterEqual((starter["Pos"] == "MID").sum(), 2)
        self.assertGreaterEqual((starter["Pos"] == "FWD").sum(), 1)
        self.assertEqual(len(hasil["bench"]), 4)

    def test_simulasi_transfer_deterministik(self):
        transfer = pd.DataFrame([{
            "Keluar": "A", "Masuk": "B", "Gain 5GW": 6.0, "Risiko Masuk": "Sedang"
        }])

        satu = strategi.simulasi_transfer(transfer, horizon=5, jumlah=300, seed=7)
        dua = strategi.simulasi_transfer(transfer, horizon=5, jumlah=300, seed=7)

        pd.testing.assert_frame_equal(satu, dua)
        self.assertGreater(satu.iloc[0]["Peluang Untung%"], 50)

    def test_keputusan_om_menaikkan_setuju_dan_menurunkan_tolak(self):
        transfer = pd.DataFrame([
            {"Keluar": "A", "Masuk": "B", "Gain 5GW": 9.0,
             "_keluar_id": 1, "_masuk_id": 2},
            {"Keluar": "C", "Masuk": "D", "Gain 5GW": 5.0,
             "_keluar_id": 3, "_masuk_id": 4},
        ])
        keputusan = [
            {"gw": 4, "keluar_id": 1, "masuk_id": 2, "status": "DITOLAK"},
            {"gw": 4, "keluar_id": 3, "masuk_id": 4, "status": "DISETUJUI"},
        ]

        hasil = strategi.terapkan_keputusan(transfer, keputusan, 4)

        self.assertEqual(hasil.iloc[0]["Status Om"], "DISETUJUI")
        self.assertEqual(hasil.iloc[-1]["Status Om"], "DITOLAK")

    def test_backtest_mengkalibrasi_prediksi_gw_berikutnya(self):
        pemain = pd.DataFrame([
            {"_id": i, "Poin": 10.0} for i in range(1, 21)
        ])
        prediksi_1 = pd.DataFrame([
            {"_id": i, "GW1": 4.0, "Total 1GW": 4.0, "Rata-rata": 4.0}
            for i in range(1, 21)
        ])
        prediksi_2 = pd.DataFrame([
            {"_id": i, "GW2": 4.0, "Total 1GW": 4.0, "Rata-rata": 4.0}
            for i in range(1, 21)
        ])

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            strategi.kalibrasi_proyeksi(pemain, prediksi_1, 1, path)
            pemain["Poin"] = 15.0
            _, hasil = strategi.kalibrasi_proyeksi(pemain, prediksi_2, 2, path)

        self.assertIsNotNone(hasil["Evaluasi Terakhir"])
        self.assertGreater(hasil["Faktor"], 1.0)


if __name__ == "__main__":
    unittest.main()
