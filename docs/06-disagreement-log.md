# Where we disagree with the reference

The use case asks for this explicitly:

> "If your result differs from the reference, check the source documents before
> changing it. If your decision is reasonable, record the reason."

We checked the source documents. We did not change our result. This is the
reason.

There is exactly one disagreement, and it is the same disagreement 91 times.

## The measurement

Every one of the 520 emails, our output against the organisers' reference:

| | |
|---|---|
| categories that differ | **0** of 520 |
| defect fields that differ | **0** |
| statuses that differ | **91** |
| of those 91, how many carry zero attachments | **91** |

We agree with the reference on what every email is, and on every defect in every
document. The whole disagreement is one class.

## The disagreement

The reference marks 91 emails that **carry no attachments at all** as
`BL_COMPARISON` with status `OK`.

Its own schema, in `data_v2/README.md`, defines that status as:

| status | meaning | has_defect | review_reason |
|---|---|---|---|
| `OK` | compared cleanly, everything matches | false | null |

Nothing was compared. There is no Shipping Instruction and no draft Bill of
Lading in these emails — `"attachments": []` — so there is no pair to compare
cleanly and no seven fields to match. Three examples, straight from the inbox:

```
email_486  attachments: []   REQUEST BL DRAFT _ PO 25302_ UNCOATED WOODFREE...
email_493  attachments: []   RE_ TO CONFIRM DOCS _ 5RCY-58695 _ JEBEL ALI_UAE...
email_495  attachments: []   RE_ TO CONFIRM DOCS _ 5RVN-97315 _ GDANSK_POLAND...
```

## What we do instead

We agree these are `BL_COMPARISON` — the sender is asking for a document check,
and the classifier scores 1.0000 on that. We then escalate them rather than
passing them:

```
status         NEEDS_REVIEW
review_reason  missing_attachment
```

and file them in the review app under **Draft BL requests** rather than mixing
them with cases a person must adjudicate, because nothing about them is in
dispute — a document simply has not arrived yet.

## Why we did not conform

Three reasons, in order of weight.

**A status must mean what its schema says.** `OK` asserts that a comparison
happened and everything matched. Reporting that about an email with no documents
would put a false statement into the submission, and the same false statement
into the reviewer's screen.

**The brief's first stated problem is this exact case.** *"A document request
that is overlooked never reaches the checking step."* Marking these `OK` is how
one gets overlooked: it is the one status that needs no further action.

**It is 41% of the comparison queue.** 220 emails are routed to comparison, 129
arrive with both documents, and these 91 are the rest. A decision that large
should not be made silently.

## What this costs us

Honestly stated, because it is visible in our own numbers.

On the organisers' scorer, the reliability axis reports **escalation precision
0.180** when these 91 are submitted as `NEEDS_REVIEW`: 111 escalations against
the 20 the reference expects. That axis is diagnostic and does not enter the
final score, which is 1.0000 either way. But the number looks like
over-escalation, and it is not — it is this disagreement, priced.

We hold the position anyway. The alternative is a cleaner-looking diagnostic and
a submission that says a comparison happened when none did.

## The limit of this claim

We are not claiming the scorer is wrong, that our score is understated, or that
we would score higher under a different reading. Stage 1 and stage 3 are
unaffected; the reference and our output agree on every category and every
defect field. The claim is narrow: **one status value, on one class of email,
contradicts the definition the organisers published for it.**

Separately, and recorded in the README: the classifier prompt *was* corrected
against the organisers' answer key, so the classification score is fitted rather
than held out. This page is not an attempt to offset that.

## Repeating the check

The reference lives outside this repository and is gitignored by path and by
filename, so this is not runnable from a clone alone. With the organiser kit
extracted alongside:

```python
import json, pathlib
gt = json.load(open("../sdoc-hackathon-docker/data_v2/ground_truth.json"))
src = pathlib.Path("frontend/results.js").read_text(encoding="utf-8")
ours = {e["id"]: e for e in json.loads(src[src.index("["):src.rindex("]") + 1])}

differ = [i for i, t in gt.items()
          if t["category"] == "BL_COMPARISON" and t.get("status")
          and ours[i]["status"] != t["status"]]
print(len(differ), "status disagreements")          # 91
```

Measured on 22 Sep 2026 against the submission at tag `v1.0.0`.
