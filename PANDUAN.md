> **Catatan.** Berkas ini adalah referensi teknis: cara kerja rumus, arti
> tiap kolom, dan cara menjalankan bot di komputer sendiri.
>
> **Kalau tujuanmu memasang bot di GitHub tanpa laptop, ikuti
> `PANDUAN-PEMASANGAN.md` saja.** Berkas itu sudah lengkap dan berdiri sendiri.

---

# Agen FPL — panduan pemasangan

Agen ini menarik data resmi FPL, menghitung skor tiap pemain, membedah skuadmu,
lalu membuat proyeksi dan strategi transfer beberapa gameweek. Laporan mendalam
masuk ke HTML/Excel, sedangkan Telegram menerima satu decision brief agar tidak
panjang atau berulang. Sekali dipasang, dia jalan sendiri sesuai jadwal.

---

## 1. Siapkan (sekali saja)

```bash
pip install requests pandas openpyxl
```

Taruh ketiga berkas dalam satu folder, misal `D:\AgenFPL\`:

```
agen_fpl.py
config.json
jalankan.bat
```

## 2. Isi config.json

| Kunci | Isi |
|---|---|
| `entry_id` | ID tim FPL kamu. Buka tim kamu di web FPL, lihat URL: `/entry/1234567/event/1` → angka itulah ID-nya. |
| `jumlah_gw_dipantau` | Berapa GW ke depan yang dipakai menilai jadwal. 5 itu pas. |
| `skuad_manual` | Cadangan kalau API skuad belum bisa dibaca (misal sebelum GW1 dimulai). Isi nama pendek pemain seperti yang tampil di FPL. |
| `telegram_token` | Kosongkan kalau belum mau notifikasi. Cara ambil di bawah. |
| `anthropic_api_key` | Opsional. Tanpa ini agen tetap jalan penuh, hanya tanpa komentar naratif. |
| `ambang_harga` | Sensitivitas sinyal harga. Turunkan ke 0.5 kalau mau lebih banyak peringatan. |
| `horizon_strategi` | Jarak proyeksi 1–8 GW. Bawaan 5 GW. |
| `biaya_hit` | Biaya transfer tambahan untuk simulasi. Bawaan 4 poin. |
| `free_transfers` | Free transfer yang tersedia saat laporan dibuat. Bawaan 1. |

## 3. Uji jalan

```bash
python agen_fpl.py
```

Hasilnya masuk ke folder `laporan/`: satu file HTML (buka di browser) dan satu
file Excel dengan sheet terpisah per posisi.

## 4. Pasang notifikasi Telegram

1. Chat **@BotFather** di Telegram → kirim `/newbot` → salin token yang diberikan.
2. Kirim satu pesan apa saja ke bot barumu.
3. Buka `https://api.telegram.org/bot<TOKEN>/getUpdates` di browser → cari angka di
   bagian `"chat":{"id":...}`.
4. Masukkan keduanya ke `config.json`.

## 5. Buat dia jalan sendiri

**Windows** — Task Scheduler:
1. Buka Task Scheduler → *Create Basic Task* → beri nama "Agen FPL".
2. Trigger: *Daily*, jam **06.00**.
3. Action: *Start a program* → pilih `jalankan.bat`.
4. Setelah selesai, buka properti task → tab *Triggers* → *Edit* → centang
   **Repeat task every 6 hours** supaya harga pemain terpantau menjelang tengah malam.

**Mac / Linux** — cron:
```bash
crontab -e
# tambahkan (jam 6 pagi dan 11 malam):
0 6,23 * * * cd /path/AgenFPL && /usr/bin/python3 agen_fpl.py
```

Laptop harus menyala saat jadwalnya tiba. Kalau mau benar-benar 24 jam tanpa
laptop, script yang sama bisa ditaruh di VPS murah atau GitHub Actions.

---

## Cara membaca skornya

`Skor` adalah gabungan lima hal, bukan ramalan poin:

| Bobot | Komponen | Maksudnya |
|---|---|---|
| 30% | Nilai per harga | form dibagi harga — inti berburu pemain murah produktif |
| 25% | xGI per 90 menit | kualitas peluang, bukan sekadar hasil |
| 20% | Kemudahan jadwal | rata-rata FDR beberapa GW ke depan |
| 15% | Keandalan menit | seberapa konsisten dia main penuh |
| 10% | Poin per laga | rekam jejak keseluruhan |

Skor dikali 0,45 kalau pemain cedera atau meragukan.

