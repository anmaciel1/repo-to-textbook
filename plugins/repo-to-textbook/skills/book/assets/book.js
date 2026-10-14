/*
 * repo-to-textbook renderer.
 * Reads the embedded book payload (Markdown chapters + metadata), renders it
 * into a classic book DOM, then either wires up the screen reader (sidebar
 * TOC) or hands the document to Paged.js for print pagination.
 *
 * Markdown conventions handled here (documented in references/markdown-conventions.md):
 *   [[path/to/file.py:10-20]]      code citation -> permalink at the chapter's commit
 *   ```python path/file.py:10-20 "Caption"   numbered, cited listing
 *   ```mermaid Caption              numbered figure
 *   $inline$  $$display$$           KaTeX math
 *   > [!PRIMER] Title               boxes: NOTE, PRIMER, PITFALL, EXERCISE, DEFINITION
 *   <details>…</details> after an EXERCISE box   its solution
 *   <dfn>term</dfn>                 defined term -> back-of-book index
 *   [text](ch03.md#heading)         cross-reference to another chapter
 */
(function () {
  "use strict";

  var DATA = JSON.parse(document.getElementById("book-data").textContent);
  var META = DATA.meta;
  var PRINT = DATA.mode === "print";
  var CHAPTER_IDS = {};
  DATA.chapters.forEach(function (c) { CHAPTER_IDS[c.id] = c; });

  // ------------------------------------------------------------ helpers

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function slug(s) {
    return String(s).toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "")
      .replace(/[^\w\s-]/g, "").trim().replace(/[\s_]+/g, "-").replace(/-+/g, "-") || "section";
  }

  function el(tag, attrs, html) {
    var e = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (attrs[k] !== null && attrs[k] !== undefined) e.setAttribute(k, attrs[k]);
    });
    if (html !== undefined) e.innerHTML = html;
    return e;
  }

  // path, optional :start, optional -end. No spaces in paths.
  var CITE_RE = /^([^\s\]]+?)(?::(\d+)(?:-(\d+))?)?$/;

  function looksLikePath(p) { return /[\/.]/.test(p) && !/^https?:/.test(p); }

  // "demo.ipynb#cell-8" -> notebook cell 8 (1-based); hosts cannot deep-link
  // into a cell, so the permalink points at the notebook file.
  function cellRef(path) {
    var m = path.match(/^(.+\.ipynb)#cell-(\d+)$/);
    return m ? { file: m[1], cell: m[2] } : null;
  }

  function permalink(path, a, b, sha) {
    var repo = META.repo || {};
    if (!repo.web_url || !sha) return null;
    var cr = cellRef(path);
    if (cr) {
      return repo.web_url + (repo.host === "gitlab" ? "/-/blob/" : "/blob/") + sha + "/" + cr.file.replace(/^\.?\//, "");
    }
    var clean = path.replace(/^\.?\//, "");
    if (repo.host === "gitlab") {
      return repo.web_url + "/-/blob/" + sha + "/" + clean + (a ? "#L" + a + (b ? "-" + b : "") : "");
    }
    return repo.web_url + "/blob/" + sha + "/" + clean + (a ? "#L" + a + (b ? "-L" + b : "") : "");
  }

  function citeLabel(path, a, b) {
    var cr = cellRef(path);
    if (cr) {
      var lines = a ? (b && b !== a ? ", lines " + a + "–" + b : ", line " + a) : "";
      return cr.file + ", cell " + cr.cell + lines;
    }
    return path + (a ? ":" + a + (b ? "–" + b : "") : "");
  }

  function citeHTML(path, a, b, sha) {
    var href = permalink(path, a, b, sha);
    var label = "<code>" + esc(citeLabel(path, a, b)) + "</code>";
    return href ? '<a class="cite" href="' + esc(href) + '">' + label + "</a>"
                : '<span class="cite">' + label + "</span>";
  }

  function numLabel(chapter, n) { return chapter.number ? chapter.number + "." + n : String(n); }

  function highlight(code, lang) {
    if (window.hljs && lang && hljs.getLanguage(lang)) {
      try { return hljs.highlight(code, { language: lang, ignoreIllegals: true }).value; } catch (e) { /* fall through */ }
    }
    return esc(code);
  }

  function renderMath(tex, display) {
    if (!window.katex) return esc(tex);
    try {
      return katex.renderToString(tex, { displayMode: display, throwOnError: false, output: "html" });
    } catch (e) {
      return "<code>" + esc(tex) + "</code>";
    }
  }

  // ------------------------------------------------------------ markdown-it

  var md = window.markdownit({ html: true, linkify: true, typographer: true });
  // Only linkify explicit URLs; "main.py" must not become http://main.py.
  md.linkify.set({ fuzzyLink: false, fuzzyEmail: false });

  // $$ display math $$ as a block
  md.block.ruler.before("fence", "math_block", function (state, startLine, endLine, silent) {
    var pos = state.bMarks[startLine] + state.tShift[startLine];
    var max = state.eMarks[startLine];
    if (state.src.slice(pos, pos + 2) !== "$$") return false;
    var first = state.src.slice(pos + 2, max);
    var content = "", next = startLine, found = false;
    if (first.trim().length >= 2 && first.trim().slice(-2) === "$$") {
      content = first.trim().slice(0, -2);
      found = true;
    } else {
      content = first + "\n";
      for (next = startLine + 1; next < endLine; next++) {
        var line = state.src.slice(state.bMarks[next] + state.tShift[next], state.eMarks[next]);
        if (line.trim().slice(-2) === "$$") { content += line.trim().slice(0, -2); found = true; break; }
        content += line + "\n";
      }
    }
    if (!found) return false;
    if (silent) return true;
    state.line = next + 1;
    var t = state.push("math_block", "", 0);
    t.block = true;
    t.content = content;
    t.map = [startLine, state.line];
    return true;
  }, { alt: ["paragraph", "reference", "blockquote", "list"] });

  // $inline$ (pandoc rules: no space after opening or before closing, no digit after closing)
  md.inline.ruler.after("escape", "math_inline", function (state, silent) {
    var src = state.src, start = state.pos;
    if (src.charCodeAt(start) !== 0x24) return false;
    var display = src.charCodeAt(start + 1) === 0x24;
    var open = display ? 2 : 1;
    var next = src.charAt(start + open);
    if (!next || (!display && /\s/.test(next))) return false;
    var end = start + open;
    for (;;) {
      end = src.indexOf(display ? "$$" : "$", end);
      if (end === -1) return false;
      if (src.charAt(end - 1) === "\\") { end += 1; continue; }
      break;
    }
    if (end === start + open) return false;
    if (!display && (/\s/.test(src.charAt(end - 1)) || /\d/.test(src.charAt(end + 1)))) return false;
    if (!silent) {
      var t = state.push(display ? "math_display_inline" : "math_inline", "", 0);
      t.content = src.slice(start + open, end);
    }
    state.pos = end + open;
    return true;
  });

  md.renderer.rules.math_block = function (tokens, idx) {
    return '<div class="math-display">' + renderMath(tokens[idx].content, true) + "</div>\n";
  };
  md.renderer.rules.math_display_inline = function (tokens, idx) { return renderMath(tokens[idx].content, true); };
  md.renderer.rules.math_inline = function (tokens, idx) { return renderMath(tokens[idx].content, false); };

  // [[path:10-20]] citations
  md.inline.ruler.before("link", "citeref", function (state, silent) {
    var src = state.src, pos = state.pos;
    if (src.charCodeAt(pos) !== 0x5B || src.charCodeAt(pos + 1) !== 0x5B) return false;
    var end = src.indexOf("]]", pos + 2);
    if (end < 0) return false;
    var m = src.slice(pos + 2, end).trim().match(CITE_RE);
    if (!m || !looksLikePath(m[1])) return false;
    if (!silent) {
      var t = state.push("citeref", "", 0);
      t.meta = { path: m[1], a: m[2], b: m[3] };
    }
    state.pos = end + 2;
    return true;
  });
  md.renderer.rules.citeref = function (tokens, idx, opts, env) {
    var m = tokens[idx].meta;
    return citeHTML(m.path, m.a, m.b, env.chapter.sha);
  };

  // fences: listings (optionally cited) and mermaid figures
  md.renderer.rules.fence = function (tokens, idx, opts, env) {
    var t = tokens[idx];
    var info = (t.info || "").trim();
    var im = info.match(/^(\S*)\s*([\s\S]*)$/);
    var lang = (im[1] || "").toLowerCase();
    var rest = (im[2] || "").trim();
    var ch = env.chapter;

    if (lang === "mermaid") {
      env.figure += 1;
      var fnum = numLabel(ch, env.figure);
      var fcap = rest.replace(/^["']|["']$/g, "");
      return '<figure class="figure" id="' + ch.id + "-fig-" + env.figure + '">' +
        '<pre class="mermaid">' + esc(t.content) + "</pre>" +
        '<figcaption><span class="cap-label">Figure ' + fnum + ".</span>" +
        (fcap ? md.renderInline(fcap, env) : "") + "</figcaption></figure>\n";
    }

    var cite = null, caption = "";
    if (rest) {
      var rm = rest.match(/^(\S+)\s*([\s\S]*)$/);
      var cm = rm && rm[1].match(CITE_RE);
      if (cm && looksLikePath(cm[1])) {
        cite = { path: cm[1], a: cm[2], b: cm[3] };
        caption = rm[2].trim();
      } else {
        caption = rest;
      }
      caption = caption.replace(/^["']|["']$/g, "");
    }

    var pre = '<pre class="code"><code class="hljs' + (lang ? " language-" + esc(lang) : "") + '">' +
      highlight(t.content, lang) + "</code></pre>";
    if (!cite && !caption) return pre + "\n";

    env.listing += 1;
    var lnum = numLabel(ch, env.listing);
    var capHtml = '<span class="cap-label">Listing ' + lnum + ".</span>";
    if (caption) capHtml += md.renderInline(caption, env) + (cite ? " " : "");
    if (cite) capHtml += citeHTML(cite.path, cite.a, cite.b, ch.sha);
    return '<figure class="listing" id="' + ch.id + "-lst-" + env.listing + '">' + pre +
      "<figcaption>" + capHtml + "</figcaption></figure>\n";
  };

  // cross-chapter links: ch03.md#heading -> #ch03--heading
  var defaultLinkOpen = md.renderer.rules.link_open || function (tokens, idx, opts, env, self) {
    return self.renderToken(tokens, idx, opts);
  };
  md.renderer.rules.link_open = function (tokens, idx, opts, env, self) {
    var t = tokens[idx];
    var href = t.attrGet("href") || "";
    var m = href.match(/^(?:\.\/)?(?:chapters\/)?([\w.-]+?)\.md(?:#(.*))?$/);
    if (m && CHAPTER_IDS[m[1]]) {
      t.attrSet("href", "#" + m[1] + (m[2] ? "--" + slug(decodeURIComponent(m[2])) : ""));
      t.attrJoin("class", "xref");
    } else if (/^#/.test(href) && href.indexOf("--") < 0) {
      t.attrSet("href", "#" + env.chapter.id + "--" + slug(decodeURIComponent(href.slice(1))));
    } else if (/^https?:\/\//.test(href)) {
      // Printed copies show the URL after the link text (see book.css), unless the text is the URL.
      var text = tokens[idx + 1] && tokens[idx + 1].type === "text" ? tokens[idx + 1].content : "";
      if (text.replace(/\/$/, "") !== href.replace(/\/$/, "")) t.attrJoin("class", "ext");
    }
    return defaultLinkOpen(tokens, idx, opts, env, self);
  };

  // ------------------------------------------------------------ chapter DOM passes

  var BOX_LABELS = { NOTE: "Note", TIP: "Note", PRIMER: "Primer", PITFALL: "Pitfall", WARNING: "Pitfall",
    CAUTION: "Pitfall", EXERCISE: "Exercise", DEFINITION: "Definition", IMPORTANT: "Note" };

  function convertBoxes(root, ch, state) {
    Array.prototype.slice.call(root.querySelectorAll("blockquote")).forEach(function (bq) {
      var p = bq.firstElementChild;
      if (!p || p.tagName !== "P") return;
      var m = p.innerHTML.match(/^\s*\[!([A-Za-z]+)\]([^\n]*?)(?:\n|<br\s*\/?>|$)/);
      if (!m) return;
      var kind = m[1].toUpperCase();
      var label = BOX_LABELS[kind];
      if (!label) return;
      var title = m[2].trim();
      p.innerHTML = p.innerHTML.slice(m[0].length);
      if (!p.textContent.trim() && !p.querySelector("img,svg,.katex")) p.remove();

      var cls = "box box-" + label.toLowerCase();
      var aside = el("aside", { "class": cls });
      var labelText = label;
      if (label === "Exercise") {
        state.exercise += 1;
        labelText = "Exercise " + numLabel(ch, state.exercise);
        aside.id = ch.id + "-ex-" + state.exercise;
      }
      aside.appendChild(el("div", { "class": "box-label" },
        esc(labelText) + (title ? '<span class="box-title">' + title + "</span>" : "")));
      while (bq.firstChild) aside.appendChild(bq.firstChild);
      bq.parentNode.replaceChild(aside, bq);

      if (label === "Exercise") {
        var sib = aside.nextElementSibling;
        if (sib && sib.tagName === "DETAILS") {
          sib.classList.add("solution");
          sib.dataset.exercise = labelText;
          sib.dataset.target = aside.id;
          var sum = sib.querySelector("summary");
          if (!sum) { sum = el("summary"); sib.insertBefore(sum, sib.firstChild); }
          sum.textContent = "Solution to " + labelText;
        }
      }
    });
  }

  function numberHeadings(root, ch) {
    var used = {};
    var h2 = 0, h3 = 0;
    var toc = [];
    Array.prototype.slice.call(root.querySelectorAll("h2, h3, h4")).forEach(function (h) {
      var base = slug(h.textContent);
      var id = ch.id + "--" + base;
      if (used[id]) { used[id] += 1; id += "-" + used[id]; } else { used[id] = 1; }
      h.id = id;
      if (!ch.number) {
        if (h.tagName === "H2") toc.push({ id: id, num: "", text: h.textContent });
        return;
      }
      var num = "";
      if (h.tagName === "H2") { h2 += 1; h3 = 0; num = ch.number + "." + h2; }
      else if (h.tagName === "H3") { h3 += 1; num = ch.number + "." + h2 + "." + h3; }
      if (num) {
        h.insertBefore(el("span", { "class": "secnum" }, num), h.firstChild);
        h.dataset.secnum = num;
      }
      if (h.tagName === "H2") toc.push({ id: id, num: num, text: h.textContent.replace(num, "").trim() });
    });
    return toc;
  }

  function renderChapter(ch) {
    var env = { chapter: ch, listing: 0, figure: 0 };
    var html = md.render(ch.md || "", env);
    var body = el("div", { "class": "chapter-body" }, html);

    // The first h1 is the chapter title; any later h1 is demoted.
    var title = ch.title;
    var h1s = body.querySelectorAll("h1");
    if (h1s.length) {
      title = h1s[0].textContent.trim() || title;
      h1s[0].remove();
      Array.prototype.slice.call(h1s, 1).forEach(function (h) {
        var h2 = el("h2", null, h.innerHTML);
        h.parentNode.replaceChild(h2, h);
      });
    }

    Array.prototype.slice.call(body.querySelectorAll("table")).forEach(function (t) {
      var wrap = el("div", { "class": "table-wrap" });
      t.parentNode.insertBefore(wrap, t);
      wrap.appendChild(t);
    });

    // Printed URLs cannot be justified nicely; set their paragraphs ragged-right.
    Array.prototype.slice.call(body.querySelectorAll("a.ext")).forEach(function (a) {
      var block = a.closest("p, li");
      if (block) block.classList.add("ragged");
    });

    var state = { exercise: 0 };
    convertBoxes(body, ch, state);
    var toc = numberHeadings(body, ch);

    var sectionClass = ch.kind === "chapter" ? "chapter" : "matter-" + ch.kind;
    var section = el("section", { "class": sectionClass + " kind-" + ch.kind, "data-chapter": ch.id });
    var head = el("header", { "class": "chapter-head" });
    if (ch.number) head.appendChild(el("div", { "class": "chapter-label" }, "Chapter " + esc(ch.number)));
    head.appendChild(el("h1", { "class": "chapter-title", id: ch.id }, esc(title)));
    section.appendChild(head);
    section.appendChild(body);
    return { section: section, title: title, toc: toc };
  }

  // ------------------------------------------------------------ book-level parts

  function titlePage() {
    var r = META.repo || {};
    var s = el("section", { "class": "title-page" });
    s.appendChild(el("h1", { "class": "book-title" }, esc(META.title)));
    if (META.subtitle) s.appendChild(el("p", { "class": "book-subtitle" }, esc(META.subtitle)));
    s.appendChild(el("hr", { "class": "title-rule" }));
    s.appendChild(el("p", { "class": "book-byline" },
      esc("A textbook on " + (r.name || "the repository")) + (META.edition ? " &middot; Edition " + esc(META.edition) : "")));
    return s;
  }

  function copyrightPage() {
    var r = META.repo || {};
    var rows = [];
    if (r.url) rows.push(["Source", r.url]);
    if (r.sha) rows.push(["Commit", r.sha]);
    if (META.edition) rows.push(["Edition", String(META.edition)]);
    if (META.date) rows.push(["Generated", META.date]);
    if (META.level) rows.push(["Written for", META.level + " readers"]);
    var dl = "<dl>" + rows.map(function (row) {
      return "<dt>" + esc(row[0]) + "</dt><dd>" + esc(row[1]) + "</dd>";
    }).join("") + "</dl>";
    var note = '<p class="disclaimer">This book was generated with AI assistance from the source code at the ' +
      "commit above. Code citations link to that exact commit. Where the text and the code disagree, the code is right.</p>";
    return el("section", { "class": "copyright-page" }, dl + note);
  }

  function tocPage(entries) {
    var s = el("section", { "class": "toc-page" });
    s.appendChild(el("h1", { "class": "toc-heading", id: "contents" }, "Contents"));
    s.appendChild(buildTocList(entries, "toc", true));
    return s;
  }

  function buildTocList(entries, cls, withSections) {
    var ol = el("ol", { "class": cls });
    entries.forEach(function (e) {
      var li = el("li", { "class": e.front ? "front-entry" : null });
      li.appendChild(tocLink(e.id, e.num, e.title, cls === "toc"));
      if (withSections && e.sections && e.sections.length) {
        var sub = el("ol");
        e.sections.forEach(function (s) {
          var sli = el("li", { "class": e.front ? "front-entry" : null });
          sli.appendChild(tocLink(s.id, s.num, s.text, cls === "toc"));
          sub.appendChild(sli);
        });
        li.appendChild(sub);
      }
      ol.appendChild(li);
    });
    return ol;
  }

  function tocLink(id, num, text, dotted) {
    var a = el("a", { href: "#" + id });
    if (dotted) {
      a.innerHTML = '<span class="toc-num">' + esc(num || "") + '</span><span class="toc-text">' + esc(text) +
        '</span><span class="toc-dots"></span><span class="toc-pg" data-pageref="' + esc(id) + '"></span>';
    } else {
      a.innerHTML = (num ? '<span class="side-num">' + esc(num) + "</span>" : "") + esc(text);
    }
    return a;
  }

  function solutionsAppendix(main) {
    var sols = Array.prototype.slice.call(main.querySelectorAll("details.solution"));
    if (!sols.length) return null;
    var s = el("section", { "class": "matter-back kind-back solutions-chapter", "data-chapter": "solutions" });
    var head = el("header", { "class": "chapter-head" });
    head.appendChild(el("h1", { "class": "chapter-title", id: "solutions" }, "Solutions to Exercises"));
    s.appendChild(head);
    var lastChapter = null;
    sols.forEach(function (d) {
      var sec = d.closest("section");
      var chId = sec && sec.dataset.chapter;
      if (chId !== lastChapter) {
        lastChapter = chId;
        var ch = CHAPTER_IDS[chId];
        s.appendChild(el("h3", null, esc((ch && ch.number ? "Chapter " + ch.number + ". " : "") + (ch ? ch.title : ""))));
      }
      var entry = el("div", { "class": "solution-entry" });
      entry.appendChild(el("p", { "class": "solution-label" }, esc(d.dataset.exercise || "Exercise")));
      Array.prototype.slice.call(d.childNodes).forEach(function (n) {
        if (n.nodeType === 1 && n.tagName === "SUMMARY") return;
        entry.appendChild(n.cloneNode(true));
      });
      s.appendChild(entry);
    });
    return s;
  }

  function indexPage(main) {
    var terms = {};
    var n = 0;
    Array.prototype.slice.call(main.querySelectorAll("dfn")).forEach(function (d) {
      var term = (d.getAttribute("title") || d.textContent).trim();
      if (!term) return;
      var key = term.toLowerCase();
      n += 1;
      d.id = d.id || "dfn-" + n;
      var sec = d.closest("section");
      var ch = sec && CHAPTER_IDS[sec.dataset.chapter];
      var h = null;
      var walker = d;
      while (walker && walker !== sec) {
        var prev = walker.previousElementSibling;
        while (prev && !/^H[23]$/.test(prev.tagName)) prev = prev.previousElementSibling;
        if (prev) { h = prev; break; }
        walker = walker.parentElement;
      }
      var label = (h && h.dataset.secnum) || (ch && ch.number) || (ch ? ch.title : "");
      if (!terms[key]) terms[key] = { term: term, refs: [] };
      terms[key].refs.push({ id: d.id, label: label });
    });
    var keys = Object.keys(terms).sort(function (a, b) { return a.localeCompare(b); });
    if (!keys.length) return null;

    var s = el("section", { "class": "matter-back kind-back index-chapter", "data-chapter": "index" });
    var head = el("header", { "class": "chapter-head" });
    head.appendChild(el("h1", { "class": "chapter-title", id: "index" }, "Index"));
    s.appendChild(head);
    var ul = el("ul", { "class": "index-list" });
    var letter = "";
    keys.forEach(function (k) {
      var t = terms[k];
      var first = t.term.charAt(0).toUpperCase();
      if (/[A-Z]/.test(first) && first !== letter) {
        letter = first;
        ul.appendChild(el("li", { "class": "index-letter" }, esc(letter)));
      }
      var refs = t.refs.map(function (r) {
        return '<a href="#' + esc(r.id) + '"><span class="ref-screen">' + esc(r.label) + "</span>" +
          '<span class="ref-print" data-pageref="' + esc(r.id) + '">00</span></a>';
      }).join(", ");
      ul.appendChild(el("li", null, esc(t.term) + ', <span class="index-refs">' + refs + "</span>"));
    });
    s.appendChild(ul);
    return s;
  }

  // ------------------------------------------------------------ assemble

  function build() {
    document.title = META.title + (META.subtitle ? " — " + META.subtitle : "");
    var main = el("main", { id: "book" });
    main.appendChild(titlePage());
    main.appendChild(copyrightPage());

    var rendered = DATA.chapters.map(function (ch) {
      var r = renderChapter(ch);
      return { ch: ch, section: r.section, title: r.title, toc: r.toc };
    });

    var tocEntries = rendered.map(function (r) {
      return { id: r.ch.id, num: r.ch.number ? String(r.ch.number) : "", title: r.title,
        sections: r.ch.kind === "chapter" ? r.toc : [], front: r.ch.kind === "front" };
    });

    var firstMain = true;
    var sections = rendered.map(function (r) {
      if (r.ch.kind === "chapter" && firstMain) { r.section.classList.add("first-main"); firstMain = false; }
      return r.section;
    });

    main.appendChild(el("div", { "class": "toc-slot" }));
    sections.forEach(function (s) { main.appendChild(s); });

    if (PRINT) {
      var sol = solutionsAppendix(main);
      if (sol) {
        main.appendChild(sol);
        tocEntries.push({ id: "solutions", num: "", title: "Solutions to Exercises", sections: [] });
      }
    }
    var idx = indexPage(main);
    if (idx) {
      main.appendChild(idx);
      tocEntries.push({ id: "index", num: "", title: "Index", sections: [] });
    }

    main.replaceChild(tocPage(tocEntries), main.querySelector(".toc-slot"));
    document.body.appendChild(main);
    return tocEntries;
  }

  function screenChrome(tocEntries) {
    var btn = el("button", { id: "toc-toggle", type: "button", "aria-controls": "sidebar", "aria-expanded": "false" }, "Contents");
    var nav = el("nav", { id: "sidebar", "aria-label": "Table of contents" });
    nav.appendChild(buildTocList(tocEntries, "side-toc", true));
    document.body.insertBefore(nav, document.body.firstChild);
    document.body.insertBefore(btn, document.body.firstChild);

    var KEY = "repo-to-textbook:toc-open";
    function setOpen(open) {
      document.body.classList.toggle("toc-open", open);
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      try { localStorage.setItem(KEY, open ? "1" : "0"); } catch (e) { /* storage unavailable */ }
    }
    var initial = window.innerWidth >= 1180;
    try { var saved = localStorage.getItem(KEY); if (saved !== null) initial = saved === "1"; } catch (e) { /* ignore */ }
    setOpen(initial);
    btn.addEventListener("click", function () { setOpen(!document.body.classList.contains("toc-open")); });
    nav.addEventListener("click", function (e) {
      if (e.target.closest("a") && window.innerWidth < 1180) setOpen(false);
    });

    // Highlight the chapter currently in view.
    var links = {};
    Array.prototype.slice.call(nav.querySelectorAll("a")).forEach(function (a) { links[a.getAttribute("href").slice(1)] = a; });
    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (!en.isIntersecting) return;
          var id = en.target.id;
          if (!links[id]) return;
          Object.keys(links).forEach(function (k) { links[k].classList.remove("current"); });
          links[id].classList.add("current");
        });
      }, { rootMargin: "0px 0px -70% 0px" });
      Array.prototype.slice.call(document.querySelectorAll(".chapter-title, .chapter-body h2")).forEach(function (h) {
        if (h.id) io.observe(h);
      });
    }
  }

  async function renderMermaid() {
    if (!window.mermaid || !document.querySelector("pre.mermaid")) return;
    mermaid.initialize({
      startOnLoad: false,
      theme: "neutral",
      securityLevel: "strict",
      fontFamily: '"Source Serif 4", Georgia, serif',
      flowchart: { htmlLabels: false, curve: "basis" },
      themeVariables: { fontSize: "13px" }
    });
    var nodes = Array.prototype.slice.call(document.querySelectorAll("pre.mermaid"));
    for (var i = 0; i < nodes.length; i++) {
      var pre = nodes[i];
      try {
        var out = await mermaid.render("mmd-" + i, pre.textContent);
        var holder = el("div", { "class": "mermaid-svg" }, out.svg);
        pre.parentNode.replaceChild(holder, pre);
      } catch (e) {
        pre.classList.add("mermaid-error");
        pre.setAttribute("title", "Diagram failed to render: " + (e && e.message ? e.message : e));
        console.warn("[repo-to-textbook] mermaid diagram " + i + " failed:", e);
      }
    }
    // Keep Mermaid's per-diagram <style> elements inside their SVGs; Paged.js
    // would otherwise lift them into the global stylesheet.
    Array.prototype.slice.call(document.querySelectorAll("svg style")).forEach(function (s) {
      s.setAttribute("data-pagedjs-ignore", "");
    });
    // Leftover render containers Mermaid sometimes attaches to <body>.
    Array.prototype.slice.call(document.querySelectorAll("body > div[id^='dmmd-']")).forEach(function (d) { d.remove(); });
  }

  function toRoman(n) {
    var map = [[1000, "m"], [900, "cm"], [500, "d"], [400, "cd"], [100, "c"], [90, "xc"],
      [50, "l"], [40, "xl"], [10, "x"], [9, "ix"], [5, "v"], [4, "iv"], [1, "i"]];
    var out = "";
    map.forEach(function (m) { while (n >= m[0]) { out += m[1]; n -= m[0]; } });
    return out;
  }

  // Number pages ourselves after Paged.js has laid them out: roman from the
  // title page through the front matter, arabic from the first chapter. The
  // same labels go into the footers, the TOC and the index, so they agree.
  function numberPages() {
    var pages = Array.prototype.slice.call(document.querySelectorAll(".pagedjs_page"));
    var firstMain = -1;
    pages.forEach(function (p, i) {
      if (firstMain < 0 && p.querySelector(".first-main .chapter-head")) firstMain = i;
    });
    var labels = pages.map(function (p, i) {
      return firstMain >= 0 && i >= firstMain ? String(i - firstMain + 1) : toRoman(i + 1);
    });
    var rules = [];
    pages.forEach(function (p, i) {
      if (!p.id) p.id = "r2t-page-" + (i + 1);
      var box = p.querySelector(".pagedjs_margin-bottom-center > .pagedjs_margin-content");
      if (!box) return;
      var c = getComputedStyle(box, "::after").content;
      if (!c || c === "none" || c === "normal") return;
      rules.push("#" + p.id + " .pagedjs_margin-bottom-center > .pagedjs_margin-content::after{content:\"" +
        labels[i] + "\" !important}");
    });
    var st = document.createElement("style");
    st.setAttribute("data-pagedjs-ignore", "");
    st.textContent = rules.join("\n");
    document.head.appendChild(st);
    Array.prototype.slice.call(document.querySelectorAll("[data-pageref]")).forEach(function (span) {
      var target = document.getElementById(span.getAttribute("data-pageref"));
      var page = target && target.closest(".pagedjs_page");
      var i = page ? pages.indexOf(page) : -1;
      span.textContent = i >= 0 ? labels[i] : "";
    });
  }

  async function main() {
    var tocEntries = build();
    await renderMermaid();
    if (document.fonts && document.fonts.ready) { try { await document.fonts.ready; } catch (e) { /* ignore */ } }

    if (PRINT) {
      var data = document.getElementById("book-data");
      if (data) data.remove();
      await window.PagedPolyfill.preview();
      numberPages();
    } else {
      screenChrome(tocEntries);
      if (location.hash) {
        var target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
        if (target) target.scrollIntoView();
      }
    }
    window.__BOOK_READY__ = true;
    document.documentElement.setAttribute("data-book-ready", "true");
  }

  function start() {
    main().catch(function (e) {
      console.error("[repo-to-textbook] render failed:", e);
      window.__BOOK_ERROR__ = String(e && e.stack ? e.stack : e);
      window.__BOOK_READY__ = true;
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
