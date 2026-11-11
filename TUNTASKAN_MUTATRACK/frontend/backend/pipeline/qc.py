import os
import re
import zipfile
from typing import Callable, Dict, List, Optional
from .utils import SubprocessRunner, ensure_dir

def parse_fastqc_data(data_txt_content: str) -> Dict[str, any]:
    stats = {
        "basic_statistics": {},
        "modules": {},
        "total_sequences": 0,
        "sequence_length": "",
        "gc_percent": 0.0,
    }

    current_module = None
    for line in data_txt_content.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(">>"):
            if line == ">>END_MODULE":
                current_module = None
            else:
                parts = line[2:].split("\t")
                mod_name = parts[0]
                mod_status = parts[1] if len(parts) > 1 else "unknown"
                stats["modules"][mod_name] = mod_status
                current_module = mod_name
            continue

        if current_module == "Basic Statistics" and "\t" in line:
            k, v = line.split("\t", 1)
            stats["basic_statistics"][k] = v
            if k == "Total Sequences":
                try:
                    stats["total_sequences"] = int(v)
                except ValueError:
                    pass
            elif k == "Sequence length":
                stats["sequence_length"] = v
            elif k == "%GC":
                try:
                    stats["gc_percent"] = float(v)
                except ValueError:
                    pass

    return stats

def run_fastqc_stage(
    r1_path: str,
    r2_path: Optional[str],
    out_dir: str,
    runner: SubprocessRunner,
    log: Callable[[str], None],
    threads: int = 2,
) -> Dict[str, any]:
    ensure_dir(out_dir)
    log("[FastQC] Memulai Quality Control sekuens mentah...")

    cmd = ["fastqc", "-t", str(threads), "--outdir", out_dir, r1_path]
    if r2_path:
        cmd.append(r2_path)

    runner.run_cmd(cmd, log)

    results: Dict[str, any] = {
        "r1": None,
        "r2": None,
        "reports": [],
    }

    # Extract parsed metrics and identify html/zip
    for fname in os.listdir(out_dir):
        if fname.endswith(".html"):
            results["reports"].append(os.path.join(out_dir, fname))
        if fname.endswith("_fastqc.zip"):
            zip_path = os.path.join(out_dir, fname)
            is_r2 = ("_R2_" in fname or "_2_fastqc" in fname or (r2_path and os.path.basename(r2_path).split(".")[0] in fname))
            try:
                with zipfile.ZipFile(zip_path, "r") as z:
                    for name in z.namelist():
                        if name.endswith("fastqc_data.txt"):
                            with z.open(name) as f:
                                data_str = f.read().decode("utf-8", errors="replace")
                                parsed = parse_fastqc_data(data_str)
                                parsed["zip_file"] = fname
                                html_candidate = fname.replace(".zip", ".html")
                                parsed["html_file"] = html_candidate if os.path.exists(os.path.join(out_dir, html_candidate)) else None
                                if is_r2 and r2_path:
                                    results["r2"] = parsed
                                else:
                                    results["r1"] = parsed
            except Exception as e:
                log(f"[FastQC Warning] Gagal membaca data dari {fname}: {e}")

    log(f"[FastQC] Analisis QC selesai. File HTML dan ZIP tersimpan di {out_dir}")
    return results
