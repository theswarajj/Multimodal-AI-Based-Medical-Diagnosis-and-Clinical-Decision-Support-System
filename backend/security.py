import datetime
import hashlib
import json
import secrets
from typing import Optional, Dict, Any
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import jwt
import pyotp
from sqlalchemy.orm import Session as DBSession

from backend.config import (
    SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS
)
from backend.models import AuditLog, Session, User

ph = PasswordHasher()


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(hash_str: str, password: str) -> bool:
    try:
        return ph.verify(hash_str, password)
    except (VerifyMismatchError, Exception):
        return False


def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + (expires_delta or datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except Exception:
        return None


def verify_totp(secret: str, code: str) -> bool:
    totp = pyotp.TOTP(secret)
    # Validates current code and allows +-1 step (30s drift)
    return totp.verify(code, valid_window=1)


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def get_totp_uri(secret: str, email: str) -> str:
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name="ClinicalLens")


def create_audit_log(
    db: DBSession,
    action: str,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> AuditLog:
    """Creates a tamper-evident audit log entry with cryptographic SHA-256 hash chaining."""
    last_entry = db.query(AuditLog).order_by(AuditLog.sequence_num.desc()).first()
    if last_entry:
        sequence_num = last_entry.sequence_num + 1
        prev_hash = last_entry.current_hash
    else:
        sequence_num = 1
        prev_hash = "0" * 64

    now = datetime.datetime.utcnow()
    details_str = json.dumps(details or {}, sort_keys=True)
    payload = f"{prev_hash}|{sequence_num}|{now.isoformat()}|{actor_id}|{actor_role}|{action}|{target_type}|{target_id}|{details_str}"
    current_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    entry = AuditLog(
        sequence_num=sequence_num,
        prev_hash=prev_hash,
        current_hash=current_hash,
        timestamp=now,
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id else None,
        ip_address=ip_address,
        user_agent=user_agent,
        details_json=details_str
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def verify_audit_chain(db: DBSession) -> tuple[bool, Optional[int]]:
    """Verifies that the entire audit log has not been tampered with."""
    entries = db.query(AuditLog).order_by(AuditLog.sequence_num.asc()).all()
    expected_prev = "0" * 64
    for e in entries:
        if e.prev_hash != expected_prev:
            return False, e.sequence_num
        payload = f"{e.prev_hash}|{e.sequence_num}|{e.timestamp.isoformat()}|{e.actor_id}|{e.actor_role}|{e.action}|{e.target_type}|{e.target_id}|{e.details_json}"
        calc_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        if calc_hash != e.current_hash:
            return False, e.sequence_num
        expected_prev = e.current_hash
    return True, None
