#!/usr/bin/env python3
"""Deterministic helpers for curriculum.json. The agent decides; these check and bookkeep.

    curriculum.py validate <book>             schema, cycles, order, dependency guard (exit 1 on errors)
    curriculum.py order    <book> [--write]   dependency-respecting chapter order (stable)
    curriculum.py outline  <book>             render the review-checkpoint outline (Markdown)
    curriculum.py approve  <book>             mark kept, proposed chapters as approved
    curriculum.py waves    <book>             chapters to write, grouped so each wave's prereqs are done
    curriculum.py snapshot <book> <id>        save current chapter to .history/ before overwriting
    curriculum.py record   <book> <id>...     after writing: store hash, cites, sha, status=written
    curriculum.py bump     <book> --note TXT  new edition + changelog entry
    curriculum.py edited   <book>             chapters hand-edited since last record (exit 1 if any)
    curriculum.py revert   <book> <id> <edition>
    curriculum.py comments <book>             list <!-- feedback: ... --> notes left in chapters
"""

import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bookutil as bu  # noqa: E402

DIFFICULTY = {1: "introductory", 2: "intermediate", 3: "advanced"}
MODE_LABEL = {"applied": "applied", "foundations+applied": "fundamentals + applied", "assumed": "assumed"}


# ------------------------------------------------------------------ validate

def primed_nodes(cur):
    """Nodes covered as a primer box inside some kept chapter."""
    out = set()
    for c in cur.get("chapters", []):
        if bu.kept(c):
            out.update(c.get("primers", []))
    return out


def check(cur):
    errors, warnings = [], []
    nodes = bu.node_index(cur)
    chapters = cur.get("chapters", [])

    ids = [n.get("id") for n in cur.get("nodes", [])]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append("duplicate node id '%s'" % dup)
    cids = [c.get("id") for c in chapters]
    for dup in sorted({i for i in cids if cids.count(i) > 1}):
        errors.append("duplicate chapter id '%s'" % dup)

    for n in cur.get("nodes", []):
        if n.get("mode", "applied") not in bu.MODES:
            errors.append("node '%s': mode must be one of %s" % (n["id"], ", ".join(bu.MODES)))
        for p in n.get("prereqs", []):
            if p not in nodes:
                errors.append("node '%s': unknown prereq '%s'" % (n["id"], p))

    for c in chapters:
        if c.get("kind", "chapter") not in bu.KINDS:
            errors.append("chapter '%s': kind must be one of %s" % (c["id"], ", ".join(bu.KINDS)))
        if c.get("status", "proposed") not in bu.STATUSES:
            errors.append("chapter '%s': status must be one of %s" % (c["id"], ", ".join(bu.STATUSES)))
        for nid in c.get("nodes", []):
            if nid not in nodes:
                errors.append("chapter '%s': unknown node '%s'" % (c["id"], nid))
        for nid in c.get("primers", []):
            if nid not in nodes:
                errors.append("chapter '%s': unknown primer node '%s'" % (c["id"], nid))
        if c.get("kind", "chapter") == "chapter" and bu.kept(c) and not c.get("nodes"):
            warnings.append("chapter '%s' has no topic nodes" % c["id"])

    # node-level cycles
    state = {}

    def visit(nid, stack):
        state[nid] = 1
        for p in nodes.get(nid, {}).get("prereqs", []):
            if p not in nodes:
                continue
            if state.get(p) == 1:
                cyc = stack[stack.index(p):] + [p] if p in stack else [nid, p]
                errors.append("prerequisite cycle: %s" % " -> ".join(cyc))
            elif not state.get(p):
                visit(p, stack + [p])
        state[nid] = 2

    for nid in nodes:
        if not state.get(nid):
            visit(nid, [nid])

    # dependency guard: every prereq of a kept chapter must be taught earlier,
    # assumed (links only), or folded into that chapter as a primer.
    owner = bu.node_owner(cur)
    position = {c["id"]: i for i, c in enumerate(chapters)}
    guard = []
    for c in chapters:
        if not bu.kept(c):
            continue
        for nid in c.get("nodes", []):
            for p in nodes.get(nid, {}).get("prereqs", []):
                pn = nodes.get(p)
                if not pn or pn.get("mode") == "assumed" or p in c.get("primers", []):
                    continue
                o = owner.get(p)
                if o is None:
                    if any(g["chapter"] == c["id"] and g["needs"] == p for g in guard):
                        continue
                    dropped_in = [d["id"] for d in chapters if not bu.kept(d) and p in d.get("nodes", [])]
                    guard.append({
                        "chapter": c["id"], "needs": p, "needs_title": pn.get("title", p),
                        "dropped": dropped_in[0] if dropped_in else None,
                    })
                elif o != c["id"] and position[o] > position[c["id"]]:
                    errors.append("order: '%s' comes before '%s', which teaches its prerequisite '%s' "
                                  "(run: curriculum.py order <book> --write)" % (c["id"], o, p))
    for g in guard:
        where = ("taught only in dropped chapter '%s'" % g["dropped"]) if g["dropped"] else "not taught in any chapter"
        errors.append("guard: '%s' needs '%s' (%s), which is %s. Options: keep that chapter; "
                      "add it to %s.primers; or set its mode to 'assumed' (links only)"
                      % (g["chapter"], g["needs"], g["needs_title"], where, g["chapter"]))

    taught = set(owner) | primed_nodes(cur)
    prereq_of_kept = set()
    for c in chapters:
        if bu.kept(c):
            for nid in c.get("nodes", []):
                prereq_of_kept.update(nodes.get(nid, {}).get("prereqs", []))
    for nid, n in nodes.items():
        if n.get("mode") != "assumed" and nid not in taught and nid not in prereq_of_kept:
            warnings.append("node '%s' (%s) is not taught by any kept chapter" % (nid, n.get("title", nid)))

    return errors, warnings, guard


