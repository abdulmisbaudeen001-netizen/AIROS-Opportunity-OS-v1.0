"""
AIROS Opportunity OS v1.0
Opportunity Analyzer — parses raw search results into standardized opportunity objects
and performs eligibility checks.
"""

import logging
from typing import Optional
from llm import llm
from prompts import prompts
from search import search_engine
from storage import storage
from utils import Result, opportunity_hash, days_until, utcnow_iso

logger = logging.getLogger("airos.opportunity")

OPPORTUNITY_SCHEMA = {
    "id": None,
    "hash": None,
    "title": "",
    "organization": "",
    "country": "",
    "category": "job",
    "deadline": None,
    "salary": None,
    "funding": None,
    "visa_sponsored": False,
    "remote": False,
    "requirements": [],
    "application_url": "",
    "source": "",
    "description": "",
    "score": 0,
    "eligible": None,
    "eligibility_reason": "",
    "days_until_deadline": None,
    "session_id": None,
    "created_at": None,
}


class OpportunityAnalyzer:

    def normalize(self, raw: dict) -> dict:
        """Convert raw search result into a normalized opportunity object."""
        opp = OPPORTUNITY_SCHEMA.copy()
        opp.update({k: v for k, v in raw.items() if k in opp})

        # Compute hash if missing
        if not opp.get("hash"):
            opp["hash"] = opportunity_hash(
                opp.get("title", ""),
                opp.get("organization", ""),
                opp.get("application_url", ""),
            )

        # Compute days until deadline
        if opp.get("deadline"):
            opp["days_until_deadline"] = days_until(str(opp["deadline"]))

        opp["created_at"] = utcnow_iso()
        return opp

    def parse_from_search_result(self, search_result: dict, profile_summary: str) -> Result:
        """
        Parse a raw search result into a structured opportunity.
        Fetches full page content if URL is available.
        """
        url = search_result.get("url", "")
        snippet = search_result.get("snippet", "")
        title = search_result.get("title", "")

        # Try to get full detail from the page
        if url:
            detail_result = search_engine.fetch_opportunity_detail(url)
            if detail_result.ok():
                opp = self.normalize(detail_result.data)
                opp["source"] = url
                return Result.success(opp)

        # Fallback: parse from snippet
        text = f"Title: {title}\nURL: {url}\nDescription: {snippet}"
        parsed = llm.generate_json(
            prompt=prompts.OPPORTUNITY_PARSE.format(text=text),
            temperature=0.1,
        )
        if not parsed:
            return Result.failed(f"Could not parse opportunity: {title}")

        parsed["application_url"] = parsed.get("application_url") or url
        parsed["source"] = url
        opp = self.normalize(parsed)
        return Result.success(opp)

    def check_eligibility(self, opportunity: dict, profile_summary: str) -> dict:
        """
        Check whether the candidate is eligible for an opportunity.
        Returns eligibility dict with status and reasons.
        """
        result = llm.generate_json(
            prompt=prompts.ELIGIBILITY_CHECK.format(
                profile=profile_summary,
                opportunity=str(opportunity),
            ),
            temperature=0.1,
        )
        if not result:
            return {
                "eligible": "possibly_eligible",
                "score": 50,
                "matched_requirements": [],
                "missing_requirements": [],
                "reason": "Eligibility could not be determined.",
                "recommended": True,
            }
        return result

    def determine_required_documents(self, opportunity: dict) -> list[str]:
        """
        Determine which documents are required for this opportunity.
        Returns list of document type strings.
        """
        category = opportunity.get("category", "job")
        description = opportunity.get("description", "").lower()
        requirements = str(opportunity.get("requirements", [])).lower()
        combined = description + " " + requirements

        docs = ["resume"]  # Always needed

        # Cover letter
        if any(w in combined for w in ["cover letter", "motivation letter", "letter of motivation"]):
            docs.append("cover_letter")
        elif category == "job":
            docs.append("cover_letter")  # Default for jobs

        # SOP
        if any(w in combined for w in ["statement of purpose", "sop", "research statement"]):
            docs.append("sop")

        # Personal statement
        if any(w in combined for w in ["personal statement", "essay", "personal essay"]):
            docs.append("personal_statement")

        # Scholarship/fellowship-specific
        if category in ("scholarship", "fellowship", "grant", "research"):
            if "sop" not in docs:
                docs.append("sop")

        # Biography
        if any(w in combined for w in ["biography", "bio", "about yourself"]):
            docs.append("biography")

        return docs

    def is_duplicate(self, opportunity: dict) -> bool:
        """Check if this opportunity already exists in storage."""
        h = opportunity.get("hash", "")
        if not h:
            return False
        return storage.opportunity_exists(h)

    def save(self, opportunity: dict, session_id: Optional[str] = None) -> dict:
        """Persist an opportunity to storage."""
        if session_id:
            opportunity["session_id"] = session_id
        return storage.save_opportunity(opportunity)

    def get_deadline_urgency(self, opportunity: dict) -> str:
        """Return urgency label based on days until deadline."""
        days = opportunity.get("days_until_deadline")
        if days is None:
            return "unknown"
        if days < 0:
            return "expired"
        if days <= 3:
            return "critical"
        if days <= 7:
            return "urgent"
        if days <= 14:
            return "soon"
        return "normal"

    def smart_apply_eligible(self, opportunity: dict) -> tuple[bool, str]:
        """
        Determine if this opportunity qualifies for smart (automatic) application.
        Returns (can_auto_apply, reason_if_not).
        """
        required_docs = self.determine_required_documents(opportunity)
        non_standard = [d for d in required_docs if d not in ("resume", "cover_letter")]

        if non_standard:
            return False, f"Requires non-standard documents: {', '.join(non_standard)}"

        description = opportunity.get("description", "").lower()
        blockers = [
            ("payment", "Application requires payment"),
            ("application fee", "Application fee detected"),
            ("essay question", "Custom essay questions detected"),
            ("research proposal", "Research proposal required"),
        ]
        for keyword, reason in blockers:
            if keyword in description:
                return False, reason

        eligibility = opportunity.get("eligible", "")
        if eligibility == "not_eligible":
            return False, "Candidate is not eligible"

        return True, ""


# Singleton
opportunity_analyzer = OpportunityAnalyzer()
