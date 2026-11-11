# MutaTrack — Platform Bioinformatika untuk Analisis Variant Calling

**MutaTrack** adalah aplikasi web bioinformatika berbasis React + TypeScript untuk visualisasi, pengelolaan, dan eksekusi alur kerja *variant calling* sekuensing DNA mikroorganisme (*Escherichia coli*).

Aplikasi ini di-porting dari repositori Pembangunan Perangkat Lunak Bioinformatika IPB University (Kelompok 07).

---

## Fitur Utama

- **Otomasi 6 Tahap Pipeline Bioinformatika**:
  1. **Kontrol Kualitas (FastQC)**: Evaluasi kualitas sekuens Phred dan GC content.
  2. **Pemrosesan Sekuens (fastp)**: Pemotongan adapter, filtering kualitas basa (`-q`), dan panjang bacaan (`-l`).
  3. **Alignment Genom (BWA-MEM & SAMtools)**: Pemetaan sekuens terhadap genom referensi, sorting koordinat, pengindeksan BAM, dan statistik flagstat persentase terpetakan.
  4. **Variant Calling (BCFtools)**: Identifikasi kandidat varian haploid (*E. coli* ploidy 1) menggunakan mpileup dan call (`-mv`).
  5. **Penyaringan Varian (BCFtools filter)**: Eliminasi false-positives berdasarkan skor kualitas (`QUAL >= min_qual`) dan kedalaman bacaan (`INFO/DP >= min_depth`).
  6. **Anotasi Fungsional (SnpEff)**: Karakterisasi varian menjadi dampak HIGH (Stop Gained, Frameshift), MODERATE (Missense), LOW (Sinomin), serta identifikasi gen terdampak (*gyrA*, *rpoB*, *katG*, *ampC*, dll).

- **Manajemen Proyek Analisis**:
  - Pembuatan analisis baru dengan berkas FASTQ R1 (forward), R2 (reverse/paired-end), dan FASTA referensi.
  - Preset data uji *E. coli K-12 MG1655* dengan 1-klik untuk pengujian cepat.
  - Validasi integritas berkas masukan (struktur FASTQ `@`/`+` dan header FASTA `>`).
  - Penyetelan parameter pipeline secara interaktif (`trim_quality`, `min_length`, `min_mapq`, `min_baseq`, `min_qual`, `min_depth`).

- **Visualisasi Metrik & Tabel Varian Interaktif**:
  - Dashboard analitik: persentase alignment terpetakan, rasio Q30 sebelum dan sesudah trimming, perbandingan kandidat varian lolos filter vs gugur, dan distribusi dampak fungsional.
  - Tabel varian dengan pencarian gen/efek, filter dampak (HIGH, MODERATE, LOW, MODIFIER), filter tipe (SNP, INDEL), pengurutan kolom, dan paginasi.

- **Ekspor & Unduhan Terstandardisasi**:
  - **VCF v4.2**: Berkas Variant Call Format lengkap dengan field SnpEff ANN dan depth DP.
  - **CSV**: Rekapitulasi tabel seluruh varian untuk analisis data lanjutan.
  - **Laporan Dokumen PDF**: Laporan ringkasan metrik dan daftar varian yang siap dicetak.
  - **Log Eksekusi**: Berkas catatan log proses command line (`.log`).

- **Terminal Log Eksekusi Live**:
  - Pemantauan eksekusi langkah demi langkah dengan indikator ANSI/highlight perintah bash dan auto-scroll.

---

## Struktur Proyek

Repositori ini kini memiliki pembagian direktori yang terpisah dan terorganisir antara **Frontend** dan **Backend**:

```
.
├── backend/                  # MODUL BACKEND (Python, Docker, Pipeline & Database)
│   ├── Dockerfile            # Konfigurasi container Bioconda & Python 3.10
│   ├── docker-compose.yml    # Orkestrasi backend service + database MySQL
│   ├── main.py               # REST API Server FastAPI (CORS, background tasks)
│   ├── pipeline.py           # Eksekutor 6 tahap pipeline (FastQC, fastp, BWA, BCFtools, SnpEff)
│   ├── schema.sql            # Skema basis data SQL (users, analyses, variants, logs)
│   ├── config.py             # Pengaturan konfigurasi & environment
│   ├── requirements.txt      # Dependensi Python
│   └── README.md             # Panduan menjalankan backend
│
├── frontend/                 # MODUL FRONTEND (React 19 + TypeScript + Vite)
│   ├── src/                  # Kode sumber antarmuka (komponen, layanan, tipe data)
│   │   ├── components/       # LandingView, Dashboard, VariantTable, LogTerminal, dll.
│   │   ├── services/         # pipelineRunner, exportService, storage, sampleData
│   │   ├── types/            # TypeScript interfaces (Analysis, Variant, PipelineConfig)
│   │   ├── App.tsx           # Komponen root aplikasi
│   │   └── main.tsx          # React DOM entry point
│   ├── public/               # Aset statis (DNA Helix 3D, ikon)
│   ├── package.json          # Dependensi npm frontend
│   └── README.md             # Panduan menjalankan frontend
│
└── README.md                 # Dokumentasi utama proyek
```

---

## Teknologi yang Digunakan

- **Frontend**: React 19, TypeScript, Vite
- **Styling**: Tailwind CSS v4
- **Backend API**: Python 3.10, FastAPI, Uvicorn, Pydantic
- **Bioinformatics Tools**: FastQC, fastp, BWA-MEM, SAMtools, BCFtools, SnpEff
- **Database**: MySQL / PostgreSQL (didukung `backend/schema.sql`)
- **Kontainer**: Docker & Docker Compose
- **Komponen & Ikon**: Lucide React
- **Ekspor Dokumen**: jsPDF (PDF), VCF v4.2 generator, CSV exporter
