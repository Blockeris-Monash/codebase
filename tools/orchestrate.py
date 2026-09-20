import os
import re
import asyncio
from typing import Dict, List, Any, Optional
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

# Import Milk's extractor
from google import genai
from google.genai import types

# Import JJ's deterministic comparator
from comparator import compare_documents, ComparisonReport

load_dotenv()
app = FastAPI()
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

SENTINEL = re.compile(r"^\s*$|^(n/?a|tba|tbc|-+)$|^_+\s*\w*$", re.I)

# ==========================================
# 1. Input/Output Models
# ==========================================
class PairedInput(BaseModel):
    email_id: str
    si_pairs: List[tuple[str, str]]
    bl_pairs: List[tuple[str, str]]

class ExtractedField(BaseModel):
    present: bool
    label_seen: Optional[str] = None
    raw: Optional[str] = None

class ModelFields(BaseModel):
    shipper: ExtractedField
    consignee: ExtractedField
    notify_party: ExtractedField
    port_of_loading: ExtractedField
    port_of_discharge: ExtractedField
    container_count: ExtractedField
    gross_weight_kg: ExtractedField

# ==========================================
# 2. Milk's AI Extractor (Adapted for Async FastAPI)
# ==========================================
PROMPT = """You extract fields from one shipping document (a Shipping Instruction or a Bill of Lading), given as lines of "label: value".
Return these 7 fields: shipper, consignee, notify_party, port_of_loading, port_of_discharge, container_count, gross_weight_kg.
For each field return:
present: true if the document gives a real value, false if the field is missing, blank, TBA, TBC, N/A, or only underscores.
label_seen: the label exactly as written. null if not present.
raw: the value exactly as written, copied character for character. Do not fix, translate, reformat or normalise. null if not present.
DOCUMENT:

"""

def pairs_as_text(pairs: List[tuple[str, str]]) -> str:
    return "\n".join(f"{label}: {value}" for label, value in pairs)

async def extract_fields_async(email_id: str, pairs: List[tuple[str, str]]) -> Dict[str, dict]:
    text = pairs_as_text(pairs)
    try:
        response = await client.aio.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=PROMPT + text,
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=ModelFields,
            ),
        )
        parsed_fields = ModelFields.model_validate_json(response.text)
        return parsed_fields.model_dump()
    except Exception as e:
        print(f"Extraction failed for {email_id}: {e}")
        return {}

# ==========================================
# 3. Hanif's Data Cleaner (Adjusted for JJ)
# ==========================================
def clean_entity(text: str) -> str:
    text = text.upper().strip()
    text = re.sub(r'[.,;:]+$', '', text) 
    text = re.sub(r'\s+', ' ', text)     
    return text

def clean_port(text: str) -> str:
    text_no_locode = re.sub(r'\s*\(\s*[A-Z]{5}\s*\)', '', text.upper())
    return clean_entity(text_no_locode)

def clean_containers(text: str) -> str:
    text = text.upper().strip()
    return re.sub(r'\s*X\s*', ' x ', text) 

def clean_weight(text: str) -> str:
    text_upper = text.upper()
    is_mt = "MT" in text_upper or "M/T" in text_upper
    numeric_str = re.sub(r'[^\d.]', '', text)
    if not numeric_str: return ""
    try:
        weight_val = float(numeric_str)
        if is_mt: weight_val *= 1000
        # JJ expects a float string like "135126.0" for his math tolerance
        return str(float(weight_val)) 
    except ValueError:
        return text.strip()

def apply_cleaner(fields: Dict[str, dict]) -> Dict[str, dict]:
    cleaned = {}
    for key, field_data in fields.items():
        raw_text = field_data.get("raw")
        present = field_data.get("present", False)
        
        if not present or not raw_text or SENTINEL.match(raw_text.strip()):
            field_data["norm"] = None
        else:
            if key in ["shipper", "consignee", "notify_party"]:
                field_data["norm"] = clean_entity(raw_text)
            elif key in ["port_of_loading", "port_of_discharge"]:
                field_data["norm"] = clean_port(raw_text)
            elif key == "container_count":
                field_data["norm"] = clean_containers(raw_text)
            elif key == "gross_weight_kg":
                field_data["norm"] = clean_weight(raw_text)
            else:
                field_data["norm"] = raw_text.strip()
                
        cleaned[key] = field_data
    return cleaned

# ==========================================
# 4. FastAPI Orchestrator Route
# ==========================================
@app.post("/extract-clean-compare", response_model=ComparisonReport)
async def run_pipeline(payload: PairedInput):
    
    # 1. EXTRACTION: Run Milk's logic on both documents concurrently
    si_task = extract_fields_async(payload.email_id, payload.si_pairs)
    bl_task = extract_fields_async(payload.email_id, payload.bl_pairs)
    
    si_raw_fields, bl_raw_fields = await asyncio.gather(si_task, bl_task)
    
    # 2. CLEANING: Run Hanif's normalizer
    si_cleaned_fields = apply_cleaner(si_raw_fields)
    bl_cleaned_fields = apply_cleaner(bl_raw_fields)
    
    # Format into nodes for JJ's comparator
    si_doc = {"email_id": payload.email_id, "fields": si_cleaned_fields}
    bl_doc = {"email_id": payload.email_id, "fields": bl_cleaned_fields}
    
    # 3. COMPARISON: Run JJ's deterministic engine
    report = compare_documents(si_doc, bl_doc)
    
    return report