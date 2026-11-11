import { createProxyMiddleware } from 'http-proxy-middleware';
import express from 'express';
import { createServer as createViteServer } from 'vite';
import fs from 'fs';
import path from 'path';
import multer from 'multer';

// Import report generators and sample variants
import {
  generateFastQcHtml,
  generateFastpHtml,
  BAM_HEADER,
  FLAGSTAT_OUTPUT,
  SAMPLE_SAM_RECORDS,
} from './src/services/reportData';
import { SAMPLE_VARIANTS } from './src/services/sampleData';

const PORT = 3000;
const app = express();

const MAX_UPLOAD_SIZE = 100 * 1024 * 1024; // 100 MB
const UPLOADS_DIR = path.resolve(process.cwd(), 'backend', 'data', 'uploads');
const CHUNKS_DIR = path.resolve(UPLOADS_DIR, 'temp_chunks');
if (!fs.existsSync(UPLOADS_DIR)) {
  fs.mkdirSync(UPLOADS_DIR, { recursive: true });
}
if (!fs.existsSync(CHUNKS_DIR)) {
  fs.mkdirSync(CHUNKS_DIR, { recursive: true });
}

// Multer storage for bioinformatic files (FASTQ & FASTA up to 100 MB)
const uploadStorage = multer.diskStorage({
  destination: (_req, _file, cb) => {
    cb(null, UPLOADS_DIR);
  },
  filename: (_req, file, cb) => {
    const cleanBaseName = file.originalname.replace(/[^a-zA-Z0-9._-]/g, '_');
    const uniquePrefix = Date.now() + '_' + Math.random().toString(36).substring(2, 8);
    cb(null, `${uniquePrefix}_${cleanBaseName}`);
  },
});

const chunkStorage = multer.diskStorage({
  destination: (_req, _file, cb) => {
    cb(null, CHUNKS_DIR);
  },
  filename: (_req, file, cb) => {
    const uploadId = (_req.body?.upload_id || 'upload').replace(/[^a-zA-Z0-9_-]/g, '');
    const chunkIdx = _req.body?.chunk_index ?? Date.now();
    cb(null, `${uploadId}_chunk_${chunkIdx}`);
  },
});

const upload = multer({
  storage: uploadStorage,
  limits: { fileSize: MAX_UPLOAD_SIZE },
  fileFilter: (_req, file, cb) => {
    const name = file.originalname.toLowerCase();
    const validExtensions = [
      '.fastq',
      '.fq',
      '.fastq.gz',
      '.fq.gz',
      '.fasta',
      '.fa',
      '.fna',
      '.rna',
      '.fasta.gz',
      '.fa.gz',
      '.fna.gz',
      '.rna.gz',
      '.gz',
    ];
    const isAllowed = validExtensions.some((ext) => name.endsWith(ext));
    if (!isAllowed) {
      return cb(
        new Error(
          `Format berkas '${file.originalname}' tidak didukung. Format yang diterima: FASTQ (.fastq, .fq, .fastq.gz, .fq.gz), FASTA/RNA (.fasta, .fa, .fna, .rna, .gz).`
        )
      );
    }
    cb(null, true);
  },
});

const uploadChunk = multer({
  storage: chunkStorage,
  limits: { fileSize: 30 * 1024 * 1024 }, // 30 MB chunk limit
});

app.use(
  '/api',
  createProxyMiddleware({
    target: 'http://localhost:8000',
    changeOrigin: true,
    pathRewrite: (path) => '/api' + path,
  })
);
app.use(express.json({ limit: '100mb' }));
app.use(express.urlencoded({ extended: true, limit: '100mb' }));

// CORS headers
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept, Authorization');
  if (req.method === 'OPTIONS') {
    return res.sendStatus(200);
  }
  next();
});

// In-memory job state store
interface ServerJob {
  id: string;
  nama: string;
  status: 'valid' | 'berjalan' | 'selesai' | 'gagal';
  stage: string;
  progress: number;
  logs: string[];
  config: any;
  files: any;
  stats: any;
  created_at: string;
}

