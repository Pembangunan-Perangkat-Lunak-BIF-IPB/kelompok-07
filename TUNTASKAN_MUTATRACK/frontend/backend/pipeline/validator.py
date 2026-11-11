import gzip
import os
import re
from typing import Dict, List, Optional, Tuple

ALLOWED_FASTQ_EXTENSIONS = (".fastq", ".fq", ".fastq.gz", ".fq.gz")
ALLOWED_FASTA_EXTENSIONS = (".fasta", ".fa", ".fna", ".rna", ".fasta.gz", ".fa.gz", ".fna.gz", ".rna.gz")

# Maksimal ukuran berkas masukan (100 MB)
MAX_FASTQ_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB
MAX_FASTA_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB

class ValidationError(Exception):
    pass

def is_gzipped(filepath: str) -> bool:
    if filepath.endswith(".gz"):
        return True
    try:
        with open(filepath, "rb") as f:
            return f.read(2) == b"\x1f\x8b"
    except Exception:
        return False

def open_text_file(filepath: str):
    if is_gzipped(filepath):
        return gzip.open(filepath, "rt", encoding="utf-8", errors="replace")
    return open(filepath, "r", encoding="utf-8", errors="replace")

def validate_fastq_format(filepath: str, sample_records: int = 100) -> Dict[str, any]:
    if not os.path.isfile(filepath):
        raise ValidationError(f"File FASTQ tidak ditemukan: {filepath}")

    file_size = os.path.getsize(filepath)
    if file_size == 0:
        raise ValidationError(f"File FASTQ kosong (0 byte): {os.path.basename(filepath)}")

    if file_size > MAX_FASTQ_SIZE_BYTES:
        size_mb = file_size / (1024 * 1024)
        raise ValidationError(
            f"Ukuran berkas FASTQ '{os.path.basename(filepath)}' ({size_mb:.1f} MB) melebihi batas maksimal 100 MB."
        )

    valid_ext = any(filepath.lower().endswith(ext) for ext in ALLOWED_FASTQ_EXTENSIONS)
    if not valid_ext:
        raise ValidationError(
            f"Ekstensi file FASTQ tidak valid: '{os.path.basename(filepath)}'. "
            f"Gunakan salah satu dari: {', '.join(ALLOWED_FASTQ_EXTENSIONS)}"
        )

    read_count = 0
    first_header = ""
    avg_len = 0
    total_len = 0

    try:
        with open_text_file(filepath) as f:
            while read_count < sample_records:
                header = f.readline()
                if not header:
                    break
                seq = f.readline()
                plus = f.readline()
                qual = f.readline()

                if not (seq and plus and qual):
                    raise ValidationError(
                        f"Format FASTQ rusak pada read #{read_count + 1} di {os.path.basename(filepath)}: 4 baris tidak lengkap."
                    )

                header = header.strip()
                seq = seq.strip()
                plus = plus.strip()
                qual = qual.strip()

                if not header.startswith("@"):
                    raise ValidationError(
                        f"Baris header FASTQ #{read_count + 1} tidak diawali '@': {header[:30]} di {os.path.basename(filepath)}"
                    )
                if not plus.startswith("+"):
                    raise ValidationError(
                        f"Baris tanda FASTQ #{read_count + 1} tidak diawali '+': {plus[:30]} di {os.path.basename(filepath)}"
                    )
                if len(seq) != len(qual):
                    raise ValidationError(
                        f"Panjang sekuens ({len(seq)}) tidak sama dengan kualitas ({len(qual)}) pada read #{read_count + 1} di {os.path.basename(filepath)}"
                    )

                if read_count == 0:
                    first_header = header
                total_len += len(seq)
                read_count += 1

    except gzip.BadGzipFile:
        raise ValidationError(f"File terkompresi gzip rusak: {os.path.basename(filepath)}")
    except Exception as e:
        if isinstance(e, ValidationError):
            raise
        raise ValidationError(f"Gagal membaca file FASTQ {os.path.basename(filepath)}: {str(e)}")

    if read_count == 0:
        raise ValidationError(f"File FASTQ tidak memuat sekuens yang valid: {os.path.basename(filepath)}")

    return {
        "valid": True,
        "sample_reads": read_count,
        "first_header": first_header,
        "sample_avg_length": round(total_len / read_count, 1),
        "file_size": file_size,
    }

def count_fastq_reads_fast(filepath: str) -> int:
    """Accurately count total reads in FASTQ/FASTQ.GZ"""
    count = 0
    with open_text_file(filepath) as f:
        for i, _ in enumerate(f):
            if (i & 3) == 0:  # every 4th line
                count += 1
    return count

