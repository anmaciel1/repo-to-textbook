# Chapter template

**The repository is the subject.** A reader should finish every chapter knowing more about *this
codebase*, not only about the general topic. Generic material is allowed only:

- in a **Foundations** section, for nodes whose mode is `foundations+applied`;
- in a one-paragraph **primer** box, for nodes listed in the chapter's `primers`.

Both must point back to the code.

Write in Markdown using [markdown-conventions.md](markdown-conventions.md). Start the file with
`# <Chapter title>`. The renderer adds "Chapter N" and numbers the sections, so do not number
headings yourself.

## Main chapter, `applied` mode (the default)

Use these `##` sections, in this order. Rename a heading only when the default reads badly for the
topic. "Why tinynet needs it" is better than "Why this repo needs it".

1. **Learning objectives.** This is a bold lead-in paragraph, not a heading: `**Learning objectives.** After this chapter you will be able to:` followed by 2–4 bullets taken from the chapter's `objectives`.
   Follow it with one sentence saying which earlier chapter(s) this one builds on, linked as
   `[the forward pass](ch01-big-picture.md#the-forward-pass)`.
2. **Why <repo> needs it.** The problem this topic solves *here*: what would break or be harder
   without it. Use concrete scenarios from the code.
3. **Where it lives.** A map before the walk:
   - the files, types and functions involved, each with a `[[path:a-b]]` citation;
   - how data or control moves between them;
   - a Mermaid diagram when there are three or more moving parts. Keep it small: at most about 10 nodes.
4. **Walkthrough.** The heart of the chapter.
   - Show real code as cited listings (`lang path:a-b`), each **followed** by prose explaining it.
     Explain the lines that matter by line number ("Line 27 computes …"), not every line.
   - Keep listings to about 25 lines or fewer. Elide the irrelevant middle with `...`.
   - Use `###` subsections for distinct steps.
   - Trace one concrete example through the code, e.g. "a GET to `/items/3`".
5. **Design decisions.** The choices this code makes, the alternatives it did not take, and the
   trade-offs. If the reasoning is not documented, label it as your inference.
6. **Pitfalls.** One or more `> [!PITFALL]` boxes on mistakes that are specific to this
   implementation, e.g. ordering bugs, edge cases, configuration traps, or performance or security
   concerns you saw in the code. Leave out generic advice.
7. **Exercises.** 2–4 `> [!EXERCISE]` boxes, each followed by a `<details>` solution. Mix these kinds:
   - *predict*: "what happens if …";
   - *trace*: "which function handles …";
   - *modify*: "change X so that Y; which tests break?";
   - *explain*: "why does line N come before line M?".

   Every exercise refers to real code.
8. **Further reading.** Two short bulleted lists, each introduced by a bold label on its own line:
   - **Fundamentals:** general sources for the concepts;
   - **As used in this stack:** the docs for the exact libraries and versions the repo uses.

   Each bullet is `[Title](url): one sentence on why it is worth reading.` The PDF prints the URL
   after the title. Take the sources from `BOOK/resources.json`. Do not add URLs that are not there
   or that you have not verified.

## Main chapter, `foundations+applied` mode

Insert `## Foundations` **immediately after the learning objectives**, with these subsections:

1. `### Intuition`. Plain language and an analogy, if a good one exists. No symbols yet.
2. `### The formal statement` (or "How it works"). The precise definition, algorithm or protocol.
   For math, use KaTeX and **define every symbol** the first time it appears. Mark defined terms
   with `<dfn>`.
3. `### A worked example`. A minimal example worked by hand or in a few lines of standalone code,
   independent of the repo. Keep it small enough to check mentally.
4. `### Bridge to this repository`. **Required.** A table that maps each concept or symbol from the
   section above to this repo's identifier and a `[[path:line]]` citation:

   | Textbook symbol | In <repo> | Where |
   |---|---|---|
   | $\delta_{\text{out}}$ | `delta_out` | [[tinynet/model.py:25]] |

   From here on, **use the repo's names**, so the reader sees the theory in the code. Then continue
   with sections 2–8 of the applied template.

