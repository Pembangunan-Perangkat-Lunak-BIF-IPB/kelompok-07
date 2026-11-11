import os
import re
import subprocess
from typing import Callable, Dict, Optional, Tuple
from .utils import SubprocessRunner, ensure_dir

def ensure_reference_indexed(
    ref_path: str,
    runner: SubprocessRunner,
    log: Callable[[str], None],
) -> None:
    # Check if reference is compressed with gzip (.gz)
    # BWA requires uncompressed fasta or bgzip. If it's a .fasta.gz, we decompress it.
    actual_ref = ref_path
    if ref_path.endswith(".gz"):
        uncompressed_path = ref_path[:-3]
        if not os.path.isfile(uncompressed_path) or os.path.getsize(uncompressed_path) == 0:
            log(f"[Alignment] Mengekstrak reference genome terkompresi {os.path.basename(ref_path)}...")
            import gzip
            with gzip.open(ref_path, "rb") as f_in:
                with open(uncompressed_path, "wb") as f_out:
                    import shutil
                    shutil.copyfileobj(f_in, f_out)
        actual_ref = uncompressed_path

    # Check BWA index files: .bwt, .pac, .ann, .amb, .sa
    bwa_indices = [actual_ref + ext for ext in [".bwt", ".pac", ".ann", ".amb", ".sa"]]
    all_bwa_present = all(os.path.isfile(idx) and os.path.getsize(idx) > 0 for idx in bwa_indices)

    if not all_bwa_present:
        log(f"[bwa index] Membuat indeks BWA untuk {os.path.basename(actual_ref)}...")
        runner.run_cmd(["bwa", "index", actual_ref], log)
        log("[bwa index] Indeks BWA selesai dibuat.")
    else:
        log(f"[bwa index] Menggunakan indeks BWA yang sudah tersedia untuk {os.path.basename(actual_ref)}.")

    # Check samtools faidx (.fai)
    fai_file = actual_ref + ".fai"
    if not (os.path.isfile(fai_file) and os.path.getsize(fai_file) > 0):
        log(f"[samtools faidx] Mengindeks FASTA {os.path.basename(actual_ref)}...")
        runner.run_cmd(["samtools", "faidx", actual_ref], log)

    return actual_ref

def parse_flagstat_output(flagstat_text: str) -> Dict[str, any]:
    stats = {
        "total_reads": 0,
        "terpetakan": 0,
        "tidak_terpetakan": 0,
        "persen_terpetakan": 0.0,
    }

    for line in flagstat_text.splitlines():
        line = line.strip()
        # Format: 600000 + 0 in total (QC-passed reads + QC-failed reads)
        if "in total" in line:
            m = re.match(r"^(\d+)\s*\+\s*(\d+)", line)
            if m:
                stats["total_reads"] = int(m.group(1)) + int(m.group(2))
        # Format: 599996 + 0 mapped (100.00% : N/A)
        elif " mapped (" in line:
            m = re.match(r"^(\d+)\s*\+\s*(\d+)\s+mapped\s+\(([0-9.]+)%", line)
            if m:
                stats["terpetakan"] = int(m.group(1)) + int(m.group(2))
                stats["persen_terpetakan"] = float(m.group(3))

    stats["tidak_terpetakan"] = max(0, stats["total_reads"] - stats["terpetakan"])
    if stats["total_reads"] > 0 and stats["persen_terpetakan"] == 0.0:
        stats["persen_terpetakan"] = round((stats["terpetakan"] / stats["total_reads"]) * 100, 2)

    return stats

def run_alignment_stage(
    ref_path: str,
    clean_r1: str,
    clean_r2: Optional[str],
    out_dir: str,
    runner: SubprocessRunner,
    log: Callable[[str], None],
    threads: int = 2,
) -> Tuple[Dict[str, any], str]:
    ensure_dir(out_dir)
    actual_ref = ensure_reference_indexed(ref_path, runner, log)

    sorted_bam = os.path.join(out_dir, "sorted.bam")
    flagstat_file = os.path.join(out_dir, "flagstat.txt")

    log(f"[bwa mem] Memulai alignment genom ke {os.path.basename(actual_ref)}...")

    read_group = "@RG\\tID:s1\\tSM:s1\\tPL:ILLUMINA"
    bwa_cmd = ["bwa", "mem", "-t", str(threads), "-R", read_group, actual_ref, clean_r1]
    if clean_r2:
        bwa_cmd.append(clean_r2)

    sort_cmd = ["samtools", "sort", "-@", str(threads), "-o", sorted_bam, "-"]

    log(f"$ {' '.join(bwa_cmd)} | {' '.join(sort_cmd)}")

    # Execute piped command safely
    p_bwa = subprocess.Popen(
        bwa_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
    )
    p_sort = subprocess.Popen(
        sort_cmd,
        stdin=p_bwa.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    p_bwa.stdout.close()

    # Capture bwa stderr
    def read_bwa_stderr():
        if p_bwa.stderr:
            for raw_line in iter(p_bwa.stderr.readline, b''):
                line = raw_line.decode("utf-8", errors="replace").strip()
                if line:
                    log(line)

    import threading
    t_err = threading.Thread(target=read_bwa_stderr)
    t_err.daemon = True
    t_err.start()

    sort_out, sort_err = p_sort.communicate()
    if sort_err:
        for line in sort_err.splitlines():
            line = line.strip()
            if line:
                log(line)

    p_bwa.wait()
    t_err.join(timeout=2.0)

    if p_bwa.returncode != 0:
        raise RuntimeError(f"bwa mem gagal dengan exit code {p_bwa.returncode}")
    if p_sort.returncode != 0:
        raise RuntimeError(f"samtools sort gagal dengan exit code {p_sort.returncode}")

    if not os.path.isfile(sorted_bam) or os.path.getsize(sorted_bam) == 0:
        raise RuntimeError("Gagal menghasilkan sorted.bam yang valid.")

    # Index BAM
    log("[samtools index] Mengindeks sorted.bam...")
    runner.run_cmd(["samtools", "index", sorted_bam], log)

    # Flagstat
    log("[samtools flagstat] Menghitung statistik pemetaan alignment...")
    flagstat_proc = subprocess.run(
        ["samtools", "flagstat", sorted_bam],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    flagstat_text = flagstat_proc.stdout

    with open(flagstat_file, "w", encoding="utf-8") as f:
        f.write(flagstat_text)

    for line in flagstat_text.splitlines():
        line = line.strip()
        if line:
            log(line)

    stats = parse_flagstat_output(flagstat_text)
    log(f"[samtools flagstat] Terpetakan: {stats['terpetakan']:,} / {stats['total_reads']:,} reads ({stats['persen_terpetakan']}%)")

    return stats, sorted_bam
