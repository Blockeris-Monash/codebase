"""Write the edge-case emails (task 23, issue #71): python tests/edge_cases/make_cases.py

Real customer mail is not one request, one SI and one BL. Each case here starts
from a clean pair laid out like the corpus (email_001) and changes one thing,
so a failure points at that one thing. Set A is how the email arrives; set B is
what is inside the documents.

The expected result is what a careful person checking the pair should conclude,
decided before running, following docs/01-comparison-rules.md where it rules.
`known_gap` (the verdict) and `category_gap` (the live classifier) are filled in
only after running: a case the system gets wrong is a finding to fix or explain,
never a case to delete, and its expected result is not changed to match.
"""
from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
INBOX, ATTACHMENTS = HERE / "inbox", HERE / "attachments"

CUSTOMER = "willy.situmorang@aprilasia.com"
SUBJECT = "TO CONFIRM DOCS _ 5RSG-00133 _ CALLAO_PERU _ MOORIM SP CO., LTD _ MEDUUD104332"
ASK = "Hi Najiha,\n\nAttached are the SI and draft BL for OC 5RSG-00133. Please check the details and confirm.\n\nBest Regards,\nWilly Situmorang\nShipping Documentation"

# The seven fields as email_001 carries them. Every case edits a copy.
BASE = {
    "shipper": "APRIL FAR EAST (M) SDN BHD",
    "consignee": "MOORIM SP CO., LTD",
    "notify_party": "UAB NOVAKOPA",
    "port_of_loading": "PORT KLANG (WESTPORT), MALAYSIA (MYPKG)",
    "port_of_discharge": "CALLAO, PERU (PECLL)",
    "container_count": "1 x 40'HC",
    "gross_weight_kg": "21,577 KG",
}


def si_text(v: dict[str, str]) -> str:
    return f"""SHIPPING INSTRUCTION
========================================

Shipper/Exporter: {v['shipper']}
  TOWER 2, AVENUE 5, LEVEL 6; BANGSAR SOUTH CITY, NO. 8 JALAN KERINCHI; 59200 KUALA LUMPUR, MALAYSIA
CONSIGNEE: {v['consignee']}
  656, GANGNAM-DAERO, GANGNAM-GU; SEOUL, SOUTH KOREA; T. 82-2-3485-1500
NOTIFY PARTY: {v['notify_party']}
Port of Loading: {v['port_of_loading']}
Discharge Port: {v['port_of_discharge']}
No. of Containers or Packages: {v['container_count']}
Gross Weight (KG): {v['gross_weight_kg']}
Vessel Name: MMSS 2507 V.257087E
Voy. No: 11S
Kinds of Packages; Description of Goods: PAPERONE DIGITAL COPIER PAPER
HS Code: 48025600
Booking Ref: MSDUL0942518196
OC No.: 5RSG-00133
Freight: PREPAID
"""


def bl_text(v: dict[str, str]) -> str:
    return f"""BILL OF LADING (DRAFT)
========================================

SHIPPER: {v['shipper']}
  TOWER 2, AVENUE 5, LEVEL 6; BANGSAR SOUTH CITY, NO. 8 JALAN KERINCHI; 59200 KUALA LUMPUR, MALAYSIA
CONSIGNEE: {v['consignee']}
  656, GANGNAM-DAERO, GANGNAM-GU; SEOUL, SOUTH KOREA; T. 82-2-3485-1500
Notify: {v['notify_party']}
Port of Loading (POL): {v['port_of_loading']}
POD: {v['port_of_discharge']}
Container Count: {v['container_count']}
Gross Wt (kgs): {v['gross_weight_kg']}
Vessel Name: MMSS 2507 V.257087E
Voyage: 11S
Commodity: PAPERONE DIGITAL COPIER PAPER
Bill of Lading No.: MEDUUD104332
Booking Ref: MSDUL0942518196
Freight: PREPAID
"""


def edit(**changes: str) -> dict[str, str]:
    return {**BASE, **changes}


