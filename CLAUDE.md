# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

Lab material for the "Introduction to Programming" (C) course at the University of Athens.
It is **content, not software**: the deliverable is a set of PDF lab handouts built from
Greek-language Markdown. There is no application, no test suite, and no linter.

The same Markdown is consumed two ways:

1. **PDF handouts** — `make` runs a Docker/pandoc pipeline, output lands in `build/`.
2. **GitHub Pages site** — the `labs/*/README.md` files render directly on GitHub;
   `_includes/head-custom.html` is the Jekyll hook that adds MathJax and client-side
   mermaid rendering (it rewrites `code.language-mermaid` blocks into `.mermaid` divs).

Any change to a lab must keep both paths working.

## Build

Requires `make`, `docker` and `python3` — no pandoc or LaTeX is installed locally;
both rendering stages run in containers.

```sh
make                          # build every lab PDF + build/all.pdf
make -j4                      # same, in parallel; the per-lab targets are independent
make build/lab05.pdf          # single lab (fastest edit/preview loop)
make labs/lab05/README-out.md # just the mermaid->PNG stage, to debug diagram rendering
make lint                     # defect linter (see tools/lint.py)
make toc / make check-toc     # regenerate / verify the per-lab tables of contents
```

Both images are multi-arch, so nothing runs under emulation any more: a full
`make -j4` takes about **2 minutes** and produces twelve PDFs. (Until the
`pandoctex:20260825` bump the pandoc stage had no arm64 manifest and a serial build
on Apple silicon took ~13 minutes.)

The pandoc image is **pinned to a dated tag** rather than `latest`, because a pandoc
major version can silently change the generated LaTeX — see the babel note below for
exactly that happening. `minlag/mermaid-cli` is still unpinned.

If a build dies with `Error 137` (SIGKILL), the Docker daemon is out of resources
rather than the document being at fault. The `docker run` invocations now pass `--rm`;
before that every build left ~11 stopped containers behind, which is how this repo
accumulated 216 of them (5.3 GB) and started getting builds OOM-killed. Clear any
strays with:

```sh
docker ps -a --format '{{.ID}} {{.Image}}' \
  | grep -E 'mermaid-cli|pandoctex|poppler' | awk '{print $1}' | xargs docker rm
```

**Greek/babel gotcha (pandoc 3.7).** `-V lang=el` alone no longer builds. pandoc 3.1.3
emitted `\babelprovide[main,import]{greek}`, which reads babel's `locale/el/babel-el.ini`;
pandoc 3.7 instead passes `greek` as a *documentclass option*, which makes babel look for
`greek.ldf` — the `babel-greek` package, which the pandoctex image does not ship. The
build then dies with `Package babel Error: Unknown option 'greek'`. The fix is split
across two files: the Makefile passes `-V babel-lang=` to suppress the class option
while keeping `lang=el` (so `pdflang` metadata survives), and `labs/header.tex` issues
the `\babelprovide` call itself. Without this the TOC heading reverts to English.
The cleaner long-term fix is to add `babel-greek` to the image.

**Fontconfig noise:** the pandoc stage runs with `-e HOME=/tmp`. The containers run as
the invoking uid via `-u`, so `$HOME` is unwritable and fontconfig printed three
`No writable cache directories` errors on every single invocation. They were harmless
but buried real diagnostics.

**Encoding gotcha:** the pandoc stage must run with `-e LANG=C.UTF-8`. Without a UTF-8
locale the container's GHC runtime decodes command-line arguments as Latin-1, so any
non-ASCII value passed via `-V` (e.g. the Greek lab title used in the running header)
silently becomes one replacement character per UTF-8 byte. Files read via `-H` are
unaffected — this only bites values passed on the command line.

Pipeline (see `Makefile`), per lab:

