"""Pipeline variant calling MutaTrack: QC -> trimming -> alignment -> variant calling -> filtering -> anotasi."""
import json
import re
import subprocess
from pathlib import Path

STAGES = ["qc", "trimming", "alignment", "variant_calling", "filtering", "annotation"]

DEFAULT_CONFIG = {
    "trim_quality": 20,      # fastp -q
    "min_length": 50,        # fastp -l
    "min_mapq": 20,          # bcftools mpileup -q
    "min_baseq": 20,         # bcftools mpileup -Q
    "min_qual": 30,          # filter QUAL
    "min_depth": 10,         # filter DP
}


class PipelineError(Exception):
    pass


def sh(cmd: str, logf, label: str):
    logf.write(f"\n$ {cmd}\n")
    logf.flush()
    p = subprocess.run(cmd, shell=True, stdout=logf, stderr=subprocess.STDOUT, executable="/bin/bash")
    if p.returncode != 0:
        raise PipelineError(f"Tahap {label} gagal (kode {p.returncode}). Lihat log untuk detail.")


def run_pipeline(workdir: Path, r1: Path, r2, ref: Path, config: dict, snpeff_db: str, threads: int, on_stage, on_stats):
    """on_stage(stage_name) dipanggil saat tahap dimulai; on_stats(dict) menyimpan statistik."""
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    t = threads
    out = workdir / "out"
    out.mkdir(exist_ok=True)
    stats = {}
    log_path = workdir / "pipeline.log"

    with open(log_path, "a") as logf:
        # 1. QC
        on_stage("qc")
        (out / "qc").mkdir(exist_ok=True)
        reads = f'"{r1}"' + (f' "{r2}"' if r2 else "")
        sh(f"fastqc -t {t} --outdir {out/'qc'} {reads}", logf, "quality control")

        # 2. Trimming
        on_stage("trimming")
        t1 = out / "clean_R1.fastq.gz"
        t2 = out / "clean_R2.fastq.gz"
        fj = out / "fastp.json"
        if r2:
            cmd = (f'fastp -i "{r1}" -I "{r2}" -o {t1} -O {t2} -q {cfg["trim_quality"]} '
                   f'-l {cfg["min_length"]} -w {t} -j {fj} -h {out/"fastp.html"}')
        else:
            cmd = (f'fastp -i "{r1}" -o {t1} -q {cfg["trim_quality"]} '
                   f'-l {cfg["min_length"]} -w {t} -j {fj} -h {out/"fastp.html"}')
        sh(cmd, logf, "trimming")
        try:
            fp = json.loads(fj.read_text())["summary"]
            stats["trimming"] = {
                "reads_sebelum": fp["before_trimming"]["total_reads"],
                "reads_sesudah": fp["after_trimming"]["total_reads"],
                "q30_sebelum": round(fp["before_trimming"]["q30_rate"] * 100, 2),
                "q30_sesudah": round(fp["after_trimming"]["q30_rate"] * 100, 2),
            }
            on_stats(stats)
        except Exception:
            pass

        # 3. Alignment
        on_stage("alignment")
        sh(f'bwa index "{ref}"', logf, "indeks referensi")
        bam = out / "sorted.bam"
        clean = f"{t1} {t2}" if r2 else f"{t1}"
        sh(f"bwa mem -t {t} -R '@RG\\tID:s1\\tSM:s1\\tPL:ILLUMINA' \"{ref}\" {clean} "
           f"| samtools sort -@ {t} -o {bam} -", logf, "alignment")
        sh(f"samtools index {bam}", logf, "pengindeksan BAM")
        sh(f"samtools flagstat {bam} > {out/'flagstat.txt'}", logf, "flagstat")
        fs = (out / "flagstat.txt").read_text()
        total = int(re.search(r"^(\d+) \+ \d+ in total", fs, re.M).group(1))
        mapped = int(re.search(r"^(\d+) \+ \d+ mapped", fs, re.M).group(1))
        stats["alignment"] = {
            "total_reads": total,
            "terpetakan": mapped,
            "tidak_terpetakan": total - mapped,
            "persen_terpetakan": round(mapped / total * 100, 2) if total else 0,
        }
        on_stats(stats)

        # 4. Variant calling (E. coli = haploid)
        on_stage("variant_calling")
        raw = out / "raw.vcf"
        sh(f'bcftools mpileup -f "{ref}" -q {cfg["min_mapq"]} -Q {cfg["min_baseq"]} -a FORMAT/AD -Ou {bam} '
           f"| bcftools call -mv --ploidy 1 -Ov -o {raw}", logf, "variant calling")
        stats["variant_calling"] = {"varian_mentah": _count_vcf(raw)}
        on_stats(stats)

        # 5. Filtering
        on_stage("filtering")
        filt = out / "filtered.vcf"
        sh(f"bcftools filter -i 'QUAL>={cfg['min_qual']} && INFO/DP>={cfg['min_depth']}' -Ov -o {filt} {raw}",
           logf, "filtering")
        stats["filtering"] = {"varian_lolos": _count_vcf(filt)}
        on_stats(stats)

        # 6. Anotasi SnpEff
        on_stage("annotation")
        ann = out / "annotated.vcf"
        n_err = annotate(filt, ann, out, snpeff_db, logf)
        rows = parse_annotated_vcf(ann)
        stats["annotation"] = summarize(rows)
        stats["annotation"]["tidak_teranotasi"] = n_err
        on_stats(stats)
    return rows