def cmd_validate(a):
    cur = bu.load(a.book)
    errors, warnings, _ = check(cur)
    for w in warnings:
        print("warning: " + w)
    for e in errors:
        print("ERROR: " + e)
    if not errors:
        print("ok: %d nodes, %d chapters (%d kept)" % (
            len(cur.get("nodes", [])), len(cur.get("chapters", [])),
            sum(1 for c in cur.get("chapters", []) if bu.kept(c))))
    sys.exit(1 if errors else 0)


# ------------------------------------------------------------------ order

def compute_order(cur):
    chapters = cur.get("chapters", [])
    by_id = {c["id"]: c for c in chapters}
    deps = bu.chapter_deps(cur)
    front = [c["id"] for c in chapters if bu.kept(c) and c.get("kind") == "front"]
    main = [c["id"] for c in chapters if bu.kept(c) and c.get("kind", "chapter") == "chapter"]
    back = [c["id"] for c in chapters if bu.kept(c) and c.get("kind") == "back"]
    dropped = [c["id"] for c in chapters if not bu.kept(c)]
    ordered, cycle = bu.topo_order(main, deps)
    if cycle:
        bu.die("chapter dependency cycle among: %s (merge these chapters or break a prereq)" % ", ".join(cycle), 1)
    return [by_id[i] for i in front + ordered + back + dropped]


def cmd_order(a):
    cur = bu.load(a.book)
    new = compute_order(cur)
    old_ids = [c["id"] for c in cur.get("chapters", [])]
    new_ids = [c["id"] for c in new]
    for i, cid in enumerate(new_ids):
        mark = "" if i < len(old_ids) and old_ids[i] == cid else "  (moved)"
        print("%2d. %s%s" % (i + 1, cid, mark))
    if a.write and new_ids != old_ids:
        cur["chapters"] = new
        bu.save(a.book, cur)
        print("order written")
    elif new_ids == old_ids:
        print("order already respects dependencies")


