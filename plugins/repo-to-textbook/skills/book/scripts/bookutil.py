"""Shared helpers for the repo-to-textbook scripts (stdlib only, Python 3.8+)."""

import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
from typing import NoReturn

SCHEMA_VERSION = 1
MODES = ("applied", "foundations+applied", "assumed")
KINDS = ("front", "chapter", "back")
STATUSES = ("proposed", "approved", "dropped", "written", "stale")

# [[path]] / [[path:10]] / [[path:10-20]]
CITE_INLINE_RE = re.compile(r"\[\[([^\s\]:]+?)(?::(\d+)(?:-(\d+))?)?\]\]")
# opening fence: ```lang path:10-20 "caption"
FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})\s*([^\s`]*)\s*(.*)$")
CITE_TOKEN_RE = re.compile(r"^([^\s\]:]+?)(?::(\d+)(?:-(\d+))?)?$")
FEEDBACK_RE = re.compile(r"<!--\s*feedback:\s*(.*?)\s*-->", re.S | re.I)


def die(msg, code=2) -> NoReturn:
    sys.stderr.write("error: " + msg + "\n")
    sys.exit(code)


def today():
    return datetime.date.today().isoformat()


# ------------------------------------------------------------------ curriculum

def curriculum_path(book):
    return os.path.join(book, "curriculum.json")


def load(book):
    path = curriculum_path(book)
    if not os.path.exists(path):
        die("no curriculum.json in %s (run init_book.py first)" % book)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(book, cur):
    path = curriculum_path(book)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cur, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def chapter_file(book, chapter_id):
    return os.path.join(book, "chapters", chapter_id + ".md")


def note_file(book, chapter_id):
    return os.path.join(book, "notes", chapter_id + ".md")


def kept(chapter):
    return chapter.get("status") != "dropped"


def chapter_numbers(cur):
    """Number main chapters by position among kept chapters (stable across partial builds)."""
    nums = {}
    n = 0
    for ch in cur.get("chapters", []):
        if ch.get("kind", "chapter") == "chapter" and kept(ch):
            n += 1
            nums[ch["id"]] = n
    return nums


def node_index(cur):
    return {n["id"]: n for n in cur.get("nodes", [])}


def node_owner(cur):
    """node id -> id of the kept chapter that teaches it (first wins)."""
    owner = {}
    for ch in cur.get("chapters", []):
        if not kept(ch):
            continue
        for nid in ch.get("nodes", []):
            owner.setdefault(nid, ch["id"])
    return owner


def chapter_deps(cur):
    """chapter id -> set of kept chapter ids it depends on (via node prereqs)."""
    nodes = node_index(cur)
    owner = node_owner(cur)
    deps = {}
    for ch in cur.get("chapters", []):
        if not kept(ch):
            continue
        d = set()
        for nid in ch.get("nodes", []):
            for p in nodes.get(nid, {}).get("prereqs", []):
                pn = nodes.get(p)
                if pn and pn.get("mode") == "assumed":
                    continue
                o = owner.get(p)
                if o and o != ch["id"]:
                    d.add(o)
        deps[ch["id"]] = d
    return deps


def topo_order(ids, deps):
    """Stable Kahn sort: keeps the given order wherever dependencies allow.
    Returns (order, cycle_members)."""
    remaining = list(ids)
    done = []
    placed = set()
    while remaining:
        progress = False
        for cid in remaining:
            if all(d in placed or d not in ids for d in deps.get(cid, ())):
                done.append(cid)
                placed.add(cid)
                remaining.remove(cid)
                progress = True
                break
        if not progress:
            return done, remaining
    return done, []


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


# ------------------------------------------------------------------ citations

def parse_citations(text):
    """Return list of dicts: {path, start, end, line, kind ('inline'|'listing'), excerpt}."""
    out = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        m = FENCE_RE.match(line)
        if m:
            fence = m.group(2)
            lang = m.group(3)
            rest = m.group(4).strip()
            body = []
            j = i + 1
            while j < len(lines):
                if lines[j].strip().startswith(fence[0] * len(fence)) and lines[j].strip().strip(fence[0]) == "":
                    break
                body.append(lines[j])
                j += 1
            if lang.lower() != "mermaid" and rest:
                tok = rest.split()[0]
                cm = CITE_TOKEN_RE.match(tok)
                if cm and ("/" in cm.group(1) or "." in cm.group(1)) and not tok.startswith("http"):
                    out.append({
                        "path": cm.group(1),
                        "start": int(cm.group(2)) if cm.group(2) else None,
                        "end": int(cm.group(3)) if cm.group(3) else (int(cm.group(2)) if cm.group(2) else None),
                        "line": i + 1,
                        "kind": "listing",
                        "excerpt": body,
                    })
            i = j + 1
            continue
        for cm in CITE_INLINE_RE.finditer(line):
            if "/" not in cm.group(1) and "." not in cm.group(1):
                continue
            start = int(cm.group(2)) if cm.group(2) else None
            out.append({
                "path": cm.group(1),
                "start": start,
                "end": int(cm.group(3)) if cm.group(3) else start,
                "line": i + 1,
                "kind": "inline",
                "excerpt": None,
            })
        i += 1
    return out


CELL_RE = re.compile(r"^(.+\.ipynb)#cell-(\d+)$")


def split_cell_ref(path):
    """'demo.ipynb#cell-8' -> ('demo.ipynb', 8); other paths -> (path, None)."""
    m = CELL_RE.match(path)
    return (m.group(1), int(m.group(2))) if m else (path, None)


def notebook_cell_lines(nb_text, n):
    """Source lines of the n-th cell (1-based, all cell types), or None."""
    try:
        cells = json.loads(nb_text).get("cells", [])
    except ValueError:
        return None
    if n < 1 or n > len(cells):
        return None
    src = cells[n - 1].get("source", "")
    src = "".join(src) if isinstance(src, list) else src
    return src.split("\n")


def cited_paths(text):
    seen = []
    for c in parse_citations(text):
        p = c["path"][2:] if c["path"].startswith("./") else c["path"]
        p = split_cell_ref(p)[0]
        if p not in seen:
            seen.append(p)
    return seen


# ------------------------------------------------------------------ git

def git(args, cwd=None, check=True):
    r = subprocess.run(["git"] + args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and r.returncode != 0:
        die("git %s failed: %s" % (" ".join(args), r.stderr.decode("utf-8", "replace").strip()))
    return r.stdout.decode("utf-8", "replace").strip()


def git_ok(args, cwd=None):
    r = subprocess.run(["git"] + args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return r.returncode == 0, r.stdout


def source_dir(book, cur):
    sd = cur.get("repo", {}).get("source_dir") or ".source"
    return sd if os.path.isabs(sd) else os.path.normpath(os.path.join(book, sd))


def web_url_for(remote):
    """Map a git remote to (web_url, host) for permalinks; (None, None) if unknown."""
    if not remote:
        return None, None
    r = remote.strip()
    m = re.match(r"^git@([^:]+):(.+?)(?:\.git)?/?$", r)
    if m:
        host, path = m.group(1), m.group(2)
    else:
        m = re.match(r"^(?:https?|ssh|git)://(?:[^@/]+@)?([^/:]+)(?::\d+)?/(.+?)(?:\.git)?/?$", r)
        if not m:
            return None, None
        host, path = m.group(1), m.group(2)
    kind = "gitlab" if "gitlab" in host else ("github" if "github" in host else None)
    if kind is None:
        return None, None
    return "https://%s/%s" % (host, path), kind
