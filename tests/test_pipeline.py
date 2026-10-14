"""End-to-end tests for the repo-to-textbook scripts (stdlib unittest).

    python3 -m unittest discover -s tests -v

Builds a throwaway git repo from tests/fixtures/source and a book from
tests/fixtures/book, then exercises validation, the dependency guard,
citation checking, editions, stale detection and the HTML/PDF build.
The PDF test is skipped when no Chrome/Chromium is installed.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "plugins", "repo-to-textbook", "skills", "book", "scripts")
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
sys.path.insert(0, SCRIPTS)
import bookutil as bu  # noqa: E402
import build_book  # noqa: E402

GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t")


def run(script, *args, check=True):
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, script)] + list(args),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if check and r.returncode != 0:
        raise AssertionError("%s %s failed (%d):\n%s" % (script, " ".join(args), r.returncode, r.stdout))
    return r


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def git(cwd, *args):
    return subprocess.run(["git"] + list(args), cwd=cwd, env=GIT_ENV, check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()


class BookTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="r2t-test-")
        self.src = os.path.join(self.tmp, "src")
        self.book = os.path.join(self.tmp, "book")
        shutil.copytree(os.path.join(FIXTURES, "source"), self.src)
        shutil.copytree(os.path.join(FIXTURES, "book"), self.book)
        git(self.src, "init", "-q")
        git(self.src, "add", "-A")
        git(self.src, "commit", "-qm", "init")
        self.sha = git(self.src, "rev-parse", "HEAD")
        with open(os.path.join(self.book, "curriculum.template.json")) as f:
            text = f.read().replace("__SHA__", self.sha).replace("__SOURCE__", self.src)
        with open(os.path.join(self.book, "curriculum.json"), "w") as f:
            f.write(text)
        run("curriculum.py", "record", self.book, "preface", "ch01-big-picture", "ch02-backpropagation", "glossary")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cur(self):
        return bu.load(self.book)

    def edit_cur(self, fn):
        cur = self.cur()
        fn(cur)
        bu.save(self.book, cur)

    def chapter(self, cid):
        return os.path.join(self.book, "chapters", cid + ".md")

    def append(self, cid, text):
        with open(self.chapter(cid), "a") as f:
            f.write(text)


class CurriculumTests(BookTestCase):
    def test_fixture_validates(self):
        r = run("curriculum.py", "validate", self.book)
        self.assertIn("ok:", r.stdout)

    def test_outline_lists_modes_and_graph(self):
        out = run("curriculum.py", "outline", self.book).stdout
        self.assertIn("fundamentals + applied", out)
        self.assertIn("```mermaid", out)
        self.assertIn("Bias terms", out)
        self.assertNotIn("Chain rule** (`chain-rule`)", out, "primer-covered node must not be 'also spotted'")

    def test_guard_fires_when_prerequisite_dropped(self):
        def drop(cur):
            cur["chapters"][1]["status"] = "dropped"
        self.edit_cur(drop)
        r = run("curriculum.py", "validate", self.book, check=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("guard: 'ch02-backpropagation' needs 'forward-pass'", r.stdout)

    def test_guard_resolved_by_primer_or_assumed(self):
        def primer(cur):
            cur["chapters"][1]["status"] = "dropped"
            cur["chapters"][2]["primers"] += ["forward-pass", "architecture"]
        self.edit_cur(primer)
        run("curriculum.py", "validate", self.book)

        def assumed(cur):
            cur["chapters"][2]["primers"] = ["chain-rule"]
            for n in cur["nodes"]:
                if n["id"] in ("forward-pass", "architecture"):
                    n["mode"] = "assumed"
        self.edit_cur(assumed)
        run("curriculum.py", "validate", self.book)

    def test_order_fixes_dependency_violations(self):
        def swap(cur):
            ch = cur["chapters"]
            ch[1], ch[2] = ch[2], ch[1]
        self.edit_cur(swap)
        r = run("curriculum.py", "validate", self.book, check=False)
        self.assertIn("order:", r.stdout)
        run("curriculum.py", "order", self.book, "--write")
        ids = [c["id"] for c in self.cur()["chapters"]]
        self.assertLess(ids.index("ch01-big-picture"), ids.index("ch02-backpropagation"))
        run("curriculum.py", "validate", self.book)

    def test_cycle_detected(self):
        def cyc(cur):
            for n in cur["nodes"]:
                if n["id"] == "architecture":
                    n["prereqs"].append("backprop")
        self.edit_cur(cyc)
        r = run("curriculum.py", "validate", self.book, check=False)
        self.assertIn("prerequisite cycle", r.stdout)

    def test_waves_respect_dependencies(self):
        def unwrite(cur):
            for c in cur["chapters"]:
                c["status"] = "approved"
        self.edit_cur(unwrite)
        out = run("curriculum.py", "waves", self.book).stdout.strip().splitlines()
        self.assertEqual(out[0], "wave 1: ch01-big-picture")
        self.assertEqual(out[1], "wave 2: ch02-backpropagation")
        self.assertEqual(out[2], "wave 3: preface glossary")

    def test_edit_snapshot_revert_cycle(self):
        run("curriculum.py", "edited", self.book)  # clean
        original = read(self.chapter("ch01-big-picture"))
        self.append("ch01-big-picture", "\nA hand edit.\n")
        r = run("curriculum.py", "edited", self.book, check=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("hand-edited: ch01-big-picture", r.stdout)

        run("curriculum.py", "snapshot", self.book, "ch01-big-picture")
        self.assertTrue(os.path.exists(os.path.join(self.book, ".history", "ch01-big-picture.e1.md")))
        with open(self.chapter("ch01-big-picture"), "w") as f:
            f.write("# Rewritten\n")
        run("curriculum.py", "record", self.book, "ch01-big-picture")
        run("curriculum.py", "bump", self.book, "--note", "rewrite")
        self.assertEqual(self.cur()["edition"], 2)

        run("curriculum.py", "revert", self.book, "ch01-big-picture", "1")
        self.assertEqual(read(self.chapter("ch01-big-picture")), original + "\nA hand edit.\n")
        self.assertEqual(self.cur()["edition"], 3)
        self.assertTrue(os.path.exists(os.path.join(self.book, ".history", "ch01-big-picture.e2.md")))

    def test_feedback_comments_listed(self):
        self.append("ch02-backpropagation", "\n<!-- feedback: shorter\n please -->\n")
        out = run("curriculum.py", "comments", self.book).stdout
        self.assertRegex(out, r"ch02-backpropagation:\d+: shorter please")


class CitationTests(BookTestCase):
    def test_fixture_citations_pass(self):
        r = run("check_citations.py", self.book)
        self.assertIn(", 0 problems", r.stdout)

    def test_paraphrased_listing_rejected(self):
        self.append("ch01-big-picture", "\n```python tinynet/model.py:7-8\ndef sigmoid(x):\n    return 1 / (1 + exp(-x))\n```\n")
        r = run("check_citations.py", self.book, "ch01-big-picture", check=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("listing does not match", r.stdout)

    def test_elided_listing_accepted(self):
        self.append("ch01-big-picture",
                    "\n```python tinynet/model.py:23-31\n    def backward(self, target, lr=0.5):\n        ...\n"
                    "        self.w2 = [w - lr * g for w, g in zip(self.w2, grad_w2)]\n```\n")
        run("check_citations.py", self.book, "ch01-big-picture")

    def test_out_of_range_and_missing_file(self):
        self.append("ch01-big-picture", "\nSee [[tinynet/model.py:30-99]] and [[tinynet/nope.py:1]].\n")
        r = run("check_citations.py", self.book, "ch01-big-picture", check=False)
        self.assertIn("outside the file", r.stdout)
        self.assertIn("does not exist", r.stdout)

    def test_unknown_chapter_link(self):
        self.append("ch01-big-picture", "\nSee [later](ch09-nothing.md).\n")
        r = run("check_citations.py", self.book, "ch01-big-picture", check=False)
        self.assertIn("unknown chapter 'ch09-nothing'", r.stdout)

    def test_notebook_cell_listing(self):
        self.append("ch01-big-picture",
                    "\n```python demo.ipynb#cell-2 \"Training from the notebook\"\nfrom tinynet.train import train\n...\n"
                    "print(net.forward([1, 0]))\n```\n\nSee [[demo.ipynb#cell-2:3]].\n")
        run("check_citations.py", self.book, "ch01-big-picture")
        run("curriculum.py", "record", self.book, "ch01-big-picture")
        self.assertIn("demo.ipynb", self.cur()["chapters"][1]["cites"])

    def test_notebook_cell_errors(self):
        self.append("ch01-big-picture", "\n```python demo.ipynb#cell-2\nnet = train(epochs=5)\n```\n"
                    "See [[demo.ipynb#cell-9]] and [[demo.ipynb#cell-2:7-8]].\n")
        r = run("check_citations.py", self.book, "ch01-big-picture", check=False)
        self.assertIn("listing does not match", r.stdout)
        self.assertIn("has no cell 9", r.stdout)
        self.assertIn("outside the file", r.stdout)

    def test_parse_citations_skips_mermaid_and_urls(self):
        cites = bu.parse_citations("```mermaid a.b\ngraph TD\n```\n```text https://x.y/z\nhi\n```\n[[a/b.py:3-4]]")
        self.assertEqual([(c["path"], c["start"], c["end"]) for c in cites], [("a/b.py", 3, 4)])


class StaleTests(BookTestCase):
    def test_changed_file_marks_citing_chapters_stale(self):
        with open(os.path.join(self.src, "tinynet", "train.py"), "a") as f:
            f.write("# tweak\n")
        git(self.src, "commit", "-qam", "tweak train")
        out = run("stale.py", self.book).stdout
        self.assertIn("STALE ch01-big-picture", out)
        self.assertIn("STALE ch02-backpropagation", out)
        self.assertNotIn("STALE preface", out)
        run("stale.py", self.book, "--apply")
        cur = self.cur()
        status = {c["id"]: c for c in cur["chapters"]}
        self.assertEqual(status["ch01-big-picture"]["status"], "stale")
        self.assertEqual(status["preface"]["status"], "written")
        new = git(self.src, "rev-parse", "HEAD")
        self.assertEqual(cur["repo"]["sha"], new)
        self.assertEqual(status["preface"]["sha"], new, "unaffected chapters are re-pinned")
        self.assertEqual(status["ch01-big-picture"]["sha"], self.sha, "stale chapters keep their commit")


class InitTests(unittest.TestCase):
    def test_init_local_repo(self):
        tmp = tempfile.mkdtemp(prefix="r2t-init-")
        try:
            src = os.path.join(tmp, "tinynet")
            shutil.copytree(os.path.join(FIXTURES, "source"), src)
            git(src, "init", "-q")
            git(src, "add", "-A")
            git(src, "commit", "-qm", "init")
            git(src, "remote", "add", "origin", "git@github.com:example/tinynet.git")
            out = json.loads(run("init_book.py", src, "--out", os.path.join(tmp, "b"), "--mode", "foundations",
                                 "--focus", "backprop, xor").stdout)
            cur = bu.load(out["book"])
            self.assertEqual(cur["repo"]["web_url"], "https://github.com/example/tinynet")
            self.assertEqual(cur["reader"]["default_mode"], "foundations+applied")
            self.assertEqual(cur["reader"]["focus"], ["backprop", "xor"])
            self.assertEqual(cur["repo"]["sha"], git(src, "rev-parse", "HEAD"))
            r = run("init_book.py", src, "--out", os.path.join(tmp, "b"), check=False)
            self.assertNotEqual(r.returncode, 0, "refuses to clobber an existing book")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_web_url_for(self):
        self.assertEqual(bu.web_url_for("https://github.com/a/b.git"), ("https://github.com/a/b", "github"))
        self.assertEqual(bu.web_url_for("git@gitlab.com:g/sub/p.git"), ("https://gitlab.com/g/sub/p", "gitlab"))
        self.assertEqual(bu.web_url_for("ssh://git@github.com/a/b"), ("https://github.com/a/b", "github"))
        self.assertEqual(bu.web_url_for("https://example.org/a/b"), (None, None))


class BuildTests(BookTestCase):
    def test_html_build(self):
        run("build_book.py", self.book, "--no-pdf")
        html = read(os.path.join(self.book, "book.html"))
        self.assertIn('id="book-data"', html)
        self.assertNotIn("pagedjs", html.split("<body>")[0].split("book-data")[0])
        self.assertIn("mermaid", html)  # fixture uses a diagram, so mermaid is bundled
        payload = html.split('id="book-data">', 1)[1].split("</script>", 1)[0]
        data = json.loads(payload)
        self.assertEqual([c["id"] for c in data["chapters"]],
                         ["preface", "ch01-big-picture", "ch02-backpropagation", "glossary"])
        self.assertEqual([c["number"] for c in data["chapters"]], [None, 1, 2, None])

    def test_payload_cannot_break_out_of_script(self):
        self.append("ch01-big-picture", "\n<!-- x -->\n```html\n<script>alert(1)</script>\n```\n")
        run("build_book.py", self.book, "--no-pdf")
        html = read(os.path.join(self.book, "book.html"))
        payload = html.split('id="book-data">', 1)[1].split("</script>", 1)[0]
        self.assertIn("alert(1)", json.loads(payload)["chapters"][1]["md"])

    @unittest.skipUnless(build_book.find_chrome(None), "no Chrome/Chromium available")
    def test_pdf_build(self):
        r = run("build_book.py", self.book)
        self.assertIn("book.pdf", r.stdout)
        pages = build_book.pdf_page_count(os.path.join(self.book, "book.pdf"))
        self.assertGreaterEqual(pages, 12)


if __name__ == "__main__":
    unittest.main()