# ------------------------------------------------------------------ outline

def cmd_outline(a):
    cur = bu.load(a.book)
    nodes = bu.node_index(cur)
    nums = bu.chapter_numbers(cur)
    chapters = cur.get("chapters", [])
    deps = bu.chapter_deps(cur)
    owner = bu.node_owner(cur)
    r = cur.get("repo", {})
    rd = cur.get("reader", {})
    out = []
    out.append("# Proposed curriculum: %s" % cur.get("book", {}).get("title", r.get("name", "")))
    out.append("")
    out.append("Repository: %s @ `%s`  " % (r.get("url", ""), (r.get("sha") or "")[:10]))
    out.append("Reader level: %s · default mode: %s%s" % (
        rd.get("level", "intermediate"), MODE_LABEL.get(rd.get("default_mode", "applied")),
        (" · focus: " + ", ".join(rd["focus"])) if rd.get("focus") else ""))
    if r.get("summary"):
        out.append("")
        out.append("> " + r["summary"])
    out.append("")

    def chap_line(c):
        tag = c.get("tag", "core")
        diff = DIFFICULTY.get(c.get("difficulty"), "")
        meta = " · ".join(x for x in [tag, diff, ("deep" if c.get("depth") == "deep" else "")] if x)
        label = ("%d." % nums[c["id"]]) if c["id"] in nums else ("-" if c.get("kind") != "chapter" else "x")
        status = "" if c.get("status") in ("proposed", "approved", None) else " [%s]" % c["status"]
        lines = ["%s **%s** `%s` (%s)%s" % (label, c.get("title", c["id"]), c["id"], meta, status)]
        if c.get("summary"):
            lines.append("   %s" % c["summary"])
        topics = []
        for nid in c.get("nodes", []):
            n = nodes.get(nid, {})
            topics.append("%s *(%s)*" % (n.get("title", nid), MODE_LABEL.get(n.get("mode", "applied"), "applied")))
        if topics:
            lines.append("   Topics: " + "; ".join(topics))
        need = sorted(deps.get(c["id"], []), key=lambda x: nums.get(x, 999))
        if need:
            lines.append("   Builds on: " + ", ".join(
                "%s (ch. %s)" % (x, nums[x]) if x in nums else x for x in need))
        if c.get("primers"):
            lines.append("   Primers: " + ", ".join(nodes.get(p, {}).get("title", p) for p in c["primers"]))
        if c.get("files"):
            lines.append("   Key files: " + ", ".join("`%s`" % f for f in c["files"][:5]) +
                         (" …" if len(c["files"]) > 5 else ""))
        return lines

    for kind, heading in (("front", "Front matter"), ("chapter", "Chapters"), ("back", "Back matter")):
        group = [c for c in chapters if bu.kept(c) and c.get("kind", "chapter") == kind]
        if not group:
            continue
        out.append("## " + heading)
        out.append("")
        for c in group:
            out.extend(chap_line(c))
            out.append("")

    dropped = [c for c in chapters if not bu.kept(c)]
    if dropped:
        out.append("## Dropped")
        out.append("")
        for c in dropped:
            out.append("- ~~%s~~ `%s`" % (c.get("title", c["id"]), c["id"]))
        out.append("")

    assumed = [n for n in cur.get("nodes", []) if n.get("mode") == "assumed"]
    if assumed:
        out.append("## Assumed knowledge (linked, not taught)")
        out.append("")
        out.append(", ".join(n.get("title", n["id"]) for n in assumed))
        out.append("")

    primed = primed_nodes(cur)
    untaught = [n for n in cur.get("nodes", [])
                if n["id"] not in owner and n["id"] not in primed and n.get("mode") != "assumed"]
    if cur.get("suggestions") or untaught:
        out.append("## Also spotted (not in the book yet)")
        out.append("")
        for s in cur.get("suggestions", []):
            out.append("- **%s**: %s" % (s.get("title", ""), s.get("why", "")))
        for n in untaught:
            out.append("- **%s** (`%s`)" % (n.get("title", n["id"]), n["id"]))
        out.append("")

    main = [c for c in chapters if bu.kept(c) and c.get("kind", "chapter") == "chapter"]
    if any(deps.get(c["id"]) for c in main):
        out.append("## Dependency graph")
        out.append("")
        out.append("```mermaid")
        out.append("graph TD")
        for c in main:
            t = c.get("title", c["id"]).replace('"', "'")
            out.append('  %s["%s. %s"]' % (c["id"].replace("-", "_"), nums.get(c["id"], "?"), t))
        for c in main:
            for d in sorted(deps.get(c["id"], [])):
                out.append("  %s --> %s" % (d.replace("-", "_"), c["id"].replace("-", "_")))
        out.append("```")
        out.append("")

    errors, warnings, _ = check(cur)
    if errors or warnings:
        out.append("## Needs attention")
        out.append("")
        for e in errors:
            out.append("- " + e)
        for w in warnings:
            out.append("- (minor) " + w)
        out.append("")
    print("\n".join(out))


