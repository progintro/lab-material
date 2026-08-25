#!/usr/bin/env python3
"""Lint the lab material.

Every check here corresponds to a defect class that was actually found in this repo,
mostly left behind by the original Word -> Markdown conversion. Standard library only,
so it runs anywhere `python3` does.

Severities:
  error  the tree is clean of these today; a new one is a regression -> CI fails
  warn   known outstanding work (the NORMALIZE sweep); reported but not fatal

Run `--strict` to promote warnings to errors. Flip CI to `--strict` once NORMALIZE
has landed.
"""

import argparse
import glob
import re
import sys
from collections import defaultdict

LABS = "labs/lab*/README.md"

# Greek capitals that are visually identical to Latin ones. Mixing them silently breaks
# copy-paste of pseudocode and makes text unsearchable.
GREEK_HOMOGLYPHS = "ΑΒΕΖΗΙΚΜΝΟΡΤΥΧ"
LATIN_HOMOGLYPHS = "ABEZHIKMNOPTYX"

# Backslash escapes that pandoc emitted when converting from .doc and that mean nothing
# in Markdown.
WORD_ESCAPES = re.compile(r"\\([\"'#%<>\[\]])")

findings = defaultdict(list)


def add(sev, check, path, line, msg):
    findings[sev].append((check, path, line, msg))


def code_spans(text):
    """Character offsets covered by inline code spans, so checks can skip them."""
    covered = set()
    for m in re.finditer(r"`+[^`]*`+", text):
        covered.update(range(m.start(), m.end()))
    return covered


def iter_blocks(lines):
    """Yield (index, line, in_fence) marking fenced code blocks."""
    in_fence = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            yield i, line, in_fence, True
            in_fence = not in_fence
        else:
            yield i, line, in_fence, False


def check_file(path):
    text = open(path, encoding="utf-8").read()
    lines = text.split("\n")

    # --- front matter (the website navigation depends on it) -------------------
    if not text.startswith("---\n"):
        add("error", "front-matter", path, 1, "missing Jekyll front matter")
    elif "layout: lab" not in text.split("---\n", 2)[1]:
        add("error", "front-matter", path, 1, "front matter is missing 'layout: lab'")

    # --- per-line checks ------------------------------------------------------
    headings = []
    fences = []
    for i, line, in_fence, is_marker in iter_blocks(lines):
        n = i + 1

        if is_marker and not in_fence:  # opening fence
            lang = line.strip()[3:].strip()
            fences.append((n, lang))
            if not lang:
                add("warn", "code-fence", path, n, "code block has no language tag")
            continue

        # Homoglyphs are checked inside fenced blocks too - pseudocode and code that
        # students copy verbatim is the worst place for them to hide.
        check_homoglyphs(path, n, line)

        if in_fence:
            continue

        # headings
        m = re.match(r"^(#+)\s+(.*)", line)
        if m:
            headings.append((n, len(m.group(1)), m.group(2)))

        # images without alt text
        for im in re.finditer(r"!\[\s*\]\(([^)]*)\)", line):
            add("warn", "img-alt", path, n, f"image has empty alt text: {im.group(1)}")

        # leftover Word escapes, ignoring anything inside inline code
        spans = code_spans(line)
        for em in WORD_ESCAPES.finditer(line):
            if em.start() not in spans:
                add("warn", "word-escape", path, n,
                    f"leftover escape {em.group(0)!r} from the .doc conversion")

    # --- heading hierarchy ----------------------------------------------------
    prev = None
    for n, level, txt in headings:
        if prev is not None and level > prev + 1:
            add("warn", "heading-jump", path, n,
                f"heading jumps from h{prev} to h{level}: {txt[:50]!r}")
        prev = level

    # --- internal anchors -----------------------------------------------------
    slugs = {github_slug(t) for _, _, t in headings}
    for i, line, in_fence, is_marker in iter_blocks(lines):
        if in_fence or is_marker:
            continue
        for lm in re.finditer(r"\]\(#([^)]+)\)", line):
            if lm.group(1) not in slugs:
                add("error", "dead-anchor", path, i + 1,
                    f"link to #{lm.group(1)} matches no heading in this file")

    return headings


def github_slug(text):
    """Approximate GitHub's heading-anchor algorithm (handles Greek)."""
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.strip().lower()
    text = "".join(c for c in text if c.isalnum() or c in " -_")
    return text.replace(" ", "-")


def check_homoglyphs(path, n, line):
    """A Greek capital sitting in a code-like context, or a Latin capital opening a
    Greek word. Both render identically and are invisible in review."""
    for hm in re.finditer(r"[" + GREEK_HOMOGLYPHS + r"](?=[\s`]*[\[\](){}0-9=]|x[A-Z0-9])", line):
        ch = hm.group(0)
        add("error", "homoglyph", path, n,
            f"Greek {ch!r} (U+{ord(ch):04X}) in a code-like context; "
            f"did you mean Latin {LATIN_HOMOGLYPHS[GREEK_HOMOGLYPHS.index(ch)]!r}?")
    for hm in re.finditer(r"(?<![A-Za-z])([" + LATIN_HOMOGLYPHS + r"])(?=[α-ωά-ώ])", line):
        ch = hm.group(1)
        add("error", "homoglyph", path, n,
            f"Latin {ch!r} (U+{ord(ch):04X}) starting a Greek word; "
            f"did you mean Greek {GREEK_HOMOGLYPHS[LATIN_HOMOGLYPHS.index(ch)]!r}?")


def check_exercise_files(all_headings):
    """Exercise headings name the .c file the student must produce. Two bugs this
    catches: a heading naming one file while the body tells you to write another
    (filediff.c vs compare.c), and the same filename reused by two different labs."""
    owner = {}
    for path, headings in all_headings.items():
        body = open(path, encoding="utf-8").read()
        for n, level, txt in headings:
            if not txt.startswith("Άσκηση"):
                continue
            names = re.findall(r"([A-Za-z_][A-Za-z0-9_]*\.c)", txt)
            for name in names:
                if name not in body.split("\n", 1)[1]:
                    add("error", "filename", path, n,
                        f"heading names {name} but it never appears in the body")
                if name in owner and owner[name] != path:
                    add("warn", "filename", path, n,
                        f"{name} is also used by {owner[name]}")
                owner[name] = path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true",
                    help="treat warnings as errors (enable after the NORMALIZE sweep)")
    args = ap.parse_args()

    paths = sorted(glob.glob(LABS))
    if not paths:
        print("no lab files found - run from the repository root", file=sys.stderr)
        return 2

    all_headings = {}
    for p in paths:
        all_headings[p] = check_file(p)
    check_exercise_files(all_headings)

    counts = defaultdict(int)
    for sev in ("error", "warn"):
        for check, path, line, msg in sorted(findings[sev], key=lambda f: (f[1], f[2])):
            print(f"{path}:{line}: {sev}: [{check}] {msg}")
            counts[check] += 1

    print()
    print(f"checked {len(paths)} files: "
          f"{len(findings['error'])} errors, {len(findings['warn'])} warnings")
    if counts:
        print("by check: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))

    failed = len(findings["error"]) or (args.strict and len(findings["warn"]))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
