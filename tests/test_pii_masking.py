"""test_pii_masking.py

Unit tests for PII masking (Microsoft Presidio) and entity whitelisting rules.
Verifies phone numbers, personal emails, and bank details are masked before AI calls,
while shipper, consignee, and notify party are strictly preserved.
"""
import pytest
from backend.security.pii import PIIMasker, get_pii_masker
from backend.contracts import ExtractedField
from backend.extract.ai import AiExtractor
from backend.classify import EmailInput, classify_email, ClassificationSchema
from backend.translate import translate_texts


@pytest.fixture
def masker() -> PIIMasker:
    return get_pii_masker()


class TestPIIMaskingBasics:
    def test_masks_phone_numbers(self, masker: PIIMasker):
        text = "Please call our manager at +60 12-345 6789 or office 03-7721 8899 for updates."
        masked = masker.mask_text(text)
        assert "<PHONE_NUMBER>" in masked
        assert "+60 12-345 6789" not in masked
        assert "03-7721 8899" not in masked

    def test_masks_personal_emails(self, masker: PIIMasker):
        text = "Contact logistics officer at john.smith@gmail.com or personal assistant at jane_doe@yahoo.com."
        masked = masker.mask_text(text)
        assert "<EMAIL_ADDRESS>" in masked
        assert "john.smith@gmail.com" not in masked
        assert "jane_doe@yahoo.com" not in masked

    def test_masks_bank_details(self, masker: PIIMasker):
        text = (
            "Remit freight charges to Account No: 1234-5678-9012, "
            "IBAN: GB29NWBK60161331926819, SWIFT: CITIUS33."
        )
        masked = masker.mask_text(text)
        assert "<BANK_DETAILS>" in masked
        assert "GB29NWBK60161331926819" not in masked
        assert "1234-5678-9012" not in masked


class TestLogisticsEntityPreservation:
    def test_preserves_shipper_consignee_notify_party(self, masker: PIIMasker):
        text = """
Shipper: ACME TRADING CORP | 123 HARBOUR ROAD, PENANG
Consignee: PACIFIC FREIGHT SERVICES B.V. | ROTTERDAM
Notify Party: ALLIANCE FORWARDING LTD | SINGAPORE
Port of Loading: PORT KLANG
Port of Discharge: ROTTERDAM
Container: MSCU1234567
Gross Weight: 24,500 KG
"""
        masked = masker.mask_text(text, preserve_logistics_entities=True)
        assert "ACME TRADING CORP" in masked
        assert "PACIFIC FREIGHT SERVICES B.V." in masked
        assert "ALLIANCE FORWARDING LTD" in masked
        assert "PORT KLANG" in masked
        assert "ROTTERDAM" in masked
        assert "MSCU1234567" in masked
        assert "24,500 KG" in masked

    def test_masks_pii_in_remarks_while_preserving_parties(self, masker: PIIMasker):
        text = """Shipper: ORIENT OVERSEAS CO | SHANGHAI
Consignee: GLOBAL IMPORT GMBH | HAMBURG
Notify Party: HANSEATIC LOGISTICS | HAMBURG
Remarks: Driver phone +60 19-876 5432, email driver@gmail.com. Account No: 8877665544."""
        masked = masker.mask_text(text, preserve_logistics_entities=True)
        assert "ORIENT OVERSEAS CO" in masked
        assert "GLOBAL IMPORT GMBH" in masked
        assert "HANSEATIC LOGISTICS" in masked
        assert "<PHONE_NUMBER>" in masked
        assert "<EMAIL_ADDRESS>" in masked
        assert "<BANK_DETAILS>" in masked


class TestReversibleMaskingForTranslation:
    def test_reversible_anonymization_and_restoration(self, masker: PIIMasker):
        original = (
            "Please call +60 12-345 6789 or email test.user@gmail.com "
            "for payment to IBAN: GB29NWBK60161331926819."
        )
        anon_text, pii_map = masker.anonymize_reversible(original)
        assert "+60 12-345 6789" not in anon_text
        assert "test.user@gmail.com" not in anon_text
        assert "GB29NWBK60161331926819" not in anon_text
        assert len(pii_map) >= 3

        # Restore
        restored = masker.deanonymize(anon_text, pii_map)
        assert restored == original


