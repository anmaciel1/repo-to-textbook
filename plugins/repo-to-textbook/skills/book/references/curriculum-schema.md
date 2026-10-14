# `curriculum.json`

This file and `chapters/*.md` are the source of truth for a book. Scripts in `SKILL_DIR/scripts/`
read and maintain it. Edit it with care: keep valid JSON, keep ids stable, and run
`curriculum.py validate BOOK` after every change.

```jsonc
{
  "schema": 1,
  "book":   { "title": "fastapi", "subtitle": "A Guided Textbook" },
  "repo": {
    "name": "fastapi",
    "url": "https://github.com/fastapi/fastapi",
    "web_url": "https://github.com/fastapi/fastapi",   // permalinks; null if unknown host
    "host": "github",                                  // github | gitlab | null
    "ref": null,                                       // branch/tag requested at init
    "sha": "<40-hex>",                                 // commit the book currently tracks
    "source_dir": ".source",                           // relative to BOOK, or absolute for local repos
    "summary": "2–3 sentences: what it is, for whom, why it is worth studying."
  },
  "edition": 1,                                        // bumped on every content change
  "paper": "letter",                                   // letter | a4
  "reader": {
    "level": "intermediate",                           // beginner | intermediate | expert
    "default_mode": "applied",                         // applied | foundations+applied
    "focus": ["dependency injection"],                 // user's focus topics
    "assumed": ["Python basics"]                       // free-text record of what the user said they know
  },
  "nodes": [
    {
      "id": "dependency-injection",                    // kebab-case, stable
      "title": "Dependency injection",
      "kind": "concept",                               // concept | technology | component | pattern
      "prereqs": ["path-operations"],                  // node ids; must form a DAG
      "files": ["fastapi/dependencies/utils.py:120-260"],
      "core": true,
      "mode": "foundations+applied"                    // applied | foundations+applied | assumed
    }
  ],
  "chapters": [
    {
      "id": "ch04-dependency-injection",               // stable; never renumber
      "kind": "chapter",                               // front | chapter | back
      "title": "Dependency Injection: How FastAPI Wires Requests",
      "summary": "One line for the outline.",
      "tag": "core",                                   // core | supporting | optional
      "difficulty": 2,                                 // 1 introductory, 2 intermediate, 3 advanced
      "nodes": ["dependency-injection"],
      "primers": ["python-decorators"],                // prereq nodes taught as a primer box here
      "depth": "deep",                                 // normal | deep
      "objectives": ["Explain how Depends() is resolved", "..."],
      "files": ["fastapi/dependencies/utils.py", "fastapi/routing.py"],
      "status": "proposed",                            // proposed | approved | dropped | written | stale
      "instructions": "optional per-chapter guidance from the user, e.g. 'fewer code dumps'",
      // maintained by scripts, do not hand-edit:
      "sha": "<commit it was written from>",
      "hash": "<sha256 of chapters/<id>.md when last recorded>",
      "cites": ["fastapi/dependencies/utils.py"]
    }
  ],
  "suggestions": [ { "title": "Background tasks", "why": "Used in 3 places; could be an optional chapter." } ],
  "changelog":   [ { "edition": 1, "date": "2026-10-13", "note": "First edition" } ]
}
```

## Semantics

- **Chapter order is reading order.** `curriculum.py order --write` topologically sorts the main
  chapters by the prerequisites of their nodes. Where dependencies allow, it keeps the current order.
- **Chapter numbers are positions** among the kept `chapter` entries. Ids never change, and
  cross-references use ids (`ch04-dependency-injection.md`), so links survive reordering.
- A node is **taught** by the first kept chapter that lists it. A node in `primers` is covered by a
  one-paragraph primer box in that chapter. An `assumed` node is never taught, only linked to in
  Further reading.
- **Dependency guard:** every prerequisite of a kept chapter's nodes must be in one of these states:
  - taught by an earlier chapter;
  - listed in that chapter's `primers`;
  - `assumed`.

  `validate` reports each violation as a `guard:` error.

## Editing at the checkpoint

| User says | Do |
|---|---|
| "drop 7" / "remove the logging chapter" | that chapter `status: "dropped"` (keep it in the list) |
| "bring back 7" | `status: "proposed"` |
| "merge 4 and 5" | Move 5's `nodes`, `files`, `objectives` and `primers` into 4, retitle 4 if needed, and set 5 to `dropped` |
| "split 6" | Create a new chapter (new id, next free number) with some of 6's nodes |
| "go deeper on 3" / "keep 3 short" | `depth: "deep"` / `"normal"`; add specifics to `instructions` |
| "add a chapter on X" | Survey X quickly (find files, which must exist), add a node or nodes and a chapter |
| "I already know X" | Set X's node(s) to `mode: "assumed"` and add X to `reader.assumed`. A chapter left empty becomes `dropped` |
| "I also want the fundamentals of X" / "teach me the theory behind X" | Set X's node(s) to `mode: "foundations+applied"`. If X was assumed, remove it from `reader.assumed` |
| "only how the repo uses X" | Set X's node(s) to `mode: "applied"` |
| "teach fundamentals for everything" | `reader.default_mode = "foundations+applied"`, and the same for every `concept`/`pattern` node not `assumed` |
| "make it for beginners/experts" | `reader.level`; revisit the `assumed` nodes and difficulty with the user |
| "rename 2 to …" | Change `title` |
| "A4 paper" | `paper: "a4"` |

After the edits, run `order --write`, `validate` and `outline`, and report each change in one line.
