# Memasang Agen FPL di GitHub — panduan lengkap

> **Versi final.** Panduan ini menggantikan semua versi sebelumnya. Cukup ikuti
> berkas ini saja. `PANDUAN.md` hanya referensi teknis — dibutuhkan nanti kalau
> suatu hari kamu ingin menjalankannya di komputer sendiri.

Setelah selesai, bot bekerja sendiri di server GitHub. Laptop boleh mati, HP
boleh di saku. Notifikasi tetap masuk Telegram.

**Waktu:** sekitar 45 menit, sekali seumur hidup.
**Biaya:** nol.
**Yang dibutuhkan:** browser di komputer, dan Telegram di HP.

Kerjakan berurutan. Jangan lompat bagian.

---

# BAGIAN 1 — Kumpulkan 3 nomor penting

Siapkan Notepad untuk menampung sementara.

## 1.1 — ID tim FPL

1. Buka **fantasy.premierleague.com**, login.
2. Klik menu **Points** (atau **Pick Team**).
3. Lihat alamat di kolom URL browser:

   `https://fantasy.premierleague.com/entry/`**`4823917`**`/event/1`

4. Angka di antara `/entry/` dan `/event/` itulah ID kamu. Catat sebagai
   **FPL_ENTRY_ID**.

> Angka ini bukan rahasia — ID tim FPL memang publik.

## 1.2 — Token bot Telegram

1. Di Telegram, cari **@BotFather** (yang bercentang biru), tekan **START**.
2. Kirim: `/newbot`
3. Nama bot — bebas, misalnya: `Agen FPL Saya`
4. Username bot — **harus diakhiri kata `bot`** dan harus unik. Coba
   `cholist_fpl_agen_bot`. Kalau ditolak, tambahkan angka.
5. BotFather membalas dengan baris:

   `Use this token to access the HTTP API:`
   `8134729581:AAF9k2mQx7vLpR3nZ8wYtB6cDeFgHiJkLmN`

6. Salin **seluruh baris token** (termasuk angka sebelum titik dua). Catat
   sebagai **TELEGRAM_TOKEN**.

> ⚠️ **Rahasia.** Siapa pun yang punya token ini bisa mengendalikan botmu.
> Jangan dikirim ke siapa pun, jangan difoto, jangan ditulis di dalam kode.

## 1.3 — Chat ID

1. Cari username bot barumu di Telegram, buka, tekan **START**.
2. Kirim pesan apa saja, misalnya `halo`.
3. Di browser komputer, buka alamat ini — **ganti `TOKEN_KAMU`** dengan token
   dari langkah 1.2:

   `https://api.telegram.org/botTOKEN_KAMU/getUpdates`

   Contoh jadinya:
   `https://api.telegram.org/bot8134729581:AAF9k2mQ.../getUpdates`

   Perhatikan: kata `bot` menempel langsung dengan token, tanpa spasi.

4. Cari bagian yang tertulis:

   `"chat":{"id":`**`729184563`**`,"first_name":...`

5. Angka setelah `"id":` itulah chat ID. Catat sebagai **TELEGRAM_CHAT_ID**.

**Kalau halamannya kosong** (`{"ok":true,"result":[]}`), pesanmu belum sampai
ke bot. Ulangi langkah 1–2, tunggu 10 detik, muat ulang halaman.

✅ **Cek:** Notepad sekarang berisi tiga baris.

---

# BAGIAN 2 — Berkas yang perlu diunggah

## Yang DIUNGGAH — berkas aplikasi

```
agen_fpl.py
pemantau_fpl.py
fitur_lanjutan.py
laporan_gw.py
berita.py
strategi_fpl.py
requirements.txt
.gitignore
.github/workflows/pantau.yml
.github/workflows/laporan.yml
.github/workflows/tests.yml
```

## Yang TIDAK diunggah

