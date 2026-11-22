import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.config import UPLOAD_DIR, OUTPUT_DIR
from backend.routes.auth import router as auth_router
from backend.routes.admin import router as admin_router
from backend.routes.doctor import router as doctor_router


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


app = FastAPI(
    title="ClinicalLens API",
    description="Local, privacy-first multimodal clinical decision-support platform",
    version="2.0.0"
)

# Security and CORS
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static file access for generated figures and uploaded docs
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")

# Include Routers
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(doctor_router)


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "ClinicalLens Local Server",
        "version": "2.0.0",
        "mode": "privacy-first-local"
    }
