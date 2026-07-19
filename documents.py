"""
AIROS Opportunity OS v1.0
Document Engine — generates professional application documents.
Provider-abstracted: swap the renderer without changing callers.
"""

import io
import logging
from typing import Optional
from llm import llm
from prompts import prompts
from storage import storage
from utils import Result, utcnow_iso

logger = logging.getLogger("airos.documents")


# ── PDF Renderer ──────────────────────────────────────────────────────────────

class PDFRenderer:
    """
    Default document renderer using ReportLab.
    Produces ATS-friendly, professional PDFs from structured JSON.
    """

    def render_resume(self, data: dict, candidate_name: str = "") -> bytes:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
        from reportlab.lib.enums import TA_LEFT, TA_CENTER

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=1.8*cm, rightMargin=1.8*cm,
            topMargin=1.5*cm, bottomMargin=1.5*cm,
        )
        styles = getSampleStyleSheet()
        story = []

        # Styles
        name_style = ParagraphStyle("Name", fontSize=20, fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=4)
        section_style = ParagraphStyle("Section", fontSize=11, fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#2C3E50"))
        body_style = ParagraphStyle("Body", fontSize=9.5, fontName="Helvetica", leading=14, spaceAfter=2)
        bullet_style = ParagraphStyle("Bullet", fontSize=9.5, fontName="Helvetica", leading=14, leftIndent=12, spaceAfter=1)
        sub_style = ParagraphStyle("Sub", fontSize=9.5, fontName="Helvetica-Bold", spaceAfter=1)

        # Header
        story.append(Paragraph(candidate_name or "Candidate", name_style))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2C3E50")))
        story.append(Spacer(1, 6))

        # Summary
        if data.get("summary"):
            story.append(Paragraph("PROFESSIONAL SUMMARY", section_style))
            story.append(Paragraph(data["summary"], body_style))
            story.append(Spacer(1, 4))

        # Skills
        if data.get("skills"):
            story.append(Paragraph("SKILLS", section_style))
            skills_text = " • ".join(data["skills"])
            story.append(Paragraph(skills_text, body_style))
            story.append(Spacer(1, 4))

        # Experience
        if data.get("experience"):
            story.append(Paragraph("EXPERIENCE", section_style))
            for exp in data["experience"]:
                story.append(Paragraph(f"{exp.get('title', '')} — {exp.get('company', '')}", sub_style))
                story.append(Paragraph(exp.get("period", ""), body_style))
                for bullet in exp.get("bullets", []):
                    story.append(Paragraph(f"• {bullet}", bullet_style))
                story.append(Spacer(1, 4))

        # Education
        if data.get("education"):
            story.append(Paragraph("EDUCATION", section_style))
            for edu in data["education"]:
                story.append(Paragraph(f"{edu.get('degree', '')} — {edu.get('institution', '')}", sub_style))
                details = " | ".join(filter(None, [edu.get("year", ""), edu.get("details", "")]))
                if details:
                    story.append(Paragraph(details, body_style))
            story.append(Spacer(1, 4))

        # Projects
        if data.get("projects"):
            story.append(Paragraph("PROJECTS", section_style))
            for proj in data["projects"]:
                tech = ", ".join(proj.get("technologies", []))
                title = proj.get("name", "")
                if tech:
                    title += f" [{tech}]"
                story.append(Paragraph(title, sub_style))
                story.append(Paragraph(proj.get("description", ""), body_style))

        # Certifications
        if data.get("certifications"):
            story.append(Paragraph("CERTIFICATIONS", section_style))
            for cert in data["certifications"]:
                story.append(Paragraph(f"• {cert}", bullet_style))

        doc.build(story)
        return buffer.getvalue()

    def render_letter(self, data: dict) -> bytes:
        """Render a cover letter / motivation letter / SOP as PDF."""
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.enums import TA_JUSTIFY

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=2.5*cm, rightMargin=2.5*cm,
            topMargin=2.5*cm, bottomMargin=2.5*cm,
        )
        body_style = ParagraphStyle("Body", fontSize=10.5, fontName="Helvetica", leading=16, alignment=TA_JUSTIFY, spaceAfter=8)
        meta_style = ParagraphStyle("Meta", fontSize=10.5, fontName="Helvetica", spaceAfter=4)
        story = []

        if data.get("salutation"):
            story.append(Paragraph(data["salutation"], meta_style))
            story.append(Spacer(1, 8))

        body = data.get("body", "")
        for para in body.split("\n\n"):
            para = para.strip()
            if para:
                story.append(Paragraph(para, body_style))

        if data.get("closing"):
            story.append(Spacer(1, 12))
            story.append(Paragraph(data["closing"], meta_style))

        doc.build(story)
        return buffer.getvalue()


# ── Document Engine ───────────────────────────────────────────────────────────

