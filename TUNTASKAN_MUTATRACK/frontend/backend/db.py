"""Koneksi PostgreSQL dan fungsi penyimpanan MutaTrack (users, analyses, variants)."""
import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from psycopg2.extras import Json, RealDictCursor, execute_values
from psycopg2.pool import ThreadedConnectionPool

log = logging.getLogger("mutatrack.db")
_pool: Optional[ThreadedConnectionPool] = None

# Sama dengan schema.sql, ditambah kolom ext_id (ID analisis berbentuk teks "ana_xxxx").
SCHEMA_STATEMENTS = [
    """create table if not exists users (
        id uuid primary key default gen_random_uuid(),
        created_at timestamptz default now(),
        email text not null unique,
        password_hash text not null,
        nama text,
        role text not null default 'user' check (role in ('user','admin'))
    )""",
    """create table if not exists analyses (
        id uuid primary key default gen_random_uuid(),
        user_id uuid not null references users(id) on delete cascade,
        created_at timestamptz default now(),
        updated_at timestamptz default now(),
        nama text not null,
        status text not null default 'draf',
        stage text,
        config jsonb default '{}'::jsonb,
        files jsonb default '{}'::jsonb,
        stats jsonb default '{}'::jsonb,
        error text,
        log_tail text
    )""",
    "alter table analyses add column if not exists ext_id text unique",
    """create table if not exists variants (
        id bigint generated always as identity primary key,
        created_at timestamptz default now(),
        analysis_id uuid not null references analyses(id) on delete cascade,
        chrom text, posisi bigint, ref text, alt text,
        tipe text, qual real, depth int,
        gen text, efek text, impact text
    )""",
    "create index if not exists variants_analysis_id_idx on variants (analysis_id)",
]


def init_pool(retries: int = 15, delay: float = 2.0) -> None:
    global _pool
    if _pool is not None:
        return
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL belum diatur.")
    last: Optional[Exception] = None
    for _ in range(retries):
        try:
            _pool = ThreadedConnectionPool(1, 10, dsn=url)
            return
        except Exception as e:  # database belum siap
            last = e
            time.sleep(delay)
    raise RuntimeError(f"Tidak dapat terhubung ke database: {last}")


@contextmanager
def get_conn():
    if _pool is None:
        init_pool()
    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def ensure_schema() -> None:
    with get_conn() as conn, conn.cursor() as cur:
        for stmt in SCHEMA_STATEMENTS:
            cur.execute(stmt)


def fetch_one(sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def fetch_all(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _clean(s: Any) -> Any:
    return s.replace("\x00", "") if isinstance(s, str) else s


# ---------------------------------------------------------------- analisis

def register_analysis(ext_id: str, user_id: str, nama: str, config: dict, files: dict) -> str:
    """Catat analisis milik user. Mengembalikan 'created', 'exists' (milik user ini), atau 'conflict'."""
    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """insert into analyses (user_id, ext_id, nama, status, config, files)
               values (%s, %s, %s, 'draf', %s, %s)
               on conflict (ext_id) do nothing returning id""",
            (user_id, ext_id, _clean(nama), Json(config), Json(files)),
        )
        if cur.fetchone():
            return "created"
        cur.execute("select user_id from analyses where ext_id = %s", (ext_id,))
        row = cur.fetchone()
        if row and str(row["user_id"]) == str(user_id):
            cur.execute(
                "update analyses set nama=%s, config=%s, files=%s, updated_at=now() where ext_id=%s",
                (_clean(nama), Json(config), Json(files), ext_id),
            )
            return "exists"
        return "conflict"


def get_owner(ext_id: str) -> Optional[str]:
    row = fetch_one("select user_id from analyses where ext_id = %s", (ext_id,))
    return str(row["user_id"]) if row else None


def list_ext_ids(user_id: str, is_admin: bool) -> List[str]:
    if is_admin:
        rows = fetch_all("select ext_id from analyses where ext_id is not null order by created_at desc")
    else:
        rows = fetch_all(
            "select ext_id from analyses where user_id=%s and ext_id is not null order by created_at desc",
            (user_id,),
        )
    return [r["ext_id"] for r in rows]


def sync_job(job) -> None:
    """Dipanggil setiap job.save_metadata(). Tidak boleh menggagalkan pipeline."""
    try:
        log_tail = _clean("\n".join(job.logs[-30:]))
        with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """update analyses set status=%s, stage=%s, stats=%s, error=%s, log_tail=%s,
                          config=%s, files=%s, updated_at=now()
                   where ext_id=%s returning id""",
                (
                    job.status, job.stage, Json(job.stats or {}), _clean(job.error), log_tail,
                    Json(job.config or {}), Json(job.files or {}), job.analysis_id,
                ),
            )
            row = cur.fetchone()
            if not row:
                return  # analisis lama tanpa pemilik; tidak disimpan
            if job.status == "selesai" and job.variants:
                cur.execute("delete from variants where analysis_id = %s", (row["id"],))
                rows = [
                    (
                        row["id"], v.get("chrom"), v.get("posisi"), v.get("ref"), v.get("alt"),
                        v.get("tipe"), v.get("qual"), v.get("depth"),
                        v.get("gen"), v.get("efek"), v.get("impact"),
                    )
                    for v in job.variants
                ]
                execute_values(
                    cur,
                    """insert into variants
                       (analysis_id, chrom, posisi, ref, alt, tipe, qual, depth, gen, efek, impact)
                       values %s""",
                    rows,
                    page_size=1000,
                )
    except Exception as e:
        log.warning("Gagal menyinkronkan analisis %s ke database: %s", getattr(job, "analysis_id", "?"), e)


def delete_analysis_row(ext_id: str) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("delete from analyses where ext_id = %s", (ext_id,))