Kolom `Tekanan` = transfer masuk bersih dibanding jumlah manajer FPL. Ini
**indikator arah harga, bukan kepastian** — FPL tidak pernah membuka rumus
resminya. Pakai untuk memutuskan "beli sekarang atau tunggu", bukan sebagai jaminan.

Kolom `Laga` menunjukkan berapa kali klub itu bertanding di rentang GW yang
dipantau. Angka di atas normal berarti ada double gameweek — itu sinyal paling
berharga di FPL.

## Mesin strategi Pro

Sheet **Proyeksi Multi GW** menghitung estimasi poin per GW dengan menggabungkan
PPG, form, xGI/90, keandalan menit, ketersediaan, FDR, venue, blank, dan double
gameweek. Sheet **Strategi Transfer** membandingkan pemain keluar dan masuk
dengan budget nyata, posisi yang sama, serta batas maksimal tiga pemain per klub.

Kolom `Gain 5GW` adalah kenaikan proyeksi sebelum hit. `Net jika -4` sudah
mengurangi biaya hit. Gunakan kolom risiko dan berita terakhir sebagai syarat
sebelum mengeksekusi keputusan; proyeksi bukan jaminan poin.

Versi Pro juga membuat:

- **Expected Minutes**: peluang starter, peluang 60+ menit, xMins, dan confidence.
- **Rute Transfer**: optimasi satu atau dua langkah dengan budget, hit, posisi,
  dan batas tiga pemain per klub.
- **Simulasi**: rentang P10–P90 dan peluang transfer menghasilkan gain positif.
- **Starting XI**: formasi legal terbaik, kapten, wakil, dan urutan bench.
- **Chip Planner**: sinyal per GW dari blank/double, kekuatan XI, dan bench.
- **Mini-League Mode**: Proteksi, Seimbang, atau Agresif sesuai jarak rival.
- **Backtest Model**: prediksi GW lalu dibandingkan hasil aktual dan dipakai
  mengalibrasi proyeksi berikutnya.

## Persetujuan transfer semi-otomatis

Laporan Telegram menampilkan tombol untuk maksimal tiga transfer teratas:
**Setujui**, **Tolak**, dan **Tunda**. Klik diproses saat workflow `Pemantau FPL`
berjalan berikutnya (biasanya maksimal 20 menit), kemudian disimpan ke
`keputusan_transfer.json`.

Keputusan Om muncul lagi di laporan Telegram, HTML, dan sheet **Keputusan Om**.
Opsi yang ditolak tidak lagi menjadi prioritas pada GW yang sama. Persetujuan
ini **tidak mengeksekusi transfer ke akun FPL**; eksekusi final tetap dilakukan
di aplikasi FPL agar tidak ada hit, chip, atau transfer permanen tanpa kontrol.

Tombol hanya muncul untuk opsi yang lolos **pagar keputusan**:

- **HIJAU** — gain, expected minutes, confidence, dan risiko memenuhi syarat kuat.
- **KUNING** — masih layak dipertimbangkan, tetapi ada ketidakpastian yang perlu dipantau.
- **MERAH/TAHAN** — tidak ditawarkan untuk disetujui.

Setiap klik diperiksa ulang. Bot menolak tombol dari laporan lama, tombol setelah
deadline, rekomendasi untuk GW yang sudah lewat, atau persetujuan pemain masuk
yang status resminya berubah menjadi cedera/diragukan. Jalankan `Laporan FPL`
lagi untuk memperoleh tombol baru setelah ada perubahan penting.

### Sinkronisasi transfer pra-deadline tanpa login

FPL kadang belum membuka transfer yang baru dilakukan sebelum deadline melalui
endpoint publik. Kirim perintah berikut ke bot Telegram agar skuad sementara
langsung mengikuti aplikasi FPL:

```text
/transfer Davies > Ajayi
/bank 0.5
```

Gunakan `/statusskuad` untuk melihat konfirmasi aktif dan `/batalsync` untuk
menghapusnya. Jika nama pemain ambigu, tambahkan kode klub, misalnya
`/transfer Silva (AAA) > Silva (BBB)`. Perintah hanya diterima dari
`TELEGRAM_CHAT_ID` milik Om dan otomatis tidak berlaku ketika GW berganti.

Perintah diproses oleh jadwal `Pemantau FPL` berikutnya. Setelah bot membalas,
jalankan `Laporan FPL` agar analisis, Starting XI, dan rekomendasi dihitung ulang
dengan skuad serta bank yang sudah disinkronkan.

