import datetime
import json
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Float
)
from sqlalchemy.orm import relationship
from backend.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False, default="doctor")  # 'admin' or 'doctor'
    is_active = Column(Boolean, default=True)
    failed_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    totp_secret = Column(String(64), nullable=True)  # Used for Admin 2FA
    temp_password = Column(String(255), nullable=True)
    must_change_password = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    doctor_profile = relationship("DoctorProfile", back_populates="user", uselist=False)
    sessions = relationship("Session", back_populates="user")
    notifications = relationship("Notification", back_populates="user")


class DoctorProfile(Base):
    __tablename__ = "doctor_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    reg_number = Column(String(100), unique=True, index=True, nullable=False)
    issuing_council = Column(String(255), nullable=False)
    reg_year = Column(Integer, nullable=False)
    dob = Column(String(20), nullable=False)
    qualification = Column(String(255), nullable=False)
    specialty = Column(String(255), nullable=False)
    hospital_clinic = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=False)
    
    # Status: PENDING -> APPROVED | REJECTED | NEEDS_INFO | SUSPENDED | LOCKED | EXPIRED | DEACTIVATED
    status = Column(String(32), default="PENDING", index=True)
    status_reason = Column(Text, nullable=True)
    
    id_proof_path = Column(String(500), nullable=True)
    cert_path = Column(String(500), nullable=True)
    consent_given = Column(Boolean, default=True)

    # Permission toggles controlled by Admin
    allowed_models = Column(Text, default='["SKIN", "XRAY", "MRI"]')  # JSON list
    daily_case_limit = Column(Integer, default=50)
    ai_summary_enabled = Column(Boolean, default=True)
    pdf_export_enabled = Column(Boolean, default=True)
    expiry_date = Column(DateTime, nullable=True)
    
    # Soft delete and notes
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime, nullable=True)
    admin_notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    user = relationship("User", back_populates="doctor_profile")
    documents = relationship("DoctorDocument", back_populates="doctor")
    patients = relationship("Patient", back_populates="doctor")
    cases = relationship("Case", back_populates="doctor")


class DoctorDocument(Base):
    __tablename__ = "doctor_documents"

    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("doctor_profiles.id"), nullable=False)
    doc_type = Column(String(64), nullable=False)  # 'ID_PROOF', 'REG_CERT', etc.
    file_path = Column(String(500), nullable=False)
    original_filename = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    doctor = relationship("DoctorProfile", back_populates="documents")


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("doctor_profiles.id"), nullable=False)
    patient_code = Column(String(50), unique=True, index=True, nullable=False)  # auto e.g. PT-2026-0001
    name = Column(String(255), nullable=False)
    dob = Column(String(20), nullable=True)
    age = Column(Integer, nullable=False)
    sex = Column(String(20), nullable=False)  # 'Male', 'Female', 'Other'
    blood_group = Column(String(10), nullable=True)
    height_cm = Column(Float, nullable=True)
    weight_kg = Column(Float, nullable=True)
    phone = Column(String(50), nullable=True)
    consent_confirmed = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    doctor = relationship("DoctorProfile", back_populates="patients")
    cases = relationship("Case", back_populates="patient", cascade="all, delete-orphan")


class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("doctor_profiles.id"), nullable=False)
    case_code = Column(String(50), unique=True, index=True, nullable=False)  # e.g. CS-20260221-1234
    
    # Clinical history questions
    chief_complaint = Column(Text, nullable=True)
    onset_duration = Column(Text, nullable=True)
    associated_symptoms = Column(Text, nullable=True)
    past_history = Column(Text, nullable=True)
    family_history = Column(Text, nullable=True)
    allergies = Column(Text, nullable=True)
    lifestyle = Column(Text, nullable=True)
    modality_questions = Column(Text, default="{}")  # JSON dictionary
    doctor_question = Column(Text, nullable=True)
    
    # Vitals JSON: {temp_c, hr, bp_sys, bp_dia, spo2, rr}
    vitals = Column(Text, default="{}")

    # Triage and Status
    triage_level = Column(String(32), default="ROUTINE")  # 'URGENT', 'PRIORITY', 'ROUTINE'
    triage_alerts = Column(Text, default="[]")  # JSON list
    status = Column(String(32), default="DRAFT")  # 'DRAFT', 'QUEUED', 'ANALYZING', 'COMPLETED', 'DECIDED', 'SIGNED'

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    patient = relationship("Patient", back_populates="cases")
    doctor = relationship("DoctorProfile", back_populates="cases")
    uploads = relationship("Upload", back_populates="case", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="case", cascade="all, delete-orphan")
    lab_values = relationship("LabValue", back_populates="case", cascade="all, delete-orphan")
    medicines = relationship("Medicine", back_populates="case", cascade="all, delete-orphan")
    analysis_run = relationship("AnalysisRun", back_populates="case", uselist=False, cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="case", cascade="all, delete-orphan")
    decision = relationship("DoctorDecision", back_populates="case", uselist=False, cascade="all, delete-orphan")


