import asyncio
import datetime
import json
import queue
import threading
import time
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path

from backend.database import SessionLocal
from backend.models import Case, AnalysisRun, Upload, Document, LabValue
from backend.pipeline_adapter import (
    execute_model_inference, compute_triage, generate_medgemma_summary
)
import app as cli_app


class AnalysisQueueManager:
    """
    Single-worker analysis queue respecting the 4 GB VRAM GPU hardware limitation.
    Processes one clinical case at a time in strict FIFO order, tracking queue positions
    and publishing real-time Server-Sent Events (SSE) updates to connected clinicians.
    """

    def __init__(self):
        self._work_queue: queue.Queue = queue.Queue()
        self._current_case_id: Optional[str] = None
        self._current_stage: str = "IDLE"
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._lock = threading.RLock()
        
        # Start background worker thread
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def get_queue_status(self, case_id: str) -> Dict[str, Any]:
        """Returns the current queue status and position for a specific case."""
        with self._lock:
            if self._current_case_id == case_id:
                return {
                    "status": "RUNNING",
                    "queue_position": 0,
                    "stage": self._current_stage,
                }
            
            # Find position in queue
            items = list(self._work_queue.queue)
            for idx, item in enumerate(items, 1):
                if item["case_id"] == case_id:
                    return {
                        "status": "QUEUED",
                        "queue_position": idx,
                        "stage": "WAITING_IN_QUEUE",
                    }
            
            return {
                "status": "NOT_QUEUED",
                "queue_position": 0,
                "stage": "IDLE",
            }

    def enqueue_case(self, case_id: str, modalities: List[str]) -> int:
        """Enqueues a case for analysis. Returns the queue position (1-based)."""
        with self._lock:
            position = self._work_queue.qsize() + (1 if self._current_case_id else 0)
            self._work_queue.put({"case_id": case_id, "modalities": modalities})
            
            # Notify subscribers of new queue state
            self.broadcast_event(case_id, "queue_update", {
                "case_id": case_id,
                "status": "QUEUED",
                "queue_position": max(1, position),
                "message": f"Case queued at position {max(1, position)}"
            })
            return max(1, position)

    def subscribe(self, case_id: str) -> asyncio.Queue:
        """Registers an asyncio.Queue for a client listening to SSE for this case."""
        with self._lock:
            if case_id not in self._subscribers:
                self._subscribers[case_id] = []
            q: asyncio.Queue = asyncio.Queue()
            self._subscribers[case_id].append(q)
            return q

    def unsubscribe(self, case_id: str, q: asyncio.Queue):
        """Unregisters an SSE subscriber queue."""
        with self._lock:
            if case_id in self._subscribers:
                self._subscribers[case_id] = [sub for sub in self._subscribers[case_id] if sub != q]
                if not self._subscribers[case_id]:
                    del self._subscribers[case_id]

    def broadcast_event(self, case_id: str, event_type: str, data: Dict[str, Any]):
        """Pushes an SSE event to all connected listeners for this case."""
        with self._lock:
            subs = list(self._subscribers.get(case_id, []))
        
        payload = {"event": event_type, "data": data}
        for q in subs:
            try:
                q.put_nowait(payload)
            except Exception:
                pass

    def _worker_loop(self):
        """Sequential single-worker execution loop."""
        while True:
            try:
                task = self._work_queue.get()
                case_id = task["case_id"]
                modalities = task.get("modalities", [])

                with self._lock:
                    self._current_case_id = case_id
                    self._current_stage = "INITIALIZING"

                self._execute_analysis_job(case_id, modalities)

                with self._lock:
                    self._current_case_id = None
                    self._current_stage = "IDLE"
                    self._work_queue.task_done()

            except Exception as e:
                print(f"[QueueManager] Worker exception: {e}")
                time.sleep(1)

    def _execute_analysis_job(self, case_id: str, requested_modalities: List[str]):
        """Executes the multimodal diagnostic workflow for a single case."""
        db = SessionLocal()
        try:
            case = db.query(Case).filter(Case.case_code == case_id).first()
            if not case:
                case = db.query(Case).filter(Case.id == int(case_id)).first()
            if not case:
                return

            run = case.analysis_run
            if not run:
                run = AnalysisRun(case_id=case.id, status="RUNNING", queue_position=0)
                db.add(run)
            else:
                run.status = "RUNNING"
                run.queue_position = 0
            db.commit()

            case_code = case.case_code
            timings: Dict[str, float] = {}
            t_start = time.perf_counter()

            # Stage 1: Loading Models
            self._current_stage = "loading_models"
            self.broadcast_event(case_code, "stage", {
                "stage": "loading_models",
                "label": "Preparing neural network checkpoints and allocating memory",
                "progress": 15
            })
            time.sleep(0.5)

            # Stage 2: Scanning & Inference
            self._current_stage = "scanning"
            runs_output = []
            uploads = case.uploads
            
            for upload in uploads:
                mod_key = upload.modality.upper()
                if requested_modalities and mod_key not in requested_modalities:
                    continue

                self.broadcast_event(case_code, "stage", {
                    "stage": "scanning",
                    "label": f"Running {mod_key} CNN inference on {upload.filename}",
                    "modality": mod_key,
                    "filename": upload.filename,
                    "progress": 35
                })

                t0 = time.perf_counter()
                try:
                    result, fig_paths, desc_text = execute_model_inference(
                        mod_key, upload.file_path, case_code
                    )
                    timings[f"inference_{mod_key}"] = round(time.perf_counter() - t0, 2)
                    runs_output.append({
                        "key": mod_key,
                        "file": upload.file_path,
                        "filename": upload.filename,
                        "result": result,
                        "figures": fig_paths,
                        "text": desc_text
                    })
                except Exception as e:
                    print(f"[QueueManager] Model {mod_key} failed: {e}")

            # Stage 3: Drawing Heatmaps & Visualizations
            self._current_stage = "drawing_heatmaps"
            self.broadcast_event(case_code, "stage", {
                "stage": "drawing_heatmaps",
                "label": "Generating Grad-CAM attention heatmaps and clinical figures",
                "progress": 60
            })
            time.sleep(0.5)

            # Stage 4: Rule-based Clinical Triage
            self._current_stage = "triage"
            self.broadcast_event(case_code, "stage", {
                "stage": "triage",
                "label": "Evaluating rule-based safety alerts and vital signs thresholds",
                "progress": 75
            })
            
            vitals = json.loads(case.vitals) if case.vitals else {}
            labs = [
                {
                    "name": l.name,
                    "value": l.value,
                    "unit": l.unit,
                    "ref": l.ref_range,
                    "flag": l.flag,
                    "critical": l.is_critical,
                    "ref_source": l.ref_source
                }
                for l in case.lab_values
            ]
            triage_result = compute_triage(vitals, runs_output, labs)
            case.triage_level = triage_result["level"]
            case.triage_alerts = json.dumps(triage_result["alerts"])
            db.commit()

            # Stage 5: MedGemma Clinical Analysis
            self._current_stage = "writing_analysis"
            self.broadcast_event(case_code, "stage", {
                "stage": "writing_analysis",
                "label": "MedGemma LLM generating structured findings and considerations",
                "progress": 90
            })

            patient_data = {
                "name": case.patient.name,
                "age": case.patient.age,
                "sex": case.patient.sex,
                "patient_id": case.patient.patient_code,
                "referring_doctor": case.doctor.full_name
            }
            clinical_data = {
                "chief_complaint": case.chief_complaint,
                "duration": case.onset_duration,
                "symptoms": case.associated_symptoms,
                "history": case.past_history,
                "medications": ", ".join(m.drug_name for m in case.medicines),
                "allergies": case.allergies,
                "family_history": case.family_history,
                "lifestyle": case.lifestyle,
                "doctor_question": case.doctor_question,
                "modality_specific": json.loads(case.modality_questions) if case.modality_questions else {}
            }
            docs_text = "\n\n".join(d.extracted_text for d in case.documents if d.extracted_text)

            t0 = time.perf_counter()
            detail, quick, llm_err = generate_medgemma_summary(
                patient_data, vitals, clinical_data, docs_text, runs_output, triage_result
            )
            timings["medgemma_llm"] = round(time.perf_counter() - t0, 2)
            timings["total_pipeline"] = round(time.perf_counter() - t_start, 2)

            # Persist results
            run.status = "COMPLETED"
            run.timings_json = json.dumps(timings)
            run.result_json = json.dumps({
                "runs": runs_output,
                "triage": triage_result,
                "vitals": vitals,
                "labs": labs
            })
            run.detailed_analysis = detail
            run.quick_summary = quick
            run.error_message = llm_err
            run.completed_at = datetime.datetime.utcnow()
            case.status = "COMPLETED"
            db.commit()

            # Final Complete Event
            self.broadcast_event(case_code, "complete", {
                "status": "COMPLETED",
                "case_code": case_code,
                "triage": triage_result,
                "detailed_analysis": detail,
                "quick_summary": quick,
                "runs": runs_output,
                "timings": timings
            })

        except Exception as e:
            print(f"[QueueManager] Fatal error executing analysis for {case_id}: {e}")
            if run:
                run.status = "FAILED"
                run.error_message = str(e)
                case.status = "FAILED"
                db.commit()
            self.broadcast_event(case_id, "error", {
                "status": "FAILED",
                "error": str(e)
            })
        finally:
            db.close()


# Global Singleton Queue Manager Instance
queue_manager = AnalysisQueueManager()
