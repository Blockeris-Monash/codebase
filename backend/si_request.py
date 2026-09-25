"""An SI request: read the seven fields from the email, then ask for what is missing or
draw a Draft Bill of Lading from them.

The PDF is returned as bytes and never written to the server's disk: nothing sends it
yet (/reply takes no attachment), and a file left behind is a customer's document kept
for no one.
"""
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from backend.classify import EmailInput
from backend.extract.ai import AiExtractor
from backend.extract.fallback import with_fallback
from backend.extract.gemini import api_key as gemini_key, gemini_model
from backend.extract.qwen import qwen_model

# Build the extractor using the same Qwen-first, Gemini-fallback pattern
extractor = AiExtractor(with_fallback(qwen_model, gemini_model, enabled=lambda: bool(gemini_key())), tries=2)

# DejaVu Sans (fonts-dejavu-core 2.37, licence beside it): fpdf2's core fonts are Latin-1
# only, so a curly quote, a dash or an accented name could not be drawn as written.
FONT_DIR = Path(__file__).resolve().parent / "fonts"
FONT = "DejaVuSans"
BOLD = "B"
LINE_MM = 10
LABEL_MM = 50
FULL_WIDTH = 0
NEXT_LINE = {"new_x": XPos.LMARGIN, "new_y": YPos.NEXT}


def new_pdf() -> FPDF:
    pdf = FPDF()
    pdf.add_font(FONT, "", str(FONT_DIR / "DejaVuSans.ttf"))
    pdf.add_font(FONT, BOLD, str(FONT_DIR / "DejaVuSans-Bold.ttf"))
    pdf.add_page()
    return pdf


def generate_pdf(fields: Dict[str, Any]) -> bytes:
    """A Draft BL from the extracted fields, as the bytes of a PDF."""
    pdf = new_pdf()
    pdf.set_font(FONT, BOLD, 16)
    pdf.cell(FULL_WIDTH, LINE_MM, text="DRAFT BILL OF LADING", align="C", **NEXT_LINE)
    pdf.set_font(FONT, size=10)
    pdf.cell(FULL_WIDTH, LINE_MM, text="*** DRAFT FOR CUSTOMER REVIEW ***", align="C", **NEXT_LINE)
    pdf.ln(LINE_MM)

    for key, val in fields.items():
        pdf.set_font(FONT, BOLD, 10)
        pdf.cell(LABEL_MM, LINE_MM, text=f"{key.replace('_', ' ').title()}:")
        pdf.set_font(FONT, size=10)
        pdf.multi_cell(FULL_WIDTH, LINE_MM, text=(val or {}).get("raw") or "", **NEXT_LINE)
        pdf.ln(2)

    pdf.ln(LINE_MM)
    pdf.cell(FULL_WIDTH, LINE_MM, text="Please review all fields carefully. Reply to confirm or request changes.",
             **NEXT_LINE)
    return bytes(pdf.output())


def process_si_request(email: EmailInput) -> Tuple[str, Optional[bytes], Dict[str, Any]]:
    """The drafted reply, the Draft BL PDF when every field is present (else None), and
    the fields the model read from the email body."""
    pairs = [("Email Body", email.body)]
    fields = extractor.extract_fields(email.email_id, pairs)

    if not fields:
        return "Thank you for your email. We had trouble reading the Shipping Instruction. Please resend it.", None, {}

    missing_fields = [name.replace("_", " ").title() for name, data in fields.items() if not data.get("present")]
    if missing_fields:
        reply = f"""Hi,

Thank you for sending your Shipping Instruction.

However, we noticed the following required information is missing from your request:
- {", ".join(missing_fields)}

Could you please provide this information so we can prepare your Draft Bill of Lading?

Best regards,
GlobeTrans Support Team"""
        return reply, None, fields

    reply = """Hi,

Thank you for your Shipping Instruction.

We have prepared your Draft Bill of Lading from these details and will send it to you for review.
Kindly check all details carefully when it arrives and let us know if everything is correct, or if any changes are required.

Best regards,
GlobeTrans Support Team"""

    return reply, generate_pdf(fields), fields