# A 1x1 PNG, the size of a signature logo that rides along on every Outlook email.
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


def encrypted_pdf() -> bytes:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.encrypt(user_password="averis", owner_password="averis")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


OK = {"status": "OK", "review_reason": None, "defect_fields": []}


def mismatch(*fields: str) -> dict:
    return {"status": "MISMATCH", "review_reason": None, "defect_fields": list(fields)}


def review(reason: str | None) -> dict:
    """reason None means any reason will do: what matters is that a person looks."""
    return {"status": "NEEDS_REVIEW", "review_reason": reason, "defect_fields": []}


def case(name, title, category, expected, why, *, subject=SUBJECT, body=ASK,
         sender=CUSTOMER, files=None, known_gap=None, category_gap=None):
    """files: {name: text or bytes}, in the order the email lists them. None means a clean pair.

    `name` (edge_a1) is the label; the email id is given out in number() below."""
    if files is None:
        files = pair(name, BASE, BASE)
    return {"case": name, "set": name.split("_")[1][0].upper(), "title": title,
            "category": category, "expected": expected, "why": why, "known_gap": known_gap,
            "category_gap": category_gap,
            "email": {"from": sender, "subject": subject, "body": body}, "files": files}


def pair(email_id: str, si: dict[str, str], bl: dict[str, str]) -> dict[str, str]:
    return {f"{email_id}_SI.txt": si_text(si), f"{email_id}_BL.txt": bl_text(bl)}


FORWARD_HEADER = ("---------- Forwarded message ---------\nFrom: Willy Situmorang <willy.situmorang@aprilasia.com>\n"
                  "Date: Thu, 24 Sep 2026 at 09:12\nSubject: " + SUBJECT + "\nTo: <docs@forwarder.example>\n\n")
DISCLAIMER = ("CONFIDENTIALITY NOTICE: This email and any attachments are confidential and may be legally "
              "privileged. If you are not the intended recipient, please notify the sender immediately and delete "
              "this email. Any unauthorised use, disclosure, copying or distribution is strictly prohibited. ") * 4

