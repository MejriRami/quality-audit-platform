import os
import logging
import uvicorn
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.config.database import SessionLocal, get_db
from app.models.audit import Audit
from app.models.audit_reschedule_history import AuditRescheduleHistory
from app.models.user import User
from app.routers.kpi import router as kpi_router

# from app.routers.kpi_chatbot import router as kpi_chatbot_router
# from app.routers.kpi_copilot import router as kpi_copilot_router
from app.routers.questionnaire_api import router as questionnaire_router
from app.routers.user_api import router as user_router
from app.routers.role_api import router as role_router
from app.routers.question_api import router as question_router
from app.routers.framework import router as framework_router
from app.routers.audit_type import router as audit_type_router
from app.routers.auth_api import router as auth_router
from app.routers.audit_api import router as audit_router
from app.routers.files import router as file_router
from app.routers.car_api import router as car_router
from app.routers.audit_report import router as report_router
from app.routers.notification import router as notifications_router
from app.routers.car_admin import router as car_admin_router
from app.routers.admin_api import router as admin_router
from app.routers.org_directory import router as org_directory_router
from app.routers.audit_planning import router as audit_planning_router
from app.routers.auditor_chatbot import router as auditor_chatbot_router
from app.routers.external_certifications import router as external_certifications_router
from app.services.admin_service import ensure_default_roles
from app.services.audit_service import handle_event_reschedule
from app.services.auth_service import get_current_user
from app.services.car_reminder_scheduler import start_scheduler
from app.routers.audit_result_email import router as audit_result_email_router
from app.services.event_calendar import get_access_token, get_graph_event

# -------------------------------------------------
# Logging
# -------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# -------------------------------------------------
# Lifespan (startup / shutdown)
# -------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting application...")
    app.state.startup_error = None

    db = SessionLocal()
    try:
        created_roles = ensure_default_roles(db)
        if created_roles:
            logger.info("Created default roles: %s", ", ".join(created_roles))
    except Exception as e:
        app.state.startup_error = (
            f"ensure_default_roles failed: {traceback.format_exc()}"
        )
        logger.error(app.state.startup_error)
        db.rollback()
    finally:
        db.close()

    try:
        scheduler = start_scheduler()
        app.state.scheduler = scheduler
        logger.info("✅ Scheduler started successfully")
    except Exception as e:
        err = f"start_scheduler failed: {traceback.format_exc()}"
        app.state.startup_error = (app.state.startup_error or "") + "\n" + err
        logger.error(err)

    yield

    logger.info("🛑 Shutting down application...")
    if hasattr(app.state, "scheduler"):
        app.state.scheduler.shutdown(wait=True)
        logger.info("✅ Scheduler shut down successfully")


# -------------------------------------------------
# App
# -------------------------------------------------
app = FastAPI(
    title="Audit Management Application",
    lifespan=lifespan,
)

# -------------------------------------------------
FRONTEND_URL = os.getenv("FRONTEND_URL")
FRONTEND_URLS = [
    origin.strip()
    for origin in os.getenv("FRONTEND_URLS", "").split(",")
    if origin.strip()
]

if FRONTEND_URL:
    FRONTEND_URLS.append(FRONTEND_URL.strip())

DEFAULT_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    # "https://your-app.azurewebsites.net",
]

allow_origins = []
for origin in [*FRONTEND_URLS, *DEFAULT_ORIGINS]:
    if origin and origin not in allow_origins:
        allow_origins.append(origin)

logger.info("CORS allow_origins=%s", allow_origins)

# -------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------------------------
# Global exception handler
# -------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    response = JSONResponse(
        status_code=500,
        content={
            "error": type(exc).__name__,
            "message": str(exc),
            "traceback": tb,
        },
    )
    # Handlers for the base Exception class run on Starlette's outermost
    # ServerErrorMiddleware, which sits outside CORSMiddleware, so CORS
    # headers are never added automatically here. Add them manually so
    # the browser doesn't mask real 500s as CORS failures.
    origin = request.headers.get("origin")
    if origin in allow_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    return response


# -------------------------------------------------
# Static files
# -------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = (BASE_DIR / "assets").resolve()

if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

# -------------------------------------------------
# Routers
# -------------------------------------------------
app.include_router(auth_router)
app.include_router(questionnaire_router)
app.include_router(user_router)
app.include_router(role_router)
app.include_router(question_router)
app.include_router(framework_router)
app.include_router(audit_type_router)
app.include_router(audit_router)
app.include_router(file_router)
app.include_router(car_router)
app.include_router(audit_result_email_router)
app.include_router(report_router)
app.include_router(notifications_router)
app.include_router(kpi_router)
# app.include_router(kpi_chatbot_router)
# app.include_router(kpi_copilot_router)
app.include_router(car_admin_router)
app.include_router(admin_router)
app.include_router(org_directory_router)
app.include_router(audit_planning_router)
app.include_router(auditor_chatbot_router)
app.include_router(external_certifications_router)


# -------------------------------------------------
# Root & Health
# -------------------------------------------------
@app.get("/")
async def root():
    return {"message": "Audit Management API"}


@app.get("/startup-error")
async def startup_error():
    return {"startup_error": getattr(app.state, "startup_error", None)}


