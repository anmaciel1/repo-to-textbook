# Survey checklist

The survey is **read-only**. Its job is to understand the repository well enough to build the
concept map: a graph of what a reader must learn and in what order. Do not write any prose for the
reader yet.

## 1. Orient (about 5 minutes of reading)

- **README, docs, and project metadata.** Find what the project claims to do, who it is for, and
  how it is run.
- **Directory tree.** Look two or three levels deep, and ignore vendored, generated and build output
  (`node_modules`, `dist`, `build`, `target`, `.venv`, `vendor`, lockfiles and minified files).
- **Size.** Note the file counts per language, e.g. `git ls-files | sed 's/.*\.//' | sort | uniq -c | sort -rn | head`.
- **History hints, if cheap to get.** Recently active areas show up in `git log --stat -n 30`. This
  only works on local repos, because remote clones are shallow.

## 2. Detect the stack (manifests, then config files)

| Ecosystem | Look at |
|---|---|
| JavaScript/TypeScript | `package.json` (deps, scripts, `bin`, `main`/`exports`), `tsconfig.json`, framework configs (`next.config.*`, `vite.config.*`, `nest-cli.json`) |
| Python | `pyproject.toml`, `setup.py/cfg`, `requirements*.txt`, `environment.yml`, `__main__.py`, console-scripts entry points |
| Go | `go.mod`, `cmd/*/main.go`, `internal/` vs `pkg/` |
| Rust | `Cargo.toml` (workspace members, features), `src/main.rs`, `src/lib.rs`, `build.rs` |
| JVM | `pom.xml`, `build.gradle(.kts)`, `src/main/java/**/Application.java` |
| Ruby | `Gemfile`, `config/routes.rb`, `Rakefile` |
| C/C++ | `CMakeLists.txt`, `Makefile`, `meson.build` |
| .NET | `*.csproj`, `*.sln`, `Program.cs` |
| Infrastructure | `Dockerfile`, `docker-compose.yml`, `.github/workflows/*`, `terraform/`, `k8s/`, `helm/` |
| ML/Data | `*.ipynb`, model/config YAMLs, training scripts, `requirements` with torch/jax/tensorflow/sklearn |

Only count a technology when the code actually uses it. A dependency that nothing imports is
trivia, not a topic.

## 3. Find the spine

- **Entry points.** These are CLIs, servers, `main` functions, exported library APIs, job runners
  and notebooks.
- **Central modules.** Look for files that many others import. A cheap signal is to grep the import
  lines and count how often each internal module is referenced.
- **Main flows.** Trace one or two end-to-end paths, such as "request in → response out", "CLI args
  → result" or "batch → loss → gradient step". Read the code along each path. These flows become
  the backbone of the Big Picture chapter and the code tour.
- **Tests.** They show intended behavior and edge cases, and they make good exercise material.

## 4. Extract nodes

A **node** is one teachable thing:

- `concept`: an idea, e.g. backpropagation, event loop, consistent hashing, JWT auth or memoization;
- `technology`: a library, framework or tool the code relies on, e.g. React, PyTorch, Postgres or Docker;
- `component`: a part of *this* repo, e.g. "the scheduler" or "the storage engine";
- `pattern`: a design pattern or architectural style as used here, e.g. dependency injection, CQRS
  or a plugin registry.

For each node, record:

- `prereqs`: what must be understood first (other node ids);
- `files`: the evidence, as `path` or `path:a-b`. **Every non-assumed node needs at least one file
  that demonstrates it.**
- `core`: whether a reader must understand this node to understand the repo;
- `mode`: start from `reader.default_mode` for `concept` and `pattern` nodes, and use `applied` for
  everything else. Use `assumed` only for topics the user said they know, or for ubiquitous basics
  that fit the reader level, e.g. "what a function is" for intermediate readers. Mention the
  assumptions you made in `suggestions`, so the user can change them.

**Good granularity:** a node is one or two chapter sections' worth. "Python" is too broad, and
"the `retry` decorator" is usually too narrow, unless it is central.

Prerequisites must form a DAG. If two ideas depend on each other, merge them or pick the one that
is easier to teach first.

## 5. Group into chapters

- **Always include:**
  - a `front` chapter `preface`;
  - a first main chapter, "The Big Picture" (`ch01-big-picture`), covering what the repo is, the
    problem it solves, the architecture and its main flows;
  - a `back` chapter `glossary`.
- **Then main chapters,** each with 1–4 closely related nodes and a clear learning arc.
  - Size by repo: small repos (under ~5k lines) get 3–6, medium repos get 6–10, and large repos get
    8–14. Prefer fewer, richer chapters.
  - Order: foundations and core components first, then the features built on them, then cross-cutting
    concerns (testing, deployment, performance), then advanced or optional material.
  - Give each **focus topic** from `reader.focus` its own chapter, or a dominant section of one, with
    `depth: "deep"`.
- **Tag** each chapter `core`, `supporting` or `optional`, and give it a difficulty of 1–3.
- Write `objectives` as 2–4 verbs a reader could be tested on, e.g. "Trace a request through the
  middleware stack".
- `files`: the 3–8 files a writer must read for this chapter.
- Chapter ids follow `chNN-short-slug`, numbered in proposal order, e.g. `ch03-request-lifecycle`.
  Ids are stable and never renumbered, even after reordering. The displayed chapter numbers come
  from position.

## 6. Suggestions

Add 2–6 `suggestions`. These are topics you noticed but left out, or assumptions you made. Each one
gets a one-line `why`. They appear under "Also spotted" at the checkpoint.

## 7. Write `repo.summary`

Two or three sentences: what the repository is, what problem it solves and for whom, and what
makes it interesting to study.
