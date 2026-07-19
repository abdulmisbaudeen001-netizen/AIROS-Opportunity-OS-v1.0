"""
AIROS Opportunity OS v1.0
Report Generator — converts structured Planner results into clean Telegram messages.
Never receives raw browser or LLM output. Only standardized data.
"""

import logging
from utils import days_until, truncate

logger = logging.getLogger("airos.report")

CATEGORY_ICONS = {
    "job": "💼",
    "scholarship": "🎓",
    "fellowship": "🏅",
    "grant": "💰",
    "competition": "🏆",
    "bootcamp": "💻",
    "accelerator": "🚀",
    "conference": "🎤",
    "research": "🔬",
    "visa": "🌍",
    "other": "📋",
}

PRIORITY_ICONS = {"high": "🔴", "medium": "🟡", "low": "🟢"}
ELIGIBILITY_ICONS = {"eligible": "✅", "possibly_eligible": "⚠️", "not_eligible": "❌"}


class ReportGenerator:

    def opportunity_list(self, opportunities: list[dict], title: str = "Opportunities Found") -> str:
        """Format a ranked list of opportunities for Telegram."""
        if not opportunities:
            return f"📭 *{title}*\n\nNo opportunities found matching your profile."

        lines = [f"📊 *{title}* — Top {len(opportunities)}\n"]

        for i, opp in enumerate(opportunities[:10], 1):
            category = opp.get("category", "other")
            icon = CATEGORY_ICONS.get(category, "📋")
            score = opp.get("score", 0)
            title_text = opp.get("title", "Unknown")
            org = opp.get("organization", "")
            country = opp.get("country", "")
            deadline = opp.get("deadline", "")
            days = opp.get("days_until_deadline")
            eligible = opp.get("eligible", "")
            remote = opp.get("remote", False)
            visa = opp.get("visa_sponsored", False)
            url = opp.get("application_url", "")

            entry = [f"{i}. {icon} *{self._esc(title_text)}*"]
            if org:
                entry.append(f"   🏢 {self._esc(org)}")
            if country:
                loc = country + (" 🌐 Remote" if remote else "")
                entry.append(f"   📍 {self._esc(loc)}")
            if deadline:
                deadline_str = f"📅 {deadline}"
                if days is not None:
                    if days < 0:
                        deadline_str += " _(expired)_"
                    elif days == 0:
                        deadline_str += " ⚡ _TODAY_"
                    elif days <= 3:
                        deadline_str += f" 🔥 _{days}d left_"
                    else:
                        deadline_str += f" _({days}d)_"
                entry.append(f"   {deadline_str}")

            tags = []
            if score:
                tags.append(f"Match: {score}%")
            if eligible:
                tags.append(ELIGIBILITY_ICONS.get(eligible, ""))
            if visa:
                tags.append("Visa ✓")
            if tags:
                entry.append(f"   {' | '.join(t for t in tags if t)}")

            if url:
                entry.append(f"   🔗 [Apply]({url})")

            lines.append("\n".join(entry))
            lines.append("")

        if len(opportunities) > 10:
            lines.append(f"_...and {len(opportunities) - 10} more. Use /status to see all._")

        return "\n".join(lines)

    def single_opportunity(self, opp: dict) -> str:
        """Format a single opportunity in detail."""
        category = opp.get("category", "other")
        icon = CATEGORY_ICONS.get(category, "📋")
        lines = [
            f"{icon} *{self._esc(opp.get('title', 'Unknown'))}*\n",
            f"🏢 *Organization:* {self._esc(opp.get('organization', 'N/A'))}",
            f"📍 *Location:* {self._esc(opp.get('country', 'N/A'))}",
            f"🏷 *Category:* {category.title()}",
        ]
        if opp.get("remote"):
            lines.append("🌐 *Remote:* Yes")
        if opp.get("visa_sponsored"):
            lines.append("✈️ *Visa Sponsored:* Yes")
        if opp.get("salary"):
            lines.append(f"💵 *Salary:* {self._esc(opp['salary'])}")
        if opp.get("funding"):
            lines.append(f"💰 *Funding:* {self._esc(opp['funding'])}")
        if opp.get("deadline"):
            days = opp.get("days_until_deadline")
            d_str = f"📅 *Deadline:* {self._esc(opp['deadline'])}"
            if days is not None:
                d_str += f" _{days}d remaining_"
            lines.append(d_str)
        if opp.get("score"):
            lines.append(f"📊 *Match Score:* {opp['score']}%")
        if opp.get("eligible"):
            lines.append(f"✅ *Eligibility:* {opp['eligible'].replace('_', ' ').title()}")
        if opp.get("eligibility_reason"):
            lines.append(f"_Reason: {self._esc(opp['eligibility_reason'])}_")
        if opp.get("requirements"):
            reqs = opp["requirements"][:5]
            lines.append(f"\n📋 *Requirements:*")
            for r in reqs:
                lines.append(f"  • {self._esc(str(r))}")
        if opp.get("application_url"):
            lines.append(f"\n🔗 [Apply Now]({opp['application_url']})")
        return "\n".join(lines)

    def application_result(self, result_data: dict) -> str:
        """Format an application submission result."""
        status = result_data.get("status", "unknown")
        title = result_data.get("opportunity", "Unknown")
        reason = result_data.get("reason", "")
        url = result_data.get("url", "")

        status_map = {
            "submitted": "✅ *Application Submitted*",
            "awaiting_approval": "⏳ *Awaiting Your Approval*",
            "human_required": "🛑 *Human Action Required*",
            "failed": "❌ *Application Failed*",
            "unknown": "❓ *Result Unknown — Please Verify*",
        }

        lines = [
            status_map.get(status, f"📋 Status: {status}"),
            f"\n*Opportunity:* {self._esc(title)}",
        ]
        if reason:
            lines.append(f"*Reason:* {self._esc(reason)}")
        if url and status in ("awaiting_approval", "human_required"):
            lines.append(f"*URL:* {url}")

        return "\n".join(lines)

    def email_details(self, email_record: dict) -> str:
        """Format a single high-priority email for notification."""
        category = email_record.get("category", "general")
        icon = {
            "interview": "🎤",
            "offer": "🏆",
            "coding_test": "📝",
            "verification": "📧",
            "rejection": "❌",
        }.get(category, "📩")

        lines = [
            f"{icon} *{category.replace('_', ' ').title()}*\n",
            f"*From:* {self._esc(email_record.get('sender_organization', email_record.get('sender', 'Unknown')))}",
            f"*Subject:* {self._esc(email_record.get('subject', '')[:80])}",
            f"*Summary:* {self._esc(email_record.get('summary', ''))}",
        ]
        if email_record.get("deadline"):
            lines.append(f"*Deadline:* {self._esc(email_record['deadline'])}")
        return "\n".join(lines)

    def profile_status(self, profile: dict, completeness: dict) -> str:
        """Format profile status report."""
        personal = profile.get("personal", {})
        name = personal.get("name", "Unknown")
        score = completeness.get("score", 0)
        missing = completeness.get("missing", [])

        bar_filled = int(score / 10)
        bar = "█" * bar_filled + "░" * (10 - bar_filled)

        lines = [
            f"👤 *Profile: {self._esc(name)}*\n",
            f"Completeness: `{bar}` {score}%\n",
        ]
        fields = completeness.get("fields", {})
        for field, done in fields.items():
            icon = "✅" if done else "❌"
            lines.append(f"{icon} {field.replace('_', ' ').title()}")
        if missing:
            lines.append(f"\n⚠️ *Missing:* {', '.join(missing)}")
        return "\n".join(lines)

    def error_report(self, errors: list[dict]) -> str:
        """Format error summary."""
        if not errors:
            return ""
        lines = [f"⚠️ *{len(errors)} Error(s) During Mission*\n"]
        for e in errors[:5]:
            lines.append(f"  • `{self._esc(e.get('module', '?'))}`: {self._esc(str(e.get('error', ''))[:100])}")
        return "\n".join(lines)

    def help_message(self) -> str:
        return (
            "🤖 *AIROS Opportunity OS*\n\n"
            "*Commands:*\n"
            "/mission — Run full opportunity search \\+ apply\n"
            "/search — Search for opportunities only\n"
            "/apply — Apply to queued opportunities\n"
            "/email — Check career email\n"
            "/status — View recent applications\n"
            "/profile — View your profile\n"
            "/report — View last mission report\n"
            "/settings — View current settings\n"
            "/help — Show this message\n\n"
            "_You can also type naturally: 'Find AI scholarships in Germany'_"
        )

    def settings_message(self, mode: str, email: str) -> str:
        return (
            f"⚙️ *Settings*\n\n"
            f"Application Mode: `{mode}`\n"
            f"Career Email: `{self._esc(email or 'Not set')}`\n"
            f"Timezone: `{self._esc('Africa/Lagos')}`"
        )

    def _esc(self, text: str) -> str:
        """Escape MarkdownV2 special characters."""
        import re
        special = r"_*[]()~`>#+-=|{}.!"
        return re.sub(r"([" + re.escape(special) + r"])", r"\\\1", str(text))


# Singleton
report_generator = ReportGenerator()