class DocumentEngine:
    """
    Provider-abstracted document generation engine.
    Default: LLM → structured JSON → PDFRenderer → PDF bytes.
    """

    def __init__(self):
        self._renderer = PDFRenderer()

    def generate_resume(self, profile: dict, opportunity: dict) -> Result:
        profile_str = str(profile)
        opp_str = str(opportunity)
        name = profile.get("personal", {}).get("name", "Candidate")

        data = llm.generate_json(
            prompt=prompts.RESUME_GENERATE.format(profile=profile_str, opportunity=opp_str),
            temperature=0.3,
            max_tokens=4096,
        )
        if not data:
            return Result.failed("LLM failed to generate resume content.")

        try:
            pdf_bytes = self._renderer.render_resume(data, candidate_name=name)
        except Exception as e:
            logger.error(f"Resume render failed: {e}")
            return Result.failed(f"PDF render error: {e}")

        record = self._save_document("resume", data, pdf_bytes, opportunity)
        return Result.success({"pdf": pdf_bytes, "content": data, "document_id": record.get("id")})

    def generate_cover_letter(self, profile: dict, opportunity: dict) -> Result:
        data = llm.generate_json(
            prompt=prompts.COVER_LETTER_GENERATE.format(
                profile=str(profile), opportunity=str(opportunity)
            ),
            temperature=0.4,
        )
        if not data:
            return Result.failed("LLM failed to generate cover letter.")

        try:
            pdf_bytes = self._renderer.render_letter(data)
        except Exception as e:
            return Result.failed(f"Cover letter render error: {e}")

        record = self._save_document("cover_letter", data, pdf_bytes, opportunity)
        return Result.success({"pdf": pdf_bytes, "content": data, "document_id": record.get("id")})

    def generate_sop(self, profile: dict, opportunity: dict) -> Result:
        data = llm.generate_json(
            prompt=prompts.SOP_GENERATE.format(
                profile=str(profile), opportunity=str(opportunity)
            ),
            temperature=0.4,
        )
        if not data:
            return Result.failed("LLM failed to generate SOP.")

        try:
            pdf_bytes = self._renderer.render_letter({"body": data.get("body", ""), "salutation": "", "closing": ""})
        except Exception as e:
            return Result.failed(f"SOP render error: {e}")

        record = self._save_document("sop", data, pdf_bytes, opportunity)
        return Result.success({"pdf": pdf_bytes, "content": data, "document_id": record.get("id")})

    def generate_personal_statement(self, profile: dict, opportunity: dict) -> Result:
        data = llm.generate_json(
            prompt=prompts.PERSONAL_STATEMENT_GENERATE.format(
                profile=str(profile), opportunity=str(opportunity)
            ),
            temperature=0.4,
        )
        if not data:
            return Result.failed("LLM failed to generate personal statement.")

        try:
            pdf_bytes = self._renderer.render_letter({"body": data.get("body", ""), "salutation": "", "closing": ""})
        except Exception as e:
            return Result.failed(f"Personal statement render error: {e}")

        record = self._save_document("personal_statement", data, pdf_bytes, opportunity)
        return Result.success({"pdf": pdf_bytes, "content": data, "document_id": record.get("id")})

    def generate_motivation_letter(self, profile: dict, opportunity: dict) -> Result:
        data = llm.generate_json(
            prompt=prompts.MOTIVATION_LETTER_GENERATE.format(
                profile=str(profile), opportunity=str(opportunity)
            ),
            temperature=0.4,
        )
        if not data:
            return Result.failed("LLM failed to generate motivation letter.")

        try:
            pdf_bytes = self._renderer.render_letter(data)
        except Exception as e:
            return Result.failed(f"Motivation letter render error: {e}")

        record = self._save_document("motivation_letter", data, pdf_bytes, opportunity)
        return Result.success({"pdf": pdf_bytes, "content": data, "document_id": record.get("id")})

    def generate_biography(self, profile: dict) -> Result:
        data = llm.generate_json(
            prompt=prompts.BIOGRAPHY_GENERATE.format(profile=str(profile)),
            temperature=0.4,
        )
        if not data:
            return Result.failed("LLM failed to generate biography.")

        record = self._save_document("biography", data, None, {})
        return Result.success({"content": data, "document_id": record.get("id")})

    def generate_for_opportunity(self, profile: dict, opportunity: dict, doc_types: list[str]) -> dict[str, Result]:
        """Generate all required documents for a specific opportunity."""
        results = {}
        generators = {
            "resume": self.generate_resume,
            "cover_letter": self.generate_cover_letter,
            "sop": self.generate_sop,
            "personal_statement": self.generate_personal_statement,
            "motivation_letter": self.generate_motivation_letter,
            "biography": lambda p, o: self.generate_biography(p),
        }
        for doc_type in doc_types:
            generator = generators.get(doc_type)
            if generator:
                logger.info(f"Generating {doc_type} for {opportunity.get('title', 'Unknown')}")
                results[doc_type] = generator(profile, opportunity)
            else:
                logger.warning(f"Unknown document type: {doc_type}")
                results[doc_type] = Result.failed(f"Unknown document type: {doc_type}")
        return results

    def _save_document(self, doc_type: str, content: dict, pdf_bytes: Optional[bytes], opportunity: dict) -> dict:
        """Persist document metadata to storage."""
        import base64
        record = {
            "type": doc_type,
            "content": content,
            "opportunity_title": opportunity.get("title", ""),
            "opportunity_id": opportunity.get("id"),
            "pdf_b64": base64.b64encode(pdf_bytes).decode() if pdf_bytes else None,
        }
        try:
            return storage.save_document(record)
        except Exception as e:
            logger.error(f"Failed to save document record: {e}")
            return {}


# Singleton
document_engine = DocumentEngine()