| Berkas | Kenapa tidak |
|---|---|
| `config.json` | **Tidak dipakai di GitHub.** Fungsinya digantikan Secrets dan Variables. Berkas ini hanya perlu kalau menjalankan di komputer sendiri. |
| `jalankan.bat`, `pantau.bat` | Hanya untuk Windows. Di GitHub tidak berguna. |
| `PANDUAN.md`, `PANDUAN-PEMASANGAN.md` | Dokumen untuk kamu, bukan untuk bot. |

Kalau ketiganya terlanjur terunggah, tidak apa-apa — tidak merusak apa pun.
Tapi `config.json` sebaiknya memang jangan, supaya tidak ada kebiasaan menaruh
token di dalam berkas.

## Siapkan di komputer

Buat folder `AgenFPL` di Desktop, susun seperti ini:

```
AgenFPL/
├── agen_fpl.py
├── pemantau_fpl.py
├── fitur_lanjutan.py
├── laporan_gw.py
├── berita.py
├── strategi_fpl.py
├── requirements.txt
├── .gitignore
└── .github/
    └── workflows/
        ├── pantau.yml
        ├── laporan.yml
        └── tests.yml
```

**Windows sering menolak membuat folder berawalan titik.** Akalinya: ketik nama
foldernya sebagai **`.github.`** — dengan titik di depan **dan** di belakang.
Windows otomatis membuang titik terakhir.

Kalau tetap gagal, lewati saja — Cara B di Bagian 4 tidak butuh folder ini.

---

# BAGIAN 3 — Akun dan repo GitHub

## 3.1 — Daftar

1. Buka **github.com** → **Sign up**.
2. Pakai **email pribadi**, bukan email kantor.
3. Pilih paket **Free**.
4. Verifikasi lewat email.

## 3.2 — Buat repo

1. Klik **+** di pojok kanan atas → **New repository**.
2. Isi:
   - **Repository name:** `agen-fpl`
   - Pilih **Public**
   - **Jangan** centang "Add a README file"
3. Klik **Create repository**.

> **Kenapa Public?** Repo public dapat menit pemrosesan tak terbatas; repo
> private hanya 2.000 menit/bulan. Bot ini jalan tiap 20 menit — sebulan butuh
> sekitar 2.100 menit, tidak muat di kuota private.
>
> Public berarti **kodenya** terlihat orang. Token dan ID kamu **tidak**, karena
> disimpan terpisah di Secrets. Isi kodenya pun bukan rahasia — cuma rumus
> penilaian pemain FPL.
>
> Kalau tetap ingin private: buka `pantau.yml`, ganti baris jadwal menjadi
> `- cron: "0,30 * * * *"`. Bot jadi mengecek tiap 30 menit, muat di kuota gratis.

---

# BAGIAN 4 — Unggah berkasnya

Coba Cara A dulu.

## Cara A — Seret dan lepas

1. Di halaman repo baru, klik tautan **uploading an existing file**.
2. Buka folder `AgenFPL`, blok semua isinya (Ctrl+A).
3. Seret ke area putih di halaman GitHub.
4. **Pastikan `.github/workflows/pantau.yml` dan `laporan.yml` ikut muncul** di
   daftar berkas.
5. Gulir ke bawah → **Commit changes**.

Kalau kedua berkas `.yml` tidak muncul, pakai Cara B untuk keduanya.

## Cara B — Ketik manual (selalu berhasil)

1. Klik **Add file** → **Create new file**.
2. Di kolom nama berkas paling atas, ketik persis:

   ```
   .github/workflows/pantau.yml
   ```

   Begitu kamu mengetik `/`, GitHub otomatis membuat foldernya. Tidak perlu
   dibuat lebih dulu.

3. Buka `pantau.yml` di komputer dengan **Notepad**, blok semua (Ctrl+A),
   salin (Ctrl+C).
4. Tempel (Ctrl+V) ke kotak besar di GitHub.
5. **Commit changes** → **Commit changes**.
6. Ulangi untuk `.github/workflows/laporan.yml`.
7. Ulangi juga untuk berkas lain yang belum terunggah — untuk yang ini nama
   berkasnya ditulis polos, tanpa garis miring.

