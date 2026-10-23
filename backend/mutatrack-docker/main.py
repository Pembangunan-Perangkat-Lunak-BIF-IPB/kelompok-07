"""API MutaTrack (FastAPI + PostgreSQL). Jalankan: uvicorn main:app --host 0.0.0.0 --port 8000"""
import csv
import io
import os
import shutil
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import bcrypt
import jwt
import psycopg
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from pipeline import DEFAULT_CONFIG, STAGES, PipelineError, run_pipeline

load_dotenv()
DATA_DIR = Path(os.getenv("DATA_DIR", "./data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
SNPEFF_DB = os.getenv("SNPEFF_DB", "")
THREADS = int(os.getenv("THREADS", "2"))
DATABASE_URL = os.environ["DATABASE_URL"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_HOURS = int(os.getenv("JWT_HOURS", "12"))

app = FastAPI(title="MutaTrack API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()],
    allow_methods=["*"], allow_headers=["*"],
)

# Laptop 8 GB: hanya 1 pipeline berjalan pada satu waktu
RUN_LOCK = threading.Semaphore(1)


# ---------- Database ----------
def q(sql: str, params=(), fetch: str = "all"):
    """Jalankan satu query. fetch: 'all' | 'one' | 'none'. Transaksi otomatis di-commit."""
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        cur = conn.execute(sql, params)
        if fetch == "none" or cur.description is None:
            return None
        return cur.fetchone() if fetch == "one" else cur.fetchall()


_UPDATE_COLS = {"status", "stage", "config", "files", "stats", "error", "log_tail"}
_JSON_COLS = {"config", "files", "stats"}


def update(aid: str, **fields):
    sets, vals = ["updated_at = now()"], []
    for k, v in fields.items():
        if k not in _UPDATE_COLS:
            raise ValueError(f"Kolom tidak dikenal: {k}")
        sets.append(f"{k} = %s")
        vals.append(Jsonb(v) if k in _JSON_COLS else v)
    q(f"update analyses set {', '.join(sets)} where id = %s", (*vals, aid), "none")


# ---------- Auth (FR-01, NFR04) ----------
bearer = HTTPBearer(auto_error=False)
EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class RegisterIn(BaseModel):
    email: str = Field(pattern=EMAIL_RE, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    nama: str | None = Field(default=None, max_length=100)


class LoginIn(BaseModel):
    email: str
    password: str


def _pw_bytes(pw: str) -> bytes:
    b = pw.encode("utf-8")
    if len(b) > 72:  # batas bcrypt
        raise ValueError("Password terlalu panjang (maks. 72 byte).")
    return b


def make_token(user: dict) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=JWT_HOURS)
    return jwt.encode({"sub": str(user["id"]), "exp": exp}, JWT_SECRET, algorithm="HS256")


def current_user(cred: HTTPAuthorizationCredentials = Depends(bearer)):
    if not cred or not cred.credentials:
        raise HTTPException(401, "Harus login terlebih dahulu.")
    try:
        uid = jwt.decode(cred.credentials, JWT_SECRET, algorithms=["HS256"])["sub"]
        UUID(uid)
    except Exception:
        raise HTTPException(401, "Sesi tidak valid atau kedaluwarsa. Silakan login ulang.")
    user = q("select id, email, nama, role from users where id = %s", (uid,), "one")
    if not user:
        raise HTTPException(401, "Sesi tidak valid atau kedaluwarsa. Silakan login ulang.")
    return user


@app.post("/auth/register", status_code=201)
def register(body: RegisterIn):
    email = body.email.strip().lower()
    try:
        pw = _pw_bytes(body.password)
    except ValueError as e:
        raise HTTPException(400, str(e))
    hashed = bcrypt.hashpw(pw, bcrypt.gensalt()).decode()
    try:
        user = q("insert into users (email, password_hash, nama) values (%s, %s, %s) "
                 "returning id, email, nama, role", (email, hashed, body.nama), "one")
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, "Email sudah terdaftar.")
    return {"token": make_token(user), "user": user}


@app.post("/auth/login")
def login(body: LoginIn):
    email = body.email.strip().lower()
    row = q("select id, email, nama, role, password_hash from users where email = %s", (email,), "one")
    ok = False
    if row:
        try:
            ok = bcrypt.checkpw(_pw_bytes(body.password), row["password_hash"].encode())
        except ValueError:
            ok = False
    if not ok:
        raise HTTPException(401, "Email atau password salah.")
    row.pop("password_hash")
    return {"token": make_token(row), "user": row}


@app.get("/auth/me")
def me(user=Depends(current_user)):
    return user


# ---------- Helper analisis ----------
def get_analysis(aid: str, user) -> dict:
    try:
        UUID(aid)
    except ValueError:
        raise HTTPException(404, "Analisis tidak ditemukan.")
    a = q("select * from analyses where id = %s and user_id = %s", (aid, user["id"]), "one")
    if not a:
        raise HTTPException(404, "Analisis tidak ditemukan.")
    return a


def adir(aid: str) -> Path:
    d = DATA_DIR / aid
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------- Endpoint ----------
@app.get("/health")
def health():
    return {"ok": True, "snpeff_db": SNPEFF_DB}


@app.get("/config/default")
def default_config():
    return DEFAULT_CONFIG


@app.post("/analyses")
def create_analysis(
    nama: str = Form(...),
    r1: UploadFile = File(...),
    reference: UploadFile = File(...),
    r2: UploadFile | None = File(None),
    user=Depends(current_user),
):
    row = q("insert into analyses (user_id, nama, config) values (%s, %s, %s) returning id",
            (user["id"], nama, Jsonb(DEFAULT_CONFIG)), "one")
    aid = str(row["id"])
    d = adir(aid)
    files = {}
    for key, up in (("r1", r1), ("r2", r2), ("reference", reference)):
        if up is None or not up.filename:
            continue
        safe = Path(up.filename).name
        with open(d / safe, "wb") as out:
            shutil.copyfileobj(up.file, out)
        files[key] = safe
    update(aid, files=files)
    return {"id": aid, "files": files}


@app.post("/analyses/{aid}/validate")
def validate(aid: str, user=Depends(current_user)):
    a = get_analysis(aid, user)
    d = adir(aid)
    f = a["files"] or {}
    errors = []
    if "r1" not in f:
        errors.append("File FASTQ (R1) belum diunggah.")
    if "reference" not in f:
        errors.append("Reference genome (FASTA) belum diunggah.")
    for key in ("r1", "r2"):
        if key in f:
            err = _check_fastq(d / f[key])
            if err:
                errors.append(f"{f[key]}: {err}")
    if "reference" in f:
        err = _check_fasta(d / f["reference"])
        if err:
            errors.append(f"{f['reference']}: {err}")
    if errors:
        update(aid, status="tidak_valid", error="; ".join(errors))
        return {"valid": False, "errors": errors}
    update(aid, status="valid", error=None)
    return {"valid": True, "errors": []}


def _open(p: Path):
    import gzip
    return gzip.open(p, "rt") if p.suffix == ".gz" else open(p, "r")


def _check_fastq(p: Path):
    name = p.name.lower().replace(".gz", "")
    if not name.endswith((".fastq", ".fq")):
        return "ekstensi harus .fastq/.fq (boleh .gz)."
    try:
        with _open(p) as fh:
            lines = [fh.readline() for _ in range(4)]
    except Exception:
        return "berkas korup atau tidak dapat dibaca."
    if not lines[0].startswith("@") or not lines[2].startswith("+") or len(lines[1].strip()) != len(lines[3].strip()):
        return "format FASTQ tidak valid."
    return None


def _check_fasta(p: Path):
    if p.suffix.lower() not in (".fa", ".fasta", ".fna"):
        return "ekstensi harus .fa/.fasta/.fna."
    ids = set()
    try:
        with open(p) as fh:
            first = True
            for line in fh:
                if first:
                    if not line.startswith(">"):
                        return "format FASTA tidak valid (harus diawali '>')."
                    first = False
                if line.startswith(">"):
                    sid = line[1:].split()[0]
                    if sid in ids:
                        return f"ID sekuens ganda: {sid}."
                    ids.add(sid)
    except Exception:
        return "berkas korup atau tidak dapat dibaca."
    return None


@app.put("/analyses/{aid}/config")
def set_config(aid: str, config: dict, user=Depends(current_user)):
    get_analysis(aid, user)
    unknown = [k for k in config if k not in DEFAULT_CONFIG]
    if unknown:
        raise HTTPException(400, f"Parameter tidak dikenal: {', '.join(unknown)}")
    update(aid, config={**DEFAULT_CONFIG, **config})
    return {"ok": True}


@app.post("/analyses/{aid}/run")
def run(aid: str, user=Depends(current_user)):
    a = get_analysis(aid, user)
    if a["status"] not in ("valid", "gagal"):
        raise HTTPException(400, "Analisis hanya dapat dijalankan setelah input dinyatakan valid.")  # BR-03
    update(aid, status="berjalan", stage="qc", error=None, stats={})
    threading.Thread(target=_worker, args=(aid,), daemon=True).start()
    return {"status": "berjalan"}


def _save_variants(aid: str, rows: list):
    cols = ["chrom", "posisi", "ref", "alt", "tipe", "qual", "depth", "gen", "efek", "impact"]
    sql = (f"insert into variants (analysis_id, {', '.join(cols)}) "
           f"values (%(analysis_id)s, {', '.join('%(' + c + ')s' for c in cols)})")
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute("delete from variants where analysis_id = %s", (aid,))  # aman untuk jalankan ulang
        if rows:
            with conn.cursor() as cur:
                cur.executemany(sql, [{**r, "analysis_id": aid} for r in rows])


def _worker(aid: str):
    with RUN_LOCK:
        a = q("select * from analyses where id = %s", (aid,), "one")
        d = adir(aid)
        f = a["files"]
        try:
            rows = run_pipeline(
                d, d / f["r1"], (d / f["r2"]) if "r2" in f else None, d / f["reference"],
                a["config"], SNPEFF_DB, THREADS,
                on_stage=lambda s: update(aid, stage=s),
                on_stats=lambda s: update(aid, stats=s),
            )
            _save_variants(aid, rows)
            update(aid, status="selesai", stage="annotation")
        except PipelineError as e:
            update(aid, status="gagal", error=str(e))
        except Exception as e:
            update(aid, status="gagal", error=f"Kesalahan tak terduga: {e}")
        finally:
            lp = d / "pipeline.log"
            if lp.exists():
                update(aid, log_tail="".join(lp.read_text().splitlines(True)[-60:]))


@app.get("/analyses")
def list_analyses(user=Depends(current_user)):
    return q("select id, nama, status, stage, created_at from analyses "
             "where user_id = %s order by created_at desc", (user["id"],))


@app.get("/analyses/{aid}")
def get_one(aid: str, user=Depends(current_user)):
    a = get_analysis(aid, user)
    lp = DATA_DIR / aid / "pipeline.log"
    if a["status"] == "berjalan" and lp.exists():  # log live
        a["log_tail"] = "".join(lp.read_text().splitlines(True)[-60:])
    a["stages"] = STAGES
    return a


@app.get("/analyses/{aid}/summary")
def summary(aid: str, user=Depends(current_user)):
    a = get_analysis(aid, user)
    if a["status"] != "selesai":
        raise HTTPException(400, "Analisis belum selesai.")  # BR-07
    return a["stats"]


@app.get("/analyses/{aid}/variants")
def variants(aid: str, limit: int = 200, offset: int = 0, impact: str | None = None, user=Depends(current_user)):
    get_analysis(aid, user)
    limit = max(1, min(limit, 1000))
    offset = max(0, offset)
    sql, params = "select * from variants where analysis_id = %s", [aid]
    if impact:
        sql += " and impact = %s"
        params.append(impact.upper())
    sql += " order by posisi limit %s offset %s"
    params += [limit, offset]
    return q(sql, tuple(params))


@app.get("/analyses/{aid}/download")
def download(aid: str, format: str = "vcf", user=Depends(current_user)):
    a = get_analysis(aid, user)
    if a["status"] != "selesai":
        raise HTTPException(400, "File hasil belum tersedia.")  # BR-08
    d = DATA_DIR / aid
    if format == "vcf":
        return FileResponse(d / "out" / "annotated.vcf", filename=f"{a['nama']}.vcf")
    rows = q("select * from variants where analysis_id = %s order by posisi", (aid,))
    if format == "csv":
        buf = io.StringIO()
        cols = ["chrom", "posisi", "ref", "alt", "tipe", "qual", "depth", "gen", "efek", "impact"]
        w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
        return Response(buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{a["nama"]}.csv"'})
    if format == "pdf":
        return Response(_make_pdf(a, rows), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{a["nama"]}.pdf"'})
    raise HTTPException(400, "Format harus vcf, csv, atau pdf.")


def _make_pdf(a: dict, rows: list) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    def line(txt, size=10, dy=16):
        nonlocal y
        if y < 60:
            c.showPage(); y = 800
        c.setFont("Helvetica", size); c.drawString(50, y, txt); y -= dy
    line("Laporan Analisis MutaTrack", 16, 26)
    line(f"Nama analisis : {a['nama']}")
    line(f"Dibuat        : {a['created_at']}", dy=24)
    s = a.get("stats", {})
    al, an = s.get("alignment", {}), s.get("annotation", {})
    line("Ringkasan", 13, 20)
    line(f"Total reads: {al.get('total_reads')}   Terpetakan: {al.get('persen_terpetakan')}%")
    line(f"Total varian: {an.get('total_varian')}  (SNP {an.get('snp')}, INDEL {an.get('indel')})")
    line(f"Gen terdampak: {an.get('gen_terdampak')}   Per impact: {an.get('per_impact')}", dy=24)
    line("Daftar varian (maks. 100 pertama)", 13, 20)
    for r in rows[:100]:
        line(f"{r['chrom']}:{r['posisi']} {r['ref']}>{r['alt']} {r['tipe']} {r['gen'] or '-'} {r['efek'] or '-'} {r['impact'] or '-'}", 8, 12)
    c.save()
    return buf.getvalue()
