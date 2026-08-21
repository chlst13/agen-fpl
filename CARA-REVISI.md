# Cara merevisi berkas di GitHub

Kalau kamu **belum** mengunggah apa pun ke GitHub, abaikan berkas ini —
langsung ikuti `PANDUAN-PEMASANGAN.md` dari awal dengan berkas versi terbaru.

Kalau kamu **sudah** terlanjur mengunggah versi lama, ikuti ini.

---

## Revisi terbaru — ringkasan berita untuk pengambilan keputusan

Berkas baru **`berita.py`**. Menyaring seluruh berita resmi FPL 72 jam
terakhir, lalu menerjemahkan tiap kabar jadi satu tindakan:

| Label | Artinya |
|---|---|
| 🔴 JUAL | tidak bisa dimainkan, kursi XI terbuang |
| 🟡 PANTAU | belum pasti, tunggu sampai mendekati deadline |
| 🟢 TAHAN | risikonya kecil, tidak perlu bertindak |
| 💎 PELUANG BELI | baru pulih, masih murah, sebelum harga naik |
| 😀 KABAR BAIK | pemain populer cedera dan kamu tidak memilikinya |

Muncul di laporan Telegram dan di laporan HTML sebagai tabel.

**Yang perlu diunggah:** `berita.py` (baru, pakai Cara B) dan `agen_fpl.py`
(ditimpa, pakai Cara A).

Briefing web opsional aktif kalau `ANTHROPIC_API_KEY` terisi dan
`FPL_PAKAI_AI` bernilai `ya`. Tanpa itu, seluruh penyaringan berita tetap
berjalan penuh karena semua perhitungannya lokal.

---

## Revisi sebelumnya — nama klub di setiap peringatan

Nama pendek FPL sering ambigu: **"Bruno G." itu Newcastle**, sedangkan
**"B.Fernandes" itu Man United**. Sekarang semua peringatan menyertakan klub:

```
❗ 🔴 Bruno G. (NEW): fit → diragukan
     Thigh injury - 75% chance of playing
```

Berlaku juga untuk daftar bendera skuad, risiko rotasi, kandidat pengganti,
pergerakan harga, dan differential.

**Berkas yang perlu ditimpa:** `pemantau_fpl.py`, `agen_fpl.py`,
`fitur_lanjutan.py`. Pakai Cara A di bawah.

> Berkas `state_pantau.json` di repo tidak perlu dihapus. Snapshot lama
> menyimpan klub sebagai angka, tapi itu tidak dipakai untuk membandingkan —
> jadi tidak ada yang rusak. Snapshot berikutnya langsung memakai format baru.

---

## Yang berubah kali ini

| Berkas | Status | Tindakan |
|---|---|---|
| `fitur_lanjutan.py` | 🆕 **baru** | unggah sebagai berkas baru |
| `laporan_gw.py` | 🆕 **baru** | unggah sebagai berkas baru |
| `berita.py` | 🆕 **baru** | unggah sebagai berkas baru |
| `agen_fpl.py` | ✏️ direvisi | timpa isinya |
| `pemantau_fpl.py` | ✏️ direvisi | timpa isinya |
| `.github/workflows/pantau.yml` | ✏️ direvisi | timpa isinya |
| `.github/workflows/laporan.yml` | ✏️ direvisi | timpa isinya |
| `requirements.txt` | tetap | tidak perlu disentuh |
| `.gitignore` | tetap | tidak perlu disentuh |

---

## Cara A — Timpa berkas yang sudah ada

Lakukan untuk `agen_fpl.py`, `pemantau_fpl.py`, `pantau.yml`, dan `laporan.yml`.
Ulangi langkah berikut satu per satu.

1. Buka repo `agen-fpl` di github.com.
2. Klik nama berkas yang mau diganti. Untuk yang `.yml`, masuk dulu ke folder
   `.github` → `workflows`.
3. Di pojok kanan atas isi berkas, klik **ikon pensil** (✏️ *Edit this file*).
4. Klik di dalam kotak kode, tekan **Ctrl+A** lalu **Delete** — kosongkan total.
5. Buka berkas versi baru di komputer dengan **Notepad**, tekan **Ctrl+A**,
   **Ctrl+C**.