import asyncio

class TestClassifierPIIIntegration:
    def test_classify_masks_metadata_and_body_before_prompt(self):
        recorded_prompts = []

        def mock_model(prompt: str) -> ClassificationSchema:
            recorded_prompts.append(prompt)
            return ClassificationSchema(
                category="SI_REQUEST",
                confidence_tier="1.0",
                evidence="shipping instruction attached",
            )

        email = EmailInput(
            email_id="test_001",
            from_email="john.smith@gmail.com",
            subject="Urgent: Call +60 12-999 8888 for SI",
            body="Hi team, please find attached SI. Bank A/C No: 12345678. Contact me at john.smith@gmail.com.",
            attachments=["SI.pdf"],
        )

        result = asyncio.run(classify_email(email, model=mock_model))
        assert result.category == "SI_REQUEST"
        assert len(recorded_prompts) == 1
        sent_prompt = recorded_prompts[0]

        # Verify prompt received by AI does not contain real PII
        assert "john.smith@gmail.com" not in sent_prompt
        assert "+60 12-999 8888" not in sent_prompt
        assert "12345678" not in sent_prompt
        assert "<PERSONAL_EMAIL>" in sent_prompt or "<EMAIL_ADDRESS>" in sent_prompt
        assert "<PHONE_NUMBER>" in sent_prompt
        assert "<BANK_DETAILS>" in sent_prompt


class TestExtractorPIIIntegration:
    def test_extractor_masks_unrelated_pii_while_extracting(self):
        recorded_texts = []

        def mock_model(text: str) -> dict[str, ExtractedField]:
            recorded_texts.append(text)
            return {
                "shipper": {"present": True, "label_seen": "Shipper", "raw": "ACME CORP"},
                "consignee": {"present": True, "label_seen": "Consignee", "raw": "PACIFIC LTD"},
                "notify_party": {"present": False, "label_seen": None, "raw": None},
                "port_of_loading": {"present": False, "label_seen": None, "raw": None},
                "port_of_discharge": {"present": False, "label_seen": None, "raw": None},
                "container_count": {"present": False, "label_seen": None, "raw": None},
                "gross_weight_kg": {"present": False, "label_seen": None, "raw": None},
            }

        pairs = [
            ("Shipper", "ACME CORP | PENANG"),
            ("Consignee", "PACIFIC LTD | SINGAPORE"),
            ("Remarks", "Contact +60 12-345 6789 or Account 1234-5678"),
        ]

        extractor = AiExtractor(mock_model)
        fields = extractor.extract_fields("email_999", pairs)

        assert len(recorded_texts) == 1
        prompt_text = recorded_texts[0]
        # Verify AI prompt does not have raw phone or account
        assert "+60 12-345 6789" not in prompt_text
        assert "1234-5678" not in prompt_text
        assert "ACME CORP" in prompt_text
        assert "PACIFIC LTD" in prompt_text
        assert fields["shipper"]["raw"] == "ACME CORP"


class TestTranslatePIIIntegration:
    def test_translate_reversibly_restores_pii(self):
        def mock_post(url: str, headers: dict, body: dict) -> dict:
            # Model echoes back text with translated keywords but keeps tokens
            user_content = body["messages"][0]["content"]
            # Extract json inside prompt
            json_part = user_content[user_content.find("{") : user_content.rfind("}") + 1]
            return {"content": [{"type": "text", "text": json_part}]}

        texts = {
            "email_body": "Please contact +60 12-345 6789 or email user@gmail.com for details."
        }
        result = translate_texts(texts, target="Malay", post=mock_post)
        # Verify real values are restored in final output
        assert "+60 12-345 6789" in result["email_body"]
        assert "user@gmail.com" in result["email_body"]