---

## Batasnya

- Data berasal dari API resmi FPL. Kalau FPL mengubah struktur datanya, script
  perlu disesuaikan.
- Agen mencatat persetujuan semi-otomatis, tetapi tidak login atau mengeksekusi
  transfer ke akun FPL. Keputusan final tetap di tanganmu.
- Komentar AI opsional dan berbayar (pakai API key sendiri). Tanpa itu, seluruh
  analisis tetap berjalan karena semua perhitungan dilakukan lokal.

---

# Pemantau FPL — penjaga menjelang deadline

`agen_fpl.py` menganalisis. `pemantau_fpl.py` **menjaga**. Jalankan tiap 15 menit;
dia diam kalau tidak ada apa-apa, dan berteriak begitu ada yang berubah.

## Yang dia tangkap

| Kejadian | Terdeteksi? | Sumber |
|---|---|---|
| Cedera baru muncul di FPL | ✅ dalam ≤15 menit | status & `news` resmi FPL |
| Peluang main turun (75% → 25%) | ✅ | `chance_of_playing_next_round` |
| Pemain dinyatakan pulih | ✅ | perubahan status ke fit |
| Kartu merah / sanksi | ✅ | status `s` |
| Harga naik/turun | ✅ | `now_cost` |
| Tren menit bermain anjlok | ✅ | riwayat laga per pemain |
| **Susunan pemain resmi** | ❌ | baru terbit 1 jam sebelum kickoff — setelah deadline |
| **"Kata pelatih di konferensi pers"** | ⚠️ sebagian | perlu API key, hasilnya rumor |

Pemain di skuadmu selalu dilaporkan. Pemain lain hanya kalau kepemilikannya
di atas 5% — supaya notifikasi tidak jadi sampah.

## Soal "bakal dicadangkan atau tidak" — batas jujurnya

Tidak ada sistem mana pun yang bisa memastikan ini sebelum deadline. Susunan
pemain resmi baru terbit **satu jam sebelum kickoff**, sementara deadline FPL
jatuh **1,5 jam sebelum laga pertama**. Jadi secara struktural, informasinya
memang belum ada saat kamu harus memutuskan.

Yang bisa dilakukan pemantau ini adalah mendekatinya dari dua arah:

1. **Fakta menit bermain** — riwayat 5 laga terakhir diklasifikasi jadi
   `aman (nailed)` / `hampir aman` / `dirotasi` / `menit anjlok` / `cadangan`.
   Pemain dengan pola 90-90-85-20-15 langsung ditandai *menit anjlok* walaupun
   rata-ratanya masih terlihat bagus. Ini data historis, bukan tebakan.
2. **Pantauan berita** — menjelang deadline (< 8 jam), agen menelusuri berita
   48 jam terakhir untuk pemain bermasalah di skuadmu. Hasilnya selalu diberi
   label RESMI / RUMOR / TIDAK ADA BERITA. Butuh `anthropic_api_key`, dan
   perlakukan sebagai petunjuk — bukan kepastian.

Rotasi karena laga tengah pekan Eropa juga tidak ada di API FPL. Kalau klubmu
main Rabu lalu Sabtu, naikkan sendiri kecurigaannya.

## Pasang

```bash
python pemantau_fpl.py     # jalankan sekali untuk membuat snapshot awal
python pemantau_fpl.py     # jalankan lagi — mulai dari sini dia membandingkan
```

Eksekusi pertama tidak mengirim apa-apa karena belum ada pembanding. Itu normal.

**Windows** — Task Scheduler, task baru:
- Trigger: *Daily* jam 07.00, lalu edit trigger → **Repeat every 15 minutes**,
  duration *Indefinitely*.
- Action: `pantau.bat`
- Centang *Run whether user is logged on or not* dan *Hidden* supaya tidak
  memunculkan jendela hitam tiap 15 menit.

**Mac / Linux** — cron:
```bash
*/15 * * * * cd /path/AgenFPL && /usr/bin/python3 pemantau_fpl.py
```

## Tambahan

`config.json` punya kunci `pantau_tambahan` — isi nama pemain incaranmu yang
belum masuk skuad, misalnya `["Saka", "Isak"]`. Mereka akan dipantau seketat
pemain milikmu sendiri.

Berkas `state_pantau.json` dibuat otomatis dan menyimpan kondisi terakhir.
Hapus berkas itu kalau mau memulai pemantauan dari nol.

---

# Jalan tanpa laptop — GitHub Actions

