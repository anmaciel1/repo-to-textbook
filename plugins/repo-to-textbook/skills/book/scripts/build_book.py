#!/usr/bin/env python3
"""Build the book: chapters/*.md -> book.html (screen) + book.pdf (print).

    build_book.py <book> [--no-pdf] [--paper letter|a4] [--chrome PATH] [--timeout SECONDS]

book.html is self-contained (fonts, scripts and styles inlined) and works
offline. The PDF is produced from .build/print.html, which paginates with
Paged.js, using Playwright if installed, else headless Chrome/Chromium/Edge
driven over the DevTools protocol (scripts/cdp.py, stdlib only).
If no browser is found, open .build/print.html in Chrome and use
Print -> Save as PDF (margins: none, background graphics: on).
"""

import argparse
import base64
import json
import os
import re
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bookutil as bu  # noqa: E402

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(SKILL_DIR, "assets")

FONT_FACES = [
    ("Source Serif 4", "normal", 400, "source-serif-4-latin-400-normal.woff2"),
    ("Source Serif 4", "italic", 400, "source-serif-4-latin-400-italic.woff2"),
    ("Source Serif 4", "normal", 600, "source-serif-4-latin-600-normal.woff2"),
    ("Source Serif 4", "italic", 600, "source-serif-4-latin-600-italic.woff2"),
    ("Source Serif 4", "normal", 700, "source-serif-4-latin-700-normal.woff2"),
    ("Source Code Pro", "normal", 400, "source-code-pro-latin-400-normal.woff2"),
    ("Source Code Pro", "normal", 600, "source-code-pro-latin-600-normal.woff2"),
]

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]
CHROME_NAMES = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                "microsoft-edge", "brave-browser", "chrome"]


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def data_uri(path, mime="font/woff2"):
    return "data:%s;base64,%s" % (mime, base64.b64encode(read_bytes(path)).decode("ascii"))


def fonts_css():
    out = []
    for family, style, weight, fname in FONT_FACES:
        p = os.path.join(ASSETS, "fonts", fname)
        if os.path.exists(p):
            out.append('@font-face{font-family:"%s";font-style:%s;font-weight:%d;font-display:block;src:url(%s) format("woff2");}'
                       % (family, style, weight, data_uri(p)))
    return "\n".join(out)


def katex_css():
    css = read(os.path.join(ASSETS, "vendor", "katex", "katex.min.css"))
    css = re.sub(r',url\(fonts/[^)]+\.(?:woff|ttf)\) format\("(?:woff|truetype)"\)', "", css)

    def inline(m):
        p = os.path.join(ASSETS, "vendor", "katex", "fonts", m.group(1))
        return "url(%s)" % data_uri(p) if os.path.exists(p) else m.group(0)
    return re.sub(r"url\(fonts/([^)]+\.woff2)\)", inline, css)


def script_safe(js):
    return js.replace("</script", "<\\/script").replace("<!--", "<\\!--")


def collect(book, cur):
    nums = bu.chapter_numbers(cur)
    repo_sha = cur.get("repo", {}).get("sha")
    chapters, missing = [], []
    order = ([c for c in cur.get("chapters", []) if bu.kept(c) and c.get("kind") == "front"] +
             [c for c in cur.get("chapters", []) if bu.kept(c) and c.get("kind", "chapter") == "chapter"] +
             [c for c in cur.get("chapters", []) if bu.kept(c) and c.get("kind") == "back"])
    for c in order:
        path = bu.chapter_file(book, c["id"])
        if not os.path.exists(path):
            missing.append(c["id"])
            continue
        chapters.append({
            "id": c["id"],
            "kind": c.get("kind", "chapter"),
            "number": nums.get(c["id"]),
            "title": c.get("title", c["id"]),
            "sha": c.get("sha") or repo_sha,
            "md": read(path),
        })
    return chapters, missing


def render(cur, chapters, mode, paper):
    repo = cur.get("repo", {})
    sha = repo.get("sha") or ""
    meta = {
        "title": cur.get("book", {}).get("title") or repo.get("name", "Untitled"),
        "subtitle": cur.get("book", {}).get("subtitle", ""),
        "edition": cur.get("edition") or None,
        "date": bu.today(),
        "level": cur.get("reader", {}).get("level"),
        "repo": {
            "name": repo.get("name"), "url": repo.get("url"), "web_url": repo.get("web_url"),
            "host": repo.get("host"), "sha": sha,
        },
    }
    payload = json.dumps({"mode": mode, "meta": meta, "chapters": chapters}, ensure_ascii=False)
    # "<" only occurs inside JSON strings; < keeps "<!--"/"<script"/"</script" in
    # chapter text from confusing the HTML parser.
    payload = payload.replace("<", "\\u003c")

    all_md = "\n".join(c["md"] for c in chapters)
    need_mermaid = re.search(r"^\s*(```|~~~)\s*mermaid", all_md, re.M) is not None
    need_katex = re.search(r"\$\$|\$[^\s$][^$\n]*\$", all_md) is not None

    v = os.path.join(ASSETS, "vendor")
    parts = {
        "TITLE": meta["title"].replace("<", "&lt;"),
        "FONTS_CSS": fonts_css(),
        "KATEX_CSS": katex_css() if need_katex else "",
        "BOOK_CSS": read(os.path.join(ASSETS, "book.css")).replace("__PAPER__", paper),
        "PAYLOAD": payload,
        "MARKDOWN_IT_JS": script_safe(read(os.path.join(v, "markdown-it.min.js"))),
        "HIGHLIGHT_JS": script_safe(read(os.path.join(v, "highlight.min.js"))),
        "KATEX_JS": script_safe(read(os.path.join(v, "katex", "katex.min.js"))) if need_katex else "",
        "MERMAID_JS": script_safe(read(os.path.join(v, "mermaid.min.js"))) if need_mermaid else "",
        "PAGED_CONFIG": "<script>window.PagedConfig = { auto: false };</script>" if mode == "print" else "",
        "PAGED_JS": ("<script>%s</script>" % script_safe(read(os.path.join(v, "paged.polyfill.min.js"))))
        if mode == "print" else "",
        "BOOK_JS": script_safe(read(os.path.join(ASSETS, "book.js"))),
    }
    template = read(os.path.join(ASSETS, "book.html"))
    return re.sub(r"__([A-Z_]+)__", lambda m: parts.get(m.group(1), m.group(0)), template)


