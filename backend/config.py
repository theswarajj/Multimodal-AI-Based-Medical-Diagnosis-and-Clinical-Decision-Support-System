import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_DIR = BASE_DIR / "INPUT"
OUTPUT_DIR = BASE_DIR / "OUTPUT"
REPORTS_DIR = OUTPUT_DIR / "REPORTS"
UPLOAD_DIR = BASE_DIR / "UPLOADS"
DB_PATH = BASE_DIR / "clinical_lens.db"

# Create directories
for p in [INPUT_DIR, OUTPUT_DIR, REPORTS_DIR, UPLOAD_DIR]:
    p.mkdir(parents=True, exist_ok=True)

# Security and Auth
SECRET_KEY = os.environ.get("CLINICAL_LENS_SECRET", "clinical_lens_secure_session_key_2026_local_only")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12  # 12 hours for clinical shift
REFRESH_TOKEN_EXPIRE_DAYS = 7
SESSION_IDLE_TIMEOUT_MINUTES = 15
MAX_FAILED_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 30

# Seed Admin Credentials
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@clinicallens.local")
ADMIN_NAME = os.environ.get("ADMIN_NAME", "ClinicalLens Administrator")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "AdminSecure#2026")
ADMIN_TOTP_SECRET = os.environ.get("ADMIN_TOTP_SECRET", "JBSWY3DPEHPK3PXPFZSW63TFMR2WY2LE")

# Server Run Session OTP: Generated once at backend startup, valid until server stops
import secrets
SERVER_SESSION_OTP = f"{secrets.randbelow(900000) + 100000}"

# GPU and Analysis Config
MAX_GPU_QUEUE_SIZE = 50
LLM_MODEL = "medgemma-text"
