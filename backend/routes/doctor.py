import os
import io
import json
import time
import uuid
import shutil
import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import desc

from backend.database import get_db
from backend.models import (
    User, DoctorProfile, Patient, Case, Upload, Document, LabValue,
    Medicine, AnalysisRun, Report, DoctorDecision, Message, MessageRecipient, AuditLog
)
from backend.security import create_audit_log
from backend.routes.auth import get_current_user
from backend.queue_manager import queue_manager
from backend.pipeline_adapter import (
    extract_document_text, extract_typed_text, parse_raw_labs,
    execute_model_inference, compute_triage, generate_medgemma_summary
)
from backend.report_generator import generate_pdf_report
from backend.config import UPLOAD_DIR, REPORTS_DIR

router = APIRouter(prefix="/api/doctor", tags=["doctor"])

IMAGING_UPLOAD_DIR = UPLOAD_DIR / "imaging"
DOCS_UPLOAD_DIR = UPLOAD_DIR / "documents"
for p in [IMAGING_UPLOAD_DIR, DOCS_UPLOAD_DIR]:
    p.mkdir(parents=True, exist_ok=True)


def require_doctor(user: User = Depends(get_current_user)) -> DoctorProfile:
    if user.role != "doctor" or not user.doctor_profile:
        raise HTTPException(status_code=403, detail="Doctor credentials required")
    if user.doctor_profile.status != "APPROVED":
        raise HTTPException(status_code=403, detail=f"Doctor account is {user.doctor_profile.status.lower()}")
    return user.doctor_profile


# =============================================================================
#  SCHEMAS
# =============================================================================

class CreatePatientStep1(BaseModel):
    name: str
    dob: Optional[str] = None
    age: int
    sex: str
    blood_group: Optional[str] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    phone: Optional[str] = None
    consent_confirmed: bool = True

    # Step 2 Vitals
    temp_c: Optional[float] = None
    hr: Optional[float] = None
    bp_sys: Optional[int] = None
    bp_dia: Optional[int] = None
    spo2: Optional[float] = None
    rr: Optional[float] = None

    # Step 3 Clinical History
    chief_complaint: Optional[str] = None
    onset_duration: Optional[str] = None
    associated_symptoms: Optional[str] = None
    past_history: Optional[str] = None
    family_history: Optional[str] = None
    allergies: Optional[str] = None
    lifestyle: Optional[str] = None
    modality_questions: Optional[Dict[str, Any]] = {}
    doctor_question: Optional[str] = None

    # Step 4 Medicines
    medicines: Optional[List[Dict[str, Any]]] = []


class TypedDocumentRequest(BaseModel):
    text: str
    doc_kind: str = "report"
    doctor_narration: Optional[str] = None


class EditDocumentTextRequest(BaseModel):
    text: str
    doctor_narration: Optional[str] = None


class EditLabValueRequest(BaseModel):
    name: str
    value: float
    unit: Optional[str] = ""
    ref_range: Optional[str] = ""
    flag: Optional[str] = ""
    is_critical: Optional[bool] = False


class DoctorDecisionRequest(BaseModel):
    final_assessment: str
    management_plan: str
    follow_up_date: Optional[str] = None
    ai_recommendation_status: str = "ACCEPTED"  # 'ACCEPTED', 'MODIFIED', 'REJECTED'
    ai_status_reason: Optional[str] = None
    sign_off: bool = True


class MessageReplyRequest(BaseModel):
    reply_text: str


class DoctorSendMessageRequest(BaseModel):
    title: str
    content: str
    priority: Optional[str] = "NORMAL"
    category: Optional[str] = "CLINICAL_QUERY"


# =============================================================================
#  DASHBOARD & PATIENTS (Row-Level Security: Only doctor's own records)
# =============================================================================

@router.get("/dashboard")
async def get_doctor_dashboard(
    doc: DoctorProfile = Depends(require_doctor),
    db: DBSession = Depends(get_db)
):
    urgent_cases = db.query(Case).filter(Case.doctor_id == doc.id, Case.triage_level == "URGENT").all()
    awaiting_review = db.query(Case).filter(Case.doctor_id == doc.id, Case.status == "COMPLETED").count()
    active_analyses = db.query(Case).filter(Case.doctor_id == doc.id, Case.status.in_(["QUEUED", "ANALYZING"])).count()
    
    unread_messages = db.query(MessageRecipient).filter(
        MessageRecipient.doctor_id == doc.id,
        MessageRecipient.status.in_(["SENT", "DELIVERED"])
    ).count()

    recent_patients = db.query(Patient).filter(Patient.doctor_id == doc.id).order_by(desc(Patient.created_at)).limit(5).all()

    patients_summary = []
    for p in recent_patients:
        last_case = db.query(Case).filter(Case.patient_id == p.id).order_by(desc(Case.created_at)).first()
        patients_summary.append({
            "id": p.id,
            "patient_code": p.patient_code,
            "name": p.name,
            "age": p.age,
            "sex": p.sex,
            "triage_level": last_case.triage_level if last_case else "ROUTINE",
            "last_case_code": last_case.case_code if last_case else None,
            "created_at": p.created_at.isoformat()
        })

    return {
        "doctor_name": doc.full_name,
        "specialty": doc.specialty,
        "urgent_cases_count": len(urgent_cases),
        "cases_awaiting_review": awaiting_review,
        "analyses_in_progress": active_analyses,
        "unread_admin_messages": unread_messages,
        "recent_patients": patients_summary,
        "allowed_models": json.loads(doc.allowed_models) if doc.allowed_models else ["SKIN", "XRAY", "MRI"],
        "daily_case_limit": doc.daily_case_limit,
    }