def find_chrome(explicit):
    for c in [explicit, os.environ.get("CHROME_PATH")]:
        if c and os.path.exists(c):
            return c
    for c in CHROME_CANDIDATES:
        if os.path.exists(c):
            return c
    for n in CHROME_NAMES:
        p = shutil.which(n)
        if p:
            return p
    return None


def pdf_with_playwright(html_path, pdf_path, chrome, timeout):
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return None
    with sync_playwright() as p:
        kw = {"executable_path": chrome} if chrome else {}
        browser = p.chromium.launch(**kw)
        page = browser.new_page()
        page.goto("file://" + os.path.abspath(html_path))
        page.wait_for_function("window.__BOOK_READY__ === true", timeout=timeout * 1000)
        err = page.evaluate("window.__BOOK_ERROR__ || null")
        if err:
            browser.close()
            bu.die("render error in print.html:\n" + err, 1)
        page.pdf(path=pdf_path, prefer_css_page_size=True, print_background=True)
        browser.close()
    return "playwright"


def pdf_with_chrome(html_path, pdf_path, chrome, timeout):
    import cdp
    try:
        cdp.print_to_pdf(chrome, html_path, pdf_path, timeout=timeout)
    except cdp.CDPError as e:
        bu.die("PDF failed: %s\nOpen %s in Chrome to inspect, or print it from there "
               "(Print -> Save as PDF, Margins: None)." % (e, html_path), 1)
    return "chrome"


def pdf_page_count(path):
    data = read_bytes(path)
    return len(re.findall(rb"/Type\s*/Page(?![s\w])", data))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("book")
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--paper", choices=["letter", "a4"])
    ap.add_argument("--chrome")
    ap.add_argument("--timeout", type=int, default=180)
    a = ap.parse_args()

    book = os.path.abspath(a.book)
    cur = bu.load(book)
    paper = a.paper or cur.get("paper", "letter")
    chapters, missing = collect(book, cur)
    if not chapters:
        bu.die("no written chapters to build", 1)

    t0 = time.time()
    screen = render(cur, chapters, "screen", paper)
    out_html = os.path.join(book, "book.html")
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(screen)
    print("wrote %s (%.1f MB, %d chapters)" % (out_html, len(screen.encode("utf-8")) / 1e6, len(chapters)))
    if missing:
        print("note: not yet written, left out: %s" % ", ".join(missing))

    if a.no_pdf:
        return
    os.makedirs(os.path.join(book, ".build"), exist_ok=True)
    print_html = os.path.join(book, ".build", "print.html")
    with open(print_html, "w", encoding="utf-8") as f:
        f.write(render(cur, chapters, "print", paper))

    chrome = find_chrome(a.chrome)
    out_pdf = os.path.join(book, "book.pdf")
    tmp_pdf = out_pdf + ".tmp.pdf"
    if os.path.exists(tmp_pdf):
        os.remove(tmp_pdf)
    engine = pdf_with_playwright(print_html, tmp_pdf, chrome, a.timeout)
    if engine is None:
        if not chrome:
            print("no Chrome/Chromium/Edge found and Playwright not installed; PDF skipped.\n"
                  "To make the PDF: open %s in Chrome, then Print -> Save as PDF\n"
                  "(Margins: None, Background graphics: on). Or set CHROME_PATH." % print_html)
            return
        engine = pdf_with_chrome(print_html, tmp_pdf, chrome, a.timeout)
    pages = pdf_page_count(tmp_pdf)
    if pages < 3:
        bu.die("PDF has only %d page(s); pagination probably did not finish. Re-run with a larger --timeout, "
               "or open %s in Chrome to see console errors." % (pages, print_html), 1)
    os.replace(tmp_pdf, out_pdf)
    print("wrote %s (%d pages, %s, %.0fs)" % (out_pdf, pages, engine, time.time() - t0))


if __name__ == "__main__":
    main()
