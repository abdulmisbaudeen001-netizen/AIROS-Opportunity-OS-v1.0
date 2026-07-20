"""
AIROS Opportunity OS v1.0
REST API — FastAPI backend that powers the web UI.
Also serves the static web/ directory.
All endpoints require Bearer token auth except /api/login and static files.
"""

import asyncio
import json
import logging
import secrets
import time
from pathlib import Path
from typing import Optional, AsyncGenerator

from fastapi import FastAPI, HTTPException, Depends, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import config
from profile import profile_manager
from storage import storage
from email_agent import email_agent
from document_engine_ref import document_engine
from application import application_engine
from opportunity import opportunity_analyzer
from notification import notifier
from utils import utcnow_iso

logger = logging.getLogger("airos.api")

# ── Token store (in-memory, single user) ─────────────────────────────────────
_active_tokens: dict[str, float] = {}  # token -> expiry timestamp
TOKEN_TTL = 60 * 60 * 24  # 24 hours

security = HTTPBearer()


def issue_token() -> str:
    token = secrets.token_hex(32)
    _active_tokens[token] = time.time() + TOKEN_TTL
    return token


def validate_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    token = credentials.credentials
    expiry = _active_tokens.get(token)
    if not expiry or time.time() > expiry:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return token


# ── Request/Response models ───────────────────────────────────────────────────

class LoginRequest(BaseModel):
    password: str

class ProfileUpdateRequest(BaseModel):
    field: str
    value: str

class CommandRequest(BaseModel):
    command: str

class SkillRequest(BaseModel):
    name: str
    level: str = "intermediate"

class KnowledgeRequest(BaseModel):
    category: str
    content: str