def _vcf_chroms(path: Path):
    seen = []
    for line in open(path):
        if line.startswith("#"):
            continue
        c = line.split("\t", 1)[0]
        if c not in seen:
            seen.append(c)
    return seen


def _db_chroms(err_text: str):
    """Baca nama kromosom database dari keluaran verbose SnpEff."""
    return re.findall(r"^#\s+'([^']+)'\s+\d+\s+\S+", err_text, re.M)


def _run_snpeff(snpeff_db: str, vcf_in: Path, vcf_out: Path, logf):
    err = vcf_out.with_suffix(".err")
    sh(f"snpEff -Xmx2g -v {snpeff_db} {vcf_in} > {vcf_out} 2> {err}", logf, "anotasi (SnpEff)")
    text = err.read_text(errors="ignore")
    logf.write(text[-3000:])
    logf.flush()
    n_err = sum(1 for l in open(vcf_out) if not l.startswith("#") and "ERROR_CHROMOSOME_NOT_FOUND" in l)
    return text, n_err


def annotate(filt: Path, ann: Path, out: Path, snpeff_db: str, logf) -> int:
    """Anotasi dengan SnpEff. Jika nama kromosom referensi berbeda dengan database
    (kasus satu kromosom), nama dipetakan sementara lalu dikembalikan ke nama asli.
    Mengembalikan jumlah varian yang tidak dapat dianotasi."""
    total = _count_vcf(filt)
    text, n_err = _run_snpeff(snpeff_db, filt, ann, logf)
    if total and n_err == total:
        vc, dc = _vcf_chroms(filt), _db_chroms(text)
        if len(vc) == 1 and len(dc) == 1 and vc[0] != dc[0]:
            logf.write(f"\n[info] Nama kromosom dipetakan sementara: {vc[0]} -> {dc[0]}\n")
            fwd, rev = out / "chrmap.txt", out / "chrmap_rev.txt"
            fwd.write_text(f"{vc[0]} {dc[0]}\n")
            rev.write_text(f"{dc[0]} {vc[0]}\n")
            renamed, tmp = out / "filtered_renamed.vcf", out / "annotated_renamed.vcf"
            sh(f"bcftools annotate --rename-chrs {fwd} {filt} -Ov -o {renamed}", logf, "pemetaan nama kromosom")
            text, n_err = _run_snpeff(snpeff_db, renamed, tmp, logf)
            sh(f"bcftools annotate --rename-chrs {rev} {tmp} -Ov -o {ann}", logf, "pengembalian nama kromosom")
        else:
            raise PipelineError(
                f"Nama kromosom pada referensi ({', '.join(vc)}) tidak cocok dengan database anotasi "
                f"({', '.join(dc) or 'tidak terbaca'}) dan tidak dapat dipetakan otomatis. "
                "Gunakan referensi yang sesuai dengan database anotasi.")
        if total and n_err == total:
            raise PipelineError("Anotasi gagal: seluruh varian tidak dapat dipetakan ke database anotasi.")
    return n_err


def _count_vcf(p: Path) -> int:
    return sum(1 for l in open(p) if not l.startswith("#"))


def parse_annotated_vcf(path: Path):
    rows = []
    for line in open(path):
        if line.startswith("#"):
            continue
        f = line.rstrip("\n").split("\t")
        chrom, pos, _id, ref, alt, qual, _flt, info = f[:8]
        d = dict(kv.split("=", 1) for kv in info.split(";") if "=" in kv)
        gen = efek = impact = None
        if "ANN" in d:
            a = d["ANN"].split(",")[0].split("|")  # ambil anotasi pertama
            efek, impact, gen = a[1], a[2], a[3]
        tipe = "INDEL" if ("INDEL" in info or len(ref) != len(alt.split(",")[0])) else "SNP"
        rows.append({
            "chrom": chrom, "posisi": int(pos), "ref": ref, "alt": alt, "tipe": tipe,
            "qual": float(qual) if qual != "." else None,
            "depth": int(d["DP"]) if "DP" in d else None,
            "gen": gen, "efek": efek, "impact": impact,
        })
    return rows


def summarize(rows):
    from collections import Counter
    return {
        "total_varian": len(rows),
        "snp": sum(1 for r in rows if r["tipe"] == "SNP"),
        "indel": sum(1 for r in rows if r["tipe"] == "INDEL"),
        "gen_terdampak": len({r["gen"] for r in rows if r["gen"]}),
        "per_impact": dict(Counter(r["impact"] or "NA" for r in rows)),
        "per_efek": dict(Counter(r["efek"] or "NA" for r in rows).most_common(10)),
    }
