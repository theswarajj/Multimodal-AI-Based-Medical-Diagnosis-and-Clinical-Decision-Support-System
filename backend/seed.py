import datetime
import json
from backend.database import SessionLocal, engine, Base
from backend.models import User, DoctorProfile, Patient, Case, AuditLog
from backend.security import hash_password, create_audit_log
from backend.config import ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_TOTP_SECRET, ADMIN_NAME


def seed_database():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # 1. Seed Admin
        admin_user = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        if not admin_user:
            admin_user = User(
                email=ADMIN_EMAIL,
                password_hash=hash_password(ADMIN_PASSWORD),
                role="admin",
                is_active=True,
                totp_secret=ADMIN_TOTP_SECRET,
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
            create_audit_log(
                db,
                action="ADMIN_INITIALIZED",
                actor_id=admin_user.id,
                actor_role="admin",
                target_type="User",
                target_id=str(admin_user.id),
                details={"email": ADMIN_EMAIL, "name": ADMIN_NAME}
            )
            print(f"[Seed] Admin created: {ADMIN_EMAIL} (Password: {ADMIN_PASSWORD}, TOTP: {ADMIN_TOTP_SECRET})")

        # 2. Seed Demo Doctors
        doctors_data = [
            {
                "email": "dr.thorne@clinicallens.local",
                "password": "DoctorSecure#1",
                "full_name": "Dr. Aris Thorne",
                "reg_number": "MC-2015-88412",
                "issuing_council": "Medical Council of California",
                "reg_year": 2015,
                "dob": "1983-04-12",
                "qualification": "MD, Pulmonology & Critical Care",
                "specialty": "Pulmonology",
                "hospital_clinic": "St. Jude's Memorial Hospital",
                "phone": "+1 (555) 234-5678",
                "status": "APPROVED",
                "status_reason": "Verified credentials with state medical board.",
                "allowed_models": '["SKIN", "XRAY", "MRI"]',
                "patients": [
                    {
                        "patient_code": "PT-2026-0001",
                        "name": "Johnathan Doe",
                        "dob": "1968-08-14",
                        "age": 58,
                        "sex": "Male",
                        "blood_group": "O+",
                        "height_cm": 178.0,
                        "weight_kg": 82.5,
                        "phone": "+1 (555) 345-6789",
                        "vitals": {
                            "temp_c": 38.2,
                            "hr": 104,
                            "bp_sys": 138,
                            "bp_dia": 88,
                            "spo2": 93,
                            "rr": 22
                        },
                        "case": {
                            "case_code": "CS-20260221-001",
                            "chief_complaint": "Persistent productive cough with yellow sputum and progressive breathlessness on exertion.",
                            "onset_duration": "10 days, worsening over the last 48 hours",
                            "associated_symptoms": "Low-grade fever, mild right-sided pleuritic chest pain, fatigue",
                            "past_history": "Hypertension (controlled), no prior pneumonia",
                            "family_history": "Father had COPD",
                            "allergies": "Penicillin (rash)",
                            "lifestyle": "Former smoker (15 pack-years, quit 6 years ago), non-drinker",
                            "doctor_question": "Does the imaging show consolidation consistent with community-acquired pneumonia or effusion?",
                            "triage_level": "PRIORITY",
                            "status": "DRAFT"
                        }
                    },
                    {
                        "patient_code": "PT-2026-0002",
                        "name": "Sarah Jenkins",
                        "dob": "1984-11-20",
                        "age": 42,
                        "sex": "Female",
                        "blood_group": "A+",
                        "height_cm": 165.0,
                        "weight_kg": 61.0,
                        "phone": "+1 (555) 456-7890",
                        "vitals": {
                            "temp_c": 36.8,
                            "hr": 74,
                            "bp_sys": 118,
                            "bp_dia": 76,
                            "spo2": 99,
                            "rr": 16
                        },
                        "case": {
                            "case_code": "CS-20260221-002",
                            "chief_complaint": "Pigmented skin lesion on posterior right calf showing irregular border and recent color darkening.",
                            "onset_duration": "Noticed 4 months ago, darkening over last 6 weeks",
                            "associated_symptoms": "Occasional mild pruritus, no bleeding",
                            "past_history": "None significant",
                            "family_history": "Maternal aunt had melanoma",
                            "allergies": "No known drug allergies",
                            "lifestyle": "Recreational outdoor runner, uses sunscreen irregularly",
                            "doctor_question": "Evaluate dermoscopic features for dysplastic nevus vs malignant melanoma risk.",
                            "triage_level": "ROUTINE",
                            "status": "DRAFT"
                        }
                    }
                ]
            },
            {
                "email": "dr.rostova@clinicallens.local",
                "password": "DoctorSecure#2",
                "full_name": "Dr. Elena Rostova",
                "reg_number": "MC-2021-49102",
                "issuing_council": "New York State Board for Medicine",
                "reg_year": 2021,
                "dob": "1991-09-05",
                "qualification": "MD, Dermatology",
                "specialty": "Dermatology",
                "hospital_clinic": "Metro General Hospital & Derm Clinic",
                "phone": "+1 (555) 876-5432",
                "status": "PENDING",
                "status_reason": "Application submitted, pending license certificate cross-verification.",
                "allowed_models": '["SKIN"]',
                "patients": []
            },
            {
                "email": "dr.vance@clinicallens.local",
                "password": "DoctorSecure#3",
                "full_name": "Dr. Marcus Vance",
                "reg_number": "MC-2018-77319",
                "issuing_council": "Texas Medical Board",
                "reg_year": 2018,
                "dob": "1986-02-17",
                "qualification": "MS, Neurosurgery",
                "specialty": "Neurology & Neurosurgery",
                "hospital_clinic": "Trinity Neuro Institute",
                "phone": "+1 (555) 987-6543",
                "status": "NEEDS_INFO",
                "status_reason": "Proof of current institutional hospital affiliation document is expired. Please re-upload.",
                "allowed_models": '["MRI"]',
                "patients": []
            }
        ]

        for doc_item in doctors_data:
            existing_user = db.query(User).filter(User.email == doc_item["email"]).first()
            if not existing_user:
                u = User(
                    email=doc_item["email"],
                    password_hash=hash_password(doc_item["password"]),
                    role="doctor",
                    is_active=True
                )
                db.add(u)
                db.commit()
                db.refresh(u)

                prof = DoctorProfile(
                    user_id=u.id,
                    full_name=doc_item["full_name"],
                    reg_number=doc_item["reg_number"],
                    issuing_council=doc_item["issuing_council"],
                    reg_year=doc_item["reg_year"],
                    dob=doc_item["dob"],
                    qualification=doc_item["qualification"],
                    specialty=doc_item["specialty"],
                    hospital_clinic=doc_item["hospital_clinic"],
                    phone=doc_item["phone"],
                    status=doc_item["status"],
                    status_reason=doc_item["status_reason"],
                    allowed_models=doc_item["allowed_models"],
                    daily_case_limit=50,
                    ai_summary_enabled=True,
                    pdf_export_enabled=True
                )
                db.add(prof)
                db.commit()
                db.refresh(prof)

                create_audit_log(
                    db,
                    action="DOCTOR_REGISTERED",
                    actor_id=u.id,
                    actor_role="doctor",
                    target_type="DoctorProfile",
                    target_id=str(prof.id),
                    details={"reg_number": prof.reg_number, "status": prof.status}
                )

                # Seed sample patients if any
                for p_item in doc_item.get("patients", []):
                    pat = Patient(
                        doctor_id=prof.id,
                        patient_code=p_item["patient_code"],
                        name=p_item["name"],
                        dob=p_item["dob"],
                        age=p_item["age"],
                        sex=p_item["sex"],
                        blood_group=p_item["blood_group"],
                        height_cm=p_item["height_cm"],
                        weight_kg=p_item["weight_kg"],
                        phone=p_item["phone"],
                        consent_confirmed=True
                    )
                    db.add(pat)
                    db.commit()
                    db.refresh(pat)

                    c_item = p_item["case"]
                    c = Case(
                        patient_id=pat.id,
                        doctor_id=prof.id,
                        case_code=c_item["case_code"],
                        chief_complaint=c_item["chief_complaint"],
                        onset_duration=c_item["onset_duration"],
                        associated_symptoms=c_item["associated_symptoms"],
                        past_history=c_item["past_history"],
                        family_history=c_item["family_history"],
                        allergies=c_item["allergies"],
                        lifestyle=c_item["lifestyle"],
                        doctor_question=c_item["doctor_question"],
                        vitals=json.dumps(p_item["vitals"]),
                        triage_level=c_item["triage_level"],
                        status=c_item["status"]
                    )
                    db.add(c)
                    db.commit()

                print(f"[Seed] Doctor created: {doc_item['full_name']} ({doc_item['status']}) - Reg: {doc_item['reg_number']}")

        print("[Seed] Database successfully populated with initial clinical dataset.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
