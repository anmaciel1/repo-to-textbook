# repo-to-textbook

Turn any Git repository into a **textbook**: one that teaches what the repo is, what it is for, and
the concepts and technologies it uses, through the repo's own code.

```
/repo-to-textbook:book https://github.com/karpathy/micrograd --level beginner --focus "backpropagation"
```

1. **Survey.** The agent reads the repo and builds a concept map: the topics, technologies and
   components, and which ones you must understand first.
2. **You steer.** It proposes chapters in dependency order and waits for your edits:
   *"drop 7", "merge 4 and 5", "go deeper on 3", "I already know React", "I also want the
   fundamentals of backpropagation"*. If you remove something a later chapter depends on, it tells
   you and offers to keep it, fold it into a short primer, or link to it instead.
3. **Write.** Chapters are written in dependency order. Each one builds on the earlier ones and cites
   exact `file:line` ranges at the commit the book was generated from. Every code listing is checked
   to be verbatim.
4. **Read.** You get `book.pdf`, with classic book typography, a table of contents with page
   numbers, numbered sections, listings and figures, exercises with a solutions appendix, a glossary
   and an index. You also get `book.html`, a reader with a sidebar table of contents, and the
   Markdown sources.
5. **Iterate.** Revise a chapter or a single section, apply feedback comments you left in the
   Markdown, add or remove topics, switch a topic's learning mode, or pull new commits and refresh
   only the chapters that are now stale. Every change bumps the edition and keeps the old text.

## Learning modes

Each topic in the book has a mode, and you choose it at the review step:

| Mode | What the chapter teaches |
|---|---|
| `applied` (default) | How **this repo** uses the topic: why it needs it, where it lives, a walkthrough of the real code, design decisions, pitfalls and exercises. |
| `foundations+applied` | First the **fundamentals** (intuition, the formal statement with every symbol defined, a small worked example), then a **bridge table** that maps each concept to the repo's symbols and lines, e.g. `∂L/∂W → grad_w in model/train.py:142`. Then everything from `applied`. |
| `assumed` | Not taught; linked under Further reading. |

## Install

**Claude Code** (plugin marketplace):

```
/plugin marketplace add anmaciel1/repo-to-textbook
/plugin install repo-to-textbook@repo-to-textbook
```

Then run `/repo-to-textbook:book <github-url | owner/repo | local-path>`.

**Codex and other agents that read `SKILL.md` skills:** copy
`plugins/repo-to-textbook/skills/book/` into the agent's skills directory (for Codex,
`~/.codex/skills/`). The skill does not need Claude Code subagents. Without them, it follows the
role guides in `references/roles/` itself.

**Requirements:**
- `git`.
- Python 3.8+. Only the standard library is used, with nothing to `pip install`.
- For the PDF: Google Chrome, Chromium, Edge or Brave. If no browser is found, the build tells you to
  open the print-ready HTML and use *Print → Save as PDF*.

## Commands

| Command | What it does |
|---|---|
| `/repo-to-textbook:book <source> [--level beginner\|intermediate\|expert] [--mode applied\|foundations] [--focus "a, b"] [--paper letter\|a4] [--out DIR] [--ref REF]` | New book |
| `/repo-to-textbook:book resume` | Continue an interrupted run |
| `/repo-to-textbook:book revise ch04 "less code, more on sampling"` | Rewrite a chapter (`revise ch04 §3 "…"` rewrites one section) |
| `/repo-to-textbook:book revise --from-comments` | Apply `<!-- feedback: … -->` notes you left in the Markdown |
| `/repo-to-textbook:book add "the plugin system"` / `remove ch07` | Change the curriculum (with the dependency guard) |
| `/repo-to-textbook:book mode ch04 foundations` | Switch a chapter's topics to `foundations+applied` (or `applied` / `assumed`) |
| `/repo-to-textbook:book update` | Pull new commits and refresh only the chapters whose cited files changed |
| `/repo-to-textbook:book revert ch04 2` | Restore edition 2 of a chapter |
| `/repo-to-textbook:book build` | Rebuild the HTML and PDF after hand edits |

## What a book directory contains

```
micrograd-textbook/
  book.pdf              the textbook
  book.html             self-contained reader (works offline)
  chapters/*.md         source of truth; edit freely, then `build`
  curriculum.json       concept map, chapter plan, learning modes, editions
  notes/*.md            per-chapter summaries used for continuity
  resources.json        verified further-reading links
  .history/             earlier editions of each chapter
  .source/              shallow clone of the repo (remote sources only)
```

## Repository layout

```
.claude-plugin/marketplace.json           marketplace listing
plugins/repo-to-textbook/
  .claude-plugin/plugin.json
  agents/                                 repo-surveyor, chapter-writer, resource-finder
  skills/book/
    SKILL.md                              /repo-to-textbook:book entry point: the method
                                          (phases, checkpoint, rules)
    references/                           survey checklist, schema, chapter template,
                                          Markdown conventions, iteration, role guides
    scripts/                              init, curriculum checks, citation checker,
                                          stale detection, HTML/PDF build (stdlib only)
    assets/                               book template, CSS, renderer, fonts, vendored JS
tests/                                    unittest suite + tiny fixture repo and book
```

## Development

```bash
python3 -m unittest discover -s tests -v
```

The tests build a throwaway git repo and a sample book (`tests/fixtures/`), then exercise the
curriculum validation and dependency guard, the citation checker (including rejecting paraphrased
listings), editions and revert, stale detection, and the HTML and PDF builds. The PDF test is
skipped when no Chromium-based browser is installed.

To preview the sample book:

```bash
python3 -m unittest tests.test_pipeline.BuildTests.test_pdf_build   # sanity check
# or build it by hand: copy tests/fixtures/book, fill curriculum.template.json, then
python3 plugins/repo-to-textbook/skills/book/scripts/build_book.py <book-dir>
```

Third-party assets bundled with the skill are listed in
`plugins/repo-to-textbook/skills/book/assets/THIRD_PARTY.md`.

## License

MIT. See [LICENSE](LICENSE).
