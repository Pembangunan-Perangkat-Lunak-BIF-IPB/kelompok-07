import json
import os
from typing import Callable, Dict, Optional, Tuple
from .utils import SubprocessRunner, ensure_dir

def run_fastp_stage(
    r1_path: str,
    r2_path: Optional[str],
    out_dir: str,
    trim_quality: int,
    min_length: int,
    runner: SubprocessRunner,
    log: Callable[[str], None],
    threads: int = 2,
) -> Tuple[Dict[str, any], str, Optional[str]]:
    ensure_dir(out_dir)
    log(f"[fastp] Memulai trimming sekuens (trim_quality={trim_quality}, min_length={min_length})...")

    clean_r1 = os.path.join(out_dir, "clean_R1.fastq.gz")
    clean_r2 = os.path.join(out_dir, "clean_R2.fastq.gz") if r2_path else None
    json_report = os.path.join(out_dir, "fastp.json")
    html_report = os.path.join(out_dir, "fastp.html")

    cmd = [
        "fastp",
        "-i", r1_path,
        "-o", clean_r1,
        "-q", str(trim_quality),
        "-l", str(min_length),
        "-w", str(threads),
        "-j", json_report,
        "-h", html_report,
    ]

    if r2_path and clean_r2:
        cmd.extend(["-I", r2_path, "-O", clean_r2])

    runner.run_cmd(cmd, log)

    if not os.path.isfile(clean_r1) or os.path.getsize(clean_r1) == 0:
        raise RuntimeError("fastp gagal menghasilkan clean_R1.fastq.gz yang valid.")

    if clean_r2 and (not os.path.isfile(clean_r2) or os.path.getsize(clean_r2) == 0):
        raise RuntimeError("fastp gagal menghasilkan clean_R2.fastq.gz yang valid.")

    stats: Dict[str, any] = {}
    if os.path.isfile(json_report):
        try:
            with open(json_report, "r", encoding="utf-8") as f:
                data = json.load(f)
                summary = data.get("summary", {})
                before = summary.get("before_filtering", {})
                after = summary.get("after_filtering", {})
                filtering_result = data.get("filtering_result", {})
                adapter = data.get("adapter_cutting", {})

                reads_before = before.get("total_reads", 0)
                reads_after = after.get("total_reads", 0)
                q20_before = round(before.get("q20_rate", 0.0) * 100, 2)
                q30_before = round(before.get("q30_rate", 0.0) * 100, 2)
                q20_after = round(after.get("q20_rate", 0.0) * 100, 2)
                q30_after = round(after.get("q30_rate", 0.0) * 100, 2)

                stats = {
                    "reads_sebelum": reads_before,
                    "reads_sesudah": reads_after,
                    "q20_sebelum": q20_before,
                    "q20_sesudah": q20_after,
                    "q30_sebelum": q30_before,
                    "q30_sesudah": q30_after,
                    "bases_sebelum": before.get("total_bases", 0),
                    "bases_sesudah": after.get("total_bases", 0),
                    "reads_passed": filtering_result.get("passed_filter_reads", reads_after),
                    "low_quality_reads": filtering_result.get("low_quality_reads", 0),
                    "too_many_N_reads": filtering_result.get("too_many_N_reads", 0),
                    "too_short_reads": filtering_result.get("too_short_reads", 0),
                    "adapter_trimmed_reads": adapter.get("adapter_trimmed_reads", 0),
                    "json_report": json_report,
                    "html_report": html_report,
                }
                log(f"[fastp] Reads sebelum: {reads_before:,} | Reads sesudah: {reads_after:,} (Q30: {q30_before}% -> {q30_after}%)")
        except Exception as e:
            log(f"[fastp Warning] Gagal membaca fastp.json: {e}")

    return stats, clean_r1, clean_r2
