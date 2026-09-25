import os
import re
from pathlib import Path
from fpdf import FPDF
from typing import Dict, Any, Tuple
from backend.extract.ai import AiExtractor
from backend.extract.qwen import qwen_model
from backend.extract.gemini import gemini_model, api_key as gemini_key
from backend.extract.fallback import with_fallback
from backend.classify import EmailInput

# Build the extractor using the same Qwen-first, Gemini-fallback pattern
extractor = AiExtractor(with_fallback(qwen_model, gemini_model, enabled=lambda: bool(gemini_key())), tries=2)

RESULTS_DIR = Path("results/generated_bls")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# fpdf2's core fonts cover Latin-1 only, and a curly quote or a dash raised out of the
# whole /process-email call as a 500 (#147). Common punctuation is swapped for its plain
# form; anything else outside Latin-1 becomes "?", which the reviewer sees in the PDF.
PLAIN_PUNCTUATION = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
                                   "\u2013": "-", "\u2014": "-", "\u2026": "...", "\u00a0": " "})
# The email id becomes a file name: "../x" or an absolute id used to write outside RESULTS_DIR.
UNSAFE_FILE_CHARACTERS = re.compile(r"[^A-Za-z0-9_-]")


def pdf_text(text: str) -> str:
    """Text the PDF's font can draw."""
    return text.translate(PLAIN_PUNCTUATION).encode("latin-1", "replace").decode("latin-1")


def pdf_name(email_id: str) -> str:
    return UNSAFE_FILE_CHARACTERS.sub("_", Path(email_id).name)[:100] or "email"


def generate_pdf(fields: Dict[str, Any], email_id: str) -> str:
    """Generates a PDF Draft BL from extracted fields and returns the file path."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    # Header
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="DRAFT BILL OF LADING", ln=True, align='C')
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 10, txt="*** DRAFT FOR CUSTOMER REVIEW ***", ln=True, align='C')
    pdf.ln(10)
    
    # Body
    pdf.set_font("Arial", 'B', 12)
    
    for key, val in fields.items():
        pdf.set_font("Arial", 'B', 10)
        label = key.replace('_', ' ').title()
        pdf.cell(50, 10, txt=f"{label}:", ln=False)
        pdf.set_font("Arial", '', 10)
        
        # Handle multiline text like shipper/consignee nicely
        raw_text = val.get("raw", "") if val else ""
        if raw_text is None:
            raw_text = ""
            
        # Basic sanitization to mitigate LLM05 (Improper Output Handling) before injecting to PDF
        raw_text = raw_text.replace("<script>", "").replace("</script>", "")
        
        # Use multi_cell for wrapping long text
        pdf.multi_cell(0, 10, txt=pdf_text(raw_text))
        pdf.ln(2)

    pdf.ln(10)
    pdf.set_font("Arial", 'I', 10)
    pdf.cell(200, 10, txt="Please review all fields carefully. Reply to confirm or request changes.", ln=True)
    
    output_path = RESULTS_DIR / f"{pdf_name(email_id)}_Draft_BL.pdf"
    pdf.output(str(output_path))
    return str(output_path)

def process_si_request(email: EmailInput) -> Tuple[str, str, Dict[str, Any]]:
    """
    Extracts fields from an SI request email. 
    Checks if all 7 fields are present.
    If missing -> drafts email asking for them.
    If present -> drafts email with PDF attached (saved to disk).
    Returns: (draft_reply, pdf_path, extracted_fields)
    """
    # 1. Extract the text (treat the whole email body as the document)
    pairs = [("Email Body", email.body)]
    fields = extractor.extract_fields(email.email_id, pairs)
    
    if not fields:
        return "Thank you for your email. We had trouble reading the Shipping Instruction. Please resend it.", "", {}

    # 2. Check for missing fields
    missing_fields = []
    for field_name, data in fields.items():
        if not data.get("present"):
            missing_fields.append(field_name.replace('_', ' ').title())

    if missing_fields:
        missing_list = ", ".join(missing_fields)
        reply = f"""Hi,

Thank you for sending your Shipping Instruction. 

However, we noticed the following required information is missing from your request:
- {missing_list}

Could you please provide this information so we can prepare your Draft Bill of Lading?

Best regards,
GlobeTrans Support Team"""
        return reply, "", fields

    # 3. All fields present -> Generate PDF
    pdf_path = generate_pdf(fields, email.email_id)
    
    reply = f"""Hi,

Thank you for your Shipping Instruction. 

We have prepared your Draft Bill of Lading from these details and will send it to you for review.
Kindly check all details carefully when it arrives and let us know if everything is correct, or if any changes are required.

Best regards,
GlobeTrans Support Team"""

    return reply, pdf_path, fields