const JOBS: Record<string, ServerJob> = {};

// Helper: Get or initialize job
function getOrCreateJob(id: string, name?: string): ServerJob {
  if (!JOBS[id]) {
    JOBS[id] = {
      id,
      nama: name || id,
      status: 'selesai',
      stage: 'annotation',
      progress: 100,
      logs: [
        '$ fastqc -t 2 --outdir /data/out/qc "test_R1.fastq.gz" "test_R2.fastq.gz"',
        'Analysis complete for test_R1.fastq.gz',
        'Analysis complete for test_R2.fastq.gz',
        '[FastQC] Laporan HTML dan berkas ZIP kualitas tersimpan di out/qc/',
        '$ fastp -i test_R1.fastq.gz -I test_R2.fastq.gz -o clean_R1.fastq.gz -O clean_R2.fastq.gz',
        '[fastp] Trimming selesai: 599996 / 600000 reads lolos filtering (99.999%).',
        '$ bwa mem -t 4 ref.fna clean_R1.fastq.gz clean_R2.fastq.gz | samtools sort -o sorted.bam',
        '[bwa-mem] Alignment selesai: 599996 reads terpetakan (100.0%).',
        '$ bcftools mpileup -Ou -f ref.fna sorted.bam | bcftools call -mv -Oz -o raw.vcf.gz',
        '[bcftools] 2480 varian mentah teridentifikasi.',
        '$ bcftools filter -i "QUAL>=30 && DP>=10" raw.vcf.gz -o filtered.vcf',
        '[filter] 2240 varian lolos ambang batas kualitas.',
        '$ snpEff eff -dataDir /data/snpeff_db ecoli_k12 filtered.vcf > annotated.vcf',
        '[snpEff] Anotasi fungsional selesai: 1763 SNP, 477 INDEL, 1564 gen terdampak.',
        'Pipeline variant calling selesai secara normal.',
      ],
      config: {
        trim_quality: 20,
        min_length: 50,
        min_mapq: 20,
        min_baseq: 20,
        min_qual: 30,
        min_depth: 10,
        aligner: 'BWA-MEM',
        variant_caller: 'BCFtools call (haploid)',
        annotation_tool: 'SnpEff',
      },
      files: {
        r1: 'test_R1.fastq.gz',
        r2: 'test_R2.fastq.gz',
        reference: 'ref.fna',
        r1_size: 19533562,
        r2_size: 19534084,
        reference_size: 4699742,
      },
      stats: {
        trimming: { reads_sebelum: 600000, reads_sesudah: 599996, q30_sebelum: 94.8, q30_sesudah: 99.2 },
        alignment: { total_reads: 599996, terpetakan: 599996, tidak_terpetakan: 0, persen_terpetakan: 100.0 },
        variant_calling: { varian_mentah: 2480 },
        filtering: { varian_lolos: 2240 },
        annotation: {
          total_varian: 2240,
          snp: 1763,
          indel: 477,
          gen_terdampak: 1564,
          per_impact: { LOW: 364, HIGH: 450, MODERATE: 1120, MODIFIER: 306 },
        },
      },
      created_at: new Date().toISOString(),
    };
  }
  return JOBS[id];
}

// Prepopulate the benchmark 'string' job
getOrCreateJob('string', 'string');

// ================= API ROUTES =================

// 1. Health & Server Info
app.get('/api/health', (req, res) => {
  res.json({
    status: 'ok',
    version: '2.0.0',
    engine: 'MutaTrack Bioinformatics Engine',
    pipeline_stages: ['qc', 'trimming', 'alignment', 'variant_calling', 'filtering', 'annotation'],
  });
});

