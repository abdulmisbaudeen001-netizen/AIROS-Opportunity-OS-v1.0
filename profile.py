"""
AIROS Opportunity OS v1.0
Profile Manager — maintains the user's structured profile and knowledge base.
The only module that reads/writes profile data in Supabase.
Other agents request profile data through this interface.
"""

import logging
from typing import Any, Optional
from storage import storage
from llm import llm
from prompts import prompts
from utils import Result

logger = logging.getLogger("airos.profile")


class ProfileManager:

    # ── Public interface for other agents ────────────────────────────────────

    def get_full_profile(self) -> dict:
        """Return complete structured profile for use by other agents."""
        profile = storage.get_profile() or {}
        return {
            "personal": profile,
            "experience": storage.get_experiences(),
            "education": storage.get_education(),
            "skills": storage.get_skills(),
            "knowledge": storage.get_knowledge(),
        }

    def get_summary(self) -> str:
        """Return a compact profile summary string for LLM prompts."""
        p = self.get_full_profile()
        personal = p["personal"]
        skills = [s.get("name", "") for s in p["skills"]]
        experience = p["experience"][:3]  # Most recent 3

        lines = [
            f"Name: {personal.get('name', 'Unknown')}",
            f"Location: {personal.get('location', 'Unknown')}",
            f"Skills: {', '.join(skills[:15])}",
            f"Experience roles: {len(p['experience'])}",
            f"Education: {len(p['education'])} qualifications",
            f"Preferences - Remote: {personal.get('remote_preference', 'Yes')}, "
            f"Relocation: {personal.get('relocation_willing', 'Unknown')}, "
            f"Visa: {personal.get('visa_required', 'Unknown')}",
            f"Target salary: {personal.get('salary_expectation', 'Not set')}",
            f"Target countries: {personal.get('preferred_countries', 'Any')}",
        ]
        if experience:
            lines.append("Recent experience:")
            for exp in experience:
                lines.append(f"  - {exp.get('title')} at {exp.get('company')}")
        return "\n".join(lines)

    def get_experience(self, category: Optional[str] = None) -> list[dict]:
        """Return experience records, optionally filtered by category."""
        experiences = storage.get_experiences()
        if category:
            experiences = [e for e in experiences if category.lower() in e.get("description", "").lower()]
        return experiences

    def get_skills_list(self) -> list[str]:
        return [s.get("name", "") for s in storage.get_skills()]

    def get_knowledge_base(self, category: Optional[str] = None) -> list[dict]:
        return storage.get_knowledge(category)

    def get_preferences(self) -> dict:
        profile = storage.get_profile() or {}
        return {
            "remote_preference": profile.get("remote_preference", True),
            "relocation_willing": profile.get("relocation_willing", False),
            "visa_required": profile.get("visa_required", False),
            "salary_expectation": profile.get("salary_expectation"),
            "preferred_countries": profile.get("preferred_countries", []),
            "preferred_categories": profile.get("preferred_categories", []),
        }

    def get_completeness(self) -> dict:
        return storage.get_profile_completeness()

    # ── Onboarding / CV import ────────────────────────────────────────────────

    def import_cv_text(self, cv_text: str) -> Result:
        """Parse raw CV text and populate profile."""
        logger.info("Importing CV via LLM extraction...")
        extracted = llm.generate_json(
            prompt=prompts.CV_EXTRACT.format(cv_text=cv_text),
            temperature=0.1,
        )
        if not extracted:
            return Result.failed("Failed to extract CV data from LLM.")

        # Save personal info
        personal = {k: extracted.get(k) for k in [
            "name", "email", "phone", "location", "bio",
            "linkedin", "github", "portfolio",
        ] if extracted.get(k)}
        if personal:
            storage.upsert_profile(personal)

        # Save experience
        for exp in extracted.get("experience", []):
            if exp.get("title") and exp.get("company"):
                storage.upsert_experience(exp)

        # Save education
        for edu in extracted.get("education", []):
            if edu.get("degree") or edu.get("institution"):
                storage.upsert_education(edu)

        # Save skills
        for skill in extracted.get("skills", []):
            if skill.get("name"):
                storage.upsert_skill(skill)

        # Save certifications as knowledge
        for cert in extracted.get("certifications", []):
            if cert.get("name"):
                storage.save_knowledge({
                    "category": "certification",
                    "content": f"{cert.get('name')} — {cert.get('issuer', '')} ({cert.get('year', '')})",
                })

        # Save projects as knowledge
        for project in extracted.get("projects", []):
            if project.get("name"):
                storage.save_knowledge({
                    "category": "project",
                    "content": f"{project.get('name')}: {project.get('description', '')}",
                    "metadata": {"url": project.get("url"), "technologies": project.get("technologies", [])},
                })

        logger.info("CV import complete.")
        return Result.success({"extracted_fields": list(extracted.keys())})

    def get_onboarding_questions(self) -> list[dict]:
        """Return follow-up questions for missing profile fields."""
        profile_summary = self.get_summary()
        result = llm.generate_json(
            prompt=prompts.PROFILE_QUESTIONS.format(profile=profile_summary),
        )
        if result:
            return result.get("questions", [])
        return []

    # ── Profile updates ───────────────────────────────────────────────────────

    def update_field(self, field: str, value: Any) -> Result:
        """Update a single profile field."""
        try:
            storage.upsert_profile({field: value})
            logger.info(f"Profile field updated: {field}")
            return Result.success()
        except Exception as e:
            logger.error(f"Profile update failed: {e}")
            return Result.failed(str(e))

    def add_experience(self, data: dict) -> Result:
        try:
            storage.upsert_experience(data)
            return Result.success()
        except Exception as e:
            return Result.failed(str(e))

    def add_education(self, data: dict) -> Result:
        try:
            storage.upsert_education(data)
            return Result.success()
        except Exception as e:
            return Result.failed(str(e))

    def add_skill(self, name: str, level: str = "intermediate") -> Result:
        try:
            storage.upsert_skill({"name": name, "level": level})
            return Result.success()
        except Exception as e:
            return Result.failed(str(e))

    def add_knowledge(self, category: str, content: str, metadata: Optional[dict] = None) -> Result:
        try:
            storage.save_knowledge({"category": category, "content": content, "metadata": metadata})
            return Result.success()
        except Exception as e:
            return Result.failed(str(e))

    # ── Completeness report ───────────────────────────────────────────────────

    def format_completeness_report(self) -> str:
        data = self.get_completeness()
        score = data["score"]
        fields = data["fields"]
        missing = data["missing"]

        lines = [f"📊 *Profile Completeness: {score}%*\n"]
        for field, done in fields.items():
            icon = "✅" if done else "❌"
            lines.append(f"{icon} {field.replace('_', ' ').title()}")

        if missing:
            lines.append(f"\n⚠️ Missing: {', '.join(missing)}")
        return "\n".join(lines)


# Singleton
profile_manager = ProfileManager()