If several nodes in one chapter are `foundations+applied`, give each its own Foundations
subsection group, or one Foundations section that covers them in prerequisite order.

## Primers

For each node in the chapter's `primers`, add one `> [!PRIMER] <Title>` box where the idea is first
needed. A primer is one paragraph, or two at most. If the reader needs more than that, the node
should be a chapter or `foundations+applied` instead. Say so in your notes.

## Depth and length

| depth | Typical length (excluding listings) |
|---|---|
| `normal` | 1,500–3,000 words |
| `deep` | 3,000–5,500 words; more subsections, a second worked trace, harder exercises |
| Foundations section | +800–2,000 words, depending on the topic |

Adapt the explanation to `reader.level`:
- **beginner:** define terms, go slower, add more diagrams and small steps;
- **intermediate:** assume general programming fluency;
- **expert:** go faster, and spend more time on design decisions and edge cases.

## Voice and style (classic textbook)

- Write in a precise, calm, declarative voice, in the present tense. Use "we" sparingly for shared
  reasoning ("we can now see why …"). Address the reader as "you" only in exercises and objectives.
- Leave out hype, filler, emoji, exclamation marks and rhetorical openers ("Let's dive in", "In
  today's world"). Do not end with a summary that repeats the chapter. Instead, end the walkthrough
  with one paragraph on what the next chapter builds.
- Define a term before using it. Mark the defining occurrence with `<dfn>term</dfn>`, once per term
  per book, because these feed the index.
- One idea per paragraph. Use concrete before abstract: show the code, then name the pattern.
- Mark uncertainty honestly: "The code does not document why; a likely reason is …".
- Write numbers, units and identifiers exactly as they appear in the code.

## Chapter notes (`BOOK/notes/<id>.md`)

After writing a chapter, write a short notes file that later chapters and the Preface/Glossary rely on:

```
Summary: <2–3 sentences: what the chapter teaches and the main code paths it covers>
Terms introduced: <comma-separated, matching your <dfn> terms>
Symbols: <repo identifiers the chapter explains>
Open questions: <anything you could not verify, or "none">
```

Before writing a chapter, read the notes of the chapters it builds on, and **do not re-teach**
what they introduced. Refer back to them instead: "as we saw in [Chapter 2](ch02-….md)".

## Front and back matter

- **Preface** (`preface`, kind `front`, written last):
  - what the repository is and the problem it solves;
  - who the book is for (`reader.level`, plus what is assumed, with links);
  - how the book is organized, one sentence per chapter;
  - how to read citations and listings, and which commit the book tracks;
  - the learning modes used ("Chapters 3 and 5 begin with the fundamentals …").

  300–700 words, with no `##` sections unless needed.
- **Glossary** (`glossary`, kind `back`): every `<dfn>` term in the book, alphabetically, each as
  `**Term.** One- or two-sentence definition in this repo's context. See Chapter N.` Take the terms
  from `notes/*.md` and check them against the chapters.
- The **Solutions** appendix and the **Index** are generated automatically from `<details>` blocks
  and `<dfn>` terms. Do not write them.

## Quality bar (check before you finish)

- [ ] Every section that talks about code has at least one `[[path:a-b]]` citation or a cited listing.
- [ ] Every listing is verbatim apart from `...` elisions. `check_citations.py BOOK <id>` passes.
- [ ] No generic tutorial content in `applied` mode beyond the primer boxes.
- [ ] The `foundations+applied` chapters have a bridge table, and every row resolves to real code.
- [ ] Exercises refer to real code, and every exercise has a solution.
- [ ] Nothing that a prerequisite chapter taught is re-taught.
- [ ] The chapter respects the per-chapter `instructions` in `curriculum.json`, if any.
