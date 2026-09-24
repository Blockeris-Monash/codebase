"""pii.py

PII Masking and Data Protection Engine using Microsoft Presidio.
Masks phone numbers, personal emails, and bank details before AI/LLM calls,
while explicitly preserving logistics domain entities (shipper, consignee, notify party).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import spacy
from presidio_analyzer import (
    AnalyzerEngine,
    Pattern,
    PatternRecognizer,
    RecognizerRegistry,
)
from presidio_analyzer.nlp_engine import NerModelConfiguration, SpacyNlpEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

log = logging.getLogger(__name__)

# Personal email provider domains
PERSONAL_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "yahoo.co.uk",
    "yahoo.com.sg",
    "yahoo.com.my",
    "hotmail.com",
    "outlook.com",
    "live.com",
    "msn.com",
    "icloud.com",
    "me.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
    "zoho.com",
    "mail.com",
    "gmx.com",
    "yandex.com",
    "qq.com",
    "163.com",
    "126.com",
}

# Protected logistics labels that must NEVER be masked
PROTECTED_LOGISTICS_LABELS = {
    "shipper",
    "consignee",
    "notify party",
    "notify_party",
    "port of loading",
    "port_of_loading",
    "port of discharge",
    "port_of_discharge",
    "vessel",
    "voyage",
    "container",
    "gross weight",
    "gross_weight_kg",
}


def _create_bank_recognizers() -> List[PatternRecognizer]:
    """Create custom recognizers for banking details, account numbers, and SWIFT codes."""
    # Bank Account pattern (e.g., "Account No: 1234567890", "A/C: 9876-5432-10", "Bank details: ...")
    bank_account_pattern = Pattern(
        name="bank_account_number",
        regex=r"(?i)\b(?:acc(?:ount)?\.?\s*(?:no|num|number)?\.?|a/c\s*(?:no|number)?\.?|bank\s*a/c|routing\s*(?:no|number)?\.?|sort\s*code)\s*[:#-]?\s*([0-9A-Z -]{6,26})\b",
        score=0.85,
    )
    
    # SWIFT / BIC code pattern (8 or 11 alphanumeric characters)
    swift_pattern = Pattern(
        name="swift_bic_code",
        regex=r"(?i)\b(?:swift|bic)(?:\s*(?:code|no|number)?)?\s*[:#-]?\s*([A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\b",
        score=0.90,
    )

    # General Financial Remittance / Wire pattern
    wire_pattern = Pattern(
        name="wire_transfer_details",
        regex=r"(?i)\b(?:remittance|beneficiary\s*acc(?:ount)?|beneficiary\s*bank)\s*[:#-]\s*([^\n\r,;]{4,40})",
        score=0.80,
    )

    return [
        PatternRecognizer(
            supported_entity="BANK_DETAILS",
            patterns=[bank_account_pattern, swift_pattern, wire_pattern],
        ),
    ]


def _create_malaysia_phone_recognizer() -> PatternRecognizer:
    """Recognize regional Southeast Asian and Malaysian phone numbers."""
    phone_pattern = Pattern(
        name="sea_phone_number",
        regex=r"(?i)\b(?:\+?60|0)[ -]?(?:1[0-9][ -]?[0-9]{7,8}|[3-9][ -]?[0-9]{6,8})\b",
        score=0.75,
    )
    return PatternRecognizer(
        supported_entity="PHONE_NUMBER",
        patterns=[phone_pattern],
    )


class PIIMasker:
    """Enterprise-grade PII Masker tailored for shipping operations."""

    def __init__(self) -> None:
        self._init_engine()

    def _init_engine(self) -> None:
        nlp_config = NerModelConfiguration(
            labels_to_ignore=["O"],
            model_to_presidio_entity_mapping={
                "PER": "PERSON",
                "PERSON": "PERSON",
                "ORG": "ORGANIZATION",
            },
            low_confidence_score_multiplier=0.4,
        )
        self.spacy_engine = SpacyNlpEngine(
            models=[{"lang_code": "en", "model_name": "spacy_blank"}],
            ner_model_configuration=nlp_config,
        )
        self.spacy_engine.nlp = {"en": spacy.blank("en")}

        self.registry = RecognizerRegistry()
        self.registry.load_predefined_recognizers(nlp_engine=self.spacy_engine)

        # Add custom recognizers
        for recognizer in _create_bank_recognizers():
            self.registry.add_recognizer(recognizer)
        self.registry.add_recognizer(_create_malaysia_phone_recognizer())

        self.analyzer = AnalyzerEngine(
            nlp_engine=self.spacy_engine,
            registry=self.registry,
            supported_languages=["en"],
        )
        self.anonymizer = AnonymizerEngine()

        self.target_entities = [
            "PHONE_NUMBER",
            "EMAIL_ADDRESS",
            "IBAN_CODE",
            "CREDIT_CARD",
            "BANK_DETAILS",
            "US_BANK_NUMBER",
        ]

    def is_personal_email(self, email_str: str) -> bool:
        """Determines whether an email is from a personal provider or personal mailbox."""
        if not email_str or "@" not in email_str:
            return False
        parts = email_str.strip().lower().split("@")
        if len(parts) != 2:
            return False
        domain = parts[1]
        return domain in PERSONAL_EMAIL_DOMAINS

    def mask_text(
        self,
        text: str,
        preserve_logistics_entities: bool = True,
        custom_whitelist: Optional[Set[str]] = None,
    ) -> str:
        """Masks phone numbers, personal emails, and bank details from text.
        
        Guarantees that Shipper, Consignee, and Notify Party entities are not masked.
        """
        if not text or not text.strip():
            return text

        # Analyze text for PII
        results = self.analyzer.analyze(
            text=text,
            entities=self.target_entities,
            language="en",
        )

        if not results:
            return text

        # Filter out any false positive detections in protected logistics lines
        filtered_results = []
        whitelist = set(custom_whitelist or set())
        for r in results:
            span = text[r.start:r.end].strip()
            # Check if within a protected label context
            if preserve_logistics_entities:
                line_start = text.rfind("\n", 0, r.start)
                line_start = 0 if line_start == -1 else line_start + 1
                line_end = text.find("\n", r.end)
                line_end = len(text) if line_end == -1 else line_end
                line = text[line_start:line_end].lower()

                # If this line is explicitly identifying shipper/consignee/notify party, preserve party name
                is_protected_field = any(
                    line.startswith(f"{lbl}:") or line.startswith(f"{lbl} :")
                    for lbl in PROTECTED_LOGISTICS_LABELS
                )
                if is_protected_field and r.entity_type not in {"BANK_DETAILS", "IBAN_CODE", "CREDIT_CARD"}:
                    # Only mask bank details if found in party lines; preserve party names and addresses
                    continue

            if span.lower() in whitelist:
                continue

            filtered_results.append(r)

        if not filtered_results:
            return text

        # Anonymize using standard placeholders
        anonymized = self.anonymizer.anonymize(
            text=text,
            analyzer_results=filtered_results,
            operators={
                "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "<PHONE_NUMBER>"}),
                "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "<EMAIL_ADDRESS>"}),
                "IBAN_CODE": OperatorConfig("replace", {"new_value": "<BANK_DETAILS>"}),
                "BANK_DETAILS": OperatorConfig("replace", {"new_value": "<BANK_DETAILS>"}),
                "CREDIT_CARD": OperatorConfig("replace", {"new_value": "<BANK_DETAILS>"}),
                "US_BANK_NUMBER": OperatorConfig("replace", {"new_value": "<BANK_DETAILS>"}),
            },
        )
        return anonymized.text

    def mask_email_metadata(
        self,
        from_email: str,
        subject: str,
        body: str,
    ) -> Tuple[str, str, str]:
        """Masks PII across email metadata and body before passing to LLM."""
        masked_from = from_email
        if self.is_personal_email(from_email):
            masked_from = "<PERSONAL_EMAIL>"
        elif "@" in from_email:
            # Mask user mailbox part for privacy while keeping logistics domain
            parts = from_email.split("@")
            masked_from = f"user@{parts[1]}"

        masked_subject = self.mask_text(subject, preserve_logistics_entities=True)
        masked_body = self.mask_text(body, preserve_logistics_entities=True)

        return masked_from, masked_subject, masked_body

    def mask_document_pairs(
        self,
        pairs: List[Tuple[str, str]],
    ) -> List[Tuple[str, str]]:
        """Masks PII in document label/value pairs, safeguarding core party names."""
        masked_pairs: List[Tuple[str, str]] = []
        for label, value in pairs:
            lbl_lower = label.strip().lower()
            # If label is Shipper, Consignee, Notify Party, Gross Weight, Containers, Ports -> keep intact
            if any(lbl_lower.startswith(protected) for protected in PROTECTED_LOGISTICS_LABELS):
                masked_pairs.append((label, value))
            else:
                # Mask remarks, banking notes, contact notes
                masked_val = self.mask_text(value, preserve_logistics_entities=True)
                masked_pairs.append((label, masked_val))
        return masked_pairs

    def anonymize_reversible(self, text: str) -> Tuple[str, Dict[str, str]]:
        """Anonymizes text with numbered tokens (e.g. {{PHONE_1}}) and returns a restoration mapping.
        
        Designed for translation so real phone numbers and emails can be restored after translation.
        """
        if not text or not text.strip():
            return text, {}

        results = self.analyzer.analyze(
            text=text,
            entities=self.target_entities,
            language="en",
        )

        if not results:
            return text, {}

        # Sort results from end to start to avoid offset displacement
        sorted_results = sorted(results, key=lambda x: x.start, reverse=True)
        mapping: Dict[str, str] = {}
        token_counts: Dict[str, int] = {}
        modified = text

        for r in sorted_results:
            entity_type = r.entity_type
            token_counts[entity_type] = token_counts.get(entity_type, 0) + 1
            token = f"{{{{{entity_type}_{token_counts[entity_type]}}}}}"
            original_val = text[r.start:r.end]
            mapping[token] = original_val
            modified = modified[:r.start] + token + modified[r.end:]

        return modified, mapping

    def deanonymize(self, text: str, mapping: Dict[str, str]) -> str:
        """Restores original values for numbered placeholder tokens after translation."""
        if not text or not mapping:
            return text
        result = text
        for token, original in mapping.items():
            result = result.replace(token, original)
        return result


# Singleton instance
_GLOBAL_MASKER: Optional[PIIMasker] = None


def get_pii_masker() -> PIIMasker:
    """Returns the singleton PIIMasker instance."""
    global _GLOBAL_MASKER
    if _GLOBAL_MASKER is None:
        _GLOBAL_MASKER = PIIMasker()
    return _GLOBAL_MASKER


def mask_pii(text: str) -> str:
    """Convenience helper to mask PII in text."""
    return get_pii_masker().mask_text(text)
