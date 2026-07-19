"""
AIROS Opportunity OS v1.0
Planner — the brain. The only module that decides workflows, selects agents,
coordinates execution, and handles retries.
No other module performs orchestration.
"""

import logging
import time
from typing import Optional
from application import application_engine
from config import config
from documents import document_engine
from email_agent import email_agent
from llm import llm
from notification import notifier
from opportunity import opportunity_analyzer
from profile import profile_manager
from prompts import prompts
from ranking import ranking_engine
from report import report_generator
from search import search_engine
from storage import storage
from utils import Result, mission_id, utcnow, safe_json

logger = logging.getLogger("airos.planner")

# Commands that route deterministically without LLM
DETERMINISTIC_COMMANDS = {
    "/mission", "/search", "/apply", "/status",
    "/profile", "/email", "/report", "/help",
    "/settings", "/stop", "/pause", "/resume",
}

# Mission lock — one active mission at a time
_active_mission: Optional[str] = None


class Planner:

    # ── Entry point ───────────────────────────────────────────────────────────

    def handle(self, message: str, chat_id: str) -> None:
        """
        Main entry point. Called by telegram_bot.py for every user message.
        Routes to the correct workflow and sends all replies via notifier.
        """
        notifier.set_chat_id(chat_id)
        message = message.strip()

        # Deterministic routing
        command = message.split()[0].lower() if message.startswith("/") else None

        if command == "/help" or message.lower() in ("help", "?"):
            notifier.plain_message(report_generator.help_message())
            return

        if command == "/settings":
            notifier.plain_message(report_generator.settings_message(
                mode=config.application_mode,
                email=config.email_address,
            ))
            return

        if command == "/profile":
            self._handle_profile_view()
            return

        if command == "/status":
            self._handle_status()
            return

        if command == "/report":
            self._handle_last_report()
            return

        if command == "/email":
            self._handle_email_check()
            return

        if command == "/search":
            intent_params = {"intent": "opportunity_search", "execution": "parallel", "tools": ["search", "ranking"], "params": {}}
            self._run_mission(message, intent_params)
            return

        if command == "/apply":
            self._handle_apply_queue()
            return

        if command == "/mission":
            intent_params = {"intent": "daily_mission", "execution": "sequential", "tools": ["search", "ranking", "opportunity", "documents", "application", "email", "report"], "params": {}}
            self._run_mission(message, intent_params)
            return

        if command in ("/stop", "/pause"):
            notifier.plain_message("⚠️ No active mission to stop.")
            return

        # LLM intent classification for natural language
        intent_params = self._classify_intent(message)
        if not intent_params:
            notifier.plain_message("❓ I couldn't understand that. Try /help to see available commands.")
            return

        self._dispatch(message, intent_params)

    # ── Intent classification ─────────────────────────────────────────────────

    def _classify_intent(self, message: str) -> Optional[dict]:
        result = llm.generate_json(
            prompt=prompts.INTENT_CLASSIFY.format(message=message),
            temperature=0.1,
        )
        if not result or result.get("intent") == "unknown":
            return None
        return result

    def _dispatch(self, message: str, intent: dict) -> None:
        intent_name = intent.get("intent", "unknown")
        logger.info(f"Dispatching intent: {intent_name}")

        dispatch_map = {
            "opportunity_search": lambda: self._run_mission(message, intent),
            "daily_mission": lambda: self._run_mission(message, intent),
            "eligibility_check": lambda: self._run_mission(message, intent),
            "resume_generate": lambda: self._handle_document_request("resume", intent),
            "cover_letter_generate": lambda: self._handle_document_request("cover_letter", intent),
            "sop_generate": lambda: self._handle_document_request("sop", intent),
            "application_submit": lambda: self._handle_apply_queue(),
            "email_review": lambda: self._handle_email_check(),
            "profile_update": lambda: self._handle_profile_update(message),
            "profile_view": lambda: self._handle_profile_view(),
            "status_report": lambda: self._handle_status(),
            "interview_prep": lambda: self._handle_interview_prep(message),
        }

        handler = dispatch_map.get(intent_name)
        if handler:
            handler()
        else:
            notifier.plain_message(f"🤔 I understand you want: _{intent_name}_. This feature is coming soon.")

    # ── Mission execution ─────────────────────────────────────────────────────

    def _run_mission(self, command: str, intent: dict) -> None:
        global _active_mission

        # Mission lock
        if _active_mission:
            notifier.plain_message(
                f"⚠️ A mission is already running (`{_active_mission}`). "
                "Please wait for it to complete."
            )
            return

        mid = mission_id()
        _active_mission = mid
        start_time = time.time()

        try:
            notifier.mission_started(command)
            storage.start_mission(mid, command)

            stats = {
                "jobs_found": 0,
                "scholarships_found": 0,
                "grants_found": 0,
                "other_found": 0,
                "applications_submitted": 0,
                "awaiting_approval": 0,
                "human_required": 0,
                "emails_processed": 0,
                "interviews": 0,
                "offers": 0,
                "errors": 0,
            }
            errors = []

            # ── Step 1: Load profile ──────────────────────────────────────────
            logger.info("[Mission] Loading profile...")
            profile = profile_manager.get_full_profile()
            profile_summary = profile_manager.get_summary()

            if not profile.get("personal"):
                notifier.plain_message(
                    "⚠️ Your profile is empty. Please send your CV first.\n"
                    "Use: _Send me your CV as a PDF or paste it as text._"
                )
                return

            # ── Step 2: Search ────────────────────────────────────────────────
            logger.info("[Mission] Searching for opportunities...")
            raw_results = search_engine.search_all_categories(profile_summary, command)

            if not raw_results:
                notifier.plain_message("📭 No opportunities found in this search. Try again later.")
                return

            # ── Step 3: Parse raw results into opportunity objects ─────────────
            logger.info(f"[Mission] Parsing {len(raw_results)} raw results...")
            opportunities = []
            for raw in raw_results[:30]:  # Cap at 30 to manage API usage
                parse_result = opportunity_analyzer.parse_from_search_result(raw, profile_summary)
                if parse_result.ok():
                    opp = parse_result.data
                    if not opportunity_analyzer.is_duplicate(opp):
                        opportunities.append(opp)
                else:
                    stats["errors"] += 1
                    errors.append({"module": "opportunity", "error": parse_result.error})

            # ── Step 4: Eligibility check ─────────────────────────────────────
            logger.info(f"[Mission] Checking eligibility for {len(opportunities)} opportunities...")
            for opp in opportunities:
                eligibility = opportunity_analyzer.check_eligibility(opp, profile_summary)
                opp.update({
                    "eligible": eligibility.get("eligible", "possibly_eligible"),
                    "eligibility_reason": eligibility.get("reason", ""),
                    "eligibility_score": eligibility.get("score", 50),
                })

            # ── Step 5: Rank and deduplicate ──────────────────────────────────
            logger.info("[Mission] Ranking and deduplicating...")
            opportunities = ranking_engine.run(opportunities, profile_summary)

            # Count by category
            for opp in opportunities:
                cat = opp.get("category", "other")
                if cat == "job":
                    stats["jobs_found"] += 1
                elif cat == "scholarship":
                    stats["scholarships_found"] += 1
                elif cat in ("grant", "fellowship"):
                    stats["grants_found"] += 1
                else:
                    stats["other_found"] += 1

            # Save all ranked opportunities
            for opp in opportunities:
                try:
                    opportunity_analyzer.save(opp, session_id=mid)
                except Exception as e:
                    logger.warning(f"Failed to save opportunity: {e}")

            # ── Step 6: Send opportunity report ───────────────────────────────
            opp_report = report_generator.opportunity_list(opportunities, "Opportunities Found")
            notifier.plain_message(opp_report)

            # ── Step 7: Generate documents and apply ──────────────────────────
            intent_name = intent.get("intent", "")
            if intent_name in ("daily_mission", "application_submit"):
                for opp in opportunities[:5]:  # Top 5 only per mission
                    apply_result = self._process_application(opp, profile, profile_summary, mid, stats, errors)

            # ── Step 8: Email check ───────────────────────────────────────────
            logger.info("[Mission] Checking email...")
            email_result = email_agent.check_inbox(limit=20)
            if email_result.ok():
                email_data = email_result.data
                email_summary = email_agent.get_summary(email_data.get("emails", []))
                stats["emails_processed"] = email_summary.get("total", 0)
                stats["interviews"] = email_summary.get("interviews", 0)
                stats["offers"] = email_summary.get("offers", 0)

                notifier.email_summary(email_summary)

                # Immediate alerts for high-priority emails
                for hp_email in email_agent.get_high_priority(email_data.get("emails", [])):
                    cat = hp_email.get("category", "")
                    org = hp_email.get("sender_organization", "")
                    if cat == "interview":
                        notifier.interview_invitation(org, hp_email.get("summary", ""))
                    elif cat == "offer":
                        notifier.offer_received(org, hp_email.get("summary", ""))
                    elif cat == "verification":
                        notifier.verification_required(org, hp_email.get("subject", ""))
                    elif cat == "coding_test":
                        notifier.assessment_received(org, hp_email.get("summary", ""))
            else:
                stats["errors"] += 1
                errors.append({"module": "email", "error": email_result.error})

            # ── Step 9: Finalize and summary ──────────────────────────────────
            duration = int(time.time() - start_time)
            storage.end_mission(mid, {
                "tasks_completed": sum(v for k, v in stats.items() if k != "errors"),
                "tasks_failed": stats["errors"],
                "summary": stats,
            })

            notifier.mission_summary(
                duration_seconds=duration,
                **{k: v for k, v in stats.items()},
            )

            if errors:
                notifier.plain_message(report_generator.error_report(errors))

        except Exception as exc:
            logger.error(f"Mission {mid} crashed: {exc}", exc_info=True)
            stats["errors"] += 1
            notifier.plain_message(f"❌ Mission encountered a fatal error: {str(exc)[:200]}")
            try:
                storage.end_mission(mid, {"status": "error", "summary": stats})
            except Exception:
                pass
        finally:
            _active_mission = None

    def _process_application(
        self,
        opportunity: dict,
        profile: dict,
        profile_summary: str,
        mission_id: str,
        stats: dict,
        errors: list,
    ) -> None:
        """Generate documents and apply for a single opportunity."""
        opp_title = opportunity.get("title", "Unknown")

        if opportunity.get("eligible") == "not_eligible":
            logger.info(f"Skipping ineligible opportunity: {opp_title}")
            return

        # Determine required documents
        doc_types = opportunity_analyzer.determine_required_documents(opportunity)
        logger.info(f"Generating {doc_types} for: {opp_title}")

        # Generate documents
        doc_results = document_engine.generate_for_opportunity(profile, opportunity, doc_types)
        doc_errors = [dt for dt, r in doc_results.items() if not r.ok()]
        if doc_errors:
            for dt in doc_errors:
                errors.append({"module": "documents", "error": f"Failed to generate {dt} for {opp_title}"})

        # Apply
        apply_result = application_engine.apply(opportunity, profile, doc_results)
        if apply_result.ok():
            status = apply_result.data.get("status", "")
            if status == "submitted":
                stats["applications_submitted"] += 1
                # Send the generated resume as a document
                resume_result = doc_results.get("resume")
                if resume_result and resume_result.ok():
                    notifier.send_document(
                        resume_result.data["pdf"],
                        filename=f"resume_{opp_title[:30].replace(' ', '_')}.pdf",
                        caption=f"Resume for: {opp_title}",
                    )
            elif status == "awaiting_approval":
                stats["awaiting_approval"] += 1
                notifier.approval_required(
                    opportunity_title=opp_title,
                    organization=opportunity.get("organization", ""),
                    url=opportunity.get("application_url", ""),
                    reason=apply_result.data.get("reason", ""),
                )
            elif status == "human_required":
                stats["human_required"] += 1
                notifier.human_checkpoint(
                    opportunity_title=opp_title,
                    checkpoint_type=apply_result.data.get("reason", "Unknown"),
                    url=opportunity.get("application_url", ""),
                )
        else:
            stats["errors"] += 1
            errors.append({"module": "application", "error": f"{opp_title}: {apply_result.error}"})

    # ── Sub-handlers ──────────────────────────────────────────────────────────

    def _handle_email_check(self) -> None:
        notifier.plain_message("📧 Checking your email...")
        result = email_agent.check_inbox(limit=20)
        if not result.ok():
            notifier.plain_message(f"❌ Email check failed: {result.error}")
            return
        email_data = result.data
        summary = email_agent.get_summary(email_data.get("emails", []))
        notifier.email_summary(summary)

        for hp in email_agent.get_high_priority(email_data.get("emails", [])):
            notifier.plain_message(report_generator.email_details(hp))

    def _handle_profile_view(self) -> None:
        profile = profile_manager.get_full_profile()
        completeness = profile_manager.get_completeness()
        msg = report_generator.profile_status(profile, completeness)
        notifier.plain_message(msg)

        if completeness["score"] < 80:
            questions = profile_manager.get_onboarding_questions()
            if questions:
                q_text = "📝 *Profile Questions:*\n\n"
                for q in questions[:3]:
                    q_text += f"• {q.get('question', '')}\n"
                q_text += "\n_Reply with answers to complete your profile._"
                notifier.plain_message(q_text)

    def _handle_status(self) -> None:
        apps = storage.get_applications(limit=10)
        if not apps:
            notifier.plain_message("📭 No applications found yet. Run /mission to get started.")
            return

        lines = [f"📋 *Recent Applications ({len(apps)})*\n"]
        status_icons = {
            "submitted": "✅",
            "awaiting_approval": "⏳",
            "human_required": "🛑",
            "failed": "❌",
            "unknown": "❓",
        }
        for app in apps[:8]:
            icon = status_icons.get(app.get("status", ""), "📋")
            lines.append(f"{icon} {app.get('opportunity_title', 'Unknown')[:40]}")
            lines.append(f"   {app.get('organization', '')} — _{app.get('status', '')}_")
        notifier.plain_message("\n".join(lines))

    def _handle_last_report(self) -> None:
        missions = storage.get_recent_missions(limit=1)
        if not missions:
            notifier.plain_message("📭 No missions recorded yet. Run /mission first.")
            return
        m = missions[0]
        summary = m.get("summary", {})
        started = m.get("started_at", "")
        notifier.plain_message(
            f"📊 *Last Mission Report*\n"
            f"Started: {started[:16]}\n"
            f"Status: {m.get('status', 'unknown')}\n\n"
            f"Jobs: {summary.get('jobs_found', 0)}\n"
            f"Applications: {summary.get('applications_submitted', 0)}\n"
            f"Errors: {summary.get('errors', 0)}"
        )

    def _handle_apply_queue(self) -> None:
        pending = application_engine.get_pending_approvals()
        if not pending:
            notifier.plain_message("📭 No applications waiting for approval.")
            return
        notifier.plain_message(f"⏳ *{len(pending)} application(s) awaiting approval.*\nReply /confirm to submit all, or /status to review.")

    def _handle_document_request(self, doc_type: str, intent: dict) -> None:
        profile = profile_manager.get_full_profile()
        # Use most recent opportunity context if available
        recent_opps = storage.get_opportunities(limit=1)
        opportunity = recent_opps[0] if recent_opps else {}

        notifier.plain_message(f"📝 Generating {doc_type.replace('_', ' ')}...")
        generators = {
            "resume": document_engine.generate_resume,
            "cover_letter": document_engine.generate_cover_letter,
            "sop": document_engine.generate_sop,
        }
        gen = generators.get(doc_type)
        if not gen:
            notifier.plain_message(f"❌ Unknown document type: {doc_type}")
            return

        result = gen(profile, opportunity)
        if result.ok() and result.data.get("pdf"):
            notifier.send_document(
                result.data["pdf"],
                filename=f"{doc_type}.pdf",
                caption=f"Here is your {doc_type.replace('_', ' ').title()}.",
            )
        else:
            notifier.plain_message(f"❌ Failed to generate {doc_type}: {result.error}")

    def _handle_profile_update(self, message: str) -> None:
        # Simple LLM-assisted profile update from natural language
        profile_summary = profile_manager.get_summary()
        update_data = llm.generate_json(
            prompt=(
                f"The user said: '{message}'\n"
                f"Current profile summary: {profile_summary}\n\n"
                "Extract what profile field should be updated and to what value. "
                "Return JSON: {\"field\": \"<field_name>\", \"value\": \"<new_value>\"}"
            ),
            temperature=0.1,
        )
        if update_data and update_data.get("field"):
            result = profile_manager.update_field(update_data["field"], update_data["value"])
            if result.ok():
                notifier.plain_message(f"✅ Profile updated: *{update_data['field']}* → `{update_data['value']}`")
            else:
                notifier.plain_message(f"❌ Profile update failed: {result.error}")
        else:
            notifier.plain_message("❓ I couldn't determine what to update. Please be more specific.")

    def _handle_interview_prep(self, message: str) -> None:
        notifier.plain_message("🎤 Interview preparation coming in a future version. Stay tuned!")


# Singleton
planner = Planner()
