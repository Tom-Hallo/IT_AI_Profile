"""Create local, editable DOCX and searchable PDF from a saved version."""

from io import BytesIO
from pathlib import Path
from unicodedata import normalize
from xml.sax.saxutils import escape

from docx import Document
from docx.shared import RGBColor
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.modules.cv_studio.schemas import VersionDetail

FONT = "CVStudioDejaVu"
CV_FONT = TTFont(FONT, str(Path(__file__).with_name("fonts") / "DejaVuSans.ttf"))
pdfmetrics.registerFont(CV_FONT)


class PDFCharacterError(ValueError):
    """A glyph is unavailable in the embedded PDF font."""


PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def export_cv(version: VersionDetail, format_: str) -> tuple[bytes, str]:
    lines = [line.text for line in version.lines if line.source.type != "missing"]
    output = BytesIO()
    technical = version.template == "technical"
    accent = "215368" if technical else "222222"
    if format_ == "docx":
        document = Document()
        title = document.add_heading(version.title, 0)
        title.runs[0].font.color.rgb = RGBColor.from_string(accent)
        style = "No Spacing" if technical else "Normal"
        for text in lines:
            document.add_paragraph(text, style=style)
        document.save(output)
        return output.getvalue(), DOCX

    title = normalize("NFC", version.title)
    lines = [normalize("NFC", line) for line in lines]
    if any(
        not char.isspace() and ord(char) not in CV_FONT.face.charToGlyph
        for text in [title, *lines]
        for char in text
    ):
        raise PDFCharacterError

    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        title=title,
        author="",
        leftMargin=50,
        rightMargin=50,
        topMargin=48,
        bottomMargin=48,
    )
    heading = ParagraphStyle(
        "Title",
        fontName=FONT,
        fontSize=20,
        leading=27,
        textColor=HexColor(f"#{accent}"),
        spaceAfter=18,
    )
    body = ParagraphStyle(
        "Body",
        fontName=FONT,
        fontSize=10,
        leading=15,
        spaceAfter=4 if technical else 8,
    )
    blocks = [Paragraph(escape(title), heading)]
    for text in lines:
        blocks.append(Paragraph(escape(text), body) if text.strip() else Spacer(1, 8))
    document.build(blocks)
    return output.getvalue(), PDF
