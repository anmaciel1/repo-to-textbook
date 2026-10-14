---
name: book
description: Turn a Git repository into a textbook that teaches what the repo is, how it works, and the concepts and technologies it uses, anchored in the repo's real code. Analyzes the repo, proposes dependency-ordered chapters for the user to approve or edit, optionally teaches fundamentals (e.g. backpropagation) before showing how the repo applies them, then writes Markdown chapters and builds a classic-styled HTML book and PDF that can be revised later. Use when the user wants to learn, study, onboard onto, or "turn into a textbook/book/course" a repository, or runs /repo-to-textbook:book.
argument-hint: <github-url|owner/repo|path> [--level beginner|intermediate|expert] [--mode applied|foundations] [--focus "a, b"] | resume | revise <ch> "…" | add "…" | mode <ch> … | update | build
---

# Repo → Textbook

You turn a repository into a textbook. **The repository is the subject.** Every chapter teaches
something by showing where and how *this* code does it. General background appears only where
the reader asked for fundamentals, and it must always bridge back to the code.

`SKILL_DIR` means the directory that contains this file. The scripts are in `SKILL_DIR/scripts/`
(Python 3.8+, stdlib only) and the detailed rules are in `SKILL_DIR/references/`.

## Invocation

Parse the user's arguments:

| Form | Action |
|---|---|
| `<github-url \| owner/repo \| path> [--level beginner\|intermediate\|expert] [--mode applied\|foundations] [--focus "a, b"] [--paper letter\|a4] [--out DIR] [--ref REF]` | New book: phases 1–6 below |
| `resume [BOOK]` | Continue an interrupted run (see "Resuming") |
| `revise <chapter> ["§N"] "<instruction>"`, `revise --from-comments` | Rewrite a chapter or section ([iteration](references/iteration.md)) |
| `add "<topic>"`, `remove <chapter>`, `mode <chapter\|topic> applied\|foundations\|assumed` | Change the curriculum ([iteration](references/iteration.md)) |
| `update [--ref REF]` | Pull new commits and refresh stale chapters ([iteration](references/iteration.md)) |
| `revert <chapter> <edition>` | Restore an earlier edition of a chapter |
| `build`, `check` | Rebuild the HTML and PDF / verify the citations only |

`BOOK` is the book directory, which holds `curriculum.json`. If it is not given, use the single
`*-textbook/` directory in the current working directory that contains a `curriculum.json`. If
there are several, ask which one.

With no arguments, ask for the repository and stop.

## Phase 1: Initialize

```bash
python3 SKILL_DIR/scripts/init_book.py <source> [--level …] [--mode …] [--focus "…"] [--paper …] [--out …] [--ref …]
```

This shallow-clones remote repos into `BOOK/.source/`, uses local repos in place, and writes a
skeleton `curriculum.json`. Keep the printed `book` and `source` paths. **Never modify the source
repository.**

## Phase 2: Survey → concept map → proposed curriculum

Survey the repo and fill in `curriculum.json`: `repo.summary`, `nodes`, `chapters` (all with
`status: "proposed"`) and `suggestions`.

- **Claude Code:** delegate to the `repo-to-textbook:repo-surveyor` agent. Pass it `BOOK`, the
  source path, `SKILL_DIR` and the reader settings.
- **Without subagents** (e.g. Codex): do the work yourself, following
  [references/roles/surveyor.md](references/roles/surveyor.md).

The rules are in [references/survey-checklist.md](references/survey-checklist.md) and the format
is in [references/curriculum-schema.md](references/curriculum-schema.md).

Then run these until `validate` passes:

```bash
python3 SKILL_DIR/scripts/curriculum.py order    BOOK --write
python3 SKILL_DIR/scripts/curriculum.py validate BOOK
```

## Phase 3: Review checkpoint (the user steers; do not skip)

1. Run `curriculum.py outline BOOK` and show the user its Markdown **verbatim**. It contains the
   numbered chapters, topics with their learning modes, prerequisites, key files, dropped and
   assumed topics, "also spotted" suggestions and a dependency graph.
2. Explain in two or three sentences how the book is arranged, then invite edits in plain language.
   For example: *"drop 7", "merge 4 and 5", "go deeper on 3", "add a chapter on the test setup",
   "I already know React", "I also want the fundamentals of backpropagation", "make it for beginners".*
3. In Claude Code, also use AskUserQuestion once, as a multi-select, for the **learning mode**:
   "Which topics should also teach the fundamentals before showing how this repo uses them?"
   - Offer up to 4 of the most fundamentals-worthy concept nodes. Prefer focus topics and core
     concepts with real theory behind them.
   - Everything else stays `applied` unless the user says otherwise.

   Without that tool, ask the same question in text.