@router.get("/patients")
async def list_patients(
    search: Optional[str] = None,
    triage: Optional[str] = None,
    doc: DoctorProfile = Depends(require_doctor),
    db: DBSession = Depends(get_db)
):
    query = db.query(Patient).filter(Patient.doctor_id == doc.id)
    if search:
        s = f"%{search.strip()}%"
        query = query.filter((Patient.name.ilike(s)) | (Patient.patient_code.ilike(s)))

    patients = query.order_by(desc(Patient.created_at)).all()
    results = []
    for p in patients:
        last_case = db.query(Case).filter(Case.patient_id == p.id).order_by(desc(Case.created_at)).first()
        triage_lvl = last_case.triage_level if last_case else "ROUTINE"
        if triage and triage != "ALL" and triage_lvl != triage:
            continue

        modalities = []
        if last_case:
            modalities = list(set(u.modality for u in last_case.uploads))

        results.append({
            "id": p.id,
            "patient_code": p.patient_code,
            "name": p.name,
            "age": p.age,
            "sex": p.sex,
            "blood_group": p.blood_group,
            "triage_level": triage_lvl,
            "modalities": modalities,
            "case_count": len(p.cases),
            "created_at": p.created_at.isoformat(),
            "latest_case_id": last_case.id if last_case else None,
            "latest_case_code": last_case.case_code if last_case else None
        })
    return results


@router.post("/patients")
async def create_patient(
    payload: CreatePatientStep1,
    request: Request,
    doc: DoctorProfile = Depends(require_doctor),
    db: DBSession = Depends(get_db)
):
    # Auto-generate unique Patient Code
    count_today = db.query(Patient).count() + 1
    year = datetime.datetime.now().year
    patient_code = f"PT-{year}-{count_today:04d}"

    patient = Patient(
        doctor_id=doc.id,
        patient_code=patient_code,
        name=payload.name.strip(),
        dob=payload.dob,
        age=payload.age,
        sex=payload.sex,
        blood_group=payload.blood_group,
        height_cm=payload.height_cm,
        weight_kg=payload.weight_kg,
        phone=payload.phone,
        consent_confirmed=payload.consent_confirmed
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)

    # Automatically create the initial clinical case
    case_code = f"CS-{datetime.datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    vitals_data = {
        "temp_c": payload.temp_c,
        "hr": payload.hr,
        "bp_sys": payload.bp_sys,
        "bp_dia": payload.bp_dia,
        "spo2": payload.spo2,
        "rr": payload.rr
    }

    case = Case(
        patient_id=patient.id,
        doctor_id=doc.id,
        case_code=case_code,
        chief_complaint=payload.chief_complaint,
        onset_duration=payload.onset_duration,
        associated_symptoms=payload.associated_symptoms,
        past_history=payload.past_history,
        family_history=payload.family_history,
        allergies=payload.allergies,
        lifestyle=payload.lifestyle,
        modality_questions=json.dumps(payload.modality_questions or {}),
        doctor_question=payload.doctor_question,
        vitals=json.dumps(vitals_data),
        status="DRAFT"
    )
    db.add(case)
    db.commit()
    db.refresh(case)

    # Add structured medicines if provided
    for m in payload.medicines or []:
        med = Medicine(
            case_id=case.id,
            drug_name=m.get("drug_name", "").strip(),
            dose=m.get("dose", "").strip(),
            frequency=m.get("frequency", "").strip(),
            duration=m.get("duration", "").strip(),
            since_when=m.get("since_when", "").strip(),
            indication=m.get("indication", "").strip()
        )
        db.add(med)
    db.commit()

    ip = request.client.host if request.client else None
    create_audit_log(
        db, action="DOCTOR_CREATED_PATIENT",
        actor_id=doc.user_id, actor_role="doctor",
        target_type="Patient", target_id=str(patient.id),
        details={"patient_code": patient.patient_code, "case_code": case.case_code},
        ip_address=ip
    )

    return {
        "status": "success",
        "patient": {
            "id": patient.id,
            "patient_code": patient.patient_code,
            "name": patient.name,
            "case_id": case.id,
            "case_code": case.case_code
        }
    }


