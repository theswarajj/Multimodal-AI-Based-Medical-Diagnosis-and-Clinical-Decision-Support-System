import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

# Ensure project root is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import clinical_text as ct
import app as cli_app


def extract_document_text(file_path: str, sex_letter: Optional[str] = None) -> Dict[str, Any]:
    """Wraps clinical_text.process_document to extract text and parse labs."""
    return ct.process_document(file_path, sex_letter)


def extract_typed_text(text: str, sex_letter: Optional[str] = None) -> Dict[str, Any]:
    """Wraps clinical_text.process_typed."""
    return ct.process_typed(text, sex_letter)


def parse_raw_labs(text: str, sex_letter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Wraps clinical_text.parse_labs."""
    return ct.parse_labs(text, sex_letter)


# In-memory GPU Model Cache to keep PyTorch models resident in VRAM
# This accelerates inference from ~45s (disk reload) down to ~3s on the RTX 3070 Ti GPU
_GPU_MODEL_CACHE: Dict[str, Any] = {}


def get_or_load_model_context(modality_key: str, cfg: Dict[str, Any], prep_fn):
    """Retrieves cached GPU model context or loads it into VRAM once."""
    global _GPU_MODEL_CACHE
    if modality_key in _GPU_MODEL_CACHE:
        return _GPU_MODEL_CACHE[modality_key]

    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.init()
            torch.zeros(1, device="cuda")
    except Exception:
        pass

    ctx = prep_fn(cfg)
    _GPU_MODEL_CACHE[modality_key] = ctx
    return ctx


def clear_gpu_model_cache():
    """Flushes cached models and frees GPU VRAM."""
    global _GPU_MODEL_CACHE
    _GPU_MODEL_CACHE.clear()
    cli_app.free_gpu()


def execute_model_inference(
    modality: str,
    file_path: str,
    case_id: str
) -> Tuple[Dict[str, Any], List[str], str]:
    """
    Executes the trained CNN model (SKIN, XRAY, or MRI) directly on GPU using cached VRAM models.
    Returns (result_dict, saved_figure_paths, descriptive_text).
    """
    modality_key = modality.upper()
    mod_configs = {v["key"]: v for v in cli_app.MODALITIES.values()}
    if modality_key not in mod_configs:
        raise ValueError(f"Unknown modality: {modality}. Available: {list(mod_configs.keys())}")

    cfg = mod_configs[modality_key]
    prep_fn, infer_fn = cli_app.PIPELINES[modality_key]

    # Output directory for figures and JSON
    out_dir = cli_app.OUTPUT_DIR / modality_key / case_id
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Retrieve or load model directly in GPU VRAM (fast ~3s inference)
        ctx = get_or_load_model_context(modality_key, cfg, prep_fn)

        # 2. Run inference on GPU
        result, fig_job = infer_fn(ctx, Path(file_path))

        # 3. Generate clinical figures
        fig_paths = []
        try:
            fig_result = fig_job(out_dir)
            if fig_result:
                fig_paths = [f"/outputs/{modality_key}/{case_id}/{Path(p).name}" for p in fig_result]
        except Exception as e:
            print(f"[Pipeline] Warning: Figure drawing failed for {modality_key}: {e}")

        # 4. Build descriptive text
        desc_fn = cli_app.DESCRIBERS[modality_key]
        text_desc = desc_fn(result)

        # Save result JSON
        cli_app.save_json(result, out_dir / f"{modality_key}_result.json")

        return result, fig_paths, text_desc

    except Exception as e:
        clear_gpu_model_cache()
        raise RuntimeError(f"Inference error in {modality_key}: {str(e)}") from e


def compute_triage(
    vitals: Dict[str, Any],
    runs: List[Dict[str, Any]],
    labs: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Executes rule-based deterministic triage logic from app.py.
    Returns {'level': 'URGENT'|'PRIORITY'|'ROUTINE', 'alerts': [{'level', 'text'}]}.
    """
    return cli_app.run_triage(vitals, runs, labs)


def generate_medgemma_summary(
    patient: Dict[str, Any],
    vitals: Dict[str, Any],
    clinical: Dict[str, Any],
    docs_text: str,
    runs: List[Dict[str, Any]],
    triage: Dict[str, Any]
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Calls local MedGemma model through Ollama using prompts from app.py.
    Returns (detailed_analysis, quick_summary, error_message).
    """
    ok, msg = cli_app.check_llm()
    if not ok:
        return None, None, f"Ollama / {cli_app.LLM_MODEL} not reachable: {msg}"

    user_prompt = cli_app.build_user_prompt(patient, vitals, clinical, docs_text, runs, triage)
    detail, quick, err = cli_app.generate_analysis(user_prompt, triage)
    return detail, quick, err