4. Apply each edit to `curriculum.json` as described in
   [references/curriculum-schema.md § Editing at the checkpoint](references/curriculum-schema.md#editing-at-the-checkpoint).
   Then run `order --write`, `validate` and `outline`, and show the new outline with one line per
   change you made.
5. **Dependency guard.** When `validate` reports a `guard:` error, the user removed something that a
   chapter they kept depends on. Explain this and offer exactly three choices:
   - **keep** the prerequisite chapter;
   - **fold** it into a short primer box inside the dependent chapter (add it to that chapter's `primers`);
   - **link only** (set the node's mode to `assumed`).

   Never resolve the guard silently.
6. Repeat until the user approves ("looks good", "go", "approve"). Then run `curriculum.py approve BOOK`.

## Phase 4: Resources

Collect further reading for every node whose mode is not `assumed`, plus links for the `assumed`
nodes. Write them to `BOOK/resources.json`.

- **Claude Code:** use the `repo-to-textbook:resource-finder` agent.
- **Otherwise:** follow [references/roles/resource-finder.md](references/roles/resource-finder.md).

Only use URLs you actually saw in search results or fetched. **Never invent a link.**

## Phase 5: Write

1. Run `curriculum.py waves BOOK`. Chapters in the same wave can be written in parallel. Front and
   back matter come last.
2. For each chapter, before writing:
   - if the file already exists, run `curriculum.py edited BOOK`. If the user hand-edited this
     chapter, **ask before overwriting**;
   - run `curriculum.py snapshot BOOK <id>`.
3. Write the chapter:
   - **Claude Code:** with the `repo-to-textbook:chapter-writer` agent. Run up to 4 agents at once
     within a wave, and give each one `BOOK`, the chapter id and `SKILL_DIR`.
   - **Otherwise:** yourself, following [references/roles/chapter-writer.md](references/roles/chapter-writer.md).

   Each chapter follows [references/chapter-template.md](references/chapter-template.md) and the
   syntax in [references/markdown-conventions.md](references/markdown-conventions.md).
4. After each chapter:
   - run `check_citations.py BOOK <id>`. Fix every error, or send the writer back to fix them,
     until it passes;
   - run `curriculum.py record BOOK <id>`.
5. **Calibration.** After the first main chapter is written and recorded, build it with
   `build_book.py BOOK --no-pdf`. Give the user the `book.html` path and ask once whether the depth
   and tone are right. Apply any answer to the remaining chapters' instructions.
6. Write the Preface (front matter) and the Glossary (back matter) last, from the notes in
   `BOOK/notes/`. The template covers both.

## Phase 6: Assemble and deliver

```bash
python3 SKILL_DIR/scripts/check_citations.py BOOK          # must pass
python3 SKILL_DIR/scripts/curriculum.py bump BOOK --note "First edition"
python3 SKILL_DIR/scripts/build_book.py BOOK               # book.html + book.pdf
```

If the PDF step reports that no browser was found, tell the user to open `BOOK/.build/print.html`
in Chrome and choose Print → Save as PDF (Margins: None).

Finish with a short report:
- the paths to `book.pdf`, `book.html` and `chapters/`;
- the chapter list;
- the iteration commands (`revise`, `add`, `mode`, `update`, `build`), with a note that the
  Markdown can be edited by hand and rebuilt with `build`.

## Resuming

1. Read `curriculum.json`.
2. If any chapter is `proposed`, go back to Phase 3.
3. If any chapter is `approved` or `stale`, check whether `resources.json` exists (Phase 4), then
   continue Phase 5 from `waves`.
4. If everything is written, run Phase 6.

## Non-negotiables

- **Ground every claim in the code.** Cite files and line ranges as `[[path:a-b]]`. Do not describe
  functions, flags, files or behavior you have not read. If you are inferring, say so ("appears to",
  "likely").
- **Listings are verbatim.** Use a fenced block with `lang path:a-b`. You may elide lines with
  `...`, but never paraphrase code inside a cited listing. `check_citations.py` enforces this.
- **Keep the repo as the subject.** `applied` chapters teach through this repo's code. A Foundations
  section appears **only** for `foundations+applied` topics, and it ends with a bridge table that
  maps the theory onto real symbols.
- **Keep the style classic and professional.** Use an even, precise textbook voice: no hype, no
  emoji, no exclamation marks, no "Let's dive in".
- **Respect the user's edits.** Snapshot before overwriting. Never silently overwrite a hand-edited
  chapter.
- **Respect the reader.** Adapt explanations to `reader.level`. Never teach `assumed` topics. Link to them instead.
