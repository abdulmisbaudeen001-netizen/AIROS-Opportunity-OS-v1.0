"""
AIROS Opportunity OS v1.0
Storage — the only module that communicates with Supabase.
All other modules request data through this interface.
"""

import logging
from typing import Any, Optional
from supabase import create_client, Client
from config import config
from utils import utcnow_iso

logger = logging.getLogger("airos.storage")


class Storage:
    def __init__(self):
        self._client: Optional[Client] = None

    @property
    def db(self) -> Client:
        if self._client is None:
            self._client = create_client(config.supabase_url, config.supabase_key)
        return self._client

    def ping(self) -> None:
        """Verify Supabase connection. Raises on failure."""
        self.db.table("profile").select("id").limit(1).execute()

    # ── Profile ───────────────────────────────────────────────────────────────

    def get_profile(self) -> Optional[dict]:
        res = self.db.table("profile").select("*").limit(1).execute()
        return res.data[0] if res.data else None

    def upsert_profile(self, data: dict) -> dict:
        data["updated_at"] = utcnow_iso()
        res = self.db.table("profile").upsert(data).execute()
        return res.data[0]

    def get_experiences(self) -> list[dict]:
        return self.db.table("experience").select("*").order("start_date", desc=True).execute().data

    def upsert_experience(self, data: dict) -> dict:
        return self.db.table("experience").upsert(data).execute().data[0]

    def get_education(self) -> list[dict]:
        return self.db.table("education").select("*").order("start_date", desc=True).execute().data

    def upsert_education(self, data: dict) -> dict:
        return self.db.table("education").upsert(data).execute().data[0]

    def get_skills(self) -> list[dict]:
        return self.db.table("skills").select("*").execute().data

    def upsert_skill(self, data: dict) -> dict:
        return self.db.table("skills").upsert(data).execute().data[0]

    def get_profile_completeness(self) -> dict:
        profile = self.get_profile() or {}
        fields = {
            "name": bool(profile.get("name")),
            "email": bool(profile.get("email")),
            "phone": bool(profile.get("phone")),
            "linkedin": bool(profile.get("linkedin")),
            "github": bool(profile.get("github")),
            "portfolio": bool(profile.get("portfolio")),
            "bio": bool(profile.get("bio")),
            "location": bool(profile.get("location")),
        }
        experience = bool(self.get_experiences())
        education = bool(self.get_education())
        skills = bool(self.get_skills())
        fields["experience"] = experience
        fields["education"] = education
        fields["skills"] = skills
        completed = sum(fields.values())
        total = len(fields)
        return {
            "score": round((completed / total) * 100),
            "fields": fields,
            "missing": [k for k, v in fields.items() if not v],
        }

    # ── Opportunities ─────────────────────────────────────────────────────────

    def save_opportunity(self, data: dict) -> dict:
        data["created_at"] = utcnow_iso()
        res = self.db.table("opportunities").upsert(data, on_conflict="hash").execute()
        return res.data[0]

    def get_opportunities(self, limit: int = 50, session_id: Optional[str] = None) -> list[dict]:
        q = self.db.table("opportunities").select("*").order("score", desc=True).limit(limit)
        if session_id:
            q = q.eq("session_id", session_id)
        return q.execute().data

    def opportunity_exists(self, hash_val: str) -> bool:
        res = self.db.table("opportunities").select("id").eq("hash", hash_val).limit(1).execute()
        return bool(res.data)

    # ── Applications ──────────────────────────────────────────────────────────

    def save_application(self, data: dict) -> dict:
        data["created_at"] = utcnow_iso()
        res = self.db.table("applications").insert(data).execute()
        return res.data[0]

    def update_application(self, app_id: str, updates: dict) -> dict:
        updates["updated_at"] = utcnow_iso()
        res = self.db.table("applications").update(updates).eq("id", app_id).execute()
        return res.data[0]

    def get_applications(self, status: Optional[str] = None, limit: int = 50) -> list[dict]:
        q = self.db.table("applications").select("*").order("created_at", desc=True).limit(limit)
        if status:
            q = q.eq("status", status)
        return q.execute().data

    # ── Documents ─────────────────────────────────────────────────────────────

    def save_document(self, data: dict) -> dict:
        data["created_at"] = utcnow_iso()
        res = self.db.table("documents").insert(data).execute()
        return res.data[0]

    def get_documents(self, doc_type: Optional[str] = None) -> list[dict]:
        q = self.db.table("documents").select("*").order("created_at", desc=True)
        if doc_type:
            q = q.eq("type", doc_type)
        return q.execute().data

    # ── Accounts ──────────────────────────────────────────────────────────────

    def save_account(self, data: dict) -> dict:
        data["created_at"] = utcnow_iso()
        res = self.db.table("accounts").upsert(data, on_conflict="platform,email").execute()
        return res.data[0]

    def get_account(self, platform: str) -> Optional[dict]:
        res = self.db.table("accounts").select("*").eq("platform", platform).limit(1).execute()
        return res.data[0] if res.data else None

    def get_all_accounts(self) -> list[dict]:
        return self.db.table("accounts").select("*").execute().data

    # ── Missions / Logs ───────────────────────────────────────────────────────

    def start_mission(self, mission_id: str, command: str) -> dict:
        data = {
            "id": mission_id,
            "command": command,
            "status": "running",
            "started_at": utcnow_iso(),
            "tasks_completed": 0,
            "tasks_failed": 0,
            "retry_count": 0,
            "errors": [],
        }
        res = self.db.table("missions").insert(data).execute()
        return res.data[0]

    def end_mission(self, mission_id: str, summary: dict) -> dict:
        updates = {
            "status": "completed",
            "ended_at": utcnow_iso(),
            **summary,
        }
        res = self.db.table("missions").update(updates).eq("id", mission_id).execute()
        return res.data[0]

    def log_error(self, mission_id: str, error: str, module: str) -> None:
        try:
            self.db.table("mission_logs").insert({
                "mission_id": mission_id,
                "module": module,
                "error": error,
                "created_at": utcnow_iso(),
            }).execute()
        except Exception as e:
            logger.error(f"Failed to log error: {e}")

    def get_mission(self, mission_id: str) -> Optional[dict]:
        res = self.db.table("missions").select("*").eq("id", mission_id).limit(1).execute()
        return res.data[0] if res.data else None

    def get_recent_missions(self, limit: int = 10) -> list[dict]:
        return self.db.table("missions").select("*").order("started_at", desc=True).limit(limit).execute().data

    # ── Knowledge Base ────────────────────────────────────────────────────────

    def get_knowledge(self, category: Optional[str] = None) -> list[dict]:
        q = self.db.table("knowledge_base").select("*")
        if category:
            q = q.eq("category", category)
        return q.execute().data

    def save_knowledge(self, data: dict) -> dict:
        data["created_at"] = utcnow_iso()
        res = self.db.table("knowledge_base").upsert(data).execute()
        return res.data[0]

    # ── Email history ─────────────────────────────────────────────────────────

    def save_email_record(self, data: dict) -> dict:
        data["received_at"] = data.get("received_at", utcnow_iso())
        res = self.db.table("emails").upsert(data, on_conflict="message_id").execute()
        return res.data[0]

    def get_emails(self, category: Optional[str] = None, limit: int = 50) -> list[dict]:
        q = self.db.table("emails").select("*").order("received_at", desc=True).limit(limit)
        if category:
            q = q.eq("category", category)
        return q.execute().data

    # ── Task queue (persistent checkpoints) ───────────────────────────────────

    def enqueue_task(self, mission_id: str, task: dict) -> dict:
        task["mission_id"] = mission_id
        task["status"] = "pending"
        task["created_at"] = utcnow_iso()
        res = self.db.table("task_queue").insert(task).execute()
        return res.data[0]

    def complete_task(self, task_id: str, result: Any = None) -> None:
        self.db.table("task_queue").update({
            "status": "completed",
            "result": result,
            "completed_at": utcnow_iso(),
        }).eq("id", task_id).execute()

    def get_pending_tasks(self, mission_id: str) -> list[dict]:
        return self.db.table("task_queue").select("*").eq("mission_id", mission_id).eq("status", "pending").execute().data


# Singleton
storage = Storage()
