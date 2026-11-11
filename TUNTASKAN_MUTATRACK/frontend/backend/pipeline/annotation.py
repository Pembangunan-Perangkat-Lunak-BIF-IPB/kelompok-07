import glob
import gzip
import os
import re
import shutil
from typing import Callable, Dict, List, Optional, Tuple
from .utils import SubprocessRunner, ensure_dir

BASE_CONFIG_GLOB = "/opt/conda/share/snpeff-*/snpEff.config"
ANN_GENBANK_EXT = (".gbk", ".gb", ".genbank", ".gbff", ".gbk.gz", ".gb.gz", ".gbff.gz")
ANN_GFF_EXT = (".gff", ".gff3", ".gtf", ".gff.gz", ".gff3.gz")


def find_base_config() -> str:
    found = sorted(glob.glob(BASE_CONFIG_GLOB))
    if not found:
        raise RuntimeError("snpEff.config bawaan tidak ditemukan di /opt/conda/share.")
    return found[0]


def existing_db_available(db_name: str) -> bool:
    patterns = [
        os.path.expanduser(f"~/.snpEff/data/{db_name}/snpEffectPredictor.bin"),
        f"/opt/conda/share/snpeff-*/data/{db_name}/snpEffectPredictor.bin",
        f"/usr/share/snpEff/data/{db_name}/snpEffectPredictor.bin",
    ]
    return any(glob.glob(p) for p in patterns)


def parse_vcf_dp(info_str: str, format_str: str = "", sample_str: str = "") -> Optional[int]:
    m = re.search(r"(?:^|;)DP=(\d+)", info_str)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    if format_str and sample_str:
        f_keys = format_str.split(":")
        s_vals = sample_str.split(":")
        if "DP" in f_keys:
            idx = f_keys.index("DP")
            if idx < len(s_vals):
                try:
                    return int(s_vals[idx])
                except ValueError:
                    pass
    return None


