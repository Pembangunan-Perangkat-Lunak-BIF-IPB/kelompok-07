import json
import os
import shutil
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .alignment import run_alignment_stage
from .annotation import run_annotation_stage
from .filtering import run_filtering_stage
from .qc import run_fastqc_stage
from .trimming import run_fastp_stage
from .utils import SubprocessRunner, PipelineCancelledException, ensure_dir
from .validator import validate_pipeline_inputs
from .variant_calling import run_variant_calling_stage

# Concurrency lock to prevent multiple bioinformatics jobs running concurrently
PIPELINE_SEMAPHORE = threading.Semaphore(1)

class AnalysisJob:
    def __init__(
        self,
        analysis_id: str,
        name: str,
        files: Dict[str, Any],
        config: Dict[str, Any],
        mode: str = "paired",
        data_root: str = "/backend/data",
    ):
        self.analysis_id = analysis_id
        self.name = name
        self.files = files
        self.config = config
        self.mode = mode
        self.data_root = data_root

        self.analysis_dir = os.path.join(data_root, "analyses", analysis_id)
        self.inputs_dir = os.path.join(self.analysis_dir, "inputs")
        self.out_dir = os.path.join(self.analysis_dir, "out")

        self.status = "draf"  # draf, berjalan, selesai, gagal, dibatalkan
        self.stage: Optional[str] = None
        self.progress: int = 0
        self.logs: List[str] = []
        self.error: Optional[str] = None
        self.stats: Dict[str, Any] = {}
        self.variants: List[Dict[str, Any]] = []

        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at

        self.runner = SubprocessRunner()
        self.thread: Optional[threading.Thread] = None
        self.on_save: Optional[Callable[[Any], None]] = None  # hook sinkronisasi database

    def log(self, line: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {line}"
        self.logs.append(log_line)
        # Also write to pipeline.log
        try:
            log_path = os.path.join(self.analysis_dir, "pipeline.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(log_line + "\n")
        except Exception:
            pass

    def cancel(self):
        self.log("[PERINGATAN] Sinyal pembatalan diterima dari pengguna.")
        self.runner.cancel()
        self.status = "gagal"
        self.error = "Pipeline dibatalkan oleh pengguna."
        self.updated_at = datetime.now().isoformat()
        self.save_metadata()

    def save_metadata(self):
        ensure_dir(self.analysis_dir)
        meta_path = os.path.join(self.analysis_dir, "analysis.json")
        data = {
            "id": self.analysis_id,
            "nama": self.name,
            "status": self.status,
            "stage": self.stage,
            "progress": self.progress,
            "mode": self.mode,
            "config": self.config,
            "files": self.files,
            "stats": self.stats,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "log_tail": "\n".join(self.logs[-30:]),
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        if self.variants:
            var_path = os.path.join(self.analysis_dir, "variants.json")
            with open(var_path, "w", encoding="utf-8") as f:
                json.dump(self.variants, f, indent=2)

        if self.on_save:
            try:
                self.on_save(self)
            except Exception:
                pass  # kegagalan database tidak boleh menghentikan pipeline

    def execute_sync(self):
        ensure_dir(self.analysis_dir)
        ensure_dir(self.out_dir)

        self.status = "berjalan"
        self.progress = 5
        self.save_metadata()

        r1_path = self.files.get("r1")
        r2_path = self.files.get("r2")
        ref_path = self.files.get("reference")

        trim_quality = int(self.config.get("trim_quality", 20))
        min_length = int(self.config.get("min_length", 50))
        min_mapq = int(self.config.get("min_mapq", 20))
        min_baseq = int(self.config.get("min_baseq", 20))
        min_qual = float(self.config.get("min_qual", 30))
        min_depth = int(self.config.get("min_depth", 10))
        snpeff_db = self.config.get("snpeff_db", "")
        annotation_mode = self.config.get("annotation_mode", "none")
        annotation_path = self.files.get("annotation")
        ploidy = int(self.config.get("ploidy", 1))

        self.log(f"================================================================================")
        self.log(f"MutaTrack Bioinformatics Production Pipeline")
        self.log(f"Analisis: {self.name} (ID: {self.analysis_id})")
        self.log(f"Mode: {'Paired-End' if self.mode == 'paired' else 'Single-End'}")
        self.log(f"Waktu Mulai: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.log(f"Reference: {ref_path}")
        self.log(f"R1: {r1_path}")
        if r2_path:
            self.log(f"R2: {r2_path}")
        self.log(f"Konfigurasi Parameter:")
        self.log(f"  - fastp: trim_quality={trim_quality}, min_length={min_length}")
        self.log(f"  - bcftools mpileup: min_mapq={min_mapq}, min_baseq={min_baseq}, ploidy={ploidy}")
        self.log(f"  - bcftools filter: min_qual={min_qual}, min_depth={min_depth}")
        self.log(f"  - Anotasi: mode={annotation_mode}, db={snpeff_db or '-'}, file={annotation_path or '-'}")
        self.log(f"================================================================================")

        acquired = PIPELINE_SEMAPHORE.acquire(timeout=5)
        if not acquired:
            self.log("[Antrean] Menunggu proses pipeline lain selesai...")
            PIPELINE_SEMAPHORE.acquire()

        try:
            # 0. Validate
            self.log("[Validasi] Memeriksa integritas berkas masukan...")
            val_result = validate_pipeline_inputs(r1_path, r2_path, ref_path, self.mode)
            self.log("[Validasi] Seluruh berkas masukan lolos validasi format.")

            # Stage 1: FastQC
            self.stage = "qc"
            self.progress = 12
            self.save_metadata()
            qc_dir = os.path.join(self.out_dir, "qc")
            qc_stats = run_fastqc_stage(r1_path, r2_path, qc_dir, self.runner, self.log)
            self.stats["qc"] = qc_stats

            # Stage 2: fastp
            self.stage = "trimming"
            self.progress = 28
            self.save_metadata()
            trim_dir = os.path.join(self.out_dir, "trimming")
            trim_stats, clean_r1, clean_r2 = run_fastp_stage(
                r1_path, r2_path, trim_dir, trim_quality, min_length, self.runner, self.log
            )
            self.stats["trimming"] = trim_stats

            # Stage 3: Alignment (BWA-MEM + SAMtools)
            self.stage = "alignment"
            self.progress = 50
            self.save_metadata()
            align_dir = os.path.join(self.out_dir, "alignment")
            align_stats, sorted_bam = run_alignment_stage(
                ref_path, clean_r1, clean_r2, align_dir, self.runner, self.log
            )
            self.stats["alignment"] = align_stats

            # Stage 4: Variant Calling (BCFtools)
            self.stage = "variant_calling"
            self.progress = 72
            self.save_metadata()
            var_dir = os.path.join(self.out_dir, "variants")
            call_stats, raw_vcf = run_variant_calling_stage(
                ref_path, sorted_bam, var_dir, min_mapq, min_baseq, ploidy, self.runner, self.log
            )
            self.stats["variant_calling"] = call_stats

            # Stage 5: Variant Filtering (BCFtools filter)
            self.stage = "filtering"
            self.progress = 85
            self.save_metadata()
            filt_stats, filtered_vcf = run_filtering_stage(
                raw_vcf, var_dir, min_qual, min_depth, self.runner, self.log
            )
            self.stats["filtering"] = filt_stats

            # Stage 6: Functional Annotation (SnpEff)
            self.stage = "annotation"
            self.progress = 94
            self.save_metadata()
            ann_dir = os.path.join(self.out_dir, "annotation")
            ann_stats, annotated_vcf, variants = run_annotation_stage(
            filtered_vcf, ann_dir, self.analysis_id,
            annotation_mode, snpeff_db, annotation_path, ref_path,
            self.runner, self.log,
            )
            self.stats["annotation"] = ann_stats
            self.variants = variants

            # Completed!
            self.status = "selesai"
            self.progress = 100
            self.updated_at = datetime.now().isoformat()
            self.log(f"\n================================================================================")
            self.log(f"Pipeline Bioinformatika Selesai Secara Sukses!")
            self.log(f"Waktu Selesai: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self.log(f"Hasil: {ann_stats['total_varian']} varian terverifikasi ({ann_stats['snp']} SNP, {ann_stats['indel']} INDEL).")
            self.log(f"================================================================================")
            self.save_metadata()

        except PipelineCancelledException as ce:
            self.status = "gagal"
            self.error = str(ce)
            self.log(f"[BATAL] {ce}")
            self.save_metadata()
        except Exception as e:
            self.status = "gagal"
            self.error = str(e)
            self.log(f"[FATAL ERROR] {e}")
            self.save_metadata()
        finally:
            PIPELINE_SEMAPHORE.release()

    def start_async(self):
        self.thread = threading.Thread(target=self.execute_sync)
        self.thread.daemon = True
        self.thread.start()
