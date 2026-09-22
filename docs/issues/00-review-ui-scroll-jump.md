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
(not yet reproduced here - no working browser in this environment; chromium is
missing `libnspr4`. Needs the failing control and the viewport width.)

## Root cause
(unknown)

## Fix
(none yet)