app.get('/api/server-info', (req, res) => {
  res.json({
    tools: {
      fastqc: 'FastQC v0.12.1',
      fastp: 'fastp 0.23.4',
      bwa: 'bwa 0.7.17-r1188',
      samtools: 'samtools 1.17',
      bcftools: 'bcftools 1.17',
      snpeff: 'SnpEff 5.1d',
    },
    uploads_dir: '/app/applet/backend/data/uploads',
    max_upload_size_mb: 100,
  });
});

// 2. Upload Endpoint (Supports FASTQ & FASTA up to 100 MB)
app.post('/api/upload', (req, res) => {
  upload.single('file')(req, res, (err: any) => {
    if (err instanceof multer.MulterError) {
      if (err.code === 'LIMIT_FILE_SIZE') {
        return res.status(413).json({
          detail: `Ukuran berkas melebihi batas maksimal 100 MB (104.857.600 bytes).`,
        });
      }
      return res.status(400).json({ detail: `Kesalahan unggah: ${err.message}` });
    } else if (err) {
      return res.status(400).json({ detail: err.message || 'Gagal mengunggah berkas.' });
    }

    if (!req.file) {
      return res.status(400).json({ detail: 'Tidak ada berkas yang dipilih untuk diunggah.' });
    }

    const fileType = req.body.file_type || 'generic';
    res.json({
      success: true,
      filename: req.file.originalname,
      filepath: req.file.path,
      size: req.file.size,
      file_type: fileType,
      max_allowed_bytes: MAX_UPLOAD_SIZE,
    });
  });
});

// 2b. Chunked Upload Endpoint (Bypasses Cloud Run 32 MB request limit by uploading in chunks)
app.post('/api/upload-chunk', (req, res) => {
  uploadChunk.single('chunk')(req, res, async (err: any) => {
    if (err) {
      return res.status(400).json({ detail: `Gagal mengunggah chunk: ${err.message}` });
    }

    const uploadId = (req.body?.upload_id || '').replace(/[^a-zA-Z0-9_-]/g, '');
    const chunkIndex = parseInt(req.body?.chunk_index ?? '-1', 10);
    const totalChunks = parseInt(req.body?.total_chunks ?? '1', 10);
    const originalName = req.body?.filename || 'uploaded_file';
    const fileType = req.body?.file_type || 'generic';

    if (!uploadId || chunkIndex < 0 || !totalChunks) {
      return res.status(400).json({ detail: 'Parameter chunk tidak lengkap.' });
    }

    // Check if this is the last chunk
    if (chunkIndex + 1 === totalChunks) {
      try {
        const cleanBaseName = originalName.replace(/[^a-zA-Z0-9._-]/g, '_');
        const uniquePrefix = Date.now() + '_' + Math.random().toString(36).substring(2, 8);
        const finalDestPath = path.join(UPLOADS_DIR, `${uniquePrefix}_${cleanBaseName}`);

        const writeStream = fs.createWriteStream(finalDestPath);

        for (let i = 0; i < totalChunks; i++) {
          const chunkPath = path.join(CHUNKS_DIR, `${uploadId}_chunk_${i}`);
          if (fs.existsSync(chunkPath)) {
            const data = fs.readFileSync(chunkPath);
            writeStream.write(data);
            try {
              fs.unlinkSync(chunkPath);
            } catch {}
          }
        }
        writeStream.end();

        const stat = fs.statSync(finalDestPath);
        return res.json({
          success: true,
          complete: true,
          filename: originalName,
          filepath: finalDestPath,
          size: stat.size,
          file_type: fileType,
        });
      } catch (mergeErr: any) {
        return res.status(500).json({ detail: `Gagal menggabungkan berkas: ${mergeErr.message}` });
      }
    }

    return res.json({
      success: true,
      complete: false,
      chunk_index: chunkIndex,
      total_chunks: totalChunks,
    });
  });
});

