import os
from typing import Callable, Dict, Tuple
from .utils import SubprocessRunner, ensure_dir

def count_vcf_variants(vcf_path: str) -> int:
    count = 0
    if not os.path.isfile(vcf_path):
        return 0
    with open(vcf_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.startswith("#"):
                count += 1
    return count

def run_filtering_stage(
    raw_vcf: str,
    out_dir: str,
    min_qual: float,
    min_depth: int,
    runner: SubprocessRunner,
    log: Callable[[str], None],
) -> Tuple[Dict[str, any], str]:
    ensure_dir(out_dir)
    filtered_vcf = os.path.join(out_dir, "filtered.vcf")

    log(f"[bcftools filter] Memulai penyaringan varian (min_qual={min_qual}, min_depth={min_depth})...")

    filter_expr = f"QUAL>={min_qual} && (INFO/DP>={min_depth} || DP>={min_depth})"
    filter_cmd = [
        "bcftools", "filter",
        "-i", filter_expr,
        "-Ov",
        "-o", filtered_vcf,
        raw_vcf,
    ]

    runner.run_cmd(filter_cmd, log)

    if not os.path.isfile(filtered_vcf):
        raise RuntimeError("Gagal menghasilkan filtered.vcf.")

    passed_count = count_vcf_variants(filtered_vcf)
    raw_count = count_vcf_variants(raw_vcf)
    discarded_count = max(0, raw_count - passed_count)

    log(f"[bcftools filter] Varian lolos kriteria: {passed_count:,} (QUAL >= {min_qual}, DP >= {min_depth}).")
    log(f"[bcftools filter] Varian tereliminasi: {discarded_count:,}.")

    stats = {
        "varian_lolos": passed_count,
        "varian_tereliminasi": discarded_count,
    }
    return stats, filtered_vcf