✅ **Cek:** halaman utama repo menampilkan folder `.github` dan tiga berkas
lain. Klik `.github` → `workflows` → harus ada dua berkas `.yml`.

---

# BAGIAN 5 — Masukkan kredensial

## 5.1 — Secrets (rahasia)

1. Di repo, klik tab **Settings**.
2. Menu kiri → **Secrets and variables** → **Actions**.
3. Klik **New repository secret**. Tambahkan satu per satu.
   **Nama harus persis sama, huruf besar semua:**

   | Name | Secret |
   |---|---|
   | `TELEGRAM_TOKEN` | token dari 1.2 |
   | `TELEGRAM_CHAT_ID` | angka dari 1.3 |
   | `FPL_ENTRY_ID` | angka dari 1.1 |

> Setelah disimpan, isinya tidak bisa dilihat lagi — bahkan olehmu. Itu memang
> disengaja. Kalau lupa, buat ulang dan timpa.

## 5.2 — Variables (tidak rahasia)

Klik tab **Variables** di halaman yang sama → **New repository variable**.

| Name | Value | Wajib? |
|---|---|---|
| `FPL_SKUAD_MANUAL` | `Haaland, B.Fernandes, Calvert-Lewin, Calafiori` | cadangan |
| `FPL_BANK` | `0` | opsional |
| `FPL_PAKAI_AI` | `tidak` | opsional |
| `FPL_PANTAU_TAMBAHAN` | `Saka, Isak` | opsional |
| `FPL_TAHAP_LAPORAN` | `24,3,1` | opsional |
| `FPL_LIGA_ID` | ID liga mini | opsional |
| `FPL_HORIZON_STRATEGI` | `5` | opsional, proyeksi 1–8 GW |
| `FPL_BIAYA_HIT` | `4` | opsional, biaya simulasi transfer tambahan |

**`FPL_TAHAP_LAPORAN`** menentukan kapan pengingat deadline dikirim. `24,3,1`
berarti 1 hari, 3 jam, dan 1 jam sebelum deadline. Ubah sesukamu — misalnya
`48,12,2`.

**`FPL_LIGA_ID`** diambil dari URL liga mini: FPL → **Leagues** → klik nama
liga → lihat `https://fantasy.premierleague.com/leagues/`**`843217`**`/standings/c`.
Kalau tidak ikut liga mini, lewati saja.

### Penting: kamu TIDAK perlu mengedit `FPL_SKUAD_MANUAL` tiap transfer

Selama `FPL_ENTRY_ID` benar, bot membaca skuad langsung dari akun FPL-mu —
**termasuk transfer yang baru saja kamu lakukan untuk gameweek berikutnya.**
Isi daftar ini sekali, lalu lupakan.

Daftar manual hanya terpakai dalam dua keadaan: sebelum GW1 dimulai, atau saat
server FPL sedang menolak permintaan.

Cara memastikannya: buka log di tab Actions, cari baris `→ Skuad dibaca dari:`.
Kalau tertulis **akun FPL**, daftar manual sedang diabaikan — itu yang kita mau.
Keterangan yang sama muncul di header laporan HTML.

`FPL_PAKAI_AI` isi `tidak` dulu. Fitur itu berbayar dan butuh API key sendiri;
tanpa itu seluruh analisis tetap jalan penuh.

---

# BAGIAN 6 — Nyalakan

## 6.1 — Uji laporan

1. Klik tab **Actions**.
2. Kalau muncul tombol **I understand my workflows, go ahead and enable them**,
   klik.
3. Daftar kiri → **Laporan FPL** → tombol **Run workflow** → **Run workflow**.
4. Tunggu 1–3 menit sampai muncul **centang hijau**.
5. **Cek Telegram.** Harus masuk ringkasan + dua berkas: laporan HTML dan Excel.

Kalau silang merah, lompat ke Bagian 9.

## 6.2 — Nyalakan pemantau

1. Actions → **Pemantau FPL** → **Run workflow**.
2. Tunggu centang hijau. **Telegram tidak berbunyi.** Ini normal — eksekusi
   pertama hanya memotret kondisi awal, belum ada pembanding.
