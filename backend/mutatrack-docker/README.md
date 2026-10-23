# MutaTrack

Platform analisis variant calling untuk data genomik. Backend berupa API FastAPI yang menjalankan pipeline bioinformatika (FastQC, fastp, BWA-MEM, samtools, bcftools, SnpEff) dan menyimpan akun serta hasil analisis di PostgreSQL. Seluruh sistem dijalankan lewat Docker, jadi tidak perlu memasang Python, conda, atau PostgreSQL secara manual.

Proyek ini adalah bagian dari praktikum Pembangunan Perangkat Lunak, IPB University.

## Isi repositori

```
Dockerfile          resep image backend (Python 3.11 + tool bioinformatika + database SnpEff)
docker-compose.yml  menjalankan tiga layanan: db (PostgreSQL 16), backend (API), pgadmin
schema.sql          tabel users, analyses, variants (dibuat otomatis saat database pertama kali dibuat)
main.py             API: login, upload, validasi, menjalankan pipeline, unduh hasil
pipeline.py         enam tahap analisis
requirements.txt    library Python untuk API
env.example         contoh isi file .env
```

## Prasyarat

Yang perlu dipasang hanya tiga hal. Pertama Docker Desktop (Windows 10/11 dengan WSL 2, virtualisasi harus aktif di BIOS). Kedua Git. Ketiga VS Code sebagai editor, yang sifatnya opsional tetapi disarankan. Siapkan juga ruang disk kosong sekitar 10 GB dan RAM minimal 8 GB, karena image bioinformatika cukup besar dan pipeline dibatasi satu analisis pada satu waktu. Pengguna Mac dengan chip Apple Silicon tetap bisa menjalankannya, tetapi image berjalan lewat emulasi sehingga lebih lambat.

## Langkah menjalankan

### 1. Ambil proyek

```
git clone https://github.com/Pembangunan-Perangkat-Lunak-BIF-IPB/kelompok-07.git
cd kelompok-07/backend/mutatrack-docker
```