# ------------------------------------------------------------------ writing bookkeeping

def cmd_approve(a):
    cur = bu.load(a.book)
    errors, _, _ = check(cur)
    if errors:
        for e in errors:
            print("ERROR: " + e)
        bu.die("fix the errors above before approving", 1)
    n = 0
    for c in cur.get("chapters", []):
        if bu.kept(c) and c.get("status", "proposed") == "proposed":
            c["status"] = "approved"
            n += 1
    bu.save(a.book, cur)
    print("approved %d chapters" % n)


def cmd_waves(a):
    cur = bu.load(a.book)
    deps = bu.chapter_deps(cur)
    chapters = [c for c in cur.get("chapters", []) if bu.kept(c)]
    todo = [c["id"] for c in chapters if c.get("kind", "chapter") == "chapter" and c.get("status") != "written"]
    done = {c["id"] for c in chapters if c.get("status") == "written"}
    waves = []
    while todo:
        wave = [cid for cid in todo if all(d in done for d in deps.get(cid, ()))]
        if not wave:
            bu.die("cannot schedule %s: unresolved dependencies (run validate)" % ", ".join(todo), 1)
        waves.append(wave)
        done.update(wave)
        todo = [cid for cid in todo if cid not in wave]
    last = [c["id"] for c in chapters if c.get("kind") in ("front", "back") and c.get("status") != "written"]
    if last:
        waves.append(last)
    if not waves:
        print("nothing to write: all kept chapters are written")
    for i, w in enumerate(waves, 1):
        print("wave %d: %s" % (i, " ".join(w)))


def find_chapter(cur, cid):
    for c in cur.get("chapters", []):
        if c["id"] == cid:
            return c
    bu.die("unknown chapter id '%s'" % cid)


def snapshot(book, cur, cid):
    src = bu.chapter_file(book, cid)
    if not os.path.exists(src):
        return None
    os.makedirs(os.path.join(book, ".history"), exist_ok=True)
    base = os.path.join(book, ".history", "%s.e%d" % (cid, cur.get("edition", 0)))
    dst = base + ".md"
    k = 2
    while os.path.exists(dst):
        if bu.sha256_file(dst) == bu.sha256_file(src):
            return dst
        dst = "%s-%d.md" % (base, k)
        k += 1
    shutil.copy2(src, dst)
    return dst


def cmd_snapshot(a):
    cur = bu.load(a.book)
    find_chapter(cur, a.id)
    dst = snapshot(a.book, cur, a.id)
    print("saved %s" % dst if dst else "nothing to snapshot (chapter not written yet)")