@app.get("/debug-env")
async def debug_env():
    return {
        "DATABASE_URL_set": bool(os.getenv("DATABASE_URL")),
        "DATABASE_URL_preview": (os.getenv("DATABASE_URL") or "")[:30] + "...",
        "JWT_SECRET_KEY_set": bool(os.getenv("JWT_SECRET_KEY")),
        "JWT_ALGORITHM_set": bool(os.getenv("JWT_ALGORITHM")),
        "JWT_ALGORITHM_value": os.getenv("JWT_ALGORITHM"),
        "FRONTEND_URL": os.getenv("FRONTEND_URL"),
    }


@app.get("/import-test")
async def import_test():
    results = {}
    modules = [
        "jwt",
        "passlib",
        "argon2",
        "bcrypt",
        "sqlalchemy",
        "app.services.auth_service",
        "app.routers.auth_api",
        "app.config.database",
        "app.routers.notification",
        "app.utils.sse_manager",
    ]
    for mod in modules:
        try:
            __import__(mod)
            results[mod] = "OK"
        except Exception as e:
            results[mod] = f"FAILED: {str(e)}"
    return results


@app.post("/login-test")
async def login_test():
    return {"message": "login route works"}


@app.get("/health")
async def health_check():
    from app.utils.sse_manager import get_sse_manager

    sse_manager = get_sse_manager()
    scheduler_info = {"status": "not initialized"}
    if hasattr(app.state, "scheduler") and app.state.scheduler:
        scheduler = app.state.scheduler
        jobs = scheduler.get_jobs()
        scheduler_info = {
            "status": "running" if scheduler.running else "stopped",
            "total_jobs": len(jobs),
            "jobs": [
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": job.next_run_time.isoformat()
                    if job.next_run_time
                    else None,
                    "trigger": str(job.trigger),
                }
                for job in jobs
            ],
        }
    return {
        "status": "healthy",
        "active_sse_connections": sse_manager.get_total_connections(),
        "connected_users": len(sse_manager.get_active_users()),
        "scheduler": scheduler_info,
    }


@app.get("/token-test")
async def token_test(
    event_id: str,
    user_email: str,
    db=Depends(get_db),
    _: User = Depends(get_current_user),
):
    if os.getenv("ENABLE_TOKEN_TEST", "false").strip().lower() != "true":
        raise HTTPException(status_code=404, detail="Not found")

    try:
        token = await get_access_token()
        event = await get_graph_event(event_id, token, user_email)
        audit = db.query(Audit).filter(Audit.event_id == event["id"]).first()
        if not audit:
            return {
                "error": "No audit found for this event",
                "event_id": event["id"],
                "event": event,
            }
        before_state = {
            "audit_id": audit.id,
            "audit_number": audit.audit_number,
            "status": audit.status,
            "planned_start_date": audit.planned_start_date.isoformat()
            if audit.planned_start_date
            else None,
            "planned_end_date": audit.planned_end_date.isoformat()
            if audit.planned_end_date
            else None,
        }
        await handle_event_reschedule(audit, event, db)
        db.commit()
        db.refresh(audit)
        after_state = {
            "audit_id": audit.id,
            "audit_number": audit.audit_number,
            "status": audit.status,
            "planned_start_date": audit.planned_start_date.isoformat()
            if audit.planned_start_date
            else None,
            "planned_end_date": audit.planned_end_date.isoformat()
            if audit.planned_end_date
            else None,
        }
        reschedule_history = (
            db.query(AuditRescheduleHistory)
            .filter(AuditRescheduleHistory.audit_id == audit.id)
            .order_by(AuditRescheduleHistory.created_at.desc())
            .all()
        )
        history_list = [
            {
                "id": h.id,
                "action_type": h.action_type,
                "old_date": h.old_date.isoformat() if h.old_date else None,
                "new_date": h.new_date.isoformat() if h.new_date else None,
                "reason": h.reason,
                "changed_by": h.changed_by,
                "changed_by_user": {
                    "id": h.changed_by_user.id,
                    "name": f"{h.changed_by_user.first_name} {h.changed_by_user.last_name}",
                    "email": h.changed_by_user.email,
                }
                if h.changed_by_user
                else None,
                "created_at": h.created_at.isoformat() if h.created_at else None,
            }
            for h in reschedule_history
        ]
        return {
            "success": True,
            "message": "Event reschedule processed",
            "before": before_state,
            "after": after_state,
            "changes_detected": before_state != after_state,
            "reschedule_history": history_list,
            "event_times": {
                "start": event.get("start", {}).get("dateTime"),
                "end": event.get("end", {}).get("dateTime"),
                "timezone": event.get("start", {}).get("timeZone"),
            },
            "event_subject": event.get("subject"),
            "event_is_cancelled": event.get("isCancelled", False),
        }
    except Exception as e:
        db.rollback()
        logger.exception("Token test failed")
        return {
            "success": False,
            "error": "internal_error",
            "detail": "Token test failed",
        }


# -------------------------------------------------
# Run directly (OPTIONAL)
# -------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="localhost",
        port=8000,
        reload=True,
        log_level="info",
    )
