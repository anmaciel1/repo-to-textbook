# Iterating on a book

A book is a living document. `chapters/*.md` and `curriculum.json` are the source of truth, and
`book.html` and `book.pdf` are always rebuilt from them.

Every command below ends the same way:

1. `check_citations.py BOOK <changed ids>`, which must pass;
2. `curriculum.py record BOOK <changed ids>`;
3. `curriculum.py bump BOOK --note "<what changed>"`;
4. `build_book.py BOOK`;
5. a one-paragraph report of what changed, with the edition number.

## Protecting the user's work

Before **any** rewrite of an existing chapter:

1. **Check for hand edits.** Run `curriculum.py edited BOOK`. If the chapter is listed, the user
   edited it by hand. Ask which they want:
   - (a) revise on top of their edits, keeping them;
   - (b) discard their edits;
   - (c) cancel.

   The default is (a): treat the current file as the base and change only what the instruction
   requires.
2. **Snapshot.** Run `curriculum.py snapshot BOOK <id>`. This saves the old text to
   `.history/<id>.e<edition>.md`.

## `revise <chapter> "<instruction>"`

- `<chapter>` may be an id (`ch04-…`), a number ("4", meaning the 4th kept chapter) or a title fragment.
- Rewrite the chapter by following the instruction, the chapter template and the chapter's
  `instructions` field. If the instruction is a lasting preference ("fewer code dumps"), append it
  to the chapter's `instructions` so later revisions keep it.
- Change only what the instruction asks for. Keep the chapter's headings stable where possible,
  because other chapters link to them.
- **Section form.** `revise ch04 §3 "…"` (or "section 4.3") rewrites only that `##` section and
  its subsections. Leave the rest of the file byte-identical.
- **Downstream check.** After revising, look for anything other chapters relied on: renamed
  headings (anchors), renamed `<dfn>` terms, changed symbols in a bridge table, and removed content
  that a later chapter says "as we saw in …".
  - `grep` the dependent chapters, i.e. the ones whose nodes have this chapter's nodes as
    prerequisites, for the old anchors and terms.
  - List the breakages and offer to patch them. Patch them only with the user's approval.
- Update `notes/<id>.md` if the summary, terms or symbols changed.

## `revise --from-comments`

Adding feedback comments is itself a hand edit, so `edited` will flag these chapters. That is
expected: always revise on top of the current file (option a), keeping any other edits the user made.

1. Run `curriculum.py comments BOOK` to list every `<!-- feedback: … -->` with its location.
2. Group the comments by chapter, then apply each one as a local revision at its location.
3. Remove each comment once it has been addressed.
4. Report what you did for each comment. If a comment is ambiguous, ask instead of guessing.

## `add "<topic>"`

1. Survey the topic in the source: find the files, check that they exist, and work out the
   prerequisites among the existing nodes.
2. Add node(s) and a chapter with a new id (the next unused `chNN-`), `status: "approved"`.
3. Run `order --write` and `validate`. If the new chapter's prerequisites are not covered, apply the
   dependency guard: tell the user and offer keep / primer / link-only.
4. Show the outline excerpt around the new chapter, write it (Phase 5 of SKILL.md), and update the
   Glossary if it introduces new `<dfn>` terms.

## `remove <chapter>`

1. Set the chapter's `status` to `"dropped"` and run `validate`.
2. Guard errors mean that kept chapters depend on it. Offer, per dependent chapter:
   - keep the chapter (cancel the removal);
   - turn the needed nodes into primers in the dependents, then revise those chapters to add the
     primer boxes;
   - mark the nodes `assumed` (link only).
3. Leave the dropped chapter's file in place (it is no longer built) and mention that it can be
   restored with "bring back".

## `mode <chapter|topic> applied|foundations|assumed`

- `foundations` means `foundations+applied`. Set the mode on the node(s): every node of a chapter,
  or the matching topic.
- **To `foundations+applied`:** revise the chapter to insert the Foundations section and the bridge
  table, and rename later references to the repo's symbols where needed.
- **To `applied`:** revise the chapter to remove the Foundations section. Keep any primer-sized
  pieces the reader still needs as primer boxes.
- **To `assumed`:** this is a removal of the topic. Run the dependency guard as for `remove`.

## `update [--ref REF]`

1. Run `stale.py BOOK [--ref REF]` as a dry run and show the stale chapters with their changed files.
2. Ask which ones to refresh. The default is all.
3. Run `stale.py BOOK --apply`. This moves the checkout and marks the stale chapters.
4. For each chapter being refreshed:
   - snapshot it;
   - re-read the changed files;
   - revise only the sections whose citations or listings changed. Re-check line numbers
     everywhere: unchanged prose can still cite shifted lines.
5. Chapters the user chose not to refresh stay `stale` and keep linking to their old commit, so
   their permalinks remain correct. Mention them in the report.
6. If the update introduced significant new functionality, mention it under "Also spotted" and
   offer `add`.

## `revert <chapter> <edition>`

Run `curriculum.py revert BOOK <id> <edition>`, then rebuild. The current text is snapshotted
first, so a revert can itself be reverted.

## `build` / `check`

- `build`: `build_book.py BOOK` only. Use it after hand edits. Do not record or bump.
- `check`: `check_citations.py BOOK` plus `curriculum.py validate BOOK` and `edited`. Report only.
