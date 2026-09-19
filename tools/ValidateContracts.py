#!/usr/bin/env python3
"""Check data against the contracts in contracts/.

    python3 tools/ValidateContracts.py                 # check every fixture
    python3 tools/ValidateContracts.py mine.json ComparisonResult

Exits non-zero on the first contract violation, so it drops straight into CI
or a pre-commit hook. Supports the subset of JSON Schema the contracts use;
no third-party dependency, because every stage must be able to run this.
"""
import json
import re
import sys
from pathlib import Path

CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "contracts"
FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
JSON_TYPES = {
    "object": dict, "array": list, "string": str,
    "number": (int, float), "boolean": bool, "null": type(None),
}


def type_matches(value, name):
    """A JSON 'number' must not silently accept a bool, which is an int."""
    if name == "boolean":
        return isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, JSON_TYPES[name])


def check_type(value, schema, path, errors):
    expected = schema.get("type")
    if expected is None:
        return
    allowed = expected if isinstance(expected, list) else [expected]
    if any(type_matches(value, name) for name in allowed):
        return
    errors.append(f"{path}: expected {'|'.join(allowed)}, got {type(value).__name__}")


def check_enum(value, schema, path, errors):
    allowed = schema.get("enum")
    if allowed is None or value in allowed:
        return
    errors.append(f"{path}: {value!r} not one of {allowed}")


def check_string(value, schema, path, errors):
    pattern = schema.get("pattern")
    if pattern is None or not isinstance(value, str) or re.match(pattern, value):
        return
    errors.append(f"{path}: {value!r} does not match /{pattern}/")


def check_bounds(value, schema, path, errors):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return
    low, high = schema.get("minimum"), schema.get("maximum")
    if low is not None and value < low:
        errors.append(f"{path}: {value} below minimum {low}")
    if high is not None and value > high:
        errors.append(f"{path}: {value} above maximum {high}")


def property_schema(key, schema):
    """Resolve a key against `properties` then `patternProperties`."""
    direct = schema.get("properties", {}).get(key)
    if direct is not None:
        return direct
    for pattern, sub in schema.get("patternProperties", {}).items():
        if re.match(pattern, key):
            return sub
    return None


def check_object(value, schema, path, errors):
    if not isinstance(value, dict):
        return
    for key in schema.get("required", []):
        if key not in value:
            errors.append(f"{path}: missing required field {key!r}")
    allows_extra = schema.get("additionalProperties", True)
    for key, item in value.items():
        sub = property_schema(key, schema)
        if sub is None and not allows_extra:
            errors.append(f"{path}: unexpected field {key!r}")
        if sub is not None:
            validate(item, sub, f"{path}.{key}", errors)


def check_array(value, schema, path, errors):
    item_schema = schema.get("items")
    if not isinstance(value, list) or item_schema is None:
        return
    for index, item in enumerate(value):
        validate(item, item_schema, f"{path}[{index}]", errors)


def validate(value, schema, path, errors):
    check_type(value, schema, path, errors)
    check_enum(value, schema, path, errors)
    check_string(value, schema, path, errors)
    check_bounds(value, schema, path, errors)
    check_object(value, schema, path, errors)
    check_array(value, schema, path, errors)
    return errors


def load_contract(name):
    """Find a contract by name, ignoring its numeric ordering prefix.

    Files are numbered (01-EmailRecord.schema.json) so they list in pipeline
    order, but callers name them plainly: load_contract("EmailRecord").
    """
    matches = sorted(CONTRACTS_DIR.glob(f"*{name}.schema.json"))
    if not matches:
        available = ", ".join(sorted(contract_names()))
        raise SystemExit(f"no contract named {name!r}. Available: {available}")
    return json.loads(matches[0].read_text())


def contract_names():
    """Every contract's plain name, prefix stripped."""
    return [p.name.split("-", 1)[-1].replace(".schema.json", "")
            for p in sorted(CONTRACTS_DIR.glob("*.schema.json"))]


# Which contract each key of a fixture bundle must satisfy. DocumentExtract
# appears as a list because one email yields one extract per attachment.
BUNDLE_CONTRACTS = {
    "EmailRecord": "EmailRecord",
    "ClassificationResult": "ClassificationResult",
    "DocumentExtract": "DocumentExtract",
    "ComparisonResult": "ComparisonResult",
    "SubmissionEntry": "SubmissionEntry",
}
LIST_VALUED = {"DocumentExtract"}
SUBMISSION_SAMPLE = "SubmissionSample.json"


def check_bundle(path):
    """Validate every stage artefact inside one fixture file."""
    bundle = json.loads(path.read_text())
    errors = []
    for key, contract in BUNDLE_CONTRACTS.items():
        payload = bundle.get(key)
        if payload is None:
            continue
        schema = load_contract(contract)
        items = payload if key in LIST_VALUED else [payload]
        for index, item in enumerate(items):
            validate(item, schema, f"{path.name}:{key}[{index}]", errors)
    return errors


def check_submission(path):
    schema = load_contract("SubmissionEntry")
    errors = []
    for email_id, entry in json.loads(path.read_text()).items():
        validate(entry, schema, f"{path.name}:{email_id}", errors)
    return errors


def check_all_fixtures():
    errors, checked = [], 0
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        found = (check_submission(path) if path.name == SUBMISSION_SAMPLE
                 else check_bundle(path))
        status = f"{len(found)} error(s)" if found else "ok"
        print(f"  {path.name:28} {status}")
        errors.extend(found)
        checked += 1
    print(f"\n{checked} fixture files checked against 5 contracts")
    return errors


def check_one(target, contract):
    schema = load_contract(contract)
    return validate(json.loads(Path(target).read_text()), schema, contract, [])


def main():
    if len(sys.argv) == 3:
        errors = check_one(sys.argv[1], sys.argv[2])
    elif len(sys.argv) == 1:
        errors = check_all_fixtures()
    else:
        print(__doc__)
        return 2
    if not errors:
        print("PASS")
        return 0
    print(f"\nFAIL - {len(errors)} violation(s):")
    for message in errors:
        print(f"  {message}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
