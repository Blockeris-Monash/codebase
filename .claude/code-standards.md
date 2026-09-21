# Deliberate deviations

Read alongside the house guidelines. A rule listed here is not a finding.

## `cli/validate_contracts.py` — four parameters on the walk functions

House limit is three. The eight `check_*` functions and `validate` take
`(value, schema, path, errors)`.

These are a recursive tree walk, and that quartet is the standard shape for
one. Threading a context object through the recursion would satisfy the count
while making the algorithm harder to recognise, and the guidelines are explicit
that clarity wins over a rule when the two conflict.

Revisit if the walk grows a fifth parameter — at that point the context object
earns its keep.

## `cli/validate_contracts.py` — `Any` in the signatures

The module validates untrusted JSON of unknown shape; that is its entire
purpose. `JsonValue = Any` is aliased at the top and used only for the value
under inspection, which is the parse-boundary exemption the Python reference
allows. Every other module uses the `TypedDict`s in `backend/contracts.py`.

## `loader.py` — vendored unchanged

Supplied by the organisers. Kept byte-identical so it can be re-synced if they
issue a fix, and so `from loader import Inbox` matches their documentation.
Not held to house style.
