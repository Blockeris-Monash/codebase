# Working on this

Team process. Nothing here is needed to run or judge the project — for that,
see the [README](README.md). Every command assumes the activated virtual
environment from the README's Setup section.

## Developer checks

```bash
# 1. dataset reachable, both ways
python -m cli.smoke_test
python -m cli.smoke_test http://localhost:8081

# 2. regenerate stage fixtures from real emails
python -m cli.make_fixtures --out fixtures

# 3. check everything still satisfies the contracts
python -m cli.validate_contracts
```

The scoring server runs on **8081**, not 8080 — 8080 is commonly taken. Start
it from the organiser kit with `docker compose up -d`.

`frontend/results.js` is a build artefact, not hand-written. It is every email
with its category, its verdict and both documents, rebuilt from `results/` by:

```bash
python -m cli.make_results         # -> frontend/results.js
```

If you hold the organisers' `ground_truth.json`, you can score this yourself
with their `score_cli.py`; our saved results come out at 1.0000. The repository
ships no `submission.json`, because it is a self-check rather than a
deliverable — `cli.make_fixtures` writes a `SubmissionSample.json` showing the
shape.

## Check your output before handing it on

Write one record to a JSON file and name the contract it should satisfy:

```bash
python -m cli.validate_contracts out.json ComparisonResult
```

Fixtures are numbered by scenario, not by email id — `01-Ok.json` through
`11-SendDraftBlUnresolved.json`. Each carries a real email: `01-Ok.json` is
`email_064`, `02-Mismatch.json` is `email_025`.

Per stage:

```bash
python -m cli.validate_contracts record.json     EmailRecord
python -m cli.validate_contracts classified.json ClassificationResult
python -m cli.validate_contracts extracted.json  DocumentExtract
python -m cli.validate_contracts compared.json   ComparisonResult
python -m cli.validate_contracts entry.json      SubmissionEntry
```

With no arguments it checks every fixture instead:

```bash
python -m cli.validate_contracts
```

A failure names the field and what was wrong:

```
FAIL - 3 violation(s):
  SubmissionEntry.status: 'MISMATCHED' not one of ['OK', 'MISMATCH', 'NEEDS_REVIEW']
  SubmissionEntry.has_defect: expected boolean, got str
  SubmissionEntry.defect_fields[1]: 'vessel' not one of [...]
```

Exit code is 0 on pass and 1 on failure, so it drops into CI or a pre-commit
hook. Stdlib only — no `pip install`, so every stage can run it.

Validating a whole submission before you POST it:

```python
import json
from cli.validate_contracts import load_contract, validate

schema, errors = load_contract("SubmissionEntry"), []
for email_id, entry in json.load(open("submission.json")).items():
    validate(entry, schema, email_id, errors)
print(errors or "all 520 entries valid")
```

