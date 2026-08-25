#!/usr/bin/env python3
"""Lint the lab material.

Every check here corresponds to a defect class that was actually found in this repo,
mostly left behind by the original Word -> Markdown conversion. Standard library only,
so it runs anywhere `python3` does.

Severities:
  error  the tree is clean of these today; a new one is a regression -> CI fails
  warn   known outstanding work; reported but not fatal
  todo   a check written before the sweep that satisfies it; never fatal, not even
         under --strict, so the spec can land before the prose it describes

`todo` exists because CI already runs --strict. A structural check added as `warn`
would turn the whole repository red the moment it was written and keep it red until
the last lab was swept, which would block every unrelated change in between. Landing
these as `todo` lets the linter be the written spec first and the gate second: the
count falls lab by lab, and when it hits zero the checks are promoted to `error` and
this severity is deleted.

Run `--strict` to promote warnings to errors.
"""

import argparse
import glob
import re
import sys
from collections import defaultdict

LABS = "labs/lab*/README.md"

# Structural convention, documented in CONTRIBUTING.md under "Οδηγίες συγγραφής".
#
# STRUCTURE is what the checks below enforce; keep the two in sync. Every H2 in a lab
# is one of four kinds, and they appear in this order:
#
#   ## Βήμα N: Τίτλος                        guided walkthrough; nothing handed in
#   ## Άσκηση N: Τίτλος (file.c)             the student produces file.c
#   ## Για να πάτε παρακάτω (Προαιρετικό)    pointers outward
#   ## Παράρτημα: Τίτλος                     always last; at most one
#
# Badges attach to the number, before the colon: `## Άσκηση 3 (Παλιό θέμα): Τίτλος`.
BADGES = ("Παλιό θέμα", "Προχωρημένο", "Προαιρετικό")

H2_STEP = re.compile(r"^Βήμα (\d+): \S")
H2_EXERCISE = re.compile(
    r"^Άσκηση (\d+)(?: \(([^)]+)\))?: (.+?) "
    r"\(([a-z_][a-z0-9_]*\.(?:c|h|txt)(?: και [a-z_][a-z0-9_]*\.(?:c|h|txt))*)\)$"
)
H2_ONWARD = re.compile(r"^Για να πάτε παρακάτω \(Προαιρετικό\)$")
H2_APPENDIX = re.compile(r"^Παράρτημα: \S")

# An exercise that lives inside an appendix is an H3 using the same grammar.
H3_EXERCISE = re.compile(r"^Άσκηση (\d+)")

# The debugging appendices form one series across the book: (Πράξη 1η) .. (Πράξη 5η).
PRAXI = re.compile(r"\(Πράξη (\d+)η\)")

# Shell transcripts and program output were tagged `sh`, `bash` and `text`
# interchangeably - all three appeared inside single files for indistinguishable
# content. `text` is the one that renders identically everywhere and claims the least.
FENCE_LANGS = {"c", "text", "mermaid", "make"}
FENCE_ALIASES = {"sh": "text", "bash": "text", "console": "text", "makefile": "make"}

