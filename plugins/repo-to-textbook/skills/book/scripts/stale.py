#!/usr/bin/env python3
"""Detect chapters made stale by new commits in the source repository.

    stale.py <book> [--ref BRANCH_OR_TAG_OR_SHA] [--apply]

Fetches the newest commit (remote clones) or reads HEAD (local repos), diffs it
against the commit each chapter was written from, and reports the chapters
whose cited files changed. With --apply it:
  * moves the source checkout and repo.sha to the new commit,
  * marks affected chapters status=stale,
  * re-pins unaffected chapters to the new commit (their cited files are
    byte-identical, so their permalinks and line numbers stay correct).
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bookutil as bu  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("book")
    ap.add_argument("--ref")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    cur = bu.load(a.book)
    repo = cur.get("repo", {})
    src = bu.source_dir(a.book, cur)
    cloned = not os.path.isabs(repo.get("source_dir") or ".source")
    old = repo.get("sha")

    if cloned:
        ref = a.ref or repo.get("ref") or "HEAD"
        bu.git(["fetch", "--depth", "1", "--quiet", "origin", ref], cwd=src)
        new = bu.git(["rev-parse", "FETCH_HEAD"], cwd=src)
    else:
        new = bu.git(["rev-parse", (a.ref or "HEAD") + "^{commit}"], cwd=src)

    if new == old:
        print("up to date at %s" % new[:10])
        return

    changed_cache = {}

    def changed_since(base):
        if base not in changed_cache:
            ok, _ = bu.git_ok(["cat-file", "-e", base + "^{commit}"], cwd=src)
            if not ok and cloned:
                bu.git_ok(["fetch", "--depth", "1", "--quiet", "origin", base], cwd=src)
            out = bu.git(["diff", "--name-only", base, new], cwd=src)
            changed_cache[base] = set(x for x in out.split("\n") if x)
        return changed_cache[base]

    stale, fresh = [], []
    for c in cur.get("chapters", []):
        if c.get("status") not in ("written", "stale"):
            continue
        base = c.get("sha") or old
        hit = sorted(set(c.get("cites", [])) & changed_since(base))
        if hit or c.get("status") == "stale":
            stale.append((c, hit))
        else:
            fresh.append(c)

    all_changed = changed_since(old)
    print("source moved %s -> %s (%d files changed)" % (old[:10], new[:10], len(all_changed)))
    if not stale:
        print("no chapter cites a changed file")
    for c, hit in stale:
        print("STALE %s (%s): %s" % (c["id"], c.get("title", ""), ", ".join(hit) or "already stale"))

    if not a.apply:
        print("dry run; re-run with --apply to record this")
        return

    if cloned:
        bu.git(["checkout", "--quiet", "--detach", new], cwd=src)
    for c, _ in stale:
        c["status"] = "stale"
    for c in fresh:
        c["sha"] = new
    repo["sha"] = new
    cur.setdefault("changelog", []).append({
        "edition": cur.get("edition", 0), "date": bu.today(),
        "note": "Source updated to %s; %d chapter(s) stale" % (new[:10], len(stale)),
    })
    bu.save(a.book, cur)
    print("applied")


if __name__ == "__main__":
    main()
