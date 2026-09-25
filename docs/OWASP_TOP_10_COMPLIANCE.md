# OWASP Top 10 for LLM Applications Compliance & PII Masking

This document records the security audit, checklist, and mitigations implemented for **Blockeris Document Discrepancy Orchestration Pipeline** according to the **OWASP Top 10 for Large Language Model Applications (2025/latest standard)** and Enterprise PII protection requirements.

---

## 1. Compliance Checklist & Implementation Summary

| OWASP LLM # | Category | Status | Mitigations Implemented in Codebase |
| :--- | :--- | :---: | :--- |
| **LLM01** | **Prompt Injection** |  **Passed** | • Untrusted email body & metadata isolated in XML boundary tags (`<email_metadata>`, `<email_body>`).<br>• System prompt defense instruction instructing LLM to treat wrapped content as untrusted passive data.<br>• Translation limited to safe targets (`Literal["English", "Malay", "Chinese"]`). |
| **LLM02** | **Sensitive Information Disclosure (PII)** |  **Passed** | • **Microsoft Presidio Integration**: [`backend/security/pii.py`](file:///c:/Users/Rusdy%20Husein/Desktop/MONASH/Hackathon%20Averis/codebase/backend/security/pii.py).<br>• Phone numbers, personal emails, and bank/IBAN/credit card details are masked before sending prompts to Qwen/Gemini.<br>• **Domain Whitelist**: Shipper, Consignee, and Notify Party names/addresses are strictly preserved.<br>• Reversible placeholder mapping for translation (`<PHONE_NUMBER_1>`) restores data in UI without exposing PII to external models. |
| **LLM03** | **Supply Chain Vulnerabilities** |  **Passed** | • Pinned dependencies in [`requirements.txt`](file:///c:/Users/Rusdy%20Husein/Desktop/MONASH/Hackathon%20Averis/codebase/requirements.txt).<br>• API keys loaded strictly via environment variables, never hardcoded in repo. |
| **LLM04** | **Data and Model Poisoning** |  **Passed** | • `is_cache_current()` checks file headers and declared parse status against disk records.<br>• Distrusts filenames; reads internal document headers. |
| **LLM05** | **Improper Output Handling** |  **Passed** | • Strict Pydantic model validation (`ClassificationSchema`, `ModelFields`, `ComparisonResult`).<br>• Output normalization and sanitization before rendering in UI. |
| **LLM06** | **Excessive Agency** |  **Passed** | • LLMs are strictly advisory (classification and field extraction).<br>• Deterministic comparator (`compare()`) makes all discrepancy judgments; ambiguities escalate to human review (`NEEDS_REVIEW`). |
| **LLM07** | **System Prompt Leakage** |  **Passed** | • Structured JSON-only output mode (`response_schema` / `response_mime_type="application/json"`).<br>• Output parser extracts only predefined schema keys. |
| **LLM08** | **Vector and Embedding Weaknesses** |  **N/A** | • No vector databases or dynamic RAG embeddings used in pipeline. |
| **LLM09** | **Misinformation / Hallucination** |  **Passed** | • `keep_only_values_under_their_label()` in [`backend/extract/ai.py`](../backend/extract/ai.py) drops any extracted field whose raw text does not appear whole, under the label the model says it read. |
| **LLM10** | **Unbounded Consumption (DoS)** |  **Passed** | • Maximum character boundaries: `body[:1500]` for triage, `MAX_CHARS = 30000` for translation.<br>• Pydantic validation: `Field(..., max_length=100_000)` on incoming email bodies.<br>• Rate limiting and concurrency semaphores on batch execution. |

---

## 2. PII Masking Architecture

### Protected Entities vs Masked Data
1. **Masked Entities (Before External AI Call)**:
   - **Phone Numbers**: International (`+60...`, `+1...`), local landlines (`03-...`), mobile numbers.
   - **Personal Emails**: Personal webmail providers (`@gmail.com`, `@yahoo.com`, `@hotmail.com`, etc.) and personal mailboxes.
   - **Bank Details**: IBAN numbers, SWIFT/BIC codes, Bank Account numbers, credit cards.
2. **Whitelisted Logistics Entities (Preserved)**:
   - **Shipper**, **Consignee**, **Notify Party** company names and addresses.
   - Ports of Loading/Discharge, container numbers, gross weights, and document reference IDs.

### Translation Reversibility
For the UI Translate feature:
```
Raw Email with PII ---> Reversible Tokenizer ({{PHONE_NUMBER_1}}) ---> LLM Translates Content ---> Placeholder Restorer ---> Clean Translated Output in UI
```
The user sees the real phone number/email translated in the interface, while the AI model never saw the raw PII.