Buka folder itu di VS Code (File > Open Folder), lalu buka terminal bawaan dengan Ctrl+`.

### 2. Nyalakan Docker Desktop

Buka Docker Desktop dari menu Start dan tunggu sampai di pojok kiri bawah tertulis "Engine running". Cek dari terminal:

```
docker info
```

Jika keluarannya panjang dan memuat bagian `Server:`, Docker siap. Jika muncul "cannot connect" atau "Engine stopped", Docker Desktop belum selesai menyala.

### 3. Buat file .env

File `.env` berisi password dan tidak ikut ke GitHub, jadi setiap orang membuatnya sendiri dari contoh.

```
copy env.example .env
```

(di macOS/Linux: `cp env.example .env`). Buka `.env` di VS Code dan ganti nilai berikut dengan milik sendiri:

```
POSTGRES_PASSWORD=isi-password-database
JWT_SECRET=isi-teks-acak-yang-panjang
PGADMIN_EMAIL=admin@example.com
PGADMIN_PASSWORD=isi-password-pgadmin
```

Baris lain biarkan seperti aslinya. Catatan penting: `PGADMIN_EMAIL` harus memakai domain email yang valid. Domain berakhiran `.local` ditolak pgAdmin dan membuat container-nya langsung berhenti. Simpan file dengan Ctrl+S.

### 4. Jalankan semua layanan

```
docker compose up -d --build
```

Build pertama paling lama karena mengunduh tool bioinformatika dan database anotasi SnpEff, kira-kira 10 sampai 20 menit tergantung koneksi. Build berikutnya hanya beberapa detik. Setelah selesai, cek:

```
docker compose ps
```

Ketiga layanan (`db`, `backend`, `pgadmin`) harus berstatus Up, dan `db` berstatus healthy.

### 5. Alamat yang bisa dibuka

| Layanan | Alamat |
|---|---|
| Dokumentasi dan uji API (Swagger) | http://localhost:8000/docs |
| pgAdmin (melihat isi database) | http://localhost:5050 |
| PostgreSQL (untuk alat lain di komputer Anda) | localhost, port 5433 |

## Menguji login

Buka http://localhost:8000/docs. Pada `POST /auth/register` klik Try it out, isi data seperti berikut, lalu Execute.

```json
{
  "email": "uji@example.com",
  "password": "password123",
  "nama": "Uji Coba"
}
```

Hasil yang benar adalah kode 201 dengan `token` di dalam respons. Password minimal 8 karakter. Lalu uji `POST /auth/login` dengan email dan password yang sama, dan ekspektasinya kode 200. Login dengan password salah harus menghasilkan 401, dan register dengan email yang sama dua kali menghasilkan 409.

Untuk mengecek token, salin nilai `token` (tanpa tanda kutip), klik tombol Authorize di kanan atas halaman, tempel, lalu Authorize. Setelah itu `GET /auth/me` harus menampilkan data akun Anda. Semua endpoint selain `/health`, `/config/default`, `/auth/register`, dan `/auth/login` memerlukan token ini.

## Melihat isi database di pgAdmin

Buka http://localhost:5050 dan login dengan `PGADMIN_EMAIL` dan `PGADMIN_PASSWORD` dari `.env`. Pertama kali masuk, daftarkan server dengan klik kanan Servers > Register > Server. Di tab General beri nama bebas, misalnya `mutatrack`. Di tab Connection isi host `db`, port 5432, maintenance database `mutatrack`, username `postgres`, dan password dari `POSTGRES_PASSWORD`. Tabel ada di Databases > mutatrack > Schemas > public > Tables. Klik kanan `users` lalu View/Edit Data > All Rows untuk melihat akun yang terdaftar. Kolom `password_hash` berisi teks acak diawali `$2b$`, bukan password asli.

Kalau Anda memakai pgAdmin atau DBeaver yang terpasang langsung di komputer (di luar Docker), sambungkan ke host `localhost` dan port 5433. Jangan tertukar dengan PostgreSQL lain yang mungkin sudah ada di komputer Anda: database Docker ini terpisah dan memiliki isi sendiri.

## Menguji analisis

Alur analisis dijalankan dari halaman `/docs` setelah Authorize. Urutannya `POST /analyses` (unggah nama analisis, file FASTQ R1, dan genom referensi FASTA; R2 opsional), lalu `POST /analyses/{aid}/validate`, kemudian `POST /analyses/{aid}/run`. Pantau dengan `GET /analyses/{aid}` sampai `status` menjadi `selesai` atau `gagal`; bila gagal, kolom `error` dan `log_tail` menunjukkan sebabnya. Hasil dapat dilihat lewat `/summary` dan `/variants`, atau diunduh lewat `/download?format=vcf`, `csv`, atau `pdf`.

Untuk data uji, gunakan genom E. coli K-12 MG1655 (GCA_000005845.2) dari NCBI sebagai referensi dan FASTQ hasil simulasi seperti pada LKP 7. Catatan status: pipeline sudah pernah dijalankan penuh di luar API pada data ini, tetapi pengujian lewat endpoint API ini belum didokumentasikan, jadi hasil pertama kali perlu dicek dengan teliti.

## Perintah sehari-hari

```
docker compose up -d              menyalakan semua layanan
docker compose ps                 melihat status
docker compose logs backend       melihat log backend (ganti nama untuk layanan lain)
docker compose stop               mematikan tanpa menghapus apa pun
docker compose up -d --build backend   membangun ulang backend setelah main.py atau pipeline.py diubah
docker compose down               menghapus container, data tetap aman
docker compose down -v            menghapus container DAN seluruh data database (hati-hati)
```

Data database dan file hasil analisis disimpan di volume Docker (`pgdata` dan `appdata`), sehingga tetap ada setelah `docker compose down` biasa. Hanya perintah dengan `-v` yang menghapusnya.

## Masalah yang sering muncul

Peringatan `The "POSTGRES_PASSWORD" variable is not set` berarti file `.env` belum dibuat atau belum berada di folder yang sama dengan `docker-compose.yml`. Buat dari langkah 3 lalu ulangi.

Galat `Docker Desktop is unable to start`, `Engine stopped`, atau pesan soal WSL berarti Docker Desktop belum benar-benar menyala. Jalankan `wsl --update` dan `wsl --shutdown` di PowerShell, restart Docker Desktop, dan bila perlu restart Windows.

Container `pgadmin` langsung berhenti dengan log `does not appear to be a valid email address` berarti `PGADMIN_EMAIL` memakai domain yang ditolak. Ganti dengan email biasa seperti `admin@example.com`, lalu `docker compose rm -f pgadmin` dan `docker compose up -d pgadmin`. Jika `docker compose config` masih menampilkan email lama padahal `.env` sudah benar, ada variabel lingkungan dengan nama sama di terminal yang mengalahkan `.env`. Hapus dengan `Remove-Item Env:PGADMIN_EMAIL` (PowerShell).

Container `backend` langsung berhenti: jalankan `docker compose logs backend`. Penyebab umum adalah variabel di `.env` belum terisi, atau database belum siap sehingga cukup `docker compose up -d` sekali lagi.

Tabel tidak muncul di database berarti `schema.sql` tidak terbaca saat database pertama dibuat. Pastikan nama file tepat `schema.sql`, lalu jalankan `docker compose down -v` dan `docker compose up -d`. Perintah itu mengosongkan database, jadi lakukan hanya bila belum ada data penting.

Galat `port is already allocated` berarti port 8000, 5050, atau 5433 sedang dipakai program lain. Matikan program itu, atau ubah angka di kiri pada bagian `ports` di `docker-compose.yml`.

Container atau image tampak rusak (misalnya galat `input/output error` atau `invalid user name 'postgres'`): di Docker Desktop buka Settings > General, matikan "Use containerd for pulling and storing images", Apply & restart, lalu ulangi `docker compose down -v` dan `docker compose up -d --build`. Jika masih gagal, gunakan Troubleshoot (ikon bug) > Clean / Purge data.

## Keamanan dan kerja tim

Jangan pernah meng-commit file `.env`. File `.gitignore` di repositori sudah mengecualikannya, tetapi tetap cek `git status` sebelum commit dan pastikan `.env` tidak muncul. Jika password pernah tidak sengaja terunggah, ganti semuanya. Setiap anggota tim memiliki database sendiri di komputernya, jadi akun yang dibuat di satu komputer tidak otomatis ada di komputer lain. Sebelum mulai bekerja, jalankan `git pull`, dan setelah mengubah `main.py` atau `pipeline.py`, bangun ulang dengan `docker compose up -d --build backend`.

Saat frontend (Base44) disambungkan nanti, tambahkan alamat situsnya ke `ALLOWED_ORIGINS` di `.env`, dipisahkan koma, lalu jalankan `docker compose up -d` agar browser tidak memblokir permintaan ke API.