def record(book, cur, cid):
    c = find_chapter(cur, cid)
    path = bu.chapter_file(book, cid)
    if not os.path.exists(path):
        bu.die("%s does not exist" % path)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    c["hash"] = bu.sha256_file(path)
    c["cites"] = bu.cited_paths(text)
    c["sha"] = cur.get("repo", {}).get("sha")
    c["status"] = "written"
    if c.get("kind", "chapter") == "chapter" and not os.path.exists(bu.note_file(book, cid)):
        print("warning: notes/%s.md missing (later chapters rely on it for continuity)" % cid)
    return c


def cmd_record(a):
    cur = bu.load(a.book)
    for cid in a.ids:
        c = record(a.book, cur, cid)
        print("recorded %s: %d cited files" % (cid, len(c["cites"])))
    bu.save(a.book, cur)


def cmd_bump(a):
    cur = bu.load(a.book)
    cur["edition"] = int(cur.get("edition", 0)) + 1
    cur.setdefault("changelog", []).append({"edition": cur["edition"], "date": bu.today(), "note": a.note})
    bu.save(a.book, cur)
    print("edition %d" % cur["edition"])


def cmd_edited(a):
    cur = bu.load(a.book)
    hits = []
    for c in cur.get("chapters", []):
        p = bu.chapter_file(a.book, c["id"])
        if c.get("hash") and os.path.exists(p) and bu.sha256_file(p) != c["hash"]:
            hits.append(c["id"])
    for h in hits:
        print("hand-edited: %s" % h)
    if not hits:
        print("no hand edits since last record")
    sys.exit(1 if hits else 0)


def cmd_revert(a):
    cur = bu.load(a.book)
    find_chapter(cur, a.id)
    hist = os.path.join(a.book, ".history")
    cands = sorted(f for f in os.listdir(hist) if f.startswith("%s.e%d" % (a.id, a.edition)) and f.endswith(".md")) \
        if os.path.isdir(hist) else []
    if not cands:
        bu.die("no saved copy of %s at edition %d in .history/" % (a.id, a.edition))
    snapshot(a.book, cur, a.id)
    shutil.copy2(os.path.join(hist, cands[-1]), bu.chapter_file(a.book, a.id))
    record(a.book, cur, a.id)
    cur["edition"] = int(cur.get("edition", 0)) + 1
    cur.setdefault("changelog", []).append({"edition": cur["edition"], "date": bu.today(),
                                            "note": "Reverted %s to edition %d" % (a.id, a.edition)})
    bu.save(a.book, cur)
    print("reverted %s to %s (now edition %d)" % (a.id, cands[-1], cur["edition"]))


def cmd_comments(a):
    cur = bu.load(a.book)
    total = 0
    for c in cur.get("chapters", []):
        p = bu.chapter_file(a.book, c["id"])
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            text = f.read()
        for m in bu.FEEDBACK_RE.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            print("%s:%d: %s" % (c["id"], line, " ".join(m.group(1).split())))
            total += 1
    if not total:
        print("no feedback comments found")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    sub.required = True
    for name, fn in (("validate", cmd_validate), ("outline", cmd_outline), ("approve", cmd_approve),
                     ("waves", cmd_waves), ("edited", cmd_edited), ("comments", cmd_comments)):
        p = sub.add_parser(name)
        p.add_argument("book")
        p.set_defaults(fn=fn)
    p = sub.add_parser("order")
    p.add_argument("book")
    p.add_argument("--write", action="store_true")
    p.set_defaults(fn=cmd_order)
    p = sub.add_parser("snapshot")
    p.add_argument("book")
    p.add_argument("id")
    p.set_defaults(fn=cmd_snapshot)
    p = sub.add_parser("record")
    p.add_argument("book")
    p.add_argument("ids", nargs="+")
    p.set_defaults(fn=cmd_record)
    p = sub.add_parser("bump")
    p.add_argument("book")
    p.add_argument("--note", required=True)
    p.set_defaults(fn=cmd_bump)
    p = sub.add_parser("revert")
    p.add_argument("book")
    p.add_argument("id")
    p.add_argument("edition", type=int)
    p.set_defaults(fn=cmd_revert)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