3. **Klik Run workflow sekali lagi.** Sekarang bot sudah punya pembanding.

Mulai sekarang GitHub menjalankannya sendiri. Kamu tidak perlu melakukan apa pun
lagi.

> Jadwal otomatis kadang baru mulai berjalan 15–60 menit setelah dinyalakan.
> Kalau setelah 2 jam tab Actions masih sepi, jalankan sekali manual — itu
> biasanya "membangunkan" penjadwalnya.

---

# BAGIAN 7 — Cara kerjanya sehari-hari

| Kapan | Isi |
|---|---|
| Tiap 20 menit, **hanya kalau ada perubahan** | cedera baru, pemain pulih, peluang main berubah, harga bergerak |
| Tiap pagi 06.00 WIB | satu ringkasan Telegram + strategi multi-GW + berkas HTML & Excel |
| **1 hari sebelum deadline** | laporan lengkap + saran chip |
| **3 jam sebelum deadline** | laporan + risiko rotasi + pemeriksaan skuad |
| **1 jam sebelum deadline** | pengingat terakhir, kondisi paling mutakhir |
| **Begitu gameweek rampung** | pembedahan: poinmu, skor pertandingan, analisis mendalam |

## Deadline dibaca otomatis, bukan hari tetap

Deadline FPL berpindah-pindah — kadang Jumat dini hari, kadang Sabtu sore,
kadang Selasa untuk gameweek tengah pekan. Bot membaca jadwal aslinya dari
FPL tiap 20 menit dan menghitung mundur sendiri. **Kamu tidak perlu mengatur
apa pun saat jadwalnya berubah.**

Tiap tahap hanya dikirim sekali per gameweek, dan catatannya otomatis kedaluwarsa
begitu masuk gameweek berikutnya.

## Skuad dibaca otomatis, termasuk transfer terbaru

Kalau Rabu kamu jual seseorang dan beli penggantinya untuk gameweek berikutnya,
bot langsung memindahkan pantauannya ke pemain yang baru — tanpa kamu ubah apa
pun.

## Yang tetap perlu kamu urus sendiri

- **`FPL_BANK`** — nilai bank dibaca otomatis dari FPL, tapi baru diperbarui
  setelah deadline lewat. Kalau ingin rekomendasi transfer di tengah pekan
  akurat, sesuaikan angkanya. Kalau tidak, bot hanya jadi sedikit lebih
  konservatif.
- **Sepuluh menit terakhir sebelum deadline** — cek manual. Jadwal GitHub bisa
  molor, jangan bergantung padanya untuk keputusan menit-menit akhir.

---

# BAGIAN 8 — Mengubah pengaturan nanti

Semua lewat browser, tanpa menyentuh kode:

**Settings → Secrets and variables → Actions → tab Variables → ikon pensil.**

| Mau apa | Caranya |
|---|---|
| Tambah pemain incaran | edit `FPL_PANTAU_TAMBAHAN`, isi `Saka, Isak` |
| Perbarui nilai bank | edit `FPL_BANK` |
| Nyalakan pantauan berita | isi Secret `ANTHROPIC_API_KEY`, lalu set `FPL_PAKAI_AI` jadi `ya` |
| Kurangi frekuensi | edit `.github/workflows/pantau.yml`, ganti cron jadi `"0,30 * * * *"` |
| Matikan sementara | Actions → klik nama workflow → titik tiga di kanan → **Disable workflow** |
| Ubah titik pengingat deadline | edit `tahap_laporan_jam` di `agen_fpl.py`, misal `[12, 4, 1]` |

---

# BAGIAN 9 — Kalau ada yang merah

Klik baris yang gagal di tab Actions, lalu klik langkah bertanda silang merah.
Tulisannya memang menakutkan — cari **kalimat terakhirnya**, biasanya di situ
masalahnya.