@router.get("/patients/{id}")
async def get_patient_detail(
    id: int,
    doc: DoctorProfile = Depends(require_doctor),
    db: DBSession = Depends(get_db)
):
    patient = db.query(Patient).filter(Patient.id == id, Patient.doctor_id == doc.id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")

    cases_data = []
    for c in patient.cases:
        cases_data.append({
            "id": c.id,
            "case_code": c.case_code,
            "triage_level": c.triage_level,
            "status": c.status,
            "chief_complaint": c.chief_complaint,
            "uploads_count": len(c.uploads),
            "created_at": c.created_at.isoformat()
        })

    return {
        "id": patient.id,
        "patient_code": patient.patient_code,
        "name": patient.name,
        "dob": patient.dob,
        "age": patient.age,
        "sex": patient.sex,
        "blood_group": patient.blood_group,
        "height_cm": patient.height_cm,
        "weight_kg": patient.weight_kg,
        "phone": patient.phone,
        "cases": cases_data,
        "created_at": patient.created_at.isoformat()
    }


# =============================================================================
#  PATIENT WORKSPACE & CASE MULTIMODAL DATA
# =============================================================================

@router.get("/cases/{id}")
async def get_case_workspace(
    id: int,
    doc: DoctorProfile = Depends(require_doctor),
    db: DBSession = Depends(get_db)
):
    case = db.query(Case).filter(Case.id == id, Case.doctor_id == doc.id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Clinical case not found")

    # Uploads (Skin, X-ray, MRI)
    uploads_data = []
    for u in case.uploads:
        uploads_data.append({
            "id": u.id,
            "filename": u.filename,
            "modality": u.modality,
            "body_site": u.body_site,
            "view": u.view,
            "doctor_narration": u.doctor_narration,
            "file_size": u.file_size,
            "file_url": f"/uploads/imaging/{Path(u.file_path).name}",
            "created_at": u.created_at.isoformat()
        })

    # Documents & extracted labs
    docs_data = []
    for d in case.documents:
        labs = [
            {
                "id": l.id,
                "name": l.name,
                "value": l.value,
                "unit": l.unit,
                "ref_range": l.ref_range,
                "flag": l.flag,
                "is_critical": l.is_critical,
                "ref_source": l.ref_source
            }
            for l in d.lab_values
        ]
        docs_data.append({
            "id": d.id,
            "filename": d.filename,
            "kind": d.doc_kind,
            "extracted_text": d.extracted_text,
            "extraction_method": d.extraction_method,
            "doctor_narration": d.doctor_narration,
            "file_url": f"/uploads/documents/{Path(d.file_path).name}" if d.file_path else None,
            "labs": labs,
            "created_at": d.created_at.isoformat()
        })

    # Medicines
    medicines_data = [
        {
            "id": m.id,
            "drug_name": m.drug_name,
            "dose": m.dose,
            "frequency": m.frequency,
            "duration": m.duration,
            "since_when": m.since_when,
            "indication": m.indication
        }
        for m in case.medicines
    ]

    # Analysis results if completed
    analysis_data = None
    if case.analysis_run:
        ar = case.analysis_run
        analysis_data = {
            "status": ar.status,
            "queue_position": ar.queue_position,
            "timings": json.loads(ar.timings_json) if ar.timings_json else {},
            "results": json.loads(ar.result_json) if ar.result_json else {},
            "detailed_analysis": ar.detailed_analysis,
            "quick_summary": ar.quick_summary,
            "error_message": ar.error_message,
            "completed_at": ar.completed_at.isoformat() if ar.completed_at else None
        }

    # Decision
    decision_data = None
    if case.decision:
        cd = case.decision
        decision_data = {
            "final_assessment": cd.final_assessment,
            "management_plan": cd.management_plan,
            "follow_up_date": cd.follow_up_date,
            "ai_recommendation_status": cd.ai_recommendation_status,
            "ai_status_reason": cd.ai_status_reason,
            "is_signed_off": cd.is_signed_off,
            "signed_at": cd.signed_at.isoformat() if cd.signed_at else None
        }

    return {
        "id": case.id,
        "case_code": case.case_code,
        "patient": {
            "id": case.patient.id,
            "patient_code": case.patient.patient_code,
            "name": case.patient.name,
            "age": case.patient.age,
            "sex": case.patient.sex,
            "blood_group": case.patient.blood_group,
            "height_cm": case.patient.height_cm,
            "weight_kg": case.patient.weight_kg
        },
        "vitals": json.loads(case.vitals) if case.vitals else {},
        "clinical_history": {
            "chief_complaint": case.chief_complaint,
            "onset_duration": case.onset_duration,
            "associated_symptoms": case.associated_symptoms,
            "past_history": case.past_history,
            "family_history": case.family_history,
            "allergies": case.allergies,
            "lifestyle": case.lifestyle,
            "doctor_question": case.doctor_question,
            "modality_questions": json.loads(case.modality_questions) if case.modality_questions else {}
        },
        "triage_level": case.triage_level,
        "triage_alerts": json.loads(case.triage_alerts) if case.triage_alerts else [],
        "status": case.status,
        "uploads": uploads_data,
        "documents": docs_data,
        "medicines": medicines_data,
        "analysis": analysis_data,
        "decision": decision_data,
        "has_report": bool(case.reports)
    }


@router.post("/cases/{id}/upload-imaging")
async def upload_imaging(
    id: int,
    file: UploadFile = File(...),
    modality: str = Form(...),
    body_site: Optional[str] = Form(None),
    view: Optional[str] = Form(None),
    doctor_narration: Optional[str] = Form(None),
    doc: DoctorProfile = Depends(require_doctor),
    db: DBSession = Depends(get_db)
):
    case = db.query(Case).filter(Case.id == id, Case.doctor_id == doc.id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    mod_key = modality.upper()
    if mod_key not in ["SKIN", "XRAY", "MRI"]:
        raise HTTPException(status_code=400, detail="Invalid modality (must be SKIN, XRAY, or MRI)")

    safe_ext = os.path.splitext(file.filename)[1].lower()
    fname = f"{mod_key.lower()}_{uuid.uuid4().hex[:12]}{safe_ext}"
    target = IMAGING_UPLOAD_DIR / fname

    with open(target, "wb") as f:
        shutil.copyfileobj(file.file, f)

    fsize = os.path.getsize(target)

    upload_rec = Upload(
        case_id=case.id,
        file_path=str(target),
        filename=file.filename,
        modality=mod_key,
        body_site=body_site,
        view=view,
        doctor_narration=doctor_narration,
        file_size=fsize,
        mime_type=file.content_type
    )
    db.add(upload_rec)
    db.commit()
    db.refresh(upload_rec)

    return {
        "status": "success",
        "upload_id": upload_rec.id,
        "filename": upload_rec.filename,
        "modality": upload_rec.modality,
        "file_url": f"/uploads/imaging/{fname}"
    }


@router.post("/cases/{id}/upload-document")
async def upload_document(
    id: int,
    file: UploadFile = File(...),
    doc_kind: str = Form("report"),
    doctor_narration: Optional[str] = Form(None),
    doc: DoctorProfile = Depends(require_doctor),
    db: DBSession = Depends(get_db)
):
    case = db.query(Case).filter(Case.id == id, Case.doctor_id == doc.id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    safe_ext = os.path.splitext(file.filename)[1].lower()
    fname = f"doc_{uuid.uuid4().hex[:12]}{safe_ext}"
    target = DOCS_UPLOAD_DIR / fname

    with open(target, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Extract text using rapidocr / pymupdf / python-docx
    sex_letter = "M" if case.patient.sex == "Male" else "F" if case.patient.sex == "Female" else None
    extracted = extract_document_text(str(target), sex_letter)

    doc_rec = Document(
        case_id=case.id,
        file_path=str(target),
        filename=file.filename,
        doc_kind=extracted.get("kind", doc_kind),
        extracted_text=extracted.get("text", ""),
        extraction_method=extracted.get("method", "local"),
        doctor_narration=doctor_narration
    )
    db.add(doc_rec)
    db.commit()
    db.refresh(doc_rec)

    # Save parsed labs
    for l in extracted.get("labs", []):
        lab_rec = LabValue(
            case_id=case.id,
            document_id=doc_rec.id,
            name=l["name"],
            value=l["value"],
            unit=l["unit"],
            ref_range=l["ref"],
            ref_low=l.get("ref_low"),
            ref_high=l.get("ref_high"),
            flag=l.get("flag", ""),
            is_critical=l.get("critical", False),
            ref_source=l.get("ref_source")
        )
        db.add(lab_rec)
    db.commit()

    return {
        "status": "success",
        "document_id": doc_rec.id,
        "filename": doc_rec.filename,
        "extracted_chars": len(doc_rec.extracted_text),
        "labs_count": len(extracted.get("labs", [])),
        "extraction_method": doc_rec.extraction_method
    }


@router.post("/cases/{id}/typed-document")
async def add_typed_document(
    id: int,
    payload: TypedDocumentRequest,
    doc: DoctorProfile = Depends(require_doctor),
    db: DBSession = Depends(get_db)
):
    case = db.query(Case).filter(Case.id == id, Case.doctor_id == doc.id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    sex_letter = "M" if case.patient.sex == "Male" else "F" if case.patient.sex == "Female" else None
    extracted = extract_typed_text(payload.text, sex_letter)

    doc_rec = Document(
        case_id=case.id,
        filename="Physician Clinical Notes",
        doc_kind=payload.doc_kind,
        extracted_text=payload.text,
        extraction_method="typed",
        doctor_narration=payload.doctor_narration
    )
    db.add(doc_rec)
    db.commit()
    db.refresh(doc_rec)

    for l in extracted.get("labs", []):
        lab_rec = LabValue(
            case_id=case.id,
            document_id=doc_rec.id,
            name=l["name"],
            value=l["value"],
            unit=l["unit"],
            ref_range=l["ref"],
            flag=l.get("flag", ""),
            is_critical=l.get("critical", False),
            ref_source=l.get("ref_source")
        )
        db.add(lab_rec)
    db.commit()

    return {
        "status": "success",
        "document_id": doc_rec.id,
        "labs_count": len(extracted.get("labs", []))
    }


@router.put("/cases/{id}/documents/{doc_id}")
async def edit_document_text(
    id: int,
    doc_id: int,
    payload: EditDocumentTextRequest,
    doc: DoctorProfile = Depends(require_doctor),
    db: DBSession = Depends(get_db)
):
    document = db.query(Document).filter(Document.id == doc_id, Document.case_id == id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    document.extracted_text = payload.text
    if payload.doctor_narration is not None:
        document.doctor_narration = payload.doctor_narration
    db.commit()
    return {"status": "success", "message": "Document text updated"}


@router.put("/cases/{id}/labs/{lab_id}")
async def edit_lab_value(
    id: int,
    lab_id: int,
    payload: EditLabValueRequest,
    doc: DoctorProfile = Depends(require_doctor),
    db: DBSession = Depends(get_db)
):
    lab = db.query(LabValue).filter(LabValue.id == lab_id, LabValue.case_id == id).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab value not found")

    lab.name = payload.name
    lab.value = payload.value
    lab.unit = payload.unit
    lab.ref_range = payload.ref_range
    lab.flag = payload.flag
    lab.is_critical = payload.is_critical
    db.commit()
    return {"status": "success", "message": "Lab value corrected"}


# =============================================================================
#  MEDICINES TABLE
# =============================================================================

@router.post("/cases/{id}/medicines")
async def add_medicine(
    id: int,
    data: Dict[str, Any],
    doc: DoctorProfile = Depends(require_doctor),
    db: DBSession = Depends(get_db)
):
    case = db.query(Case).filter(Case.id == id, Case.doctor_id == doc.id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    med = Medicine(
        case_id=case.id,
        drug_name=data.get("drug_name", "").strip(),
        dose=data.get("dose", "").strip(),
        frequency=data.get("frequency", "").strip(),
        duration=data.get("duration", "").strip(),
        since_when=data.get("since_when", "").strip(),
        indication=data.get("indication", "").strip()
    )
    db.add(med)
    db.commit()
    db.refresh(med)
    return {"status": "success", "medicine_id": med.id}


@router.delete("/cases/{id}/medicines/{med_id}")
async def delete_medicine(
    id: int,
    med_id: int,
    doc: DoctorProfile = Depends(require_doctor),
    db: DBSession = Depends(get_db)
):
    med = db.query(Medicine).filter(Medicine.id == med_id, Medicine.case_id == id).first()
    if not med:
        raise HTTPException(status_code=404, detail="Medicine record not found")
    db.delete(med)
    db.commit()
    return {"status": "success", "message": "Medicine removed"}


# =============================================================================
#  ANALYSIS RUN & SSE STREAMING
# =============================================================================

@router.post("/cases/{id}/run-analysis")
async def run_case_analysis(
    id: int,
    modalities: Optional[List[str]] = Query(None),
    doc: DoctorProfile = Depends(require_doctor),
    db: DBSession = Depends(get_db)
):
    case = db.query(Case).filter(Case.id == id, Case.doctor_id == doc.id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not case.uploads:
        raise HTTPException(status_code=400, detail="Cannot run analysis: no diagnostic images uploaded")

    # Enqueue in single-worker hardware queue
    pos = queue_manager.enqueue_case(case.case_code, modalities or [])
    case.status = "QUEUED"
    db.commit()

    return {
        "status": "queued",
        "case_code": case.case_code,
        "queue_position": pos,
        "message": f"Case enqueued for AI analysis at queue position {pos}"
    }


@router.get("/cases/{id}/analysis-stream")
async def analysis_events_stream(
    id: int,
    request: Request,
    doc: DoctorProfile = Depends(require_doctor),
    db: DBSession = Depends(get_db)
):
    case = db.query(Case).filter(Case.id == id, Case.doctor_id == doc.id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    subscriber_queue = queue_manager.subscribe(case.case_code)

    async def event_generator():
        try:
            # Yield initial status
            q_stat = queue_manager.get_queue_status(case.case_code)
            yield f"event: queue_update\ndata: {json.dumps(q_stat)}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    # Wait for next event from worker
                    msg = await asyncio.wait_for(subscriber_queue.get(), timeout=15.0)
                    yield f"event: {msg['event']}\ndata: {json.dumps(msg['data'])}\n\n"
                    if msg['event'] in ["complete", "error"]:
                        break
                except asyncio.TimeoutError:
                    # Keep-alive heartbeat comment
                    yield ": ping\n\n"
        finally:
            queue_manager.unsubscribe(case.case_code, subscriber_queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


# =============================================================================
#  DOCTOR DECISION & PDF REPORT
# =============================================================================

@router.post("/cases/{id}/decision")
async def submit_doctor_decision(
    id: int,
    payload: DoctorDecisionRequest,
    request: Request,
    doc: DoctorProfile = Depends(require_doctor),
    db: DBSession = Depends(get_db)
):
    case = db.query(Case).filter(Case.id == id, Case.doctor_id == doc.id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    decision = case.decision
    now = datetime.datetime.utcnow()
    if not decision:
        decision = DoctorDecision(
            case_id=case.id,
            doctor_id=doc.id,
            final_assessment=payload.final_assessment,
            management_plan=payload.management_plan,
            follow_up_date=payload.follow_up_date,
            ai_recommendation_status=payload.ai_recommendation_status,
            ai_status_reason=payload.ai_status_reason,
            is_signed_off=payload.sign_off,
            signed_at=now if payload.sign_off else None
        )
        db.add(decision)
    else:
        decision.final_assessment = payload.final_assessment
        decision.management_plan = payload.management_plan
        decision.follow_up_date = payload.follow_up_date
        decision.ai_recommendation_status = payload.ai_recommendation_status
        decision.ai_status_reason = payload.ai_status_reason
        decision.is_signed_off = payload.sign_off
        if payload.sign_off and not decision.signed_at:
            decision.signed_at = now

    case.status = "SIGNED" if payload.sign_off else "DECIDED"
    db.commit()

    ip = request.client.host if request.client else None
    create_audit_log(
        db, action="DOCTOR_SIGNED_OFF_DECISION",
        actor_id=doc.user_id, actor_role="doctor",
        target_type="DoctorDecision", target_id=str(decision.id),
        details={"case_code": case.case_code, "status": payload.ai_recommendation_status},
        ip_address=ip
    )

    return {"status": "success", "message": "Clinical decision saved and locked for reporting."}


class GeneratePdfCustomRequest(BaseModel):
    final_assessment: Optional[str] = None
    management_plan: Optional[str] = None
    detailed_analysis: Optional[str] = None
    quick_summary: Optional[str] = None
    triage_level: Optional[str] = None
    follow_up_date: Optional[str] = None
    doctor_narration: Optional[str] = None


@router.post("/cases/{id}/run-model/{modality}")
async def run_specific_model(
    id: int,
    modality: str,
    doc: DoctorProfile = Depends(require_doctor),
    db: DBSession = Depends(get_db)
):
    case = db.query(Case).filter(Case.id == id, Case.doctor_id == doc.id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    mod_key = modality.upper()
    if mod_key in ["SKIN", "XRAY", "MRI"]:
        upload = db.query(Upload).filter(Upload.case_id == case.id, Upload.modality == mod_key).order_by(desc(Upload.created_at)).first()
        if not upload:
            raise HTTPException(status_code=400, detail=f"No {mod_key} scan uploaded yet. Please upload a scan image first.")

        t0 = time.perf_counter()
        result, fig_paths, desc_text = execute_model_inference(mod_key, upload.file_path, case.case_code)
        duration = round(time.perf_counter() - t0, 2)

        # Ensure analysis_run exists
        run = case.analysis_run
        if not run:
            run = AnalysisRun(case_id=case.id, status="IN_PROGRESS")
            db.add(run)
            db.commit()
            db.refresh(run)

        # Merge run into result_json
        existing_result = json.loads(run.result_json) if run.result_json else {"runs": [], "triage": {}}
        existing_runs = [r for r in existing_result.get("runs", []) if r.get("key") != mod_key]
        new_entry = {
            "key": mod_key,
            "file": upload.file_path,
            "filename": upload.filename,
            "result": result,
            "figures": fig_paths,
            "text": desc_text,
            "duration": duration
        }
        existing_runs.append(new_entry)
        existing_result["runs"] = existing_runs
        run.result_json = json.dumps(existing_result)
        db.commit()

        return {
            "status": "success",
            "modality": mod_key,
            "result": result,
            "figures": fig_paths,
            "text": desc_text,
            "duration": duration,
            "message": f"{mod_key} model completed successfully in {duration}s"
        }
    elif mod_key in ["TEXT", "LABS", "TEXT_DATA"]:
        labs = db.query(LabValue).filter(LabValue.case_id == case.id).all()
        docs = db.query(Document).filter(Document.case_id == case.id).all()
        vitals = json.loads(case.vitals) if case.vitals else {}

        runs_data = []
        if case.analysis_run and case.analysis_run.result_json:
            runs_data = json.loads(case.analysis_run.result_json).get("runs", [])

        labs_data = [
            {"name": l.name, "value": l.value, "unit": l.unit, "ref": l.ref_range, "flag": l.flag, "critical": l.is_critical}
            for l in labs
        ]
        triage_result = compute_triage(vitals, runs_data, labs_data)
        case.triage_level = triage_result["level"]
        case.triage_alerts = json.dumps(triage_result["alerts"])
        db.commit()

        return {
            "status": "success",
            "modality": "TEXT",
            "documents_count": len(docs),
            "labs_count": len(labs),
            "triage": triage_result,
            "message": f"Processed {len(docs)} documents and extracted {len(labs)} lab values"
        }
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported model modality: {modality}")


@router.post("/cases/{id}/generate-pdf")
async def generate_case_pdf(
    id: int,
    payload: Optional[GeneratePdfCustomRequest] = None,
    doc: DoctorProfile = Depends(require_doctor),
    db: DBSession = Depends(get_db)
):
    case = db.query(Case).filter(Case.id == id, Case.doctor_id == doc.id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Apply custom doctor edits before generating PDF
    if payload:
        if payload.triage_level:
            case.triage_level = payload.triage_level
        if payload.final_assessment or payload.management_plan or payload.follow_up_date:
            if not case.decision:
                case.decision = DoctorDecision(
                    case_id=case.id,
                    final_assessment=payload.final_assessment or "Clinical evaluation finalized.",
                    management_plan=payload.management_plan or "Prescribed management initiated.",
                    follow_up_date=payload.follow_up_date,
                    ai_recommendation_status="ACCEPTED",
                    signed_at=datetime.datetime.utcnow()
                )
            else:
                if payload.final_assessment:
                    case.decision.final_assessment = payload.final_assessment
                if payload.management_plan:
                    case.decision.management_plan = payload.management_plan
                if payload.follow_up_date:
                    case.decision.follow_up_date = payload.follow_up_date
        if payload.detailed_analysis and case.analysis_run:
            case.analysis_run.detailed_analysis = payload.detailed_analysis
        if payload.quick_summary and case.analysis_run:
            case.analysis_run.quick_summary = payload.quick_summary
        db.commit()

    # Determine report version
    existing_reports = db.query(Report).filter(Report.case_id == case.id).count()
    version = existing_reports + 1

    # Prepare bundle data for ReportLab
    runs_data = []
    if case.analysis_run and case.analysis_run.result_json:
        runs_data = json.loads(case.analysis_run.result_json).get("runs", [])

    report_payload = {
        "case_code": case.case_code,
        "doctor_name": doc.full_name,
        "doctor_reg": doc.reg_number,
        "hospital": doc.hospital_clinic,
        "patient": {
            "name": case.patient.name,
            "patient_code": case.patient.patient_code,
            "age": case.patient.age,
            "sex": case.patient.sex,
            "blood_group": case.patient.blood_group
        },
        "vitals": json.loads(case.vitals) if case.vitals else {},
        "chief_complaint": case.chief_complaint,
        "onset_duration": case.onset_duration,
        "allergies": case.allergies,
        "medicines": [{"drug_name": m.drug_name, "dose": m.dose, "frequency": m.frequency, "duration": m.duration, "indication": m.indication} for m in case.medicines],
        "labs": [{"name": l.name, "value": l.value, "unit": l.unit, "ref": l.ref_range, "flag": l.flag, "critical": l.is_critical} for l in case.lab_values],
        "triage_level": case.triage_level,
        "runs": runs_data,
        "detailed_analysis": case.analysis_run.detailed_analysis if case.analysis_run else None,
        "quick_summary": case.analysis_run.quick_summary if case.analysis_run else None,
        "decision": {
            "ai_recommendation_status": case.decision.ai_recommendation_status if case.decision else "ACCEPTED",
            "follow_up_date": case.decision.follow_up_date if case.decision else None,
            "final_assessment": case.decision.final_assessment if case.decision else "Clinical review completed.",
            "management_plan": case.decision.management_plan if case.decision else "Proceed with recommended plan.",
            "signed_at": case.decision.signed_at.strftime("%Y-%m-%d %H:%M") if case.decision and case.decision.signed_at else None
        } if case.decision else None
    }

    pdf_file_path = generate_pdf_report(report_payload, version=version)

    rep_record = Report(
        case_id=case.id,
        version=version,
        pdf_path=pdf_file_path,
        signed_by_doctor_id=doc.id,
        signed_at=datetime.datetime.utcnow()
    )
    db.add(rep_record)
    db.commit()

    return {
        "status": "success",
        "version": version,
        "pdf_url": f"/api/doctor/cases/{case.id}/pdf?version={version}",
        "filename": Path(pdf_file_path).name
    }


@router.get("/cases/{id}/pdf")
async def download_case_pdf(
    id: int,
    version: Optional[int] = None,
    doc: DoctorProfile = Depends(require_doctor),
    db: DBSession = Depends(get_db)
):
    case = db.query(Case).filter(Case.id == id, Case.doctor_id == doc.id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    query = db.query(Report).filter(Report.case_id == case.id)
    if version:
        report = query.filter(Report.version == version).first()
    else:
        report = query.order_by(desc(Report.version)).first()

    if not report or not os.path.exists(report.pdf_path):
        raise HTTPException(status_code=404, detail="PDF report not found. Please generate it first.")

    return FileResponse(
        report.pdf_path,
        media_type="application/pdf",
        filename=Path(report.pdf_path).name
    )


# =============================================================================
#  MESSAGES & DOCTOR INBOX
# =============================================================================

@router.get("/messages")
async def list_doctor_messages(
    doc: DoctorProfile = Depends(require_doctor),
    db: DBSession = Depends(get_db)
):
    rcpts = db.query(MessageRecipient).filter(MessageRecipient.doctor_id == doc.id).all()
    results = []
    for r in rcpts:
        m = r.message
        if not m:
            continue
        is_from_doc = (m.sender_user_id == doc.user_id)
        results.append({
            "recipient_id": r.id,
            "message_id": m.id,
            "title": m.title,
            "content": m.content,
            "msg_type": m.msg_type,
            "priority": m.priority,
            "is_pinned": m.is_pinned,
            "status": r.status,
            "created_at": m.created_at.isoformat(),
            "read_at": r.read_at.isoformat() if r.read_at else None,
            "acknowledged_at": r.acknowledged_at.isoformat() if r.acknowledged_at else None,
            "reply_text": r.reply_text,
            "replied_at": r.replied_at.isoformat() if r.replied_at else None,
            "sender_role": "doctor" if is_from_doc else "admin",
            "sender_name": f"Dr. {doc.full_name}" if is_from_doc else "Clinical Administration"
        })
    results.sort(key=lambda x: x["created_at"], reverse=True)
    return results


@router.post("/messages")
async def send_doctor_message(
    payload: DoctorSendMessageRequest,
    request: Request,
    doc: DoctorProfile = Depends(require_doctor),
    db: DBSession = Depends(get_db)
):
    title = payload.title.strip()
    content = payload.content.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Subject/Title cannot be empty")
    if not content:
        raise HTTPException(status_code=400, detail="Message content cannot be empty")

    priority = (payload.priority or "NORMAL").upper()
    if priority not in ("LOW", "NORMAL", "URGENT"):
        priority = "NORMAL"

    msg = Message(
        sender_user_id=doc.user_id,
        title=title,
        content=content,
        msg_type=payload.category or "CLINICAL_QUERY",
        priority=priority,
        is_pinned=False
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    rcpt = MessageRecipient(
        message_id=msg.id,
        doctor_id=doc.id,
        status="SENT"
    )
    db.add(rcpt)
    db.commit()

    ip = request.client.host if request.client else None
    create_audit_log(
        db, action="DOCTOR_SENT_ADMIN_MESSAGE",
        actor_id=doc.user_id, actor_role="doctor",
        target_type="Message", target_id=str(msg.id),
        details={
            "doctor_name": doc.full_name,
            "reg_number": doc.reg_number,
            "title": msg.title,
            "priority": msg.priority,
            "category": msg.msg_type
        },
        ip_address=ip
    )

    return {
        "status": "success",
        "message": "Message transmitted to Clinical Administration",
        "message_id": msg.id
    }


@router.post("/messages/{recipient_id}/acknowledge")
async def acknowledge_message(
    recipient_id: int,
    doc: DoctorProfile = Depends(require_doctor),
    db: DBSession = Depends(get_db)
):
    rcpt = db.query(MessageRecipient).filter(MessageRecipient.id == recipient_id, MessageRecipient.doctor_id == doc.id).first()
    if not rcpt:
        raise HTTPException(status_code=404, detail="Message not found")

    rcpt.status = "ACKNOWLEDGED"
    rcpt.acknowledged_at = datetime.datetime.utcnow()
    db.commit()
    return {"status": "success", "message": "Message acknowledged"}


@router.post("/messages/{recipient_id}/reply")
async def reply_to_message(
    recipient_id: int,
    payload: MessageReplyRequest,
    doc: DoctorProfile = Depends(require_doctor),
    db: DBSession = Depends(get_db)
):
    rcpt = db.query(MessageRecipient).filter(MessageRecipient.id == recipient_id, MessageRecipient.doctor_id == doc.id).first()
    if not rcpt:
        raise HTTPException(status_code=404, detail="Message not found")

    rcpt.reply_text = payload.reply_text.strip()
    rcpt.replied_at = datetime.datetime.utcnow()
    rcpt.status = "ACKNOWLEDGED"
    db.commit()
    return {"status": "success", "message": "Reply sent to administrator"}