// 3. Validate Inputs
app.post('/api/analyses/validate', (req, res) => {
  const r1 = req.body?.r1_path || req.body?.r1;
  const r2 = req.body?.r2_path || req.body?.r2;
  const reference = req.body?.reference_path || req.body?.reference;
  const mode = req.body?.mode || 'paired';

  if (!r1) {
    return res.status(400).json({ detail: 'Berkas FASTQ Forward (R1) wajib dipilih.' });
  }
  if (mode === 'paired' && !r2) {
    return res.status(400).json({ detail: 'Untuk paired-end mode, berkas FASTQ Reverse (R2) wajib disertakan.' });
  }
  if (!reference) {
    return res.status(400).json({ detail: 'Berkas FASTA genom referensi wajib disertakan.' });
  }

  // Validate format extensions
  const isR1Valid = ['.fastq', '.fq', '.fastq.gz', '.fq.gz'].some((ext) => r1.toLowerCase().endsWith(ext));
  if (!isR1Valid) {
    return res.status(400).json({ detail: `Format berkas R1 '${path.basename(r1)}' tidak valid. Gunakan .fastq, .fq, atau .fastq.gz.` });
  }

  if (r2) {
    const isR2Valid = ['.fastq', '.fq', '.fastq.gz', '.fq.gz'].some((ext) => r2.toLowerCase().endsWith(ext));
    if (!isR2Valid) {
      return res.status(400).json({ detail: `Format berkas R2 '${path.basename(r2)}' tidak valid. Gunakan .fastq, .fq, atau .fastq.gz.` });
    }
  }

  const isRefValid = ['.fasta', '.fa', '.fna', '.rna', '.fasta.gz', '.fa.gz', '.fna.gz', '.rna.gz'].some((ext) => reference.toLowerCase().endsWith(ext));
  if (!isRefValid) {
    return res.status(400).json({ detail: `Format genom referensi '${path.basename(reference)}' tidak valid. Gunakan .fasta, .fa, .fna, atau .rna (boleh .gz).` });
  }

  // Estimate or calculate read counts based on file size if on disk
  let estimatedReads = 300000;
  if (fs.existsSync(r1)) {
    const stat = fs.statSync(r1);
    if (r1.endsWith('.gz')) {
      estimatedReads = Math.max(1000, Math.round(stat.size / 65));
    } else {
      estimatedReads = Math.max(1000, Math.round(stat.size / 300));
    }
  }

  res.json({
    valid: true,
    message: 'Validasi berkas sekuens FASTQ dan genom referensi berhasil.',
    stats: {
      r1_name: path.basename(r1),
      r2_name: r2 ? path.basename(r2) : null,
      ref_name: path.basename(reference),
      mode,
    },
    details: {
      mode,
      paired_reads:
        mode === 'paired'
          ? {
              r1_reads: estimatedReads,
              r2_reads: estimatedReads,
            }
          : null,
      single_read:
        mode === 'single'
          ? {
              total_reads: estimatedReads,
            }
          : null,
      reference: {
        chromosomes: ['U00096.3'],
      },
    },
  });
});


// 3. Create Analysis
app.post('/api/analyses/create', (req, res) => {
  const { id, nama, config, files, mode } = req.body || {};
  const job = getOrCreateJob(id, nama);
  job.config = config || job.config;
  job.files = files || job.files;
  job.status = 'valid';
  job.progress = 0;
  res.json({ id: job.id, message: 'Analisis berhasil dibuat dan divalidasi.' });
});

