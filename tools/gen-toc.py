#!/usr/bin/env python3
"""Generate the per-lab table of contents.

Three renderers, one source. The approach:

  * a TOC is injected into the Markdown between `<!-- toc -->` markers, using
    GitHub's heading-anchor rules, so it works on github.com and on the Pages site;
  * the Makefile strips that block before pandoc runs and passes `--toc` instead,
    so the PDF gets a native, page-numbered, clickable contents list.

Injecting into the Markdown alone would give the PDF a list of dead anchors, because
pandoc slugifies headings differently from GitHub. Using `--toc` alone would leave the
website with nothing. Doing both without the strip would put two contents lists in
every PDF.

  tools/gen-toc.py           rewrite the TOC in every lab
  tools/gen-toc.py --check   exit non-zero if any TOC is out of date (for CI)
"""

import argparse
import glob
import io
import re
import sys

BEGIN = "<!-- toc -->"
END = "<!-- /toc -->"
MIN_ENTRIES = 3  # below this a contents list is just noise


def github_slug(text):
    """GitHub's algorithm: strip markup, lowercase, drop anything that is not a
    letter, digit, space, hyphen or underscore, then spaces to hyphens. Greek
    characters are letters and survive, which is why str.isalnum() is used rather
    than an ASCII-only character class."""
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_]{1,3}([^*_]*)[*_]{1,3}", r"\1", text)
    text = text.strip().lower()
    text = "".join(c for c in text if c.isalnum() or c in " -_")
    return text.replace(" ", "-")


def headings(text):
    out, in_fence = [], False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = re.match(r"^(#{2,3})\s+(.*?)\s*$", line)
        if m:
            out.append((len(m.group(1)), m.group(2)))
    return out


def render(hs):
    seen, lines = {}, []
    for level, title in hs:
        slug = github_slug(title)
        n = seen.get(slug, 0)
        seen[slug] = n + 1
        if n:
            slug = f"{slug}-{n}"
        label = re.sub(r"\s+", " ", title).strip()
        lines.append(f"{'  ' * (level - 2)}- [{label}](#{slug})")
    return "\n".join(lines)


def build_block(text):
    hs = headings(text)
    if len(hs) < MIN_ENTRIES:
        return None
    return f"{BEGIN}\n\n**Περιεχόμενα**\n\n{render(hs)}\n\n{END}"


def apply(text, block):
    if block is None:
        # remove any stale block
        return re.sub(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n*", "", text,
                      flags=re.S)
    if BEGIN in text:
        # lambda, not a plain string: the block can contain backslashes (e.g. $\pi$)
        # which re.sub would otherwise read as replacement-template escapes.
        return re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), lambda _m: block, text, flags=re.S)
    # first insertion: place it just before the first level-2 heading
    lines = text.split("\n")
    for i, l in enumerate(lines):
        if re.match(r"^##\s", l):
            lines[i:i] = [block, ""]
            return "\n".join(lines)
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="report out-of-date tables of contents instead of rewriting")
    args = ap.parse_args()

    stale = []
    for path in sorted(glob.glob("labs/lab*/README.md")):
        src = io.open(path, encoding="utf-8").read()
        dst = apply(src, build_block(src))
        if dst == src:
            continue
        if args.check:
            stale.append(path)
        else:
            io.open(path, "w", encoding="utf-8").write(dst)
            print(f"{path}: table of contents updated")

    if args.check:
        if stale:
            print("out of date, run `make toc`:", file=sys.stderr)
            for p in stale:
                print(f"  {p}", file=sys.stderr)
            return 1
        print("every table of contents is up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
