import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlparse
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from sqlalchemy import select, delete
from app.models import EmailToken, utcnow

hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)

def hash_password(raw: str) -> str:
    return hasher.hash(raw)

def verify_password(stored: str, raw: str) -> bool:
    try:
        return hasher.verify(stored, raw)
    except (VerifyMismatchError, VerificationError, ValueError):
        return False

def create_token(db, user_id: int, purpose: str, hours=24):
    db.execute(delete(EmailToken).where(EmailToken.user_id == user_id, EmailToken.purpose == purpose))
    raw = secrets.token_urlsafe(32)
    token = EmailToken(user_id=user_id, purpose=purpose,
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        expires_at=utcnow() + timedelta(hours=hours))
    db.add(token)
    db.flush()
    return raw

def consume_token(db, raw: str, purpose: str):
    digest = hashlib.sha256(raw.encode()).hexdigest()
    item = db.scalar(select(EmailToken).where(EmailToken.token_hash == digest, EmailToken.purpose == purpose))
    if not item or item.expires_at < utcnow():
        return None
    uid = item.user_id
    db.delete(item)
    db.flush()
    return uid

def valid_url(raw):
    if not raw:
        return ''
    parsed = urlparse(raw)
    return raw[:400] if parsed.scheme in ('https', 'http') and parsed.netloc else ''

def clean_text(raw, limit=500):
    return str(raw or '').strip()[:limit]

def password_ok(raw):
    return len(raw) >= 10 and len(raw) <= 128