# Headings are labels, not instructions. lab01 had 28 headings that were whole
# sentences ending in a period, which is what made its contents list unreadable.
HEADING_MAX = 80

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
            elif lang in FENCE_ALIASES:
                add("todo", "fence-lang", path, n,
                    f"code fence tagged `{lang}`; use `{FENCE_ALIASES[lang]}` "
                    f"(the labs tagged indistinguishable transcripts three ways)")
            elif lang not in FENCE_LANGS:
                add("todo", "fence-lang", path, n,
                    f"code fence tagged `{lang}`, which is not one of "
                    f"{', '.join(sorted(FENCE_LANGS))}")
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

    # --- heading style --------------------------------------------------------
    for n, level, txt in headings:
        if level == 1:
            continue
        bare = txt.rstrip()
        if bare.endswith("."):
            add("todo", "heading-style", path, n,
                f"heading ends with a period - headings are labels, not sentences: "
                f"{bare[:60]!r}")
        if len(bare) > HEADING_MAX:
            add("todo", "heading-style", path, n,
                f"heading is {len(bare)} chars (max {HEADING_MAX}); it belongs in the "
                f"body, not the contents list: {bare[:60]!r}...")

    # --- heading hierarchy ----------------------------------------------------
    prev = None
    for n, level, txt in headings:
        if prev is not None and level > prev + 1:
            add("warn", "heading-jump", path, n,
                f"heading jumps from h{prev} to h{level}: {txt[:50]!r}")
        prev = level

    # --- internal anchors -----------------------------------------------------
    # Short explicit anchors (<a id="webmail"></a>) let a heading be descriptive
    # without making its link unwieldy, and keep inbound links stable across a rename.
    slugs = {github_slug(t) for _, _, t in headings}
    slugs |= set(re.findall(r'<a\s+id="([^"]+)"', text))
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


def parse_badges(path, n, raw):
    """Split and validate the parenthetical after an exercise number.

    Before the sweep this slot held seven different spellings - `Advanced #1:`,
    `(Παλιό Θέμα)`, `(Παλιό θέμα)`, `(από θέμα εξετάσεων)`, `(Παλιό Θέμα / Προαιρετικό)`
    and two more - which is why the vocabulary is closed and the order fixed.
    """
    if raw is None:
        return []
    parts = [b.strip() for b in raw.split(",")]
    bad = [b for b in parts if b not in BADGES]
    if bad:
        add("todo", "badge-vocab", path, n,
            f"unknown badge {bad[0]!r}; allowed: {', '.join(BADGES)}")
        return parts
    order = [BADGES.index(b) for b in parts]
    if order != sorted(order):
        add("todo", "badge-vocab", path, n,
            f"badges out of order: {raw!r}; canonical order is {', '.join(BADGES)}")
    return parts


def check_structure(path, headings):
    """Every H2 is one of the four documented kinds, in the documented order."""
    h2 = [(n, t) for n, level, t in headings if level == 2]

    seen_exercise = False
    appendix_at = None
    exercise_numbers = []

    for i, (n, txt) in enumerate(h2):
        if H2_APPENDIX.match(txt):
            if appendix_at is not None:
                add("todo", "section-type", path, n,
                    "a lab has at most one appendix")
            appendix_at = i
            continue

        # Anything after the appendix breaks the "appendix is last" rule. lab07 and
        # lab08 both did this, for different reasons and with different fixes.
        if appendix_at is not None:
            add("todo", "appendix-last", path, n,
                f"{txt[:40]!r} follows the appendix; the appendix is always the "
                f"last H2 (an exercise that depends on it belongs inside it as an H3)")

        if H2_STEP.match(txt):
            if seen_exercise:
                add("todo", "section-type", path, n,
                    f"Βήμα after an Άσκηση: {txt[:40]!r}; walkthrough steps come first")
            continue
        if H2_ONWARD.match(txt):
            continue
        m = H2_EXERCISE.match(txt)
        if m:
            seen_exercise = True
            exercise_numbers.append((n, int(m.group(1))))
            parse_badges(path, n, m.group(2))
            continue

        add("todo", "section-type", path, n,
            f"H2 {txt[:50]!r} is not one of: 'Βήμα N: …', 'Άσκηση N: … (file.c)', "
            f"'Για να πάτε παρακάτω (Προαιρετικό)', 'Παράρτημα: …'")

    # Exercises inside the appendix continue the lab's own numbering.
    if appendix_at is not None:
        start = next(n for n, lvl, t in headings if lvl == 2 and H2_APPENDIX.match(t))
        for n, level, txt in headings:
            if level == 3 and n > start and txt.startswith("Άσκηση"):
                m = H3_EXERCISE.match(txt)
                if not m:
                    add("todo", "exercise-heading", path, n,
                        f"appendix exercise {txt[:40]!r} has no number; it continues "
                        f"the lab's own series")
                else:
                    exercise_numbers.append((n, int(m.group(1))))

    nums = [num for _, num in exercise_numbers]
    if nums and sorted(nums) != list(range(1, len(nums) + 1)):
        add("todo", "exercise-heading", path, exercise_numbers[0][0],
            f"exercise numbers are {nums}; they must run 1..{len(nums)} with no gaps "
            f"or repeats")
    return appendix_at is not None


