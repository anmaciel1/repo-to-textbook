#!/usr/bin/env python3
"""Create a new book directory for a repository.

    init_book.py <github-url | owner/repo | local-path> [--out DIR] [--ref BRANCH_OR_TAG]
                 [--level beginner|intermediate|expert] [--mode applied|foundations]
                 [--focus "auth, caching"] [--paper letter|a4] [--title TITLE]

Remote repos are shallow-cloned into <book>/.source. Local paths are used in
place (the book records their current HEAD). Prints a JSON summary.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bookutil as bu  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("--out")
    ap.add_argument("--ref")
    ap.add_argument("--level", default="intermediate", choices=["beginner", "intermediate", "expert"])
    ap.add_argument("--mode", default="applied", choices=["applied", "foundations"])
    ap.add_argument("--focus", default="")
    ap.add_argument("--paper", default="letter", choices=["letter", "a4"])
    ap.add_argument("--title")
    a = ap.parse_args()

    src = a.source.strip()
    is_local = os.path.isdir(os.path.expanduser(src))
    top = None
    if not is_local and re.match(r"^[\w.-]+/[\w.-]+$", src):
        src = "https://github.com/" + src

    if is_local:
        local = os.path.abspath(os.path.expanduser(src))
        ok, _ = bu.git_ok(["rev-parse", "--is-inside-work-tree"], cwd=local)
        if not ok:
            bu.die("%s is not a git repository" % local)
        top = bu.git(["rev-parse", "--show-toplevel"], cwd=local)
        name = os.path.basename(top)
        remote = bu.git(["remote", "get-url", "origin"], cwd=top, check=False) or ""
        url = remote or top
    else:
        name = re.sub(r"\.git$", "", src.rstrip("/").split("/")[-1].split(":")[-1])
        remote = src
        url = src

    book = os.path.abspath(a.out or (name + "-textbook"))
    if os.path.exists(bu.curriculum_path(book)):
        bu.die("%s already has a curriculum.json; use resume instead of init" % book)
    for d in ("chapters", "notes", ".history", ".build"):
        os.makedirs(os.path.join(book, d), exist_ok=True)
    with open(os.path.join(book, ".gitignore"), "w") as f:
        f.write(".source/\n.build/\n")

    if is_local:
        source_dir = top
        if a.ref:
            sha = bu.git(["rev-parse", a.ref + "^{commit}"], cwd=top)
        else:
            sha = bu.git(["rev-parse", "HEAD"], cwd=top)
        dirty = bu.git(["status", "--porcelain"], cwd=top, check=False)
    else:
        source_dir = ".source"
        dest = os.path.join(book, ".source")
        if not os.path.isdir(os.path.join(dest, ".git")):
            cmd = ["clone", "--depth", "1", "--quiet"]
            if a.ref:
                cmd += ["--branch", a.ref]
            bu.git(cmd + [src, dest])
        sha = bu.git(["rev-parse", "HEAD"], cwd=dest)
        dirty = ""

    web_url, host = bu.web_url_for(remote)
    focus = [t.strip() for t in a.focus.split(",") if t.strip()]
    cur = {
        "schema": bu.SCHEMA_VERSION,
        "book": {"title": a.title or name, "subtitle": "A Guided Textbook"},
        "repo": {
            "name": name,
            "url": url,
            "web_url": web_url,
            "host": host,
            "ref": a.ref,
            "sha": sha,
            "source_dir": source_dir,
            "summary": "",
        },
        "edition": 0,
        "paper": a.paper,
        "reader": {
            "level": a.level,
            "default_mode": "foundations+applied" if a.mode == "foundations" else "applied",
            "focus": focus,
            "assumed": [],
        },
        "nodes": [],
        "chapters": [],
        "suggestions": [],
        "changelog": [],
    }
    bu.save(book, cur)

    print(json.dumps({
        "book": book,
        "source": bu.source_dir(book, cur),
        "sha": sha,
        "web_url": web_url,
        "warning": "local repo has uncommitted changes; citations use HEAD" if dirty else None,
    }, indent=2))


if __name__ == "__main__":
    main()
