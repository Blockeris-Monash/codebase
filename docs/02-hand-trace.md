# Hand trace — everyone, before you write code

Twenty minutes each. Run from `~/Projects/hackathon` unless a step says
otherwise. The point is not to check my work — it is that you will hit these
traps on day two, and it is cheaper to meet them now.

Everyone does **Common** first. Then your own role's section.

---

## Common — the one email, end to end

```bash
cd ~/Projects/hackathon
cat inbox/email_004.json
cat attachments/email_004_SI.txt
cat attachments/email_004_BL.txt
```

Look for: shipper, both ports, container count, gross weight, vessel and
booking ref all identical. Consignee and notify party changed —
`EAST BRIGHT FZ-LLC` became `UAB NOVAKOPA`, while the address block below the
name stayed the same. That is the defect the whole system exists to catch: the
cargo would be released to the wrong company.

Also note the SI calls it `Consignee (Non-Negotiable)` and the BL calls it
`To the Order of`. Same field, different words.

---

## R2 — classify and extract

**The subject line does not tell you the category.**

```bash
python3 -c "
import json,os
E=[json.load(open('inbox/'+f)) for f in sorted(os.listdir('inbox'))]
for e in E:
    if 'TO CONFIRM DOCS' not in e['subject'].upper(): continue
    kind='HAS ATTACHMENTS' if e['attachments'] else 'none'
    line=[l for l in e['body'].split(chr(10)) if l.strip()][1][:62]
    print(f\"{e['email_id']}  {kind:15} {line}\")
" | head -6
```

`email_001` and `email_003` share a subject family. One has the documents
attached and needs comparing. The other is *asking someone else to send* the
draft BL and needs nothing. 46 versus 38 across the corpus. The verb in the
body is the discriminator, not the subject.

**The filename lies.**

```bash
head -1 attachments/email_501_BL.txt    # COMMERCIAL INVOICE
head -1 attachments/email_001_BL.txt    # BILL OF LADING (DRAFT)
```

Five emails ship an invoice, packing list or certificate of origin under a
`_BL` filename. Check the document header before extracting.

**Labels are a closed set — a table, not a model.**

```bash
grep -ho '^[A-Za-z][^:]*:' attachments/*_SI.txt | sort | uniq -c | sort -rn | head -20
```

Four or five variants per field, and the SI and BL draw from the same pool.

---

## R3 — normalise and compare

**The locode is a decoy.**

```bash
grep -hiE 'discharge|POD' attachments/email_013_SI.txt attachments/email_013_BL.txt
```

Different city, different country, **same `(KEMBA)`**. Every port defect works
this way. Compare the city name, treat the code as noise. Note also that a
grep for `POD` alone only matches the SI — the BL omits the abbreviation.

**Check for absent values before comparing.**

```bash
grep -i 'gross' attachments/email_516_SI.txt attachments/email_516_BL.txt
```

`N/A` against `235,550 KG`. Compare first and you report a false weight
mismatch; the right answer is escalate as `missing_value`. Note the CJK
characters inline in the label: `Gross Weight毛重(KGS)`.

**Do not strip corporate suffixes.**

```bash
grep -i 'shipper' attachments/email_145_SI.txt attachments/email_145_BL.txt
```

`APRIL FINE PAPER TRADING` versus
`APRIL FINE PAPER TRADING (MIDDLE EAST) FZE`. Strip `FZE` and `(MIDDLE EAST)`
and they collapse into one string — but they are two different legal entities,
and the consignee on a bill of lading is who can legally collect the cargo.

**Then build against the fixture, not against R2.**

```bash
cd codebase
python3 -c "import json;print(json.dumps(json.load(open('fixtures/Mismatch.json'))['ComparisonResult']['rows'],indent=2))"
```

Every rule above, with its evidence, is in `docs/01-comparison-rules.md`.

---

## R4 — cloud and deployment

```bash
cd ~/Projects/hackathon/sdoc-hackathon-docker
docker compose ps
curl -s localhost:8081/health
```

Expect `{"status":"ok","emails":520,"scoring_available":true}`.

**Port 8080 is already taken** on this machine by an unrelated container,
which is why `docker-compose.override.yml` maps 8081. Whatever we deploy must
not hardcode 8080.

```bash
cd ~/Projects/hackathon/codebase
python3 tools/smoke_test.py ../
python3 tools/smoke_test.py http://localhost:8081
```

Both must print 520 / 126. The code reaches data through `DATA_DIR`, so the
deployed build can point somewhere else without a code change.

**Never ship the organiser kit.** `sdoc-hackathon-docker/` contains
`ground_truth.json` — the answer key. It is outside the repo and `.gitignore`
blocks it. Verify before any deploy:

```bash
git check-ignore -v ../sdoc-hackathon-docker/data_v2/ground_truth.json
```

---

## R5 — report UI and media

**The table you are rendering.**

```bash
cd ~/Projects/hackathon/codebase
python3 -c "import json;print(json.dumps(json.load(open('fixtures/Mismatch.json'))['ComparisonResult'],indent=2))"
```

Seven rows, an SI column and a BL column. Both `raw` and `norm` are supplied:
show `raw` to the human, because that is the source evidence, and let `norm`
explain why the verdict went the way it did.

A mismatch is a verdict about a **pair**, not a property of one document. One
table, not two panels.

**The four escalation reasons, each with its evidence string.**

```bash
for f in ReviewWrongDoc ReviewMissingAtt ReviewUnreadable ReviewMissingVal; do
  python3 -c "
import json;d=json.load(open('fixtures/$f.json'))['ComparisonResult']
print(f\"{d['review_reason']:20} {d['evidence']}\")"
done
```

Those strings go on screen next to a confirm / correct action. Escalation is a
named capability in the brief and it is scored on its own axis, so the review
pile needs to be a first-class destination, not a status buried in a list.

**Counts for the left rail.**

```bash
cd ~/Projects/hackathon
python3 -c "
import json,os,re,collections
SP={'webmail-verify.co','secure-mailbox.org','parcel-track.co','logistics-deals.biz','prize-claims.info','crypto-invest.net'}
E=[json.load(open('inbox/'+f)) for f in sorted(os.listdir('inbox'))]
c=collections.Counter()
for e in E:
    b=e['body']
    if e['from'].split('@')[1] in SP: c['SPAM']+=1
    elif e['attachments'] or 'Please compare the SI and draft BL' in b: c['BL_COMPARISON']+=1
    elif 'Please find Shipping instruction' in b or 'send the draft BL' in b: c['SI_REQUEST?']+=1
    elif re.search(r'invoice|THC|D&D|detention|GR is still',b,re.I): c['INVOICE_QUERY']+=1
    else: c['GENERAL']+=1
for k,v in c.most_common(): print(f'  {k:16}{v}')
"
```

Roughly 129 / 216 / 75 / 60 / 40. The `SI_REQUEST?` bucket carries a question
mark on purpose — 91 of those are unresolved, see below.

---

## What nobody can resolve without asking

91 emails say *"Please assist to send the draft BL for X for checking asap."*
They are not comparisons, not invoice queries, not spam. Either `SI_REQUEST`
or `GENERAL`, and nothing in the brief decides it. That is 17.5% of the inbox,
and Stage 1 is scored on macro-F1, so a wrong call damages two categories at
once.

This needs to go to `#faq` today.

---

## Report back

In the team chat, one line each: **what surprised you.** If nothing did, you
probably did not run it.
