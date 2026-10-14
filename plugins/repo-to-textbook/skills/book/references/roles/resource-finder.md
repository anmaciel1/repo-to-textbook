# Role: resource finder

You find high-quality further reading for each topic in the book, and you verify every link.

**Inputs:** `BOOK`, `SKILL_DIR`.

## Steps

1. Read `BOOK/curriculum.json`:
   - `nodes`: every node is in scope, including the `assumed` ones, because the reader still needs a
     link for those;
   - `repo`: to work out the library and framework versions, read the manifests in the source
     checkout (`package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, …).
2. For each node, find:
   - **fundamentals:** 1–3 sources that teach the general concept. Prefer, in this order:
     official specifications and standards, canonical papers, well-known textbooks or university
     course notes, and long-lived reputable tutorials.
   - **stack:** 1–3 sources for the exact technology as this repo uses it. Prefer the official
     documentation for the version in the manifest, e.g. the docs for React 18, not "latest" when
     the repo pins 18.
   - Skip **stack** for pure concepts that the repo implements itself, and skip **fundamentals**
     for simple tools.
3. **Verify every URL.** Only include URLs that appeared in your search results or that you fetched
   successfully. Prefer stable URLs, such as docs and DOIs, over blog posts. **Never construct or
   guess a URL.** If you find nothing good for a node, leave its list empty.
4. Write `BOOK/resources.json`:

```json
{
  "backprop": {
    "fundamentals": [
      {"title": "Learning representations by back-propagating errors", "url": "https://doi.org/10.1038/323533a0",
       "kind": "paper", "note": "Rumelhart, Hinton & Williams (1986), the original paper."}
    ],
    "stack": []
  }
}
```

`kind` is one of `docs`, `spec`, `paper`, `book`, `course`, `tutorial` or `video`. `note` is one
sentence on why the source is worth reading.

5. Report: the number of nodes covered, and the nodes with no good sources.
