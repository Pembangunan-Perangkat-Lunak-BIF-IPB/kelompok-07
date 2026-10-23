# MutaTrack — Platform Bioinformatika untuk Analisis Variant Calling

**MutaTrack** adalah platform perangkat lunak bioinformatika yang dirancang untuk mengintegrasikan dan mengotomatisasi alur kerja *variant calling* DNA, mulai dari pemrosesan data sekuensing mentah hingga identifikasi, penyaringan, dan anotasi varian genetik.

MutaTrack menggabungkan antarmuka web, layanan backend berbasis REST API, perangkat lunak bioinformatika berbasis command-line, serta sistem basis data untuk membantu pengguna mengelola analisis secara terstruktur.

Proyek ini dikembangkan sebagai bagian dari **Praktik Pengalaman Lapangan (PPL)** dengan fokus pada pengembangan perangkat lunak bioinformatika, integrasi pipeline analisis, pengelolaan basis data, dan pengembangan aplikasi web.

---

## Daftar Isi

- [Gambaran Umum](#gambaran-umum)
- [Latar Belakang](#latar-belakang)
- [Tujuan Pengembangan](#tujuan-pengembangan)
- [Fitur Utama](#fitur-utama)
- [Arsitektur Sistem](#arsitektur-sistem)
- [Alur Kerja Pipeline Bioinformatika](#alur-kerja-pipeline-bioinformatika)
- [Teknologi yang Digunakan](#teknologi-yang-digunakan)
- [Rancangan Basis Data](#rancangan-basis-data)
- [Struktur Direktori](#struktur-direktori)
- [Instalasi dan Konfigurasi](#instalasi-dan-konfigurasi)
- [Menjalankan Aplikasi](#menjalankan-aplikasi)
- [Data Masukan dan Keluaran](#data-masukan-dan-keluaran)
- [Status Pengembangan](#status-pengembangan)
- [Pengujian Sistem](#pengujian-sistem)
- [Batasan Sistem](#batasan-sistem)
- [Rencana Pengembangan](#rencana-pengembangan)
- [Kontribusi](#kontribusi)
- [Lisensi](#lisensi)

---

## Gambaran Umum

MutaTrack dikembangkan untuk mengintegrasikan berbagai perangkat lunak bioinformatika ke dalam satu alur kerja analisis varian genetik. Platform ini dirancang untuk mengurangi kompleksitas pengoperasian sejumlah perangkat lunak secara terpisah serta mempermudah pengelolaan data, pemantauan proses analisis, dan penyimpanan hasil.

Secara umum, MutaTrack terdiri atas empat komponen utama:

1. **Frontend:** antarmuka pengguna untuk mengelola analisis dan melihat hasil.
2. **Backend:** layanan API yang menangani permintaan pengguna, validasi data, dan eksekusi pipeline.
3. **Pipeline bioinformatika:** rangkaian perangkat lunak untuk pemrosesan data sekuensing dan identifikasi varian.
4. **Basis data dan penyimpanan:** komponen untuk mengelola informasi pengguna, metadata analisis, hasil varian, serta berkas keluaran.

Alur kerja yang dirancang mencakup pengunggahan data, kontrol kualitas, pemrosesan sekuens, alignment terhadap genom referensi, pemanggilan varian, penyaringan, anotasi, dan pengelolaan hasil analisis.

## Latar Belakang

*Variant calling* merupakan salah satu tahapan penting dalam analisis bioinformatika untuk mengidentifikasi perbedaan genetik antara data sekuensing DNA dan genom referensi. Proses ini melibatkan sejumlah tahapan yang saling bergantung dan memerlukan perangkat lunak dengan fungsi berbeda.

Dalam praktiknya, pengguna perlu mengelola format data seperti FASTQ, BAM, dan VCF, mengatur parameter analisis, memastikan ketersediaan perangkat lunak, serta menangani berkas keluaran dari setiap tahapan.

MutaTrack dirancang untuk mengintegrasikan proses tersebut melalui aplikasi web yang terhubung dengan backend dan pipeline bioinformatika. Dengan pendekatan ini, pengelolaan analisis diharapkan menjadi lebih terstruktur, mudah dipantau, dan dapat ditelusuri berdasarkan konfigurasi serta hasil pemrosesannya.

## Tujuan Pengembangan

Pengembangan MutaTrack memiliki beberapa tujuan utama:

- Mengembangkan aplikasi web untuk pengelolaan analisis *variant calling*.
- Mengintegrasikan perangkat lunak bioinformatika ke dalam pipeline yang terstruktur.
- Membangun backend berbasis REST API untuk menangani data masukan dan menjalankan proses analisis.
- Mengintegrasikan autentikasi pengguna dan pengelolaan data melalui Supabase.
- Menyediakan pencatatan status, log, dan hasil dari setiap tahapan analisis.
- Menyimpan metadata analisis dan informasi varian secara terstruktur.
- Membangun arsitektur perangkat lunak yang modular, mudah diuji, dan dapat dikembangkan lebih lanjut.

## Fitur Utama

Fitur berikut merupakan ruang lingkup pengembangan MutaTrack. Ketersediaan setiap fitur perlu disesuaikan dengan implementasi aktual pada repository.

| Fitur | Deskripsi |
|---|---|
| Autentikasi pengguna | Pengelolaan login dan identitas pengguna melalui Supabase Auth. |
| Manajemen analisis | Pembuatan dan pengelolaan proyek analisis varian. |
| Pengelolaan data masukan | Pengunggahan berkas sekuensing dan pengaturan parameter analisis. |
| Kontrol kualitas | Evaluasi kualitas data sekuensing menggunakan FastQC. |
| Pemrosesan sekuens | Pemotongan adapter dan penyaringan kualitas menggunakan fastp. |
| Alignment | Pemetaan sekuens terhadap genom referensi menggunakan BWA. |
| Pemrosesan alignment | Pengurutan dan pengindeksan berkas alignment menggunakan SAMtools. |
| Variant calling | Identifikasi kandidat varian genetik menggunakan BCFtools. |
| Penyaringan varian | Penyaringan kandidat varian berdasarkan kriteria kualitas. |
| Anotasi varian | Prediksi dampak fungsional varian menggunakan SnpEff. |
| Pelacakan analisis | Pencatatan status proses, log, dan tahapan pipeline. |
| Pengelolaan hasil | Penyimpanan metadata analisis dan hasil varian secara terstruktur. |

## Arsitektur Sistem

MutaTrack menggunakan arsitektur modular yang memisahkan antarmuka pengguna, layanan backend, pemrosesan bioinformatika, dan penyimpanan data.

```text
                    +----------------------+
                    |       Frontend       |
                    |      React / UI      |
                    +----------+-----------+
                               |
                         REST API / HTTP
                               |
                    +----------v-----------+
                    |       Backend        |
                    |        FastAPI       |
                    +----------+-----------+
                               |
                    +----------v-----------+
                    |   Pipeline Manager   |
                    | Validasi dan Eksekusi|
                    +----------+-----------+
                               |
             +-----------------+------------------+
             |                 |                  |
       +-----v-----+     +-----v------+     +-----v------+
       | FastQC /  |     | BWA /      |     | BCFtools / |
       | fastp     |     | SAMtools   |     | SnpEff     |
       +-----------+     +------------+     +------------+
                               |
                    +----------v-----------+
                    | Penyimpanan Data     |
                    | Supabase / Database  |
                    | Metadata dan Hasil   |
                    +----------------------+
```

### Frontend

Frontend dikembangkan menggunakan React untuk menyediakan antarmuka interaksi pengguna dengan sistem. Komponen ini dirancang untuk mendukung autentikasi, pembuatan analisis, pengelolaan data masukan, pemantauan status pipeline, dan penyajian hasil.

Frontend berkomunikasi dengan backend melalui REST API.

### Backend

Backend dikembangkan menggunakan FastAPI dan Python. Komponen ini bertanggung jawab untuk:

- Menerima permintaan analisis dari frontend.
- Memvalidasi data masukan dan parameter analisis.
- Menangani berkas yang diunggah.
- Mengatur eksekusi perangkat lunak bioinformatika.
- Mencatat status proses dan log.
- Mengelola komunikasi dengan basis data.
- Menyediakan informasi analisis dan hasil melalui endpoint API.

Eksekusi pipeline perlu dikelola secara terkontrol agar penggunaan sumber daya komputasi, khususnya memori, tetap sesuai dengan kapasitas lingkungan pengembangan.

### Pipeline Bioinformatika

Pipeline manager mengatur urutan eksekusi perangkat lunak berdasarkan dependensi setiap tahapan. Kegagalan pada suatu tahapan harus dapat dicatat agar proses berikutnya tidak dijalankan menggunakan keluaran yang tidak valid.

### Basis Data dan Penyimpanan

Supabase digunakan untuk mendukung autentikasi dan pengelolaan data aplikasi. Basis data menyimpan metadata analisis, relasi pengguna, serta informasi hasil yang diperlukan oleh aplikasi.

Berkas berukuran besar, seperti FASTQ, BAM, VCF, dan log, memerlukan mekanisme penyimpanan berkas yang sesuai dengan kebutuhan kapasitas dan kontrol akses.

## Alur Kerja Pipeline Bioinformatika

Pipeline MutaTrack dirancang untuk menjalankan analisis varian secara berurutan.

```text
Data FASTQ
    |
    v
Validasi Data Masukan
    |
    v
Kontrol Kualitas (FastQC)
    |
    v
Pemrosesan Sekuens (fastp)
    |
    v
Alignment (BWA)
    |
    v
Pemrosesan BAM (SAMtools)
    |
    v
Variant Calling (BCFtools)
    |
    v
Penyaringan Varian
    |
    v
Anotasi Fungsional (SnpEff)
    |
    v
Penyimpanan dan Pelaporan Hasil
```

### Tahapan Pipeline

| Tahapan | Perangkat Lunak | Fungsi |
|---|---|---|
| Validasi data | Python | Memeriksa berkas masukan dan parameter analisis. |
| Kontrol kualitas | FastQC | Menghasilkan laporan kualitas data sekuensing. |
| Pemrosesan sekuens | fastp | Melakukan pemotongan adapter dan penyaringan kualitas sekuens. |
| Alignment | BWA | Memetakan sekuens terhadap genom referensi. |
| Pemrosesan alignment | SAMtools | Mengurutkan, mengindeks, dan menyiapkan berkas BAM. |
| Variant calling | BCFtools | Mengidentifikasi kandidat varian berdasarkan data alignment. |
| Penyaringan varian | BCFtools | Menyaring varian berdasarkan kriteria yang ditentukan. |
| Anotasi | SnpEff | Memprediksi dampak fungsional varian. |
| Pengelolaan hasil | Python dan layanan basis data | Mengelola metadata analisis dan hasil pemrosesan. |

Parameter, perintah, dan urutan eksekusi aktual mengikuti implementasi pipeline yang digunakan. Beberapa tahapan tambahan, seperti pembuatan indeks genom referensi, diperlukan sesuai konfigurasi dan format data.

## Teknologi yang Digunakan

| Komponen | Teknologi |
|---|---|
| Frontend | React |
| Backend | FastAPI |
| Bahasa pemrograman | Python |
| Autentikasi | Supabase Auth |
| Basis data | Supabase Database Services |
| Kontrol kualitas | FastQC |
| Pemrosesan sekuens | fastp |
| Alignment | BWA |
| Pemrosesan alignment | SAMtools |
| Variant calling dan filtering | BCFtools |
| Anotasi varian | SnpEff |
| Lingkungan pengembangan | Ubuntu / WSL |
| Manajemen lingkungan | Conda-compatible environment |
| Version control | Git dan GitHub |

## Rancangan Basis Data

Basis data dirancang untuk menghubungkan pengguna, proyek analisis, sampel, proses pipeline, dan hasil varian.

| Entitas | Fungsi |
|---|---|
| Profiles | Menyimpan metadata pengguna. |
| Projects | Mengelompokkan analisis yang saling berkaitan. |
| Samples | Menyimpan identitas sampel biologis. |
| Reference Genomes | Menyimpan informasi genom referensi dan versinya. |
| Analyses | Menyimpan konfigurasi, pemilik, dan status analisis. |
| Pipeline Steps | Mencatat tahapan pemrosesan, status, dan log. |
| Variants | Menyimpan informasi varian genetik dan metrik terkait. |
| Genotypes | Menyimpan informasi genotipe sampel jika didukung pipeline. |
| Annotations | Menyimpan informasi anotasi fungsional varian. |

Relasi antarentitas perlu menjaga integritas data dan membatasi akses berdasarkan kepemilikan pengguna sesuai kebijakan keamanan aplikasi.

Data varian idealnya mencakup genom referensi yang digunakan, kromosom, posisi genomik, alel referensi (REF), dan alel alternatif (ALT). Informasi ini diperlukan untuk membedakan varian serta menafsirkan hasil secara tepat.

## Struktur Direktori

Berikut contoh struktur direktori yang disarankan untuk pengembangan MutaTrack. Struktur ini perlu disesuaikan dengan susunan folder aktual pada repository.

```text
MutaTrack/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── services/
│   │   └── ...
│   ├── public/
│   ├── package.json
│   └── ...
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   ├── core/
│   │   ├── services/
│   │   ├── pipeline/
│   │   ├── database/
│   │   └── ...
│   ├── tests/
│   ├── requirements.txt
│   └── ...
│
├── docs/
│   ├── architecture/
│   ├── database/
│   └── ...
│
├── .gitignore
└── README.md
```

## Instalasi dan Konfigurasi

### Prasyarat

Sebelum menjalankan MutaTrack, siapkan:

- Git.
- Python 3.11.
- Node.js dan npm.
- Conda atau pengelola lingkungan yang kompatibel.
- Perangkat lunak bioinformatika yang diperlukan.
- Proyek Supabase dengan konfigurasi autentikasi dan basis data yang sesuai.

### 1. Clone Repository

```bash
git clone <URL_REPOSITORY_GITHUB>
cd MutaTrack
```

Ganti `<URL_REPOSITORY_GITHUB>` dengan URL repository yang sebenarnya.

### 2. Membuat Lingkungan Bioinformatika

Buat lingkungan Conda untuk MutaTrack:

```bash
conda create -n mutatrack python=3.11
conda activate mutatrack
```

Instal perangkat lunak bioinformatika:

```bash
conda install -c conda-forge -c bioconda \
    fastqc fastp bwa samtools bcftools snpeff
```

Periksa instalasi perangkat lunak:

```bash
fastqc --version
fastp --version
bwa
samtools --version
bcftools --version
snpEff
```

Beberapa perangkat lunak, seperti BWA, dapat menampilkan informasi penggunaan ketika dijalankan tanpa argumen.

### 3. Menyiapkan Backend

Buka terminal dan masuk ke direktori backend:

```bash
cd backend
```

Jika repository menyediakan `requirements.txt`, instal dependensi Python:

```bash
pip install -r requirements.txt
```

Jika dependensi dikelola melalui `pyproject.toml`, ikuti petunjuk instalasi yang tercantum di dalamnya.

Buat berkas `.env` berdasarkan templat konfigurasi proyek, jika tersedia. Pastikan seluruh variabel lingkungan yang dibutuhkan backend telah diatur.

### 4. Menyiapkan Frontend

Buka terminal terpisah dan masuk ke direktori frontend:

```bash
cd frontend
```

Instal dependensi:

```bash
npm install
```

Sesuaikan variabel lingkungan frontend dengan konfigurasi API yang digunakan oleh aplikasi.

## Konfigurasi Lingkungan

Contoh variabel konfigurasi yang mungkin dibutuhkan:

```env
# Backend
APP_ENV=development
API_HOST=127.0.0.1
API_PORT=8000

# Supabase
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=

# Frontend
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Nama variabel tersebut merupakan contoh dan harus disesuaikan dengan kode aktual aplikasi.

**Ketentuan keamanan:**

- Jangan mengunggah berkas `.env` atau kredensial asli ke GitHub.
- Simpan kunci Supabase dengan hak istimewa tinggi hanya di backend.
- Terapkan Row Level Security (RLS) untuk membatasi akses data berdasarkan pengguna.
- Validasi berkas dan parameter analisis di backend.
- Batasi akses terhadap berkas sementara dan hasil analisis.
- Terapkan pengamanan yang sesuai untuk data sekuensing yang bersifat sensitif.

## Menjalankan Aplikasi

Perintah berikut merupakan contoh dan perlu disesuaikan dengan struktur proyek aktual.

### Menjalankan Backend

Dari direktori backend, jalankan:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Jika lokasi modul utama berbeda, sesuaikan jalur `app.main:app`.

Dokumentasi API FastAPI biasanya tersedia melalui:

```text
http://127.0.0.1:8000/docs
```

### Menjalankan Frontend

Dari direktori frontend, jalankan:

```bash
npm run dev
```

Buka alamat lokal yang ditampilkan oleh server pengembangan frontend.

### Hal yang Perlu Diperiksa

- URL API frontend harus sesuai dengan alamat backend.
- Konfigurasi autentikasi dan basis data harus valid.
- Perangkat lunak bioinformatika harus dapat diakses melalui `PATH` lingkungan backend.
- Gunakan dataset pengujian berukuran kecil sebelum memproses data yang lebih besar.
- Pantau log dan penggunaan sumber daya selama pipeline dijalankan.

## Data Masukan dan Keluaran

### Data Masukan

Data masukan yang direncanakan untuk mendukung pipeline meliputi:

- Berkas FASTQ hasil sekuensing.
- Identitas sampel dan metadata analisis.
- Informasi genom referensi.
- Versi genom referensi dan indeks yang diperlukan.
- Parameter analisis dan kriteria penyaringan varian.

Format berkas yang diterima dan batas ukuran unggahan harus mengikuti aturan validasi yang benar-benar diterapkan pada aplikasi.

### Data Keluaran

Bergantung pada tahapan pipeline yang berhasil dijalankan, keluaran dapat mencakup:

| Keluaran | Deskripsi |
|---|---|
| Laporan kontrol kualitas | Ringkasan kualitas sekuensing dari FastQC. |
| FASTQ hasil pemrosesan | Sekuens yang telah diproses menggunakan fastp. |
| Berkas BAM | Hasil alignment sekuens terhadap genom referensi. |
| Indeks BAM | Berkas indeks untuk mengakses data alignment. |
| Berkas VCF | Hasil pemanggilan varian genetik. |
| Hasil anotasi | Informasi prediksi dampak fungsional varian. |
| Metadata analisis | Konfigurasi, status, dan waktu pemrosesan. |
| Log proses | Informasi diagnostik dari setiap tahapan pipeline. |

Ketersediaan keluaran bergantung pada keberhasilan eksekusi tahapan terkait.

## Status Pengembangan

Pengembangan MutaTrack dilakukan secara bertahap, mencakup antarmuka pengguna, backend, basis data, instalasi perangkat lunak bioinformatika, integrasi pipeline, dan pengujian sistem.

Daftar berikut dapat digunakan untuk memantau progres pengembangan.

- [ ] Finalisasi arsitektur dan struktur repository.
- [ ] Penyelesaian alur analisis pada frontend.
- [ ] Integrasi autentikasi pengguna.
- [ ] Implementasi pembuatan analisis dan validasi data masukan.
- [ ] Integrasi frontend dengan endpoint backend.
- [ ] Integrasi basis data dan kebijakan kontrol akses.
- [ ] Implementasi orkestrasi pipeline dan pelacakan status pekerjaan.
- [ ] Integrasi dan validasi setiap tahapan perangkat lunak bioinformatika.
- [ ] Implementasi penyimpanan hasil varian dan anotasi.
- [ ] Penambahan pengujian otomatis untuk komponen pipeline dan endpoint API.
- [ ] Pengujian end-to-end menggunakan dataset yang sesuai.
- [ ] Penyelesaian dokumentasi dan persiapan deployment.

Perbarui daftar ini berdasarkan implementasi dan hasil pengujian yang telah diverifikasi, bukan hanya berdasarkan rancangan atau keberhasilan instalasi perangkat lunak.

## Pengujian Sistem

Pengujian diperlukan untuk memastikan bahwa setiap komponen berfungsi sesuai kebutuhan dan seluruh sistem dapat bekerja secara terintegrasi.

Area pengujian yang disarankan meliputi:

1. **Pengujian autentikasi:** memeriksa login, pengelolaan sesi, dan hak akses pengguna.
2. **Pengujian validasi masukan:** memeriksa format berkas, parameter wajib, dan penanganan masukan tidak valid.
3. **Pengujian API:** memeriksa respons endpoint, kode status, dan penanganan kesalahan.
4. **Pengujian pipeline:** memeriksa eksekusi perangkat lunak, dependensi, keluaran, dan penanganan kegagalan.
5. **Pengujian basis data:** memeriksa relasi, integritas data, dan pembatasan akses.
6. **Pengujian integrasi:** memeriksa komunikasi antara frontend, backend, basis data, dan perangkat lunak eksternal.
7. **Pengujian end-to-end:** menjalankan analisis lengkap menggunakan dataset pengujian dan mengevaluasi hasil varian yang dihasilkan.

Pengujian menggunakan dataset dengan hasil yang diketahui dapat membantu mengevaluasi konsistensi keluaran pipeline.

## Batasan Sistem

Kemampuan MutaTrack bergantung pada perangkat lunak yang terintegrasi, konfigurasi pipeline, genom referensi, dan kapasitas lingkungan komputasi.

Beberapa hal yang perlu diperhatikan:

- Dataset sekuensing berukuran besar dapat membutuhkan waktu pemrosesan dan memori yang signifikan.
- Genom referensi beserta indeksnya harus sesuai dengan kebutuhan analisis.
- Hasil analisis dapat berbeda akibat perubahan versi perangkat lunak, parameter, atau konfigurasi pipeline.
- Berkas antara membutuhkan ruang penyimpanan dan pengaturan akses yang memadai.
- Hasil variant calling dan anotasi perlu divalidasi sebelum digunakan sebagai dasar kesimpulan penelitian.

## Rencana Pengembangan

Pengembangan berikutnya dapat difokuskan pada:

- Penyempurnaan manajemen eksekusi pipeline dan pekerjaan latar belakang.
- Penambahan indikator progres serta pelaporan kesalahan yang terstruktur.
- Pengembangan pilihan penyaringan dan anotasi varian.
- Penyediaan ekspor hasil dan laporan analisis.
- Pengembangan visualisasi statistik varian dan metrik kualitas.
- Pencatatan versi perangkat lunak, parameter, dan genom referensi untuk meningkatkan reproduktibilitas.
- Peningkatan pengujian otomatis, keamanan, dan proses deployment.
- Peningkatan pengelolaan data untuk mendukung dataset yang lebih besar.

## Kontribusi

Kontribusi berupa pengembangan fitur, perbaikan kode, dokumentasi, dan pengujian dapat dilakukan melalui repository GitHub.

Langkah kontribusi:

1. Fork repository.
2. Buat branch baru untuk fitur atau perbaikan.
3. Implementasikan perubahan dan lakukan pengujian.
4. Buat commit dengan pesan yang menjelaskan perubahan.
5. Ajukan pull request beserta deskripsi perubahan dan hasil pengujian.

Setiap perubahan yang memengaruhi pipeline, kontrak API, atau skema basis data sebaiknya disertai dokumentasi yang relevan.

## Lisensi

Lisensi proyek belum ditetapkan dalam dokumen ini. Tambahkan berkas `LICENSE` dan perbarui bagian ini setelah lisensi proyek dipilih.

---

**MutaTrack** — Integrasi alur kerja bioinformatika untuk analisis varian genetik yang terstruktur dan terotomatisasi.
