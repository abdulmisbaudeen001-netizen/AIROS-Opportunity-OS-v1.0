"""
AIROS Opportunity OS v1.0
Application Engine — fills and submits applications.
Respects the configured approval mode: manual, smart, or automatic.
"""

import logging
from typing import Optional
from account import account_manager
from browser import browser
from config import config
from llm import llm
from opportunity import opportunity_analyzer
from prompts import prompts
from storage import storage
from utils import Result, new_id, utcnow_iso

logger = logging.getLogger("airos.application")

APPLICATION_STATUS = {
    "pending": "pending",
    "awaiting_approval": "awaiting_approval",
    "submitted": "submitted",
    "failed": "failed",
    "skipped": "skipped",
    "human_required": "human_required",
}


class ApplicationEngine:

    def apply(
        self,
        opportunity: dict,
        profile: dict,
        documents: dict,
        mode: Optional[str] = None,
    ) -> Result:
        """
        Main application entry point.
        Respects the configured or overridden approval mode.
        Returns Result with status and any pending approval information.
        """
        mode = mode or config.application_mode
        opp_title = opportunity.get("title", "Unknown")
        opp_url = opportunity.get("application_url", "")

        logger.info(f"Applying to: {opp_title} | mode={mode}")

        if not opp_url:
            return Result.failed("No application URL found.")

        # Manual mode — always queue for approval
        if mode == "manual":
            return self._queue_for_approval(opportunity, profile, documents, reason="Manual mode")

        # Smart mode — check if auto-apply is appropriate
        if mode == "smart":
            can_auto, reason = opportunity_analyzer.smart_apply_eligible(opportunity)
            if not can_auto:
                return self._queue_for_approval(opportunity, profile, documents, reason=reason)

        # Auto or smart-eligible — attempt submission
        return self._submit(opportunity, profile, documents)

    def _submit(self, opportunity: dict, profile: dict, documents: dict) -> Result:
        """Attempt automated form submission."""
        opp_url = opportunity.get("application_url", "")
        opp_title = opportunity.get("title", "")

        # Detect platform and handle account
        platform = account_manager.infer_platform_from_url(opp_url)
        personal = profile.get("personal", {})
        email = personal.get("email", config.email_address)

        # Get or create account
        account_result = account_manager.get_or_create(platform, email, profile)
        if not account_result.ok():
            return Result.failed(f"Account setup failed: {account_result.error}")

        account_data = account_result.data.get("account", {})

        # If account needs verification, pause
        if account_result.data.get("requires_verification"):
            return self._queue_for_human(opportunity, "Email verification required for new account")

        # Load the application page
        page_result = browser.get_page_content(opp_url, wait_ms=2500)
        if not page_result.ok():
            return Result.retry(f"Could not load application page: {page_result.error}")

        page_text = page_result.data.get("text", "")

        # Detect human checkpoint immediately
        is_checkpoint, checkpoint_type = account_manager.detect_human_checkpoint_in_page(page_text)
        if is_checkpoint:
            return self._queue_for_human(opportunity, f"Human checkpoint detected: {checkpoint_type}")

        # Map form fields using LLM
        field_mapping = llm.generate_json(
            prompt=prompts.FORM_FIELD_MAP.format(
                fields=page_text[:3000],
                profile=str(profile),
                opportunity=str(opportunity),
            ),
            temperature=0.1,
        )

        if not field_mapping:
            return Result.retry("Could not analyze form fields")

        # Check if human is required for this form
        if field_mapping.get("requires_human"):
            return self._queue_for_human(opportunity, field_mapping.get("human_reason", "Complex form detected"))

        # Fill and submit the form
        field_mappings = field_mapping.get("field_mappings", [])

        # Attach documents
        resume_result = documents.get("resume")
        if resume_result and resume_result.ok():
            resume_b64 = self._encode_pdf(resume_result.data.get("pdf"))
            # Find file upload field for resume
            for field in field_mappings:
                if field.get("action") == "upload" and "resume" in field.get("field_id", "").lower():
                    field["resume_b64"] = resume_b64

        submit_selector = self._find_submit_selector(page_text)
        fill_result = browser.fill_form_and_submit(
            url=opp_url,
            field_mappings=[f for f in field_mappings if f.get("action") in ("type", "select", "checkbox")],
            submit_selector=submit_selector,
            wait_after_ms=4000,
        )

        if not fill_result.ok():
            return Result.retry(f"Form submission failed: {fill_result.error}")

        result_text = fill_result.data.get("text", "").lower()
        if any(w in result_text for w in ["thank you", "application received", "successfully submitted", "success"]):
            record = self._save_application(opportunity, "submitted", account_data)
            logger.info(f"Application submitted: {opp_title}")
            return Result.success({
                "status": "submitted",
                "opportunity": opp_title,
                "application_id": record.get("id"),
            })

        # Ambiguous result
        record = self._save_application(opportunity, "unknown", account_data)
        return Result.success({
            "status": "unknown",
            "opportunity": opp_title,
            "note": "Submission result unclear. Please verify manually.",
            "application_id": record.get("id"),
        })

    def _queue_for_approval(self, opportunity: dict, profile: dict, documents: dict, reason: str) -> Result:
        """Queue application for manual user approval."""
        record = self._save_application(opportunity, "awaiting_approval", {})
        logger.info(f"Queued for approval: {opportunity.get('title')} — {reason}")
        return Result.success({
            "status": "awaiting_approval",
            "opportunity": opportunity.get("title"),
            "reason": reason,
            "application_id": record.get("id"),
            "url": opportunity.get("application_url"),
        })

    def _queue_for_human(self, opportunity: dict, reason: str) -> Result:
        """Pause application — human intervention required."""
        record = self._save_application(opportunity, "human_required", {})
        logger.info(f"Human required: {opportunity.get('title')} — {reason}")
        return Result.success({
            "status": "human_required",
            "opportunity": opportunity.get("title"),
            "reason": reason,
            "application_id": record.get("id"),
            "url": opportunity.get("application_url"),
        })

    def submit_approved(self, application_id: str, profile: dict, documents: dict) -> Result:
        """Submit a previously approved application."""
        apps = storage.get_applications(status="awaiting_approval")
        app = next((a for a in apps if a["id"] == application_id), None)
        if not app:
            return Result.failed(f"Application {application_id} not found or not pending approval.")

        opportunity = app.get("opportunity_data", {})
        return self._submit(opportunity, profile, documents)

    def get_pending_approvals(self) -> list[dict]:
        return storage.get_applications(status="awaiting_approval")

    def _save_application(self, opportunity: dict, status: str, account: dict) -> dict:
        record = {
            "id": new_id(),
            "opportunity_title": opportunity.get("title", ""),
            "organization": opportunity.get("organization", ""),
            "category": opportunity.get("category", ""),
            "application_url": opportunity.get("application_url", ""),
            "status": status,
            "opportunity_data": opportunity,
            "account_platform": account.get("platform", ""),
            "submitted_at": utcnow_iso() if status == "submitted" else None,
        }
        try:
            return storage.save_application(record)
        except Exception as e:
            logger.error(f"Failed to save application record: {e}")
            return record

    def _find_submit_selector(self, page_text: str) -> str:
        """Heuristic to find submit button selector."""
        if "submit application" in page_text.lower():
            return "button[type=submit], input[type=submit], button:contains('Submit')"
        if "apply now" in page_text.lower():
            return "a:contains('Apply Now'), button:contains('Apply')"
        return "button[type=submit]"

    def _encode_pdf(self, pdf_bytes: Optional[bytes]) -> Optional[str]:
        if not pdf_bytes:
            return None
        import base64
        return base64.b64encode(pdf_bytes).decode()


# Singleton
application_engine = ApplicationEngine()