class ApplicationActionRequest(BaseModel):
    application_id: str
    action: str  # approve | skip


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(title="AIROS Opportunity OS", version="1.0.0", docs_url=None, redoc_url=None)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Auth ──────────────────────────────────────────────────────────────────

    @app.post("/api/login")
    async def login(req: LoginRequest):
        if req.password != config.web_password:
            raise HTTPException(status_code=401, detail="Incorrect password")
        token = issue_token()
        return {"token": token}

    @app.post("/api/logout")
    async def logout(token: str = Depends(validate_token)):
        _active_tokens.pop(token, None)
        return {"ok": True}

    # ── Dashboard ─────────────────────────────────────────────────────────────

    @app.get("/api/dashboard")
    async def dashboard(_: str = Depends(validate_token)):
        missions = storage.get_recent_missions(limit=1)
        last_mission = missions[0] if missions else {}
        applications = storage.get_applications(limit=100)
        opportunities = storage.get_opportunities(limit=100)
        completeness = profile_manager.get_completeness()

        status_counts = {}
        for app in applications:
            s = app.get("status", "unknown")
            status_counts[s] = status_counts.get(s, 0) + 1

        category_counts = {}
        for opp in opportunities:
            c = opp.get("category", "other")
            category_counts[c] = category_counts.get(c, 0) + 1

        return {
            "last_mission": last_mission,
            "total_applications": len(applications),
            "application_statuses": status_counts,
            "total_opportunities": len(opportunities),
            "opportunity_categories": category_counts,
            "profile_completeness": completeness["score"],
            "awaiting_approval": status_counts.get("awaiting_approval", 0),
            "interviews": len([e for e in storage.get_emails(category="interview", limit=50)]),
        }

    # ── Mission Control ───────────────────────────────────────────────────────

    @app.post("/api/mission/run")
    async def run_mission(req: CommandRequest, token: str = Depends(validate_token)):
        """Trigger a mission command. Returns immediately; progress streams via SSE."""
        command = req.command.strip() or "/mission"

        # Run in background thread so we don't block the response
        def _run():
            from planner import planner
            # Use a fixed chat_id for web-triggered missions
            web_chat_id = "web_ui"
            notifier.set_chat_id(web_chat_id)
            planner.handle(command, web_chat_id)

        import threading
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return {"ok": True, "message": f"Mission started: {command}"}

    @app.get("/api/mission/stream")
    async def mission_stream(token: str = Depends(validate_token)):
        """
        SSE endpoint — streams mission log lines to the web UI in real time.
        The web JS connects here and receives log events as they happen.
        """
        async def event_generator() -> AsyncGenerator[str, None]:
            # Tail the recent mission log entries from Supabase
            seen_ids = set()
            for _ in range(120):  # max 2 minutes of polling
                try:
                    missions = storage.get_recent_missions(limit=1)
                    if missions:
                        mid = missions[0]["id"]
                        logs = storage.db.table("mission_logs")\
                            .select("*")\
                            .eq("mission_id", mid)\
                            .order("created_at")\
                            .execute().data
                        for log in logs:
                            if log["id"] not in seen_ids:
                                seen_ids.add(log["id"])
                                data = json.dumps({
                                    "module": log.get("module", ""),
                                    "message": log.get("error", ""),
                                    "time": log.get("created_at", ""),
                                })
                                yield f"data: {data}\n\n"
                except Exception:
                    pass
                await asyncio.sleep(1)
            yield "data: {\"done\": true}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    @app.get("/api/mission/recent")
    async def recent_missions(_: str = Depends(validate_token)):
        missions = storage.get_recent_missions(limit=10)
        return {"missions": missions}

    # ── Profile ───────────────────────────────────────────────────────────────

    @app.get("/api/profile")
    async def get_profile(_: str = Depends(validate_token)):
        profile = profile_manager.get_full_profile()
        completeness = profile_manager.get_completeness()
        return {"profile": profile, "completeness": completeness}

    @app.patch("/api/profile")
    async def update_profile(req: ProfileUpdateRequest, _: str = Depends(validate_token)):
        result = profile_manager.update_field(req.field, req.value)
        if not result.ok():
            raise HTTPException(status_code=400, detail=result.error)
        return {"ok": True}

    @app.post("/api/profile/cv")
    async def upload_cv(file: UploadFile = File(...), _: str = Depends(validate_token)):
        """Upload CV file (PDF or DOCX) for profile extraction."""
        content = await file.read()
        filename = file.filename or "cv.pdf"

        # Extract text
        text = _extract_text(content, filename)
        if not text:
            raise HTTPException(status_code=400, detail="Could not extract text from file.")

        result = profile_manager.import_cv_text(text)
        if not result.ok():
            raise HTTPException(status_code=500, detail=result.error)

        completeness = profile_manager.get_completeness()
        return {"ok": True, "completeness": completeness}

    @app.post("/api/profile/skills")
    async def add_skill(req: SkillRequest, _: str = Depends(validate_token)):
        result = profile_manager.add_skill(req.name, req.level)
        if not result.ok():
            raise HTTPException(status_code=400, detail=result.error)
        return {"ok": True}

    @app.post("/api/profile/knowledge")
    async def add_knowledge(req: KnowledgeRequest, _: str = Depends(validate_token)):
        result = profile_manager.add_knowledge(req.category, req.content)
        if not result.ok():
            raise HTTPException(status_code=400, detail=result.error)
        return {"ok": True}

    @app.get("/api/profile/questions")
    async def onboarding_questions(_: str = Depends(validate_token)):
        questions = profile_manager.get_onboarding_questions()
        return {"questions": questions}

    # ── Opportunities ─────────────────────────────────────────────────────────

    @app.get("/api/opportunities")
    async def get_opportunities(limit: int = 50, category: Optional[str] = None, _: str = Depends(validate_token)):
        opps = storage.get_opportunities(limit=limit)
        if category:
            opps = [o for o in opps if o.get("category") == category]
        return {"opportunities": opps, "total": len(opps)}

    @app.get("/api/opportunities/{opp_id}")
    async def get_opportunity(opp_id: str, _: str = Depends(validate_token)):
        opps = storage.db.table("opportunities").select("*").eq("id", opp_id).limit(1).execute().data
        if not opps:
            raise HTTPException(status_code=404, detail="Opportunity not found")
        return {"opportunity": opps[0]}

    # ── Applications ──────────────────────────────────────────────────────────

    @app.get("/api/applications")
    async def get_applications(status: Optional[str] = None, limit: int = 50, _: str = Depends(validate_token)):
        apps = storage.get_applications(status=status, limit=limit)
        return {"applications": apps, "total": len(apps)}

    @app.post("/api/applications/action")
    async def application_action(req: ApplicationActionRequest, _: str = Depends(validate_token)):
        if req.action == "approve":
            profile = profile_manager.get_full_profile()
            docs = storage.get_documents()
            result = application_engine.submit_approved(req.application_id, profile, {})
            if not result.ok():
                raise HTTPException(status_code=400, detail=result.error)
            return {"ok": True, "status": result.data.get("status")}
        elif req.action == "skip":
            storage.update_application(req.application_id, {"status": "skipped"})
            return {"ok": True}
        raise HTTPException(status_code=400, detail="Unknown action")

    # ── Documents ─────────────────────────────────────────────────────────────

    @app.get("/api/documents")
    async def get_documents(doc_type: Optional[str] = None, _: str = Depends(validate_token)):
        docs = storage.get_documents(doc_type=doc_type)
        # Don't send full base64 in list view — too heavy
        for d in docs:
            d.pop("pdf_b64", None)
        return {"documents": docs, "total": len(docs)}

    @app.get("/api/documents/{doc_id}/download")
    async def download_document(doc_id: str, _: str = Depends(validate_token)):
        docs = storage.db.table("documents").select("*").eq("id", doc_id).limit(1).execute().data
        if not docs:
            raise HTTPException(status_code=404, detail="Document not found")
        doc = docs[0]
        pdf_b64 = doc.get("pdf_b64")
        if not pdf_b64:
            raise HTTPException(status_code=404, detail="No PDF available for this document")

        import base64
        pdf_bytes = base64.b64decode(pdf_b64)
        doc_type = doc.get("type", "document")
        filename = f"{doc_type}_{doc_id[:8]}.pdf"

        from fastapi.responses import Response
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # ── Email ─────────────────────────────────────────────────────────────────

    @app.get("/api/email")
    async def get_emails(category: Optional[str] = None, limit: int = 50, _: str = Depends(validate_token)):
        emails = storage.get_emails(category=category, limit=limit)
        return {"emails": emails, "total": len(emails)}

    @app.post("/api/email/check")
    async def check_email(_: str = Depends(validate_token)):
        result = email_agent.check_inbox(limit=20)
        if not result.ok():
            raise HTTPException(status_code=500, detail=result.error)
        summary = email_agent.get_summary(result.data.get("emails", []))
        return {"ok": True, "summary": summary, "emails": result.data.get("emails", [])}

    # ── Settings ──────────────────────────────────────────────────────────────

    @app.get("/api/settings")
    async def get_settings(_: str = Depends(validate_token)):
        return {
            "application_mode": config.application_mode,
            "auto_apply": config.auto_apply,
            "smart_apply": config.smart_apply,
            "email_address": config.email_address,
            "timezone": config.timezone,
            "llm_model": config.llm_model,
            "document_provider": config.document_provider,
        }

    # ── Health ────────────────────────────────────────────────────────────────

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": "1.0.0", "time": utcnow_iso()}

    # ── Static files — serve web UI ───────────────────────────────────────────
    web_dir = Path(__file__).parent / "web"
    if web_dir.exists():
        app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="static")

    return app


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_text(content: bytes, filename: str) -> Optional[str]:
    import io
    filename_lower = filename.lower()
    try:
        if filename_lower.endswith(".pdf"):
            try:
                import pypdf
                reader = pypdf.PdfReader(io.BytesIO(content))
                return "\n".join(p.extract_text() or "" for p in reader.pages)
            except ImportError:
                import pdfminer.high_level
                return pdfminer.high_level.extract_text(io.BytesIO(content))
        elif filename_lower.endswith((".docx", ".doc")):
            import docx
            doc = docx.Document(io.BytesIO(content))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        else:
            return content.decode("utf-8", errors="replace")
    except Exception as e:
        logger.error(f"Text extraction failed: {e}")
        return None