| Yang tertulis | Artinya | Perbaikannya |
|---|---|---|
| `ModuleNotFoundError: No module named 'pandas'` | `requirements.txt` belum terunggah | unggah berkas itu |
| `Gagal menghubungi FPL` | server FPL sibuk atau sedang pemeliharaan | tunggu, coba lagi nanti — di luar kendali kita |
| Centang hijau tapi Telegram diam | token atau chat ID salah | ulangi 1.2 dan 1.3, timpa Secrets |
| `Permission denied` / `403` saat menyimpan state | izin repo | Settings → Actions → General → **Workflow permissions** → pilih **Read and write permissions** → Save |
| `Invalid workflow file` | isi `.yml` tidak lengkap saat menempel | buka berkas di GitHub, hapus semua, tempel ulang |
| Tab Actions kosong terus | berkas `.yml` salah lokasi | jalurnya harus persis `.github/workflows/pantau.yml` |
| Log tertulis `Skuad dibaca dari: daftar manual` | `FPL_ENTRY_ID` salah, atau musim belum mulai | periksa ulang angkanya di langkah 1.1 |

**Kalau macet:** salin tulisan merahnya, kirim ke saya. Jangan diutak-atik
sampai bingung.

---

# BAGIAN 10 — Laptop kantor dan keamanan

## 10.1 — Kalau memakai laptop kantor

Setelah pemasangan selesai, **folder `AgenFPL` di laptop tidak dibutuhkan lagi.**
Semuanya hidup di GitHub.

1. Selesaikan Bagian 1–6.
2. Pastikan Telegram sudah menerima laporan uji.
3. **Hapus folder `AgenFPL`**, kosongkan Recycle Bin.

Salinan resminya ada di repo GitHub — kalau butuh, unduh lagi.

Selama pemasangan:

- **Jangan install Python di laptop kantor.** Tidak perlu — seluruh panduan ini
  cuma pakai browser. Banyak perusahaan melarang instalasi di luar daftar resmi.
- **Jangan simpan `config.json` berisi token** di laptop kantor.
- **Login GitHub pakai email pribadi.** Kalau pindah kerja, akses email kantor
  hilang dan akunmu sulit dipulihkan.
- **Jangan centang "Simpan kata sandi"** di browser kantor.
- **Laptop kantor bisa diaudit.** IT umumnya punya akses penuh ke perangkat.

Isi skripnya sendiri tidak berisiko bagi perusahaan: hanya membaca data publik
FPL lewat internet, tidak menyentuh berkas lain, tidak mengubah sistem, tidak
jalan di latar belakang. Risikonya bukan teknis, melainkan **kepatuhan** —
pemakaian aset kantor untuk urusan pribadi. Cek aturan IT di tempatmu.

## 10.2 — Tiga aturan yang tidak boleh dilanggar

1. **Token Telegram tidak pernah masuk ke dalam kode.** Tempatnya cuma di
   Secrets. Kalau terlanjur ter-push ke repo public: @BotFather → `/revoke` →
   pilih botmu → buat token baru → perbarui Secrets. Menghapus commit saja
   **tidak cukup**, karena repo public sudah terlanjur terbaca.
2. **Jangan menyimpan data kantor di repo ini.** Repo-nya public. Ini khusus FPL.
3. **Nyalakan two-factor authentication di GitHub.** Settings → Password and
   authentication → Enable two-factor.

---

# Daftar periksa

- [ ] ID tim FPL dicatat
- [ ] Bot Telegram dibuat, token dicatat
- [ ] Chat ID dicatat
- [ ] Akun GitHub jadi, pakai email pribadi
- [ ] Repo `agen-fpl` dibuat, **Public**
- [ ] 9 berkas terunggah, termasuk 2 di `.github/workflows/`
- [ ] `config.json` **tidak** ikut diunggah
- [ ] 3 Secrets terisi
- [ ] Variables terisi
- [ ] Laporan FPL dijalankan manual → Telegram masuk
- [ ] Pemantau FPL dijalankan **dua kali**
- [ ] Log menunjukkan `Skuad dibaca dari: akun FPL`
- [ ] Two-factor authentication aktif
- [ ] Folder `AgenFPL` dihapus dari laptop kantor