def parse_snpeff_ann_field(info_str: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    m = re.search(r"(?:^|;)ANN=([^;]+)", info_str)
    if not m:
        return None, None, None
    parts = m.group(1).split(",")[0].split("|")
    efek = parts[1] if len(parts) > 1 and parts[1] else None
    impact = parts[2].upper() if len(parts) > 2 and parts[2] else None
    gen = parts[3] if len(parts) > 3 and parts[3] else None
    if impact not in {"HIGH", "MODERATE", "LOW", "MODIFIER"}:
        impact = None
    return gen, efek, impact


def parse_vcf_to_variants(vcf_path: str, analysis_id: str) -> List[Dict[str, any]]:
    variants: List[Dict[str, any]] = []
    if not os.path.isfile(vcf_path):
        return variants
    var_id = 1
    with open(vcf_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            cols = line.split("\t")
            if len(cols) < 5:
                continue
            try:
                pos = int(cols[1])
            except ValueError:
                continue
            ref, alt = cols[3], cols[4]
            qual = None
            try:
                if cols[5] != ".":
                    qual = round(float(cols[5]), 1)
            except ValueError:
                pass
            info = cols[7] if len(cols) > 7 else ""
            fmt = cols[8] if len(cols) > 8 else ""
            sample_val = cols[9] if len(cols) > 9 else ""
            is_snp = len(ref) == 1 and len(alt) == 1 and ref in "ACGTNacgtn" and alt in "ACGTNacgtn"
            gen, efek, impact = parse_snpeff_ann_field(info)  # kosong bila tidak ada anotasi
            variants.append({
                "id": var_id,
                "analysis_id": analysis_id,
                "chrom": cols[0],
                "posisi": pos,
                "ref": ref,
                "alt": alt,
                "tipe": "SNP" if is_snp else "INDEL",
                "qual": qual,
                "depth": parse_vcf_dp(info, fmt, sample_val),
                "gen": gen,
                "efek": efek,
                "impact": impact,
            })
            var_id += 1
    return variants


def _gunzip_to(src: str, dst: str) -> str:
    if src.endswith(".gz"):
        with gzip.open(src, "rb") as fi, open(dst, "wb") as fo:
            shutil.copyfileobj(fi, fo)
    else:
        shutil.copyfile(src, dst)
    return dst


def build_custom_db(
    annotation_path: str,
    reference_path: str,
    work_dir: str,
    analysis_id: str,
    runner: SubprocessRunner,
    log: Callable[[str], None],
) -> Tuple[str, str]:
    """Bangun database snpEff custom. Mengembalikan (nama_genome, path_config)."""
    if not annotation_path or not os.path.isfile(annotation_path):
        raise RuntimeError("File anotasi (GenBank/GFF) tidak ditemukan di server.")

    low = annotation_path.lower()
    is_gbk = low.endswith(ANN_GENBANK_EXT)
    is_gff = low.endswith(ANN_GFF_EXT)
    if not (is_gbk or is_gff):
        raise RuntimeError(
            "Ekstensi file anotasi tidak dikenali. Gunakan: "
            + ", ".join(ANN_GENBANK_EXT + ANN_GFF_EXT)
        )

    genome = "custom_" + re.sub(r"[^A-Za-z0-9]", "_", analysis_id)
    data_dir = os.path.abspath(os.path.join(work_dir, "snpeff_data"))
    genome_dir = os.path.join(data_dir, genome)
    ensure_dir(genome_dir)

    # Config per analisis: salin config bawaan, ganti data.dir, daftarkan genome
    base = find_base_config()
    with open(base, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    lines = [("data.dir = " + data_dir + "/") if re.match(r"^\s*data\.dir\s*=", ln) else ln for ln in lines]
    lines.append("")
    lines.append(f"{genome}.genome : {genome}")
    cfg_path = os.path.join(work_dir, "snpEff.custom.config")
    with open(cfg_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    if is_gbk:
        _gunzip_to(annotation_path, os.path.join(genome_dir, "genes.gbk"))
        build_flag = "-genbank"
    else:
        _gunzip_to(annotation_path, os.path.join(genome_dir, "genes.gff"))
        _gunzip_to(reference_path, os.path.join(genome_dir, "sequences.fa"))
        build_flag = "-gff3"

    log(f"[SnpEff] Membangun database custom '{genome}' dari {os.path.basename(annotation_path)}...")
    runner.run_cmd(
    ["snpEff", "-Xmx2g", "build", build_flag, "-noCheckCds", "-noCheckProtein",
    "-v", "-c", cfg_path, genome],
    log,
    )
    log(f"[SnpEff] Database custom '{genome}' berhasil dibangun.")
    return genome, cfg_path


def run_annotation_stage(
    filtered_vcf: str,
    out_dir: str,
    analysis_id: str,
    mode: str,
    db_name: str,
    annotation_path: Optional[str],
    reference_path: str,
    runner: SubprocessRunner,
    log: Callable[[str], None],
) -> Tuple[Dict[str, any], str, List[Dict[str, any]]]:
    ensure_dir(out_dir)
    annotated_vcf = os.path.join(out_dir, "annotated.vcf")

    if mode == "custom":
        genome, cfg = build_custom_db(annotation_path, reference_path, out_dir, analysis_id, runner, log)
        log("[SnpEff] Menjalankan anotasi dengan database custom...")
        runner.run_cmd(
            ["snpEff", "-Xmx2g", "-v", "-c", cfg, genome, filtered_vcf],
            log, pipe_stdout_to_file=annotated_vcf,
        )
    elif mode == "existing":
        if not db_name:
            raise RuntimeError("Mode 'existing' membutuhkan nama database snpEff.")
        if not existing_db_available(db_name):
            log(f"[SnpEff] Database '{db_name}' belum ada. Mengunduh...")
            runner.run_cmd(["snpEff", "download", "-v", db_name], log)
        log(f"[SnpEff] Menjalankan anotasi dengan database '{db_name}'...")
        runner.run_cmd(
            ["snpEff", "-Xmx2g", "-v", db_name, filtered_vcf],
            log, pipe_stdout_to_file=annotated_vcf,
        )
    else:
        log("[SnpEff] Tanpa anotasi: gen/efek/impact dikosongkan (varian mentah saja).")
        shutil.copyfile(filtered_vcf, annotated_vcf)

    variants = parse_vcf_to_variants(annotated_vcf, analysis_id)

    annotated_n = sum(1 for v in variants if v.get("impact"))
    if mode in ("custom", "existing") and variants and annotated_n == 0:
        log("[SnpEff Peringatan] Tidak ada varian yang teranotasi. Kemungkinan nama kromosom di "
            "FASTA dan file anotasi tidak cocok (cek header FASTA vs LOCUS/seqid anotasi).")

    snp_count = sum(1 for v in variants if v["tipe"] == "SNP")
    indel_count = sum(1 for v in variants if v["tipe"] == "INDEL")
    unique_genes = {v["gen"] for v in variants if v.get("gen")}
    per_impact: Dict[str, int] = {"HIGH": 0, "MODERATE": 0, "LOW": 0, "MODIFIER": 0}
    per_efek: Dict[str, int] = {}
    tidak_teranotasi = 0
    for v in variants:
        imp = v.get("impact")
        if imp in per_impact:
            per_impact[imp] += 1
        else:
            tidak_teranotasi += 1
        efk = v.get("efek") or "unannotated"
        per_efek[efk] = per_efek.get(efk, 0) + 1

    stats = {
        "total_varian": len(variants),
        "snp": snp_count,
        "indel": indel_count,
        "gen_terdampak": len(unique_genes),
        "per_impact": per_impact,
        "per_efek": per_efek,
        "tidak_teranotasi": tidak_teranotasi,
    }
    log(f"[SnpEff] Ringkasan: {len(variants):,} varian ({snp_count:,} SNP, {indel_count:,} INDEL), "
        f"{annotated_n:,} teranotasi, {len(unique_genes)} gen.")
    return stats, annotated_vcf, variants