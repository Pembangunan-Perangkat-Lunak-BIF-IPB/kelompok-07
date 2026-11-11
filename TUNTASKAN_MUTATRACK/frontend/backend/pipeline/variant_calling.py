import os
import re
import subprocess
from typing import Callable, Dict, Tuple
from .utils import SubprocessRunner, ensure_dir

def count_vcf_variants(vcf_path: str) -> int:
    count = 0
    with open(vcf_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.startswith("#"):
                count += 1
    return count

def run_variant_calling_stage(
    ref_path: str,
    sorted_bam: str,
    out_dir: str,
    min_mapq: int,
    min_baseq: int,
    ploidy: int,
    runner: SubprocessRunner,
    log: Callable[[str], None],
) -> Tuple[Dict[str, any], str]:
    ensure_dir(out_dir)
    raw_vcf = os.path.join(out_dir, "raw.vcf")

    log(f"[bcftools mpileup & call] Memulai variant calling (min_mapq={min_mapq}, min_baseq={min_baseq}, ploidy={ploidy})...")

    mpileup_cmd = [
        "bcftools", "mpileup",
        "-f", ref_path,
        "-q", str(min_mapq),
        "-Q", str(min_baseq),
        "-a", "FORMAT/AD",
        "-Ou",
        sorted_bam,
    ]

    call_cmd = [
        "bcftools", "call",
        "-mv",
        "--ploidy", str(ploidy),
        "-Ov",
        "-o", raw_vcf,
    ]

    log(f"$ {' '.join(mpileup_cmd)} | {' '.join(call_cmd)}")

    p_mpileup = subprocess.Popen(
        mpileup_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
    )

    p_call = subprocess.Popen(
        call_cmd,
        stdin=p_mpileup.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    p_mpileup.stdout.close()

    call_out, call_err = p_call.communicate()
    mpileup_err = p_mpileup.stderr.read().decode("utf-8", errors="replace") if p_mpileup.stderr else ""
    p_mpileup.wait()

    if mpileup_err:
        for line in mpileup_err.splitlines():
            line = line.strip()
            if line:
                log(line)
    if call_err:
        for line in call_err.splitlines():
            line = line.strip()
            if line:
                log(line)

    if p_mpileup.returncode != 0:
        raise RuntimeError(f"bcftools mpileup gagal dengan exit code {p_mpileup.returncode}")
    if p_call.returncode != 0:
        raise RuntimeError(f"bcftools call gagal dengan exit code {p_call.returncode}")

    if not os.path.isfile(raw_vcf) or os.path.getsize(raw_vcf) == 0:
        raise RuntimeError("Gagal menghasilkan raw.vcf yang valid.")

    raw_count = count_vcf_variants(raw_vcf)
    log(f"[bcftools call] Teridentifikasi {raw_count:,} kandidat varian mentah.")

    stats = {
        "varian_mentah": raw_count,
    }
    return stats, raw_vcf
