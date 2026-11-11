"""Autentikasi MutaTrack: registrasi, login, token JWT, dan pemeriksaan kepemilikan analisis."""
import base64
import hashlib
import logging
import os
import re
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Deque, Dict, Optional

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from psycopg2 import errors as pgerrors

from . import db

log = logging.getLogger("mutatrack.auth")

JWT_ALGORITHM = "HS256"
TOKEN_TTL_HOURS = int(os.environ.get("TOKEN_TTL_HOURS", "12"))

_secret = os.environ.get("JWT_SECRET", "").strip()
if len(_secret) < 16:
    log.warning(
        "JWT_SECRET kosong atau kurang dari 16 karakter. Memakai rahasia acak sementara; "
        "semua login akan hilang setiap backend dimulai ulang. Isi JWT_SECRET di .env."
    )
    _secret = secrets.token_urlsafe(48)
JWT_SECRET = _secret

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
MIN_PASSWORD = 8
MAX_PASSWORD = 128

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)


# ------------------------------------------------------------------ password

def _prehash(password: str) -> bytes:
    # bcrypt hanya membaca 72 byte pertama; pra-hash agar semua karakter ikut dihitung.
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(password), password_hash.encode("ascii"))
    except Exception:
        return False


_DUMMY_HASH = hash_password("dummy-password-for-timing")

# ------------------------------------------------------- pembatas percobaan login
_MAX_FAILS = 5
_WINDOW = 15 * 60
_fails: Dict[str, Deque[float]] = defaultdict(deque)


def _check_rate(key: str) -> None:
    now = time.time()
    q = _fails[key]
    while q and now - q[0] > _WINDOW:
        q.popleft()
    if len(q) >= _MAX_FAILS:
        raise HTTPException(status_code=429, detail="Terlalu banyak percobaan gagal. Coba lagi dalam 15 menit.")


def _record_fail(key: str) -> None:
    _fails[key].append(time.time())


# --------------------------------------------------------------------- token

def create_token(user: dict) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["id"]),
        "iat": now,
        "exp": now + timedelta(hours=TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def public_user(row: dict) -> dict:
    created = row.get("created_at")
    return {
        "id": str(row["id"]),
        "email": row["email"],
        "nama": row.get("nama") or "",
        "role": row["role"],
        "created_at": created.isoformat() if created else None,
    }


def get_current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> dict:
    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Silakan login terlebih dahulu.")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sesi login berakhir. Silakan login kembali.")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token tidak valid.")
    row = db.fetch_one("select id, email, nama, role, created_at from users where id = %s", (payload.get("sub"),))
    if not row:
        raise HTTPException(status_code=401, detail="Akun tidak ditemukan.")
    return public_user(row)


# ------------------------------------------------------------- kepemilikan

def assert_owner(analysis_id: str, user: dict) -> None:
    """404 bila analisis bukan milik user (admin boleh semua). 404, bukan 403, agar ID tidak bocor."""
    owner = db.get_owner(analysis_id)
    if owner is None or (owner != user["id"] and user["role"] != "admin"):
        raise HTTPException(status_code=404, detail="Analisis tidak ditemukan.")


def owned_analysis_ids(user: dict):
    return db.list_ext_ids(user["id"], user["role"] == "admin")


# ------------------------------------------------------------------- rute

class RegisterRequest(BaseModel):
    email: str
    password: str
    nama: str


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/register", status_code=201)
def register(req: RegisterRequest):
    email = req.email.strip().lower()
    nama = req.nama.strip()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Format email tidak valid.")
    if not (MIN_PASSWORD <= len(req.password) <= MAX_PASSWORD):
        raise HTTPException(status_code=422, detail=f"Kata sandi harus {MIN_PASSWORD} sampai {MAX_PASSWORD} karakter.")
    if not nama or len(nama) > 100:
        raise HTTPException(status_code=422, detail="Nama wajib diisi (maksimal 100 karakter).")

    pw_hash = hash_password(req.password)
    try:
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "insert into users (email, password_hash, nama) values (%s, %s, %s) "
                "returning id, email, nama, role, created_at",
                (email, pw_hash, nama),
            )
            cols = [d[0] for d in cur.description]
            row = dict(zip(cols, cur.fetchone()))
    except pgerrors.UniqueViolation:
        raise HTTPException(status_code=409, detail="Email sudah terdaftar. Silakan login.")
    return {"token": create_token(row), "user": public_user(row)}


@router.post("/login")
def login(req: LoginRequest):
    email = req.email.strip().lower()
    _check_rate(email)
    row = db.fetch_one(
        "select id, email, nama, role, created_at, password_hash from users where email = %s", (email,)
    )
    ok = verify_password(req.password, row["password_hash"] if row else _DUMMY_HASH)
    if not row or not ok:
        _record_fail(email)
        raise HTTPException(status_code=401, detail="Email atau kata sandi salah.")
    _fails.pop(email, None)
    return {"token": create_token(row), "user": public_user(row)}


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return {"user": user}
