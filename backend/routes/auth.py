import datetime
import os
import shutil
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from backend.database import get_db
from backend.models import User, DoctorProfile, DoctorDocument, Session as UserSession, AuditLog
from backend.security import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    decode_token, verify_totp, create_audit_log
)
from backend.config import (
    MAX_FAILED_LOGIN_ATTEMPTS, LOCKOUT_DURATION_MINUTES,
    UPLOAD_DIR, ACCESS_TOKEN_EXPIRE_MINUTES
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

DOCS_UPLOAD_DIR = UPLOAD_DIR / "doctors"
DOCS_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
#  SCHEMAS
# =============================================================================

class DoctorLoginRequest(BaseModel):
    reg_number: str
    password: str


class AdminLoginRequest(BaseModel):
    email: str
    password: str
    totp_code: str


class ForgotPasswordRequest(BaseModel):
    reg_number: str
    dob: str


class ChangePasswordRequest(BaseModel):
    reg_number: str
    temp_password: str
    new_password: str


# =============================================================================
#  DEPENDENCY: CURRENT USER
# =============================================================================

def get_current_user(request: Request, db: DBSession = Depends(get_db)) -> User:
    token = None
    # 1. Check Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    
    # 2. Check Cookie
    if not token:
        token = request.cookies.get("clinical_lens_token")
    
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    
    return user


# =============================================================================
#  ENDPOINTS
# =============================================================================

@router.get("/admin/demo-totp")
async def get_demo_totp(db: DBSession = Depends(get_db)):
    """Convenience helper: returns current server run session OTP or TOTP code."""
    from backend.config import SERVER_SESSION_OTP
    admin_user = db.query(User).filter(User.role == "admin").first()
    secret = admin_user.totp_secret if admin_user else ""
    return {
        "code": SERVER_SESSION_OTP,
        "secret": secret,
        "is_session_code": True,
        "message": "Valid for this entire backend run session"
    }


@router.post("/doctor/register")
async def register_doctor(
    request: Request,
    full_name: str = Form(...),
    reg_number: str = Form(...),
    issuing_council: str = Form(...),
    reg_year: int = Form(...),
    dob: str = Form(...),
    qualification: str = Form(...),
    specialty: str = Form(...),
    hospital_clinic: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    password: str = Form(...),
    consent: bool = Form(...),
    id_proof: Optional[UploadFile] = File(None),
    reg_cert: Optional[UploadFile] = File(None),
    db: DBSession = Depends(get_db)
):
    if not consent:
        raise HTTPException(status_code=400, detail="Consent for terms and local data processing is required")
    
    # Check duplicate email
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="An account with this email address already exists")
    
    # Check duplicate reg_number
    if db.query(DoctorProfile).filter(DoctorProfile.reg_number == reg_number.strip()).first():
        raise HTTPException(status_code=400, detail="This Medical Council Registration Number is already registered")

    # Save uploaded documents securely
    id_proof_path = None
    cert_path = None

    if id_proof:
        safe_ext = os.path.splitext(id_proof.filename)[1].lower()
        if safe_ext not in [".pdf", ".jpg", ".jpeg", ".png"]:
            raise HTTPException(status_code=400, detail="ID proof must be a PDF or image (JPG/PNG)")
        fname = f"id_{uuid.uuid4().hex[:12]}{safe_ext}"
        target = DOCS_UPLOAD_DIR / fname
        with open(target, "wb") as f:
            shutil.copyfileobj(id_proof.file, f)
        id_proof_path = str(target)

    if reg_cert:
        safe_ext = os.path.splitext(reg_cert.filename)[1].lower()
        if safe_ext not in [".pdf", ".jpg", ".jpeg", ".png"]:
            raise HTTPException(status_code=400, detail="Registration certificate must be a PDF or image (JPG/PNG)")
        fname = f"cert_{uuid.uuid4().hex[:12]}{safe_ext}"
        target = DOCS_UPLOAD_DIR / fname
        with open(target, "wb") as f:
            shutil.copyfileobj(reg_cert.file, f)
        cert_path = str(target)

    user = User(
        email=email,
        password_hash=hash_password(password),
        role="doctor",
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    profile = DoctorProfile(
        user_id=user.id,
        full_name=full_name.strip(),
        reg_number=reg_number.strip(),
        issuing_council=issuing_council.strip(),
        reg_year=reg_year,
        dob=dob.strip(),
        qualification=qualification.strip(),
        specialty=specialty.strip(),
        hospital_clinic=hospital_clinic.strip(),
        phone=phone.strip(),
        status="PENDING",
        status_reason="Your application has been received and is in the verification queue.",
        id_proof_path=id_proof_path,
        cert_path=cert_path,
        consent_given=consent
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    # Add document records if uploaded
    if id_proof_path and id_proof:
        db.add(DoctorDocument(
            doctor_id=profile.id,
            doc_type="ID_PROOF",
            file_path=id_proof_path,
            original_filename=id_proof.filename
        ))
    if cert_path and reg_cert:
        db.add(DoctorDocument(
            doctor_id=profile.id,
            doc_type="REG_CERT",
            file_path=cert_path,
            original_filename=reg_cert.filename
        ))
    db.commit()

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    create_audit_log(
        db,
        action="DOCTOR_APPLICATION_SUBMITTED",
        actor_id=user.id,
        actor_role="doctor",
        target_type="DoctorProfile",
        target_id=str(profile.id),
        details={"reg_number": profile.reg_number, "email": email, "name": full_name},
        ip_address=ip,
        user_agent=ua
    )

    return {
        "status": "success",
        "message": "Application submitted successfully. It is now under administrative review.",
        "reg_number": profile.reg_number,
        "doctor_status": "PENDING"
    }


@router.post("/doctor/login")
async def doctor_login(
    payload: DoctorLoginRequest,
    request: Request,
    response: Response,
    db: DBSession = Depends(get_db)
):
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    profile = db.query(DoctorProfile).filter(DoctorProfile.reg_number == payload.reg_number.strip()).first()
    if not profile or profile.is_deleted:
        create_audit_log(
            db, action="DOCTOR_LOGIN_FAILED_UNKNOWN_REG",
            actor_role="doctor", details={"reg_number": payload.reg_number},
            ip_address=ip, user_agent=ua
        )
        raise HTTPException(status_code=401, detail="Invalid registration number or password")

    user = profile.user

    # Check lockout
    now = datetime.datetime.utcnow()
    if user.locked_until and user.locked_until > now:
        remaining = int((user.locked_until - now).total_seconds() / 60)
        raise HTTPException(
            status_code=423,
            detail=f"Account locked due to 5 consecutive failed attempts. Try again in {remaining} minute(s)."
        )

    # Check temporary password or normal password
    valid = False
    is_temp = False
    if user.temp_password and payload.password == user.temp_password:
        valid = True
        is_temp = True
    elif verify_password(user.password_hash, payload.password):
        valid = True

    if not valid:
        user.failed_attempts = (user.failed_attempts or 0) + 1
        if user.failed_attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
            user.locked_until = now + datetime.timedelta(minutes=LOCKOUT_DURATION_MINUTES)
            profile.status = "LOCKED"
            db.commit()
            create_audit_log(
                db, action="DOCTOR_ACCOUNT_LOCKED",
                actor_id=user.id, actor_role="doctor",
                target_type="User", target_id=str(user.id),
                details={"reg_number": profile.reg_number, "attempts": user.failed_attempts},
                ip_address=ip, user_agent=ua
            )
            raise HTTPException(
                status_code=423,
                detail=f"Account locked after {MAX_FAILED_LOGIN_ATTEMPTS} failed attempts. Lockout lasts {LOCKOUT_DURATION_MINUTES} minutes."
            )
        db.commit()
        create_audit_log(
            db, action="DOCTOR_LOGIN_FAILED_BAD_PASSWORD",
            actor_id=user.id, actor_role="doctor",
            target_type="User", target_id=str(user.id),
            details={"reg_number": profile.reg_number, "attempt": user.failed_attempts},
            ip_address=ip, user_agent=ua
        )
        raise HTTPException(status_code=401, detail="Invalid registration number or password")

    # Reset failed attempts
    user.failed_attempts = 0
    user.locked_until = None
    db.commit()

    # Check Doctor Status Lifecycle
    if profile.status == "PENDING":
        return {
            "status": "pending_review",
            "message": "Your application is currently under review by the clinical administrator.",
            "reg_number": profile.reg_number,
            "full_name": profile.full_name,
            "doctor_status": "PENDING",
            "status_reason": profile.status_reason or "Verification in progress.",
            "submitted_at": profile.created_at.isoformat()
        }
    elif profile.status == "REJECTED":
        return {
            "status": "rejected",
            "message": "Your application was not approved.",
            "reg_number": profile.reg_number,
            "full_name": profile.full_name,
            "doctor_status": "REJECTED",
            "status_reason": profile.status_reason or "Credentials could not be verified.",
            "submitted_at": profile.created_at.isoformat()
        }
    elif profile.status == "NEEDS_INFO":
        return {
            "status": "needs_info",
            "message": "The administrator has requested additional information.",
            "reg_number": profile.reg_number,
            "full_name": profile.full_name,
            "doctor_status": "NEEDS_INFO",
            "status_reason": profile.status_reason or "Additional documentation requested.",
            "submitted_at": profile.created_at.isoformat()
        }
    elif profile.status in ["SUSPENDED", "LOCKED", "EXPIRED", "DEACTIVATED"]:
        raise HTTPException(
            status_code=403,
            detail=f"Account is {profile.status.lower()}: {profile.status_reason or 'Contact system administrator.'}"
        )

    # Approved status -> issue tokens
    token_data = {"sub": str(user.id), "role": "doctor", "doctor_id": profile.id}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    # Set httpOnly Secure SameSite Cookie
    response.set_cookie(
        key="clinical_lens_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=False,  # localhost local execution
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

    create_audit_log(
        db, action="DOCTOR_LOGIN_SUCCESS",
        actor_id=user.id, actor_role="doctor",
        target_type="DoctorProfile", target_id=str(profile.id),
        details={"reg_number": profile.reg_number, "is_temp_password": is_temp},
        ip_address=ip, user_agent=ua
    )

    return {
        "status": "success",
        "access_token": access_token,
        "token_type": "bearer",
        "must_change_password": is_temp or user.must_change_password,
        "user": {
            "id": user.id,
            "doctor_id": profile.id,
            "role": "doctor",
            "full_name": profile.full_name,
            "reg_number": profile.reg_number,
            "specialty": profile.specialty,
            "status": profile.status,
            "allowed_models": profile.allowed_models
        }
    }


@router.post("/admin/login")
async def admin_login(
    payload: AdminLoginRequest,
    request: Request,
    response: Response,
    db: DBSession = Depends(get_db)
):
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    user = db.query(User).filter(User.email == payload.email.strip(), User.role == "admin").first()
    if not user:
        create_audit_log(
            db, action="ADMIN_LOGIN_FAILED_UNKNOWN_EMAIL",
            actor_role="admin", details={"email": payload.email},
            ip_address=ip, user_agent=ua
        )
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    now = datetime.datetime.utcnow()
    if user.locked_until and user.locked_until > now:
        remaining = int((user.locked_until - now).total_seconds() / 60)
        raise HTTPException(
            status_code=423,
            detail=f"Admin account locked due to failed attempts. Try again in {remaining} minute(s)."
        )

    # Verify Password
    if not verify_password(user.password_hash, payload.password):
        user.failed_attempts = (user.failed_attempts or 0) + 1
        if user.failed_attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
            user.locked_until = now + datetime.timedelta(minutes=LOCKOUT_DURATION_MINUTES)
        db.commit()
        create_audit_log(
            db, action="ADMIN_LOGIN_FAILED_PASSWORD",
            actor_id=user.id, actor_role="admin",
            details={"email": payload.email, "attempt": user.failed_attempts},
            ip_address=ip, user_agent=ua
        )
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    # Verify TOTP 2FA or Server Session OTP
    from backend.config import SERVER_SESSION_OTP
    entered_code = payload.totp_code.strip()
    is_session_otp = (entered_code == SERVER_SESSION_OTP)
    is_time_totp = bool(user.totp_secret and verify_totp(user.totp_secret, entered_code))

    if not (is_session_otp or is_time_totp):
        user.failed_attempts = (user.failed_attempts or 0) + 1
        db.commit()
        create_audit_log(
            db, action="ADMIN_LOGIN_FAILED_TOTP",
            actor_id=user.id, actor_role="admin",
            details={"email": payload.email},
            ip_address=ip, user_agent=ua
        )
        raise HTTPException(status_code=401, detail="Invalid two-factor authentication or server session code")

    # Success: reset attempts
    user.failed_attempts = 0
    user.locked_until = None
    db.commit()

    token_data = {"sub": str(user.id), "role": "admin"}
    access_token = create_access_token(token_data)

    response.set_cookie(
        key="clinical_lens_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

    create_audit_log(
        db, action="ADMIN_LOGIN_SUCCESS",
        actor_id=user.id, actor_role="admin",
        details={"email": payload.email},
        ip_address=ip, user_agent=ua
    )

    return {
        "status": "success",
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "role": "admin",
            "full_name": "Clinical Administrator"
        }
    }


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    if user.role == "doctor" and user.doctor_profile:
        p = user.doctor_profile
        return {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "doctor": {
                "id": p.id,
                "full_name": p.full_name,
                "reg_number": p.reg_number,
                "specialty": p.specialty,
                "hospital_clinic": p.hospital_clinic,
                "status": p.status,
                "allowed_models": p.allowed_models,
                "daily_case_limit": p.daily_case_limit,
                "ai_summary_enabled": p.ai_summary_enabled,
                "pdf_export_enabled": p.pdf_export_enabled
            }
        }
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "full_name": "Clinical Administrator"
    }


@router.post("/logout")
async def logout(response: Response, user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    response.delete_cookie(key="clinical_lens_token")
    create_audit_log(
        db, action="USER_LOGOUT",
        actor_id=user.id, actor_role=user.role
    )
    return {"status": "success", "message": "Logged out successfully"}


@router.get("/application-status/{reg_number}")
async def get_application_status(reg_number: str, db: DBSession = Depends(get_db)):
    profile = db.query(DoctorProfile).filter(DoctorProfile.reg_number == reg_number.strip()).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Registration number not found")
    
    return {
        "reg_number": profile.reg_number,
        "full_name": profile.full_name,
        "specialty": profile.specialty,
        "hospital_clinic": profile.hospital_clinic,
        "status": profile.status,
        "status_reason": profile.status_reason or "Under administrative review.",
        "submitted_at": profile.created_at.isoformat(),
        "updated_at": profile.updated_at.isoformat()
    }


@router.post("/forgot-password")
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: DBSession = Depends(get_db)
):
    profile = db.query(DoctorProfile).filter(
        DoctorProfile.reg_number == payload.reg_number.strip(),
        DoctorProfile.dob == payload.dob.strip()
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="No matching doctor profile found with this registration number and date of birth.")

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    create_audit_log(
        db, action="PASSWORD_RESET_REQUESTED",
        actor_id=profile.user_id, actor_role="doctor",
        target_type="DoctorProfile", target_id=str(profile.id),
        details={"reg_number": profile.reg_number},
        ip_address=ip, user_agent=ua
    )

    return {
        "status": "success",
        "message": "Password reset request created. The administrator will review and issue a temporary password."
    }


@router.post("/change-temp-password")
async def change_temp_password(
    payload: ChangePasswordRequest,
    request: Request,
    db: DBSession = Depends(get_db)
):
    profile = db.query(DoctorProfile).filter(DoctorProfile.reg_number == payload.reg_number.strip()).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Doctor not found")
    
    user = profile.user
    if user.temp_password != payload.temp_password.strip():
        raise HTTPException(status_code=400, detail="Invalid temporary password")

    user.password_hash = hash_password(payload.new_password)
    user.temp_password = None
    user.must_change_password = False
    db.commit()

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    create_audit_log(
        db, action="PASSWORD_CHANGED_FROM_TEMP",
        actor_id=user.id, actor_role="doctor",
        target_type="DoctorProfile", target_id=str(profile.id),
        ip_address=ip, user_agent=ua
    )

    return {"status": "success", "message": "Password successfully updated. You may now login."}