CASES = [
    # --- Set A: how the email arrives ---------------------------------------
    case("edge_a1", "Reply thread, older request for another booking quoted below", "BL_COMPARISON", OK,
         "The newest message asks for the check and both documents are attached; the quoted request is history.",
         subject="RE: RE: FW: " + SUBJECT,
         body="Hi Najiha,\n\nRevised SI and draft BL attached, please check and confirm today.\n\nThanks,\nWilly\n\n"
              "-----Original Message-----\nFrom: Najiha <najiha@forwarder.example>\nSent: Tuesday, 22 September 2026 16:40\n"
              "Subject: RE: FW: Invoice for 5RSG-00099\n\nDear Willy, please find the invoice for booking 5RSG-00099 "
              "and settle by Friday.\n\n> Hi, can you send the invoice for 5RSG-00099?"),
    case("edge_a2", "Forwarded by a colleague", "BL_COMPARISON", OK,
         "The colleague forwards the customer's request unchanged, with both documents.",
         sender="najiha@forwarder.example", subject="FW: " + SUBJECT,
         body="Hi team, pls check below.\n\n" + FORWARD_HEADER + ASK),
    case("edge_a3", "Request only after a long forwarded header and disclaimer", "BL_COMPARISON", OK,
         "The ask sits past the first 1,500 characters; the attachments still say what the email is for.",
         sender="najiha@forwarder.example", subject="FW: " + SUBJECT,
         body="FYI\n\n" + DISCLAIMER + "\n\n" + FORWARD_HEADER + DISCLAIMER + "\n\n" + ASK),
    case("edge_a4", "One-line body", "BL_COMPARISON", OK,
         "SI and draft BL attached and the subject says to confirm the documents.",
         body="pls see attached, tq"),
    case("edge_a5", "Body in Malay", "BL_COMPARISON", OK,
         "Asks to check the attached SI and draft BL, in Malay.",
         body="Salam Najiha,\n\nMohon semak SI dan draf BL yang dilampirkan untuk OC 5RSG-00133 dan sahkan.\n\nTerima kasih,\nWilly"),
    case("edge_a5b", "Body in Chinese", "BL_COMPARISON", OK,
         "Asks to check the attached SI and draft BL, in Chinese.",
         body="Najiha 您好，\n\n请核对附件中 OC 5RSG-00133 的托运单(SI)和提单草稿(BL)，并确认。\n\n谢谢，\nWilly"),
    case("edge_a6", "Signature logos attached next to the SI and BL", "BL_COMPARISON", OK,
         "image001.png and image002.png are the sender's signature, not documents.",
         files={"image001.png": PNG, **pair("edge_a6", BASE, BASE), "image002.png": PNG}),
    case("edge_a7", "Revised draft BL attached next to the first draft", "BL_COMPARISON", OK,
         "The revised BL fixes the consignee; the check is against the latest draft.",
         body="Hi Najiha,\n\nPlease check the SI against the REVISED draft BL attached (consignee corrected).\n\nThanks,\nWilly",
         files={**pair("edge_a7", BASE, edit(consignee="MOORIM PAPER CO., LTD")),
                "edge_a7_BL_REVISED.txt": bl_text(BASE)},
         known_gap="The service takes the first file with _BL. in its name, so the first draft is compared and "
                   "the revised one is ignored: a false mismatch."),
    case("edge_a8", "Two shipments in one email, the second BL wrong", "BL_COMPARISON", review(None),
         "One result cannot say both pairs are fine when the second weight differs; a person must look.",
         body="Hi Najiha,\n\nSI and draft BL for OC 5RSG-00133 and OC 5RSG-00134 attached. Please check both.\n\nThanks,\nWilly",
         files={**pair("edge_a8", BASE, BASE),
                "edge_a8_SI_2.txt": si_text(BASE), "edge_a8_BL_2.txt": bl_text(edit(gross_weight_kg="22,577 KG"))},
         known_gap="Only the first SI and BL pair is read. The second pair, with the wrong weight, is never "
                   "compared and the email shows OK: a missed defect."),
    case("edge_a9", "Amendment request, no documents", "SI_REQUEST", None,
         "Asks to change the shipping instruction; there is nothing to compare.",
         subject="AMENDMENT _ 5RSG-00133 _ CONSIGNEE",
         body="Hi Najiha,\n\nPlease amend the consignee on OC 5RSG-00133 to MOORIM PAPER CO., LTD and send the updated draft BL.\n\nThanks,\nWilly",
         files={},
         category_gap="Qwen says BL_COMPARISON: the prompt rule that a request to send the draft BL is a comparison "
                      "wins over the amendment. It still reaches a person as a missing attachment, but the amendment "
                      "itself is not what they are shown."),
    case("edge_a10", "The same email sent again", "BL_COMPARISON", OK,
         "A resend must give the same answer as the first time (edge_a4).",
         subject="RESEND: " + SUBJECT, body="pls see attached, tq"),
    case("edge_a11", "Out-of-office reply quoting a BL email", "GENERAL", None,
         "An automatic reply asks for nothing.",
         sender="najiha@forwarder.example", subject="Automatic reply: " + SUBJECT,
         body="Thank you for your email. I am out of the office until 30 September with limited access to email. "
              "For urgent matters please contact docs@forwarder.example.\n\n> Attached are the SI and draft BL for OC 5RSG-00133.",
         files={},
         category_gap="Qwen says BL_COMPARISON from the quoted subject and text, so an auto-reply becomes a "
                      "missing-attachment task for staff."),
    case("edge_a12", "Phishing dressed as a draft BL", "SPAM", None,
         "An unknown portal asks for a click and a sign-in to 'view' a BL; nothing is attached.",
         sender="no-reply@bl-docs-portal.example", subject="Your Draft BL MEDUUD104332 is ready to approve",
         body="Your draft Bill of Lading is ready. Click here to view and approve before cut-off: "
              "http://bl-docs-portal.example/login?ref=MEDUUD104332\n\nYou will need to sign in with your email password.",
         files={},
         category_gap="Qwen says BL_COMPARISON: a phishing link asking for an email password is shown to staff as a "
                      "genuine BL task instead of spam."),
    case("edge_a13", "Invoice query quoting a BL number", "INVOICE_QUERY", None,
         "The BL number is a reference; the question is about charges.",
         subject="D&D CHARGES _ INV-2291 _ MEDUUD104332",
         body="Hi team,\n\nPlease explain the detention and demurrage charges on invoice INV-2291 for BL MEDUUD104332. "
              "The container was returned within free time.\n\nThanks,\nWilly",
         files={}),

    # --- Set B: what is inside the documents --------------------------------
    case("edge_b1a", "Consignee differs only in case and spacing", "BL_COMPARISON", OK,
         "Case and spaces are formatting (rules: collapse whitespace, uppercase).",
         files=pair("edge_b1a", BASE, edit(consignee="Moorim  SP Co., Ltd")),
         known_gap="clean_entity treats two spaces as the start of the address and cuts the name there, so 'Moorim  SP Co., Ltd' becomes MOORIM: a false mismatch."),
    case("edge_b1b", "CO., LTD against COMPANY LIMITED", "BL_COMPARISON", mismatch("consignee"),
         "On a title document the legal name as written is the identity; a person confirms (rules: suffix is identity).",
         files=pair("edge_b1b", BASE, edit(consignee="MOORIM SP COMPANY LIMITED"))),
    case("edge_b1c", "M/S in front of the consignee", "BL_COMPARISON", mismatch("consignee"),
         "Exact compare by the rules; a person confirms whether M/S is only a courtesy.",
         files=pair("edge_b1c", BASE, edit(consignee="M/S MOORIM SP CO., LTD"))),
    case("edge_b1d", "Two spaces inside two different names", "BL_COMPARISON", mismatch("consignee"),
         "MOORIM SP and MOORIM PAPER are different companies, however many spaces the template puts in.",
         files=pair("edge_b1d", edit(consignee="MOORIM  SP CO., LTD"), edit(consignee="MOORIM  PAPER CO., LTD")),
         known_gap="Same cause as edge_b1a the other way round: both names are cut to MOORIM and match, so a "
                   "different company passes as OK: a missed defect."),
    case("edge_b2", "Port with a country code against the locode", "BL_COMPARISON", OK,
         "SHANGHAI, CN and SHANGHAI (CNSHA) are the same port.",
         files=pair("edge_b2", edit(port_of_discharge="SHANGHAI, CN"), edit(port_of_discharge="SHANGHAI (CNSHA)"))),
    case("edge_b3a", "Weight with decimals and KGS", "BL_COMPARISON", OK,
         "21,577.00 KGS and 21,577 KG are the same weight.",
         files=pair("edge_b3a", edit(gross_weight_kg="21,577.00 KGS"), BASE)),
    case("edge_b3b", "Weight in tonnes", "BL_COMPARISON", OK,
         "21.577 MT is 21,577 kg.",
         files=pair("edge_b3b", edit(gross_weight_kg="21.577 MT"), BASE)),
    case("edge_b3c", "Weight with a European decimal comma", "BL_COMPARISON", OK,
         "21.577,00 KG is 21,577 kg written the European way.",
         files=pair("edge_b3c", edit(gross_weight_kg="21.577,00 KG"), BASE),
         known_gap="The weight is read as 21.577 kg instead of 21,577 kg: a false mismatch."),
    case("edge_b4", "Container count written out", "BL_COMPARISON", OK,
         "ONE (1) X 40' HIGH CUBE is 1 x 40'HC.",
         files=pair("edge_b4", BASE, edit(container_count="ONE (1) X 40' HIGH CUBE"))),
    case("edge_b5", "TO ORDER against TO THE ORDER OF a bank", "BL_COMPARISON", mismatch("consignee"),
         "A bank-order consignee is a different party from a plain order consignee.",
         files=pair("edge_b5", edit(consignee="TO ORDER"), edit(consignee="TO THE ORDER OF KOOKMIN BANK"))),
    case("edge_b6", "Notify party SAME AS CONSIGNEE against the name", "BL_COMPARISON", mismatch("notify_party"),
         "Same party in meaning, different instruction on the BL; a person confirms.",
         files=pair("edge_b6", edit(notify_party="SAME AS CONSIGNEE"), edit(notify_party="MOORIM SP CO., LTD"))),
    case("edge_b7", "One-letter defect: I against lowercase l", "BL_COMPARISON", mismatch("consignee"),
         "MOORlM is a typo that looks right on screen; it must be caught.",
         files=pair("edge_b7", BASE, edit(consignee="MOORlM SP CO., LTD"))),
    case("edge_b8", "Consignee name split across two lines", "BL_COMPARISON", OK,
         "The name wraps onto the next line in the SI; it is the same name.",
         files=pair("edge_b8", edit(consignee="MOORIM SP\n  CO., LTD"), BASE),
         known_gap="The reader keeps only the first line of a value, so a name wrapped onto the next line is cut to MOORIM SP: a false mismatch."),
    case("edge_b9", "File named SI is actually a BL", "BL_COMPARISON", review("wrong_doc_type"),
         "The filename lies; the document header decides (rules: verify document type first).",
         files={"edge_b9_SI.txt": bl_text(BASE), "edge_b9_BL.txt": bl_text(BASE)}),
    case("edge_b10a", "Empty SI file", "BL_COMPARISON", review("unreadable"),
         "An empty file cannot be checked.",
         files={"edge_b10a_SI.txt": "", "edge_b10a_BL.txt": bl_text(BASE)}),
    case("edge_b10b", "Password-protected PDF", "BL_COMPARISON", review("unreadable"),
         "The file will not open without the password.",
         files={"edge_b10b_SI.pdf": encrypted_pdf(), "edge_b10b_BL.txt": bl_text(BASE)}),
    case("edge_b10c", "SI sent as a photo", "BL_COMPARISON", review("unreadable"),
         "A phone photo of the SI has no text to read.",
         files={"edge_b10c_SI.jpg": PNG, "edge_b10c_BL.txt": bl_text(BASE)}),
]