class Upload(Base):
    __tablename__ = "uploads"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    file_path = Column(String(500), nullable=False)
    filename = Column(String(255), nullable=False)
    modality = Column(String(32), nullable=False)  # 'SKIN', 'XRAY', 'MRI'
    body_site = Column(String(100), nullable=True)  # Skin
    view = Column(String(50), nullable=True)        # X-ray: PA, AP, Lateral
    doctor_narration = Column(Text, nullable=True)
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    case = relationship("Case", back_populates="uploads")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    file_path = Column(String(500), nullable=True)
    filename = Column(String(255), nullable=False)
    doc_kind = Column(String(32), default="report")  # 'labs', 'medication', 'report'
    extracted_text = Column(Text, nullable=True)
    extraction_method = Column(String(50), nullable=True)  # 'ocr', 'pdf-text', 'docx', 'typed'
    doctor_narration = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    case = relationship("Case", back_populates="documents")
    lab_values = relationship("LabValue", back_populates="document", cascade="all, delete-orphan")


class LabValue(Base):
    __tablename__ = "lab_values"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    name = Column(String(100), nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String(50), nullable=True)
    ref_range = Column(String(100), nullable=True)
    ref_low = Column(Float, nullable=True)
    ref_high = Column(Float, nullable=True)
    flag = Column(String(10), default="")  # 'H', 'L', or ''
    is_critical = Column(Boolean, default=False)
    ref_source = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    case = relationship("Case", back_populates="lab_values")
    document = relationship("Document", back_populates="lab_values")


class Medicine(Base):
    __tablename__ = "medicines"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    drug_name = Column(String(255), nullable=False)
    dose = Column(String(100), nullable=False)        # e.g. 500mg
    frequency = Column(String(100), nullable=False)   # e.g. Twice daily
    duration = Column(String(100), nullable=False)    # e.g. 5 days
    since_when = Column(String(100), nullable=True)   # e.g. 2 weeks ago
    indication = Column(String(255), nullable=True)   # e.g. Hypertension
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    case = relationship("Case", back_populates="medicines")


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), unique=True, nullable=False)
    status = Column(String(32), default="QUEUED")  # 'QUEUED', 'RUNNING', 'COMPLETED', 'FAILED'
    queue_position = Column(Integer, default=0)
    current_stage = Column(String(64), nullable=True)  # 'loading_model', 'scanning', 'drawing_heatmaps', 'triage', 'writing_analysis'
    timings_json = Column(Text, default="{}")
    result_json = Column(Text, default="{}")           # Full per-model outputs, probabilities, heatmaps
    detailed_analysis = Column(Text, nullable=True)    # MedGemma 7-section report
    quick_summary = Column(Text, nullable=True)        # 5-7 bullet points
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    case = relationship("Case", back_populates="analysis_run")


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    version = Column(Integer, default=1)
    pdf_path = Column(String(500), nullable=False)
    signed_by_doctor_id = Column(Integer, ForeignKey("doctor_profiles.id"), nullable=True)
    signed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    case = relationship("Case", back_populates="reports")


class DoctorDecision(Base):
    __tablename__ = "doctor_decisions"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), unique=True, nullable=False)
    doctor_id = Column(Integer, ForeignKey("doctor_profiles.id"), nullable=False)
    final_assessment = Column(Text, nullable=False)
    management_plan = Column(Text, nullable=False)
    follow_up_date = Column(String(50), nullable=True)
    ai_recommendation_status = Column(String(32), default="ACCEPTED")  # 'ACCEPTED', 'MODIFIED', 'REJECTED'
    ai_status_reason = Column(Text, nullable=True)
    is_signed_off = Column(Boolean, default=False)
    signed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    case = relationship("Case", back_populates="decision")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    sender_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    msg_type = Column(String(32), default="ANNOUNCEMENT")  # 'ANNOUNCEMENT', 'INSTRUCTION', 'SECURITY_ALERT', 'CASE_RELATED'
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True)
    priority = Column(String(32), default="NORMAL")        # 'LOW', 'NORMAL', 'URGENT'
    is_pinned = Column(Boolean, default=False)
    scheduled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    recipients = relationship("MessageRecipient", back_populates="message", cascade="all, delete-orphan")


class MessageRecipient(Base):
    __tablename__ = "message_recipients"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("doctor_profiles.id"), nullable=False)
    status = Column(String(32), default="SENT")  # 'SENT', 'DELIVERED', 'READ', 'ACKNOWLEDGED'
    read_at = Column(DateTime, nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    reply_text = Column(Text, nullable=True)
    replied_at = Column(DateTime, nullable=True)

    message = relationship("Message", back_populates="recipients")
    doctor = relationship("DoctorProfile")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    link = Column(String(255), nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="notifications")


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_hash = Column(String(128), unique=True, index=True, nullable=False)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(500), nullable=True)
    device_name = Column(String(100), nullable=True)
    expires_at = Column(DateTime, nullable=False)
    last_active_at = Column(DateTime, default=datetime.datetime.utcnow)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="sessions")


class AuditLog(Base):
    """Tamper-evident audit log with SHA-256 hash chaining"""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    sequence_num = Column(Integer, unique=True, index=True, nullable=False)
    prev_hash = Column(String(64), nullable=False)
    current_hash = Column(String(64), nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    actor_id = Column(Integer, nullable=True)
    actor_role = Column(String(32), nullable=True)
    action = Column(String(100), index=True, nullable=False)
    target_type = Column(String(64), nullable=True)
    target_id = Column(String(64), nullable=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(500), nullable=True)
    details_json = Column(Text, default="{}")