def extract_base_read_name(header: str) -> str:
    name = header.lstrip("@").strip()
    name = re.sub(r"[ \t]+[12]:.*$", "", name)
    name = re.sub(r"/[12]$", "", name)
    name = name.split()[0]
    return name

def validate_paired_fastq(r1_path: str, r2_path: str) -> Dict[str, any]:
    val_r1 = validate_fastq_format(r1_path)
    val_r2 = validate_fastq_format(r2_path)

    # Check first headers compatibility
    base1 = extract_base_read_name(val_r1["first_header"])
    base2 = extract_base_read_name(val_r2["first_header"])

    if base1 != base2:
        raise ValidationError(
            f"Ketidakcocokan identifier pasangan reads: "
            f"Read 1 = '{val_r1['first_header']}' vs Read 2 = '{val_r2['first_header']}'. "
            f"Pastikan R1 dan R2 berasal dari sampel yang sama."
        )

    # Count reads if fast or sample checks
    r1_reads = count_fastq_reads_fast(r1_path)
    r2_reads = count_fastq_reads_fast(r2_path)

    if r1_reads != r2_reads:
        raise ValidationError(
            f"Jumlah reads R1 ({r1_reads}) tidak sama dengan R2 ({r2_reads}). "
            f"File pasangan FASTQ harus memiliki jumlah reads identik."
        )

    return {
        "valid": True,
        "r1_reads": r1_reads,
        "r2_reads": r2_reads,
        "r1_size": val_r1["file_size"],
        "r2_size": val_r2["file_size"],
    }

def validate_reference_fasta(filepath: str) -> Dict[str, any]:
    if not os.path.isfile(filepath):
        raise ValidationError(f"File Reference FASTA tidak ditemukan: {filepath}")

    file_size = os.path.getsize(filepath)
    if file_size == 0:
        raise ValidationError(f"File FASTA kosong (0 byte): {os.path.basename(filepath)}")

    if file_size > MAX_FASTA_SIZE_BYTES:
        size_mb = file_size / (1024 * 1024)
        raise ValidationError(
            f"Ukuran berkas FASTA '{os.path.basename(filepath)}' ({size_mb:.1f} MB) melebihi batas maksimal 100 MB."
        )

    valid_ext = any(filepath.lower().endswith(ext) for ext in ALLOWED_FASTA_EXTENSIONS)
    if not valid_ext:
        raise ValidationError(
            f"Ekstensi file FASTA tidak valid: '{os.path.basename(filepath)}'. "
            f"Gunakan salah satu dari: {', '.join(ALLOWED_FASTA_EXTENSIONS)}"
        )

    chrom_headers: List[str] = []
    total_bases = 0
    seq_lines = 0

    try:
        with open_text_file(filepath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith(">"):
                    chrom_headers.append(line[1:].split()[0])
                else:
                    total_bases += len(line)
                    seq_lines += 1
    except gzip.BadGzipFile:
        raise ValidationError(f"File FASTA terkompresi gzip rusak: {os.path.basename(filepath)}")
    except Exception as e:
        raise ValidationError(f"Gagal membaca file FASTA {os.path.basename(filepath)}: {str(e)}")

    if not chrom_headers:
        raise ValidationError(
            f"File FASTA tidak memiliki header sekuens yang diawali '>': {os.path.basename(filepath)}"
        )
    if total_bases == 0:
        raise ValidationError(
            f"File FASTA tidak memiliki sekuens nukleotida (panjang 0): {os.path.basename(filepath)}"
        )

    return {
        "valid": True,
        "chromosomes": chrom_headers,
        "total_bases": total_bases,
        "file_size": file_size,
    }

def validate_pipeline_inputs(
    r1_path: str,
    r2_path: Optional[str] = None,
    ref_path: Optional[str] = None,
    mode: str = "paired",
) -> Dict[str, any]:
    results = {}

    # Validate Reference
    if not ref_path:
        raise ValidationError("File reference genome (.fasta / .fna) wajib disediakan.")
    results["reference"] = validate_reference_fasta(ref_path)

    # Validate Reads
    if not r1_path:
        raise ValidationError("File R1 (.fastq / .fq) wajib disediakan.")

    if mode == "paired":
        if not r2_path:
            raise ValidationError("Mode Paired-End mewajibkan file R2.")
        results["paired_reads"] = validate_paired_fastq(r1_path, r2_path)
    else:
        results["single_read"] = validate_fastq_format(r1_path)
        results["single_read"]["total_reads"] = count_fastq_reads_fast(r1_path)

    return results