def number(cases: list[dict], first: int = 901) -> None:
    """email_901 onwards. The contracts only accept email_NNN, and the corpus stops at email_520."""
    for index, c in enumerate(cases, start=first):
        email_id = f"email_{index}"
        c["files"] = {name.replace(c["case"] + "_", email_id + "_", 1): content
                      for name, content in c["files"].items()}
        c["email_id"] = email_id
        c["email"] = {"email_id": email_id, **c["email"],
                      "attachments": [f"attachments/{name}" for name in c["files"]]}


number(CASES)


def main() -> None:
    for folder in (INBOX, ATTACHMENTS):
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)
    expected = []
    for c in CASES:
        (INBOX / f"{c['email_id']}.json").write_text(
            json.dumps(c["email"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        for name, content in c["files"].items():
            target = ATTACHMENTS / name
            if isinstance(content, bytes):
                target.write_bytes(content)
            else:
                target.write_text(content, encoding="utf-8", newline="\n")
        expected.append({k: c[k] for k in ("case", "email_id", "set", "title", "category", "expected", "why",
                                           "known_gap", "category_gap")})
    (HERE / "expected.json").write_text(json.dumps(expected, indent=2, ensure_ascii=False) + "\n",
                                        encoding="utf-8", newline="\n")
    print(f"wrote {len(CASES)} cases to {HERE}")


if __name__ == "__main__":
    main()
