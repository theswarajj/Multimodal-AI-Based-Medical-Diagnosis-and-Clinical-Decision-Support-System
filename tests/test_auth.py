import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pyotp
from fastapi.testclient import TestClient
from backend.main import app
from backend.config import ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_TOTP_SECRET

client = TestClient(app)


def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    print("✓ Health check endpoint OK")


def test_admin_login():
    totp = pyotp.TOTP(ADMIN_TOTP_SECRET)
    code = totp.now()
    res = client.post("/api/auth/admin/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD,
        "totp_code": code
    })
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "success"
    assert "access_token" in data
    assert data["user"]["role"] == "admin"
    print("✓ Admin login with TOTP 2FA OK")


def test_doctor_login_approved():
    # Dr. Aris Thorne is approved in seed
    res = client.post("/api/auth/doctor/login", json={
        "reg_number": "MC-2015-88412",
        "password": "DoctorSecure#1"
    })
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "success"
    assert "access_token" in data
    assert data["user"]["doctor_id"] is not None
    print("✓ Approved doctor login OK")


def test_doctor_login_pending():
    # Dr. Elena Rostova is pending in seed
    res = client.post("/api/auth/doctor/login", json={
        "reg_number": "MC-2021-49102",
        "password": "DoctorSecure#2"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "pending_review"
    assert data["doctor_status"] == "PENDING"
    print("✓ Pending doctor status flow OK")


def test_doctor_login_needs_info():
    # Ensure Marcus Vance is in NEEDS_INFO state for testing the lifecycle branch
    from backend.database import SessionLocal
    from backend.models import DoctorProfile
    db = SessionLocal()
    p = db.query(DoctorProfile).filter(DoctorProfile.reg_number == "MC-2018-77319").first()
    if p:
        p.status = "NEEDS_INFO"
        p.status_reason = "Proof of current affiliation required."
        db.commit()
    db.close()

    res = client.post("/api/auth/doctor/login", json={
        "reg_number": "MC-2018-77319",
        "password": "DoctorSecure#3"
    })
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "needs_info", f"Unexpected status: {data}"
    assert data["doctor_status"] == "NEEDS_INFO"
    print("✓ Needs info doctor status flow OK")


def test_application_status_lookup():
    res = client.get("/api/auth/application-status/MC-2021-49102")
    assert res.status_code == 200
    data = res.json()
    assert data["reg_number"] == "MC-2021-49102"
    assert data["status"] == "PENDING"
    print("✓ Application status public lookup OK")


if __name__ == "__main__":
    test_health()
    test_admin_login()
    test_doctor_login_approved()
    test_doctor_login_pending()
    test_doctor_login_needs_info()
    test_application_status_lookup()
    print("\nALL PHASE 1 BACKEND AUTH TESTS PASSED PERFECTLY!")
