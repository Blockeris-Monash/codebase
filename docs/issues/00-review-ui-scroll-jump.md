# Clicking in the review UI scrolls the page back to the top

## Symptom
Reported: "the click and it goes all the way up bug is still there." A click in
the review UI moves the scroll position to the top instead of leaving it where
it was. Reported as still present after an earlier fix.

Not yet pinned down: which control is clicked, and at which viewport width.
Both matter, because the two layouts scroll different elements.

## Expected
Scroll position is preserved across a re-render, except where a reset is
deliberate (opening an email, changing folder, paging, clearing the search).

## What is known

`render()` rebuilds the whole app with one `innerHTML` assignment
(`frontend/index.html:676`), so every scroll offset is destroyed on every
click. Two pieces of state guard against that:

- `S.reset` (set by `folder`, `newer`, `older`, `open`, `first`, `clearq`,
  `allmail`, `back`, search input, folder select, Escape-clears-search) means
  "do not restore" — but nothing scrolls to the top either.
- `keep` (`index.html:662`, restored at `:687`) snapshots
  `.pane.scrollTop`, `.list.scrollTop` and `window.scrollY` before the
  rebuild and writes them back after.

The two layouts scroll different elements, which the snapshot covers but which
makes the failing path ambiguous:

| viewport | scrolls | inert |
|---|---|---|
| >= 821px | `.list` and `.pane` (`overflow-y:auto`, `body{overflow:hidden}`) | `window.scrollY` is always 0 |
| <= 820px | the window (`.pane` is `position:sticky`) | `.list`/`.pane` `scrollTop` are always 0 |

Four candidate mechanisms, each on a different code path:

1. `S.reset=true` actions restore nothing, so the browser clamps wherever the
   new document height lands.
2. Height-changing toggles (`docs`, `body`, `how`, `mark`, `undo`, `discard`)
   keep the old offset, which is then clamped if the content got shorter.
3. `scrollIntoView` after the restore (`:691` `keyNav`, `:692` `scrollTo`)
   scrolls every scrollable ancestor, overriding what was just restored.
4. `box.focus()` on the search input (`:684`) scrolls the focused element into
   view before the restore runs.

The earlier fix was `d96b6c0` "Add Checked category and keep scroll position in
the review UI", which added the `keep` snapshot and restore.

## Reproduction
Desktop window, 821px wide or more. Open a folder with more than a screenful of
emails, scroll the left-hand list down, click a row near the bottom. The detail
opens correctly in the pane; the list beside it snaps to the top and the row
just clicked is no longer visible.

The same move with the keyboard - select an email, then Left/Right arrow - does
*not* do it. That asymmetry is the tell.

(Not browser-verified here: chromium in this environment is missing `libnspr4`.
The cause below is established by reading every path that can reset a scroll
container, and it is the only one that produces `scrollTop = 0` rather than a
clamp.)

## Root cause

`S.reset` is one flag standing for two different scroll containers.

`render()` rebuilds everything with a single `innerHTML` write (`:676`), so
both `.list` and `.pane` are new elements at `scrollTop = 0` every time.
`keep` (`:662`, restored `:687`) exists to put the offsets back, and
`S.reset` suppresses it.

Suppressing it is right for the pane: `open`, `first` and `back` change which
email is shown, so the pane must start at the top of the new document.

It is wrong for the list. At >= 821px the list is a separate, still-visible
scroll container, and selecting an email does not change its contents - the
same rows in the same order. Skipping the restore throws away a position that
was still valid, and the rebuilt `.list` comes back at 0.

So: **selecting an email sets `S.reset`, which suppresses the restore for both
containers, and the rebuilt list therefore returns at `scrollTop = 0` even
though its contents did not change.**

That explains every part of the symptom:

- *all the way up*, not a partial jump - it is a fresh element at 0, not a
  clamp against a shorter document.
- *only on click* - `goTo()` (`:775`) sets `S.reset` **and** `S.keyNav`, and
  `:691` then does `q(".item.on").scrollIntoView({block:"nearest"})`, which
  pulls the selected row back into view. The click path at `:746` sets
  `S.reset` alone, so nothing puts it back.
- *survived the previous fix* - `d96b6c0` added the `keep` snapshot, which is
  skipped in exactly the case that fails.
- *not reported on a phone* - at <= 820px `.split.hasSel .list{display:none}`
  (`:278`), so the list is not on screen to jump.

`back` (`:751`) has the same defect and no `.item.on` to scroll to, so
returning to the list also loses the reader's place.

## Fix

Split the flag by container, because the two groups of actions genuinely differ:

- actions that change *what is in the list* - `folder`, `newer`, `older`,
  `clearq`, `allmail`, the search box, the folder select - should send the list
  to the top. Correct today.
- actions that change *only which email is selected* - `open`, `first`, `back`,
  `goTo` - leave the list contents alone, so its offset should be kept, while
  the pane starts at the top.

Concretely: replace `S.reset` with `S.resetList` and `S.resetPane`; have `keep`
skip the list restore only on the first group and the pane restore only on the
second. Keep `S.keyNav` on `open` as well, so a click leaves the selected row
visible exactly as the arrow keys already do.

Applied. `S.reset` is now `S.resetList` and `S.resetPane`, set independently at
all thirteen sites, and the snapshot skips each container on its own flag.
`open` also sets `S.keyNav`, so a click leaves the selected row in view exactly
as the arrow keys already did.

One behaviour deliberately left alone: when a container is reset, nothing
scrolls it to the top explicitly - the browser clamps, as before. Changing that
would alter what a phone does when an email is opened, which is beyond this bug
and is not testable here.

Verified: `tests/test_review_ui_scroll.py` fails 12 of 12 against the file as it
was and passes 12 of 12 against the fix; the suite is 236 passed. Not confirmed
in a browser - chromium in this environment is missing `libnspr4` - so the
five-second check still stands: wide window, scroll the list down, click a row
near the bottom, and the list should stay put with the clicked row still
visible.

`frontend/index.html` is Milk's file. Flagging that here rather than in the
commit, since the change is behavioural.
