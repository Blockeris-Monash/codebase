import sys
import os
sys.path.append('.')

from backend.classify import EmailInput
from backend.reply import generate_rag_reply

test_email = EmailInput(
    email_id="test_001",
    from_email="customer@example.com",
    subject="Question about storage fees",
    body="Hi GlobeTrans, I was wondering how many free days I get for storage before you start charging me? And what are the rates?",
    attachments=[]
)

print("----------------------------------------")
print("USER EMAIL:")
print(test_email.body)
print("----------------------------------------")
print("Generating AI Reply from Supabase Context...")
print("----------------------------------------")

reply = generate_rag_reply(test_email, "INVOICE_QUERY")

print("DRAFTED REPLY:")
print(reply)
print("----------------------------------------")