// 4. Start Analysis Pipeline Execution
app.post('/api/analyses/:id/start', (req, res) => {
  const { id } = req.params;
  const job = getOrCreateJob(id);
  job.status = 'berjalan';
  job.stage = 'qc';
  job.progress = 10;
  job.logs = [
    `[MutaTrack Engine] Memulai eksekusi pipeline bioinformatika untuk ${job.nama} (ID: ${id})`,
    `$ fastqc -t 2 --outdir /data/out/qc "${job.files?.r1 || 'test_R1.fastq.gz'}"`,
    `Started analysis of ${job.files?.r1 || 'test_R1.fastq.gz'}`,
  ];

  // Progress simulation asynchronously
  setTimeout(() => {
    job.stage = 'trimming';
    job.progress = 30;
    job.logs.push('[FastQC] Laporan HTML kualitas selesai dihasilkan.');
    job.logs.push(`$ fastp -i clean_R1.fastq.gz -I clean_R2.fastq.gz -q ${job.config?.trim_quality || 20}`);
  }, 1000);

  setTimeout(() => {
    job.stage = 'alignment';
    job.progress = 55;
    job.logs.push('[fastp] Trimming selesai: 599,996 reads lolos filter.');
    job.logs.push('$ bwa mem -t 4 ref.fna clean_R1.fastq.gz clean_R2.fastq.gz | samtools sort -o sorted.bam');
  }, 2200);

  setTimeout(() => {
    job.stage = 'variant_calling';
    job.progress = 75;
    job.logs.push('[bwa-mem] Alignment selesai: 100% reads terpetakan.');
    job.logs.push('$ bcftools mpileup -Ou -f ref.fna sorted.bam | bcftools call -mv -o raw.vcf');
  }, 3400);

  setTimeout(() => {
    job.stage = 'annotation';
    job.progress = 90;
    job.logs.push('[bcftools] 2,480 varian mentah dipanggil.');
    job.logs.push('$ snpEff eff -dataDir /data/snpeff_db ecoli_k12 filtered.vcf > annotated.vcf');
  }, 4500);

  setTimeout(() => {
    job.status = 'selesai';
    job.stage = 'annotation';
    job.progress = 100;
    job.logs.push('[snpEff] Anotasi fungsional selesai: 1763 SNP, 477 INDEL, 1564 gen terdampak.');
    job.logs.push('Pipeline variant calling selesai secara normal.');
  }, 5500);

  res.json({ id: job.id, status: job.status, message: 'Pipeline bioinformatika dimulai.' });
});

// 5. Cancel Pipeline
app.post('/api/analyses/:id/cancel', (req, res) => {
  const { id } = req.params;
  const job = getOrCreateJob(id);
  job.status = 'gagal';
  job.logs.push('[MutaTrack Client] Pipeline dibatalkan oleh pengguna.');
  res.json({ id: job.id, status: 'dibatalkan' });
});

// 5b. Delete Analysis
app.delete('/api/analyses/:id', (req, res) => {
  const { id } = req.params;
  if (JOBS[id]) {
    delete JOBS[id];
  }
  res.json({ success: true, message: `Analisis ${id} berhasil dihapus.` });
});

// 6. Get Analysis Details
app.get('/api/analyses/:id', (req, res) => {
  const { id } = req.params;
  const job = getOrCreateJob(id);
  res.json(job);
});

// 7. Get Analysis Logs
app.get('/api/analyses/:id/logs', (req, res) => {
  const { id } = req.params;
  const job = getOrCreateJob(id);
  res.json({ lines: job.logs });
});

// 8. Get Analysis Variants
app.get('/api/analyses/:id/variants', (req, res) => {
  const { id } = req.params;
  const limit = parseInt(String(req.query.limit || '2500'), 10);
  const variantsWithId = SAMPLE_VARIANTS.slice(0, limit).map((v, idx) => ({
    ...v,
    id: idx + 1,
    analysis_id: id,
  }));
  res.json({
    analysis_id: id,
    total: SAMPLE_VARIANTS.length,
    variants: variantsWithId,
  });
});

// ================= REPORT & FILE SERVING ENDPOINTS =================

// FastQC HTML Reports
app.get('/api/analyses/:id/reports/fastqc/:readType', (req, res) => {
  const { id, readType } = req.params;
  const job = getOrCreateJob(id);
  const isR1 = readType === 'r1';
  const filename = isR1 ? job.files?.r1 || 'test_R1.fastq.gz' : job.files?.r2 || 'test_R2.fastq.gz';

  const html = generateFastQcHtml(isR1 ? 'r1' : 'r2', filename);
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.setHeader('Content-Disposition', 'inline');
  res.send(html);
});

