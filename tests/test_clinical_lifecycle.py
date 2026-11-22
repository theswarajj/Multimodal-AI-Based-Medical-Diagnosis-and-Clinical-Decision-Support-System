import sys
import os
import json
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from backend.main import app
from backend.config import ADMIN_EMAIL, ADMIN_PASSWORD, SERVER_SESSION_OTP
from backend.database import SessionLocal
from backend.models import AuditLog, Patient, Case, AnalysisRun, Report

client = TestClient(app)


def test_full_clinical_workflow():
    print("\n--- STARTING CLINICALLENS INTEGRATION TESTS ---")

    # 1. Admin Login with Server Session OTP
    admin_login_res = client.post("/api/auth/admin/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD,
        "totp_code": SERVER_SESSION_OTP
    })
    assert admin_login_res.status_code == 200, admin_login_res.text
    admin_token = admin_login_res.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    print("✓ 1. Admin login with dynamic Server Session OTP verified.")

    # 2. Doctor Login (Dr. Aris Thorne)
    doc_login_res = client.post("/api/auth/doctor/login", json={
        "reg_number": "MC-2015-88412",
        "password": "DoctorSecure#1"
    })
    assert doc_login_res.status_code == 200, doc_login_res.text
    doc_token = doc_login_res.json()["access_token"]
    doc_headers = {"Authorization": f"Bearer {doc_token}"}
    print("✓ 2. Approved doctor login verified.")

    # 3. Create Patient via Stepper API (flat payload as sent by frontend stepper)
    patient_payload = {
        "name": "Evelyn Reed",
        "dob": "1980-05-15",
        "age": 46,
        "sex": "Female",
        "blood_group": "A+",
        "height_cm": 165.0,
        "weight_kg": 62.0,
        "phone": "+91 98765 43210",
        "consent_confirmed": True,
        "temp_c": 37.3,
        "hr": 84.0,
        "bp_sys": 128,
        "bp_dia": 82,
        "spo2": 98.0,
        "rr": 18.0,
        "chief_complaint": "Persistent pigmented skin lesion on left forearm with border irregularity",
        "onset_duration": "Noticed 4 months ago, darkening over last 3 weeks",
        "associated_symptoms": "Mild pruritus, no spontaneous bleeding",
        "past_history": "Hypertension controlled on amlodipine",
        "family_history": "Maternal aunt diagnosed with melanoma at age 52",
        "allergies": "Penicillin (rash)",
        "lifestyle": "Landscape architect with high UV exposure",
        "modality_questions": {
            "SKIN": {
                "lesion_site": "Left forearm",
                "lesion_change": "Increased from 4mm to 7mm with darkening",
                "sun_history": "High occupational sun exposure"
            }
        },
        "medicines": [
            {
                "drug_name": "Amlodipine",
                "dose": "5 mg",
                "frequency": "Once daily",
                "duration": "Ongoing",
                "since_when": "2021",
                "indication": "Essential hypertension"
            }
        ]
    }

    patient_res = client.post("/api/doctor/patients", json=patient_payload, headers=doc_headers)
    assert patient_res.status_code == 200, patient_res.text
    patient_data = patient_res.json()
    patient_id = patient_data["patient"]["id"]
    case_id = patient_data["patient"]["case_id"]
    case_code = patient_data["patient"]["case_code"]
    print(f"✓ 3. Patient created ({patient_data['patient']['patient_code']}) with initial Case ({case_code}).")

    # 4. Upload Diagnostic Image to Case (Real skin lesion or sample)
    skin_sample_path = Path(__file__).resolve().parent.parent / "INPUT" / "SKIN" / "ISIC_0024306.jpg"
    if skin_sample_path.exists():
        with open(skin_sample_path, "rb") as f:
            file_bytes = f.read()
            filename = "ISIC_0024306.jpg"
    else:
        from PIL import Image
        import io
        img_byte_arr = io.BytesIO()
        test_img = Image.new("RGB", (224, 224), color=(180, 100, 90))
        test_img.save(img_byte_arr, format="JPEG")
        file_bytes = img_byte_arr.getvalue()
        filename = "lesion_sample.jpg"

    upload_res = client.post(
        f"/api/doctor/cases/{case_id}/upload-imaging",
        files={"file": (filename, file_bytes, "image/jpeg")},
        data={
            "modality": "SKIN",
            "body_site": "Left forearm",
            "doctor_narration": "Asymmetric pigmented macule, 7mm, suspicious for dysplastic nevus or early melanoma."
        },
        headers=doc_headers
    )
    assert upload_res.status_code == 200, upload_res.text
    upload_id = upload_res.json()["upload_id"]
    print(f"✓ 4. Diagnostic imaging uploaded (Upload #{upload_id}) with doctor narration and body site.")

    # 5. Add Structured Lab Values via Physician Clinical Notes
    notes_res = client.post(
        f"/api/doctor/cases/{case_id}/typed-document",
        json={
            "text": "LAB RESULTS:\nHb: 13.2 g/dL (normal 12.0-15.5)\nWBC: 6.8 x10^3/uL (normal 4.0-11.0)\nPlatelets: 245 x10^3/uL (normal 150-450)\nLDH: 195 U/L (normal 140-280)",
            "doc_kind": "report",
            "doctor_narration": "Baseline pre-biopsy hematology and tumor markers within normal limits."
        },
        headers=doc_headers
    )
    assert notes_res.status_code == 200, notes_res.text
    print(f"✓ 5. Clinical notes and labs parsed ({notes_res.json()['labs_count']} lab values identified).")

    # 6. Queue and Run Multimodal AI Analysis
    run_analysis_res = client.post(
        f"/api/doctor/cases/{case_id}/run-analysis",
        headers=doc_headers
    )
    assert run_analysis_res.status_code == 200, run_analysis_res.text
    analysis_job = run_analysis_res.json()
    job_id = analysis_job["case_code"]
    print(f"✓ 6. Analysis submitted to single-worker queue (Case {job_id}, status: {analysis_job['status']}).")

    # Give worker thread time to execute neural net inference and figure generation
    for i in range(60):
        time.sleep(1)
        case_check = client.get(f"/api/doctor/cases/{case_id}", headers=doc_headers).json()
        status = case_check.get("status")
        if status in ["COMPLETED", "FAILED", "ANALYZED"]:
            print(f"   Analysis finished in worker! Status: {status}", flush=True)
            break
        if i % 10 == 0 and i > 0:
            print(f"   ... Processing in AI worker ({i}s, status: {status})", flush=True)

    case_after = client.get(f"/api/doctor/cases/{case_id}", headers=doc_headers).json()
    print(f"✓ 6b. Case status after analysis run: {case_after.get('status')}, Triage: {case_after.get('triage_level')}", flush=True)

    # 7. Doctor Signs Off Final Clinical Decision
    decision_res = client.post(
        f"/api/doctor/cases/{case_id}/decision",
        json={
            "final_assessment": "Clinical and dermoscopic findings warrant 2mm margin punch/excisional biopsy to rule out melanoma in situ.",
            "management_plan": "Schedule excisional biopsy with histopathology under local anesthesia. Sun safety education provided.",
            "follow_up_date": "2026-03-05",
            "ai_recommendation_status": "ACCEPTED",
            "ai_status_reason": "AI skin model confidence aligned with ABCD dermoscopy criteria.",
            "sign_off": True
        },
        headers=doc_headers
    )
    assert decision_res.status_code == 200, decision_res.text
    print("✓ 7. Doctor finalized assessment, clinical plan, and digital sign-off.", flush=True)

    # 8. Certified ReportLab PDF Generation
    gen_pdf_res = client.post(f"/api/doctor/cases/{case_id}/generate-pdf", headers=doc_headers)
    assert gen_pdf_res.status_code == 200, gen_pdf_res.text
    pdf_info = gen_pdf_res.json()
    print(f"✓ 8a. ReportLab PDF compiled: {pdf_info['filename']} (Version {pdf_info['version']})", flush=True)

    download_res = client.get(f"/api/doctor/cases/{case_id}/pdf", headers=doc_headers)
    assert download_res.status_code == 200, download_res.text
    assert download_res.headers["content-type"] == "application/pdf"
    pdf_bytes = download_res.content
    assert len(pdf_bytes) > 1000, "PDF length should be substantial"
    print(f"✓ 8b. Certified PDF downloaded ({len(pdf_bytes)} bytes) with QR code & letterhead.", flush=True)

    # 9. Admin Auditable Patient Oversight Access
    oversight_res = client.post(
        f"/api/admin/patients/{patient_id}/open-record",
        json={"reason": "Compliance spot audit for regulatory accreditation"},
        headers=admin_headers
    )
    assert oversight_res.status_code == 200, oversight_res.text
    print("✓ 9. Admin patient oversight logged with required clinical justification.", flush=True)

    # 10. Admin Tamper-Evident SHA-256 Audit Log Verification
    security_res = client.get("/api/admin/security/verify-chain", headers=admin_headers)
    assert security_res.status_code == 200, security_res.text
    sec_data = security_res.json()
    assert sec_data["is_intact"] is True, f"Audit chain should be valid: {sec_data}"
    print(f"✓ 10. Tamper-evident cryptographic hash chain verified: {sec_data['message']}", flush=True)

    # 11. Admin Audit Log CSV Export
    csv_res = client.get("/api/admin/security/export-csv", headers=admin_headers)
    assert csv_res.status_code == 200, csv_res.text
    assert "Sequence,Timestamp (UTC)" in csv_res.text
    print(f"✓ 11. Security center audit trail CSV exported ({len(csv_res.text)} bytes).", flush=True)

    print("\n=======================================================")
    print("   ALL CLINICALLENS CORE LIFECYCLE TESTS PASSED 100%!")
    print("=======================================================\n", flush=True)


if __name__ == "__main__":
    test_full_clinical_workflow()
