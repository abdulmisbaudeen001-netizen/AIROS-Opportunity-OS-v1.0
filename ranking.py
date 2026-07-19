"""
AIROS Opportunity OS v1.0
Ranking Engine — scores, deduplicates, and sorts opportunities.
"""

import logging
from llm import llm
from prompts import prompts
from utils import Result

logger = logging.getLogger("airos.ranking")


class RankingEngine:

    def rank(self, opportunities: list[dict], profile_summary: str) -> list[dict]:
        """
        Score each opportunity against the candidate profile.
        Returns opportunities sorted by score descending.
        """
        scored = []
        for opp in opportunities:
            score_data = self._score_opportunity(opp, profile_summary)
            opp["score"] = score_data.get("score", 0)
            opp["score_reasons"] = score_data.get("reasons", [])
            opp["priority"] = score_data.get("priority", "low")
            scored.append(opp)

        scored.sort(key=lambda x: x["score"], reverse=True)
        logger.info(f"Ranked {len(scored)} opportunities. Top score: {scored[0]['score'] if scored else 0}")
        return scored

    def deduplicate(self, opportunities: list[dict]) -> list[dict]:
        """
        Remove duplicate opportunities.
        Priority: official company site > ATS > third-party aggregators.
        Merges duplicate entries, keeping the highest-priority source.
        """
        seen: dict[str, dict] = {}  # hash -> opportunity

        for opp in opportunities:
            h = opp.get("hash", "")
            if not h:
                seen[id(opp)] = opp  # No hash — keep as-is
                continue

            if h not in seen:
                seen[h] = opp
            else:
                # Keep the higher-priority source
                existing = seen[h]
                if self._source_priority(opp) > self._source_priority(existing):
                    seen[h] = opp

        deduped = list(seen.values())
        removed = len(opportunities) - len(deduped)
        if removed:
            logger.info(f"Duplicate detection removed {removed} entries.")
        return deduped

    def filter_by_eligibility(self, opportunities: list[dict]) -> list[dict]:
        """Remove opportunities explicitly marked as not eligible."""
        return [o for o in opportunities if o.get("eligible") != "not_eligible"]

    def filter_expired(self, opportunities: list[dict]) -> list[dict]:
        """Remove expired opportunities."""
        return [o for o in opportunities if o.get("days_until_deadline") != -1 or o.get("days_until_deadline") is None]

    def top_n(self, opportunities: list[dict], n: int = 20) -> list[dict]:
        """Return top N scored opportunities."""
        return opportunities[:n]

    def filter_minimum_score(self, opportunities: list[dict], min_score: int = 40) -> list[dict]:
        """Remove opportunities below minimum match score."""
        return [o for o in opportunities if o.get("score", 0) >= min_score]

    def run(self, opportunities: list[dict], profile_summary: str, min_score: int = 40) -> list[dict]:
        """
        Full pipeline: deduplicate → remove expired → score → filter → top 20.
        """
        logger.info(f"Ranking pipeline: {len(opportunities)} opportunities")
        opps = self.deduplicate(opportunities)
        opps = self.filter_expired(opps)
        opps = self.rank(opps, profile_summary)
        opps = self.filter_by_eligibility(opps)
        opps = self.filter_minimum_score(opps, min_score)
        opps = self.top_n(opps, n=20)
        logger.info(f"Ranking pipeline complete: {len(opps)} opportunities selected")
        return opps

    # ── Internal ───────────────────────────────────────────────────────────────

    def _score_opportunity(self, opportunity: dict, profile_summary: str) -> dict:
        """Score a single opportunity using LLM + rule adjustments."""
        llm_score = llm.generate_json(
            prompt=prompts.RANK_OPPORTUNITY.format(
                profile=profile_summary,
                opportunity=str(opportunity),
            ),
            temperature=0.1,
        )
        if llm_score:
            score = int(llm_score.get("score", 50))
        else:
            # Rule-based fallback
            score = self._rule_based_score(opportunity, profile_summary)
            llm_score = {"score": score, "reasons": ["Scored by rules (LLM unavailable)"], "priority": "medium"}

        # Adjust for deadline urgency
        days = opportunity.get("days_until_deadline")
        if days is not None:
            if days <= 3:
                score = max(score, 70)  # Boost critical deadlines
            elif days < 0:
                score = 0  # Expired

        llm_score["score"] = min(100, max(0, score))
        return llm_score

    def _rule_based_score(self, opportunity: dict, profile_summary: str) -> int:
        """Simple rule-based score when LLM is unavailable."""
        score = 50
        profile_lower = profile_summary.lower()
        opp_text = (
            opportunity.get("title", "") + " " +
            opportunity.get("description", "") + " " +
            " ".join(opportunity.get("requirements", []))
        ).lower()

        # Remote preference
        if "remote" in profile_lower and opportunity.get("remote"):
            score += 10

        # Visa check
        if "visa" in profile_lower and opportunity.get("visa_sponsored"):
            score += 15

        # Funding quality
        if opportunity.get("funding") or opportunity.get("salary"):
            score += 5

        return min(score, 85)

    def _source_priority(self, opportunity: dict) -> int:
        """
        Higher number = higher priority source.
        Official company sites > ATS > aggregators.
        """
        url = (opportunity.get("application_url") or opportunity.get("source") or "").lower()
        aggregators = ["linkedin.com", "indeed.com", "glassdoor.com", "wellfound.com", "reed.co.uk"]
        ats = ["lever.co", "greenhouse.io", "workday.com", "myworkdayjobs.com", "taleo.net", "bamboohr.com"]

        for agg in aggregators:
            if agg in url:
                return 1

        for a in ats:
            if a in url:
                return 2

        return 3  # Direct company site assumed


# Singleton
ranking_engine = RankingEngine()