def check_framing(path):
    """The opening blockquote declares what the lab needs and what it produces.

    The deliverable list is the part that rots: it is written once and then exercises
    are added or moved into an appendix without it being updated. Checking it against
    the exercise headings is what keeps it honest.
    """
    text = open(path, encoding="utf-8").read()
    head = text.split("\n## ", 1)[0]

    keys = ["**Στόχοι**", "**Προαπαιτούμενα:**", "**Αρχεία που θα φτιάξετε:**"]
    pos = []
    for k in keys:
        i = head.find(k)
        if i < 0:
            add("todo", "framing", path, 1, f"opening blockquote is missing {k}")
        pos.append(i)
    present = [i for i in pos if i >= 0]
    if present != sorted(present):
        add("todo", "framing", path, 1,
            f"opening blockquote keys are out of order; expected {' then '.join(keys)}")

    m = re.search(r"\*\*Αρχεία που θα φτιάξετε:\*\*(.*)", head)
    if not m:
        return
    declared = set(re.findall(r"`([A-Za-z_][A-Za-z0-9_]*\.(?:c|h|txt))`", m.group(1)))

    named = set()
    for line in text.split("\n"):
        hm = re.match(r"^#{2,3} (Άσκηση .*)", line)
        if hm:
            named |= set(re.findall(r"([a-z_][a-z0-9_]*\.(?:c|h|txt))", hm.group(1)))

    for f in sorted(named - declared):
        add("todo", "framing", path, 1,
            f"{f} is an exercise deliverable but is not in "
            f"'Αρχεία που θα φτιάξετε'")
    for f in sorted(declared - named):
        add("todo", "framing", path, 1,
            f"{f} is listed in 'Αρχεία που θα φτιάξετε' but no exercise heading "
            f"names it")


def check_praxi(all_headings):
    """The debugging appendices are one series running across the book, not five
    independent appendices that happen to share a title."""
    found = []
    for path in sorted(all_headings):
        for n, level, txt in all_headings[path]:
            if level == 2 and "Αποσφαλμάτωση προγραμμάτων" in txt:
                m = PRAXI.search(txt)
                if not m:
                    add("todo", "praxi-sequence", path, n,
                        "debugging appendix is missing its (Πράξη Nη) number")
                else:
                    found.append((path, n, int(m.group(1))))
    nums = [k for _, _, k in found]
    if nums != list(range(1, len(nums) + 1)):
        for path, n, k in found:
            add("todo", "praxi-sequence", path, n,
                f"(Πράξη {k}η) - the series across the book reads {nums}; it must "
                f"run 1..{len(nums)} in lab order")


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
        check_structure(p, all_headings[p])
        check_framing(p)
    check_exercise_files(all_headings)
    check_praxi(all_headings)

    counts = defaultdict(int)
    for sev in ("error", "warn", "todo"):
        for check, path, line, msg in sorted(findings[sev], key=lambda f: (f[1], f[2])):
            print(f"{path}:{line}: {sev}: [{check}] {msg}")
            counts[check] += 1

    print()
    print(f"checked {len(paths)} files: "
          f"{len(findings['error'])} errors, {len(findings['warn'])} warnings, "
          f"{len(findings['todo'])} todo")
    if counts:
        print("by check: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))

    # `todo` is deliberately excluded: it marks checks that describe the convention
    # before the prose satisfies it. See the module docstring.
    failed = len(findings["error"]) or (args.strict and len(findings["warn"]))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