1. `minlag/mermaid-cli` — rewrites ` ```mermaid ` fences into PNGs at `--scale 10` and
   emits `README-out.md`. Runs for every lab, including ones with no diagrams.
2. `ghcr.io/ethan42/pandoctex:20260825` (pandoc 3.7) — `pandoc README-out.md -f gfm`
   through `xelatex`, with `labs/header.tex` (Greek setup, brand palette, running
   headers, masthead) and fonts `Linux Libertine O` / `Noto Mono`, which exist only
   inside that image.
3. `build/all.pdf` is **not** a merge of the per-lab PDFs. `tools/build-all.py`
   concatenates the eleven `README-out.md` files into `build/all.md` — stripping front
   matter and the injected TOC, and rewriting image paths to be repo-root-relative —
   and a single pandoc run compiles it with `labs/cover.tex`. That is what makes a
   cover page, a book-wide contents list and continuous page numbering possible;
   `pdfunite` could not produce any of the three. Image paths are rewritten rather
   than resolved via `--resource-path` because basenames collide across labs (nearly
   every lab has an `image1.png`).

`README-out.md`, `README-out*.png` and `build/` are gitignored intermediates — never commit them.

## Layout and conventions

- `labs/labNN/README.md` — the source of truth. Currently **lab00–lab10**. The Makefile
  derives its target list from `$(shell seq -w 0 10)`, so adding a lab11 means editing
  that range too.
- `labs/labNN/img/media/*.png` — images, referenced as `./img/media/imageN.png`.
  `lab03` is the exception: `./img/imageN.png`.
- `docs/lab01.doc` … `docs/lab11.doc` — the legacy Word originals the Markdown was
  converted from. Historical reference only; nothing in the build reads them, and they
  are *not* kept in sync with `labs/`. **The numbering is offset by one**: `docs/labNN.doc`
  corresponds to `labs/lab(NN-1)/` — so `lab11.doc` is lab10 (file I/O), not a missing lab.
  Two exceptions worth knowing: `docs/lab05.doc` and `docs/lab06.doc` map to `labs/lab05`
  and `labs/lab04` respectively (char I/O was moved *before* functions/recursion), and
  `docs/lab05.doc` additionally covers scope/storage of variables plus an appendix on
  splitting a program across multiple `.c`/`.h` files — material with no counterpart
  anywhere in `labs/`.
- `labs/header.tex` — shared LaTeX preamble: `fvextra` line-breaking for code blocks
  (without it long terminal transcripts run off the page and get clipped), the brand
  palette, the `fancyhdr` running header/footer, and the `\AtBeginDocument` masthead
  that puts the two crests on page 1. `\labtitle` is injected per lab by the Makefile.
- `assets/` — `uoa.jpg` and `dit.jpg`, referenced from LaTeX via `\graphicspath` so the
  same preamble works whether pandoc runs from a lab directory or the repo root.

Writing conventions inside a lab README:

- All prose is in Greek. Match the existing register (second person plural, informal-
  but-instructional) and keep code identifiers, shell commands and C keywords in English.
- Exercises are `## Άσκηση N: Τίτλος - (filename.c)` — the target source filename the
  students must produce always appears in the heading.
- Past exam problems are tagged `(Παλιό Θέμα)` and are usually optional.
- Several labs carry a running debugging appendix: `## ΠΑΡΑΡΤΗΜΑ: Αποσφαλμάτωση
  προγραμμάτων (Πράξη Nη)` — the "Πράξη" numbering is a sequence across labs
  (lab02=1η, lab03=2η, lab07=3η, lab08=4η), so keep it consistent if you add one.
- Math uses `$...$` / `$$...$$`; it is rendered by MathJax on Pages and by xelatex in
  the PDF. Both must be satisfied.
- A recurring source of commits is **PDF fit**: wide tables and long code lines overflow
  the `fullpage` layout. Preview with `make build/labNN.pdf` before assuming Markdown
  that looks fine on GitHub is fine on paper.

## Root-level `*.c` files

The C files at the repo root (`prime.c`, `collatz.c`, `maxpath.c`, `fib.c`, `encode.c`,
`decode.c`, `printchar.c`, `example1.c`, …) plus their compiled binaries and `pile.txt`
are **untracked lecture/demo scratch** — worked solutions and live-coding leftovers, not
part of the build. They are not gitignored, so they show up in `git status`; do not stage
them unless explicitly asked. Compile ad hoc:

```sh
gcc -o prime prime.c && ./prime 10001
gcc -o circularprime circularprime.c -lm
```

## CI

- `.github/workflows/publish.yml` — on GitHub **release published** or manual dispatch:
  auto-increments the patch component of the latest tag, pushes the new tag, runs `make`,
  and uploads every `build/*.pdf` as release assets via `hub`. Releases are the
  distribution channel for the handouts.
- `.github/workflows/kaizen.yml` — manual-dispatch-only AI review pass (`ethan42/kaizen`);
  not part of the normal build.
