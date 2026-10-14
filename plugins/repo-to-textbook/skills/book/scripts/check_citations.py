#!/usr/bin/env python3
"""Verify every code citation in the book against the commit it claims.

    check_citations.py <book> [chapter-id ...]

Checks, per chapter (at the chapter's recorded sha, else the repo sha):
  * [[path:a-b]] and cited listings point at files that exist at that commit
    (notebook cells: [[demo.ipynb#cell-8:2-5]], lines counted inside the cell)
  * line ranges are inside the file
  * cited listings are verbatim: every non-elided excerpt line appears, in
    order, inside the cited range (whitespace-insensitive; "..." lines elide)
  * links to other chapters (chNN.md) point at chapters that exist
Exit status 1 if any error is found.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bookutil as bu  # noqa: E402

ELISION_RE = re.compile(r"^(?:#|//|--|;|/\*|\*|<!--|%)?\s*(?:\.\.\.|…)")
XREF_RE = re.compile(r"\]\((?:\./)?(?:chapters/)?([\w.-]+?)\.md(?:#[^)]*)?\)")


def norm(line):
    return " ".join(line.split())


def main():
    if len(sys.argv) < 2:
        bu.die((__doc__ or "").strip())
    book = sys.argv[1]
    only = set(sys.argv[2:])
    cur = bu.load(book)
    src = bu.source_dir(book, cur)
    if not os.path.isdir(src):
        bu.die("source checkout not found at %s" % src)
    repo_sha = cur.get("repo", {}).get("sha")
    chapter_ids = {c["id"] for c in cur.get("chapters", [])}
    cache = {}

    def file_lines(sha, path):
        key = (sha, path)
        if key not in cache:
            ok, out = bu.git_ok(["show", "%s:%s" % (sha, path)], cwd=src)
            cache[key] = out.decode("utf-8", "replace").split("\n") if ok else None
        return cache[key]

    errors = 0
    checked = 0
    for c in cur.get("chapters", []):
        if only and c["id"] not in only:
            continue
        path = bu.chapter_file(book, c["id"])
        if not os.path.exists(path):
            continue
        sha = c.get("sha") or repo_sha
        with open(path, encoding="utf-8") as f:
            text = f.read()

        problems = []
        for cite in bu.parse_citations(text):
            checked += 1
            p = cite["path"][2:] if cite["path"].startswith("./") else cite["path"]
            fpath, cell = bu.split_cell_ref(p)
            lines = file_lines(sha, fpath)
            where = "%s.md:%d" % (c["id"], cite["line"])
            if lines is None:
                problems.append("%s: %s does not exist at %s" % (where, fpath, (sha or "?")[:10]))
                continue
            if cell is not None:
                lines = bu.notebook_cell_lines("\n".join(lines), cell)
                if lines is None:
                    problems.append("%s: %s has no cell %d" % (where, fpath, cell))
                    continue
            n = len(lines) - (1 if lines and lines[-1] == "" else 0)
            a, b = cite["start"], cite["end"]
            if a is not None:
                if a < 1 or b < a or b > n:
                    problems.append("%s: %s:%s-%s is outside the file (1-%d)" % (where, p, a, b, n))
                    continue
            if cite["kind"] == "listing":
                window = lines[(a - 1 if a else 0):(b if b else n)]
                hay = [norm(x) for x in window]
                k = 0
                missing = None
                for ex in cite["excerpt"]:
                    s = norm(ex)
                    if not s or ELISION_RE.match(s):
                        continue
                    while k < len(hay) and hay[k] != s:
                        k += 1
                    if k == len(hay):
                        missing = ex.strip()
                        break
                    k += 1
                if missing is not None:
                    problems.append("%s: listing does not match %s%s; first unmatched line: %r" % (
                        where, p, (":%d-%d" % (a, b)) if a else "", missing[:100]))
        for m in XREF_RE.finditer(text):
            if m.group(1) not in chapter_ids:
                line = text.count("\n", 0, m.start()) + 1
                problems.append("%s.md:%d: link to unknown chapter '%s'" % (c["id"], line, m.group(1)))

        for pr in problems:
            print("ERROR " + pr)
        errors += len(problems)

    print("%d citations checked, %d problem%s" % (checked, errors, "" if errors == 1 else "s"))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
