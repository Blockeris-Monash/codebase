# UI prototype (throwaway, for voting)

Three layouts for the shipping-ops inbox and the SI vs BL check. Not production code.

Run: double-click `index.html`. Switch layouts with the bar at the bottom, the arrow keys, or `?variant=A|B|C`.

- A: Gmail-style inbox
- B: Status strip and split view
- C: One at a time queue

Data: `data.js` is built by `make_data.py` from the saved extraction results (all 520 emails, real SI vs BL verdicts).
Caveats: categories for non-comparison emails are a keyword guess (the real classifier is not merged), the dataset has no dates so email id order stands in for newest first, and buttons only change in-memory state.