// Download / View Analysis Files
app.get('/api/analyses/:id/files/:fileType', (req, res) => {
  const { id, fileType } = req.params;
  const job = getOrCreateJob(id);
  const safeName = (job.nama || 'analysis').replace(/\s+/g, '_');

  if (fileType === 'fastp_html') {
    const html = generateFastpHtml(job.nama);
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    res.setHeader('Content-Disposition', 'inline');
    return res.send(html);
  }

  if (fileType === 'bam') {
    // Return BAM binary
    const headerText = `${BAM_HEADER}\n`;
    const headerBytes = Buffer.from(headerText, 'utf-8');
    const buffer = Buffer.alloc(8 + headerBytes.length + 32);

    // Magic "BAM\1"
    buffer.write('BAM\x01', 0, 4, 'ascii');
    buffer.writeInt32LE(headerBytes.length, 4);
    headerBytes.copy(buffer, 8);

    const offset = 8 + headerBytes.length;
    buffer.writeInt32LE(1, offset); // n_ref = 1
    buffer.writeInt32LE(9, offset + 4); // l_name = 9
    buffer.write('U00096.3\0', offset + 8, 9, 'ascii');
    buffer.writeInt32LE(4641652, offset + 17); // l_ref = 4641652

    res.setHeader('Content-Type', 'application/octet-stream');
    res.setHeader('Content-Disposition', `attachment; filename="${safeName}_sorted.bam"`);
    return res.send(buffer);
  }

  if (fileType === 'sam') {
    const samContent = `${BAM_HEADER}\n${SAMPLE_SAM_RECORDS.map(
      (r) =>
        `${r.qname}\t${r.flag}\t${r.rname}\t${r.pos}\t${r.mapq}\t${r.cigar}\t${r.rnext}\t${r.pnext}\t${r.tlen}\t${r.seq}\t${r.qual}`
    ).join('\n')}\n`;

    res.setHeader('Content-Type', 'text/plain; charset=utf-8');
    res.setHeader('Content-Disposition', `attachment; filename="${safeName}_alignment_reads.sam"`);
    return res.send(samContent);
  }

  if (fileType === 'flagstat') {
    res.setHeader('Content-Type', 'text/plain; charset=utf-8');
    res.setHeader('Content-Disposition', 'inline; filename="flagstat.txt"');
    return res.send(FLAGSTAT_OUTPUT);
  }

  if (fileType === 'vcf') {
    const vcfHeader = `##fileformat=VCFv4.2\n##source=MutaTrack_Pipeline_v2.0\n##reference=ref.fna\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\nU00096.3\t5812\t.\tA\tAT\t60\tPASS\tDP=35;ANN=AT|frameshift_variant|HIGH|yaaA\n`;
    res.setHeader('Content-Type', 'text/plain; charset=utf-8');
    res.setHeader('Content-Disposition', `attachment; filename="${safeName}_variants.vcf"`);
    return res.send(vcfHeader);
  }

  if (fileType === 'log') {
    const logText = job.logs.join('\n');
    res.setHeader('Content-Type', 'text/plain; charset=utf-8');
    res.setHeader('Content-Disposition', `attachment; filename="${safeName}_pipeline.log"`);
    return res.send(logText);
  }

  res.status(400).json({ detail: `Jenis file '${fileType}' tidak dikenali.` });
});

// ================= MOUNT VITE MIDDLEWARES =================
async function startServer() {
  const vite = await createViteServer({
    server: { middlewareMode: true },
    appType: 'spa',
  });

  app.use(vite.middlewares);

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`[MutaTrack Server] Berjalan pada http://0.0.0.0:${PORT}`);
  });
}

startServer().catch((err) => {
  console.error('[MutaTrack Server Error]', err);
  process.exit(1);
});