6. Kembali ke GitHub, klik di kotak kode, tekan **Ctrl+V**.
7. Gulir ke bawah, klik **Commit changes** → **Commit changes** lagi.

> Pastikan kotaknya benar-benar kosong sebelum menempel. Kalau isi lama masih
> tersisa di bawah, kodenya akan rusak dan muncul error `SyntaxError`.

## Cara B — Tambahkan berkas baru

Untuk `fitur_lanjutan.py` dan `laporan_gw.py` yang belum pernah ada. Ulangi
langkah ini dua kali, sekali untuk tiap berkas:

1. Di halaman utama repo, klik **Add file** → **Create new file**.
2. Nama berkas: `fitur_lanjutan.py` (lalu ulangi dengan `laporan_gw.py`).
3. Tempel isinya dari Notepad.
4. **Commit changes**.

## Cara C — Kalau bingung, mulai bersih

Ini paling aman kalau kamu merasa sudah terlanjur acak-acakan:

1. Repo → **Settings** → gulir paling bawah → **Delete this repository**.
2. Ketik nama repo untuk konfirmasi.
3. Buat repo baru dengan nama sama, lalu ikuti `PANDUAN-PEMASANGAN.md` dari awal.

Secrets dan Variables ikut terhapus, jadi harus diisi ulang. Tapi tiga nomor di
Notepad-mu masih berlaku — tidak perlu bikin bot Telegram baru.

---

## Tambahkan Variables baru

Setelah semua berkas diperbarui: **Settings** → **Secrets and variables** →
**Actions** → tab **Variables** → **New repository variable**.

| Name | Value | Gunanya |
|---|---|---|
| `FPL_TAHAP_LAPORAN` | `24,3,1` | pengingat 1 hari, 3 jam, 1 jam sebelum deadline |
| `FPL_LIGA_ID` | ID liga mini kamu | pemantau papan liga |

**Cara mencari ID liga mini:** buka FPL → menu **Leagues** → klik nama liga
kamu. Lihat URL:

`https://fantasy.premierleague.com/leagues/`**`843217`**`/standings/c`

Angka itulah ID-nya. Kalau tidak ikut liga mini, lewati saja — fitur lain tetap
jalan.

> `FPL_TAHAP_LAPORAN` boleh diubah kapan saja tanpa menyentuh kode. Misalnya
> `48,12,2` untuk pengingat 2 hari, 12 jam, dan 2 jam sebelum deadline.

---

## Uji setelah revisi

1. Tab **Actions** → **Laporan FPL** → **Run workflow**.
2. Tunggu centang hijau.
3. Cek Telegram — sekarang isinya harus lebih panjang dari sebelumnya: ada
   bagian nilai tim, chip tersisa, liga mini, saran chip, dan differential.
4. Buka log run tadi, klik langkah **Susun laporan**. Pastikan **tidak ada**
   baris `⚠ Fitur lanjutan dilewati:`. Kalau ada, berarti `fitur_lanjutan.py`
   belum terunggah atau isinya tidak lengkap.

Kalau Telegram masih seperti versi lama, biasanya `fitur_lanjutan.py` belum
terunggah. Agen memang dirancang tetap jalan tanpa berkas itu — jadi tidak
error, hanya fiturnya tidak muncul.

---

## Kalau muncul error setelah revisi

| Yang tertulis | Sebabnya | Perbaikan |
|---|---|---|
| `SyntaxError: invalid syntax` | isi lama tidak terhapus tuntas saat menempel | ulangi Cara A, pastikan Ctrl+A → Delete dulu |
| `⚠ Fitur lanjutan dilewati` | `fitur_lanjutan.py` belum ada atau tidak lengkap | unggah ulang dengan Cara B |
| `⚠ Ringkasan berita dilewati` | `berita.py` belum ada atau tidak lengkap | unggah ulang dengan Cara B |
| `⚠ Pembedahan gameweek dilewati` | `laporan_gw.py` belum ada, atau gameweek belum rampung | unggah ulang; kalau musim belum jalan ini normal |
| `Invalid workflow file` | berkas `.yml` rusak saat ditempel | ulangi Cara A untuk berkas itu |
| Telegram diam padahal hijau | tidak ada perubahan status — memang normal | jalankan **Laporan FPL** untuk memastikan Telegram hidup |

Kalau macet, salin tulisan merahnya dan kirim ke saya.