Seluruh bot dipindah ke server GitHub. Laptop dan HP boleh mati; bot tetap
bekerja dan mengirim Telegram. Gratis.

## Langkah pemasangan

**1. Buat repo baru** di github.com — pilih **Public**.

> Kenapa public? Menit Actions untuk repo public tidak dibatasi. Repo private
> hanya dapat 2.000 menit/bulan — tidak cukup untuk pemantauan tiap 20 menit.
> Token kamu tetap aman karena disimpan di Secrets, bukan di dalam kode.
> Kalau tetap ingin private, ubah jadwal di `pantau.yml` menjadi `"0,30 * * * *"`.

**2. Unggah berkas ini** ke repo (drag & drop lewat browser juga bisa):

```
agen_fpl.py
pemantau_fpl.py
requirements.txt
.gitignore
.github/workflows/pantau.yml
.github/workflows/laporan.yml
```

Jangan unggah `config.json` — isinya digantikan Secrets.

**3. Isi Secrets** — repo → *Settings* → *Secrets and variables* → *Actions* →
tab **Secrets** → *New repository secret*:

| Nama | Isi |
|---|---|
| `TELEGRAM_TOKEN` | token dari @BotFather |
| `TELEGRAM_CHAT_ID` | chat id kamu |
| `FPL_ENTRY_ID` | ID tim FPL |
| `ANTHROPIC_API_KEY` | opsional, hanya kalau mau pantauan berita |

**4. Isi Variables** — tab **Variables** di halaman yang sama:

| Nama | Contoh isi |
|---|---|
| `FPL_SKUAD_MANUAL` | `Haaland, B.Fernandes, Calvert-Lewin, Calafiori` |
| `FPL_PANTAU_TAMBAHAN` | `Saka, Isak` |
| `FPL_PAKAI_AI` | `ya` atau `tidak` |
| `FPL_BANK` | `1.5` |
| `FPL_HORIZON_STRATEGI` | `5` |
| `FPL_BIAYA_HIT` | `4` |
| `FPL_FREE_TRANSFERS` | `1` |

Bedanya: Secrets disembunyikan dari log, Variables tidak. Jadi token wajib di
Secrets, daftar pemain boleh di Variables.

**5. Uji jalan** — tab *Actions* → pilih **Pemantau FPL** → *Run workflow*.
Eksekusi pertama hanya membuat snapshot. Jalankan sekali lagi, lalu Telegram
mulai aktif.

## Jadwalnya

| Workflow | Kapan |
|---|---|
| Pemantau FPL | tiap 20 menit, sepanjang hari |
| Laporan FPL | tiap hari 06.00 WIB, plus Jumat 10.00 WIB jelang deadline |

Laporan HTML dan Excel dikirim langsung sebagai file ke Telegram — buka di HP,
tidak perlu komputer sama sekali. Salinannya juga tersimpan 14 hari di tab
*Actions* → *Artifacts*.

## Yang perlu kamu tahu sebelum bergantung padanya

- **Cron GitHub tidak tepat waktu.** Jadwal `*/20` bisa molor 5–20 menit saat
  server GitHub ramai, kadang lebih. Untuk memantau cedera ini masih memadai,
  tapi jangan pakai untuk keputusan yang butuh presisi detik menjelang deadline.
  Sepuluh menit terakhir sebelum deadline, cek manual.
- **Workflow terjadwal otomatis dimatikan** setelah repo 60 hari tanpa aktivitas.
  Pemantau ini menyimpan state lewat commit tiap ada perubahan, jadi repo tetap
  aktif dengan sendirinya. Tapi kalau musim libur panjang, cek lagi saat musim
  dimulai.
- **State disimpan sebagai commit.** Riwayat commit akan panjang. Itu wajar,
  bukan tanda ada yang rusak.
- **Jangan pernah menaruh token di dalam kode** lalu di-push ke repo public.
  Kalau terlanjur, cabut token itu di @BotFather dan buat yang baru — menghapus
  commit saja tidak cukup.

## Alternatif kalau tidak mau pakai GitHub

| Cara | Biaya | Catatan |
|---|---|---|
| HP Android bekas + Termux | gratis | HP harus menyala & terhubung Wi-Fi; paling sederhana kalau ada HP nganggur |
| VPS kecil (Biznet, Contabo, Hetzner) | ±Rp 40–70rb/bln | paling andal, cron presisi, tanpa batas menit |
| Railway / Render | ada tier gratis terbatas | mudah, tapi kuota gratisnya sering berubah |
