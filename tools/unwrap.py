#!/usr/bin/env python3
"""Join hard-wrapped Markdown paragraphs onto single lines.

The lab sources inherited 72-column hard wraps from the original Word conversion,
sitting alongside paragraphs that were written unwrapped. That mix makes every diff
noisy: change one word and the whole block reflows, so review shows a paragraph
rewritten when a single character moved.

This rewrites body paragraphs, list items and blockquote paragraphs onto one line
each, and leaves strictly alone: YAML front matter, fenced code blocks, tables,
headings, indented (4-space) code, and anything already on its own line.

Verify with `pandoc -t plain` before and after - the rendered text must be identical.
"""

import glob
import io
import re
import sys

FENCE = re.compile(r"^\s*```")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
TABLE = re.compile(r"^\s*\|")
LIST = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+")
QUOTE = re.compile(r"^(\s*>+\s?)")
INDENTED_CODE = re.compile(r"^(?: {4,}|\t)")
# A line that must never be glued onto the previous one.
BREAKS = re.compile(r"^\s*(\|.*|>+.*|#{1,6}\s.*|[-*_]{3,}\s*|)$")


def is_block_start(line):
    return bool(
        HEADING.match(line)
        or TABLE.match(line)
        or LIST.match(line)
        or FENCE.match(line)
        or QUOTE.match(line)
        or INDENTED_CODE.match(line)
        or not line.strip()
    )


def unwrap(text):
    lines = text.split("\n")
    out = []
    i = 0
    in_fence = False

    # preserve YAML front matter verbatim
    if lines and lines[0].strip() == "---":
        out.append(lines[0])
        i = 1
        while i < len(lines) and lines[i].strip() != "---":
            out.append(lines[i])
            i += 1
        if i < len(lines):
            out.append(lines[i])
            i += 1

    while i < len(lines):
        line = lines[i]

        if FENCE.match(line):
            in_fence = not in_fence
            out.append(line)
            i += 1
            continue
        if in_fence:
            out.append(line)
            i += 1
            continue

        # blockquote paragraph: join consecutive '>' lines that carry text
        m = QUOTE.match(line)
        if m:
            # A bare '>' is a paragraph separator inside the quote. It must be emitted
            # verbatim: folding it into the line below merges two paragraphs into one.
            if not line[len(m.group(1)):].strip():
                out.append(line.rstrip())
                i += 1
                continue
            prefix = m.group(1)
            buf = [line[len(m.group(1)):].rstrip()]
            i += 1
            while i < len(lines):
                m2 = QUOTE.match(lines[i])
                if not m2:
                    break
                rest = lines[i][len(m2.group(1)):]
                if not rest.strip() or LIST.match(rest) or HEADING.match(rest) or FENCE.match(rest):
                    break
                buf.append(rest.strip())
                i += 1
            out.append(prefix.rstrip() + " " + " ".join(b for b in buf if b) if any(buf) else prefix.rstrip())
            continue

        # list item: join its wrapped continuation lines
        m = LIST.match(line)
        if m:
            buf = [line.rstrip()]
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if not nxt.strip() or is_block_start(nxt):
                    break
                buf.append(nxt.strip())
                i += 1
            out.append(buf[0] + ("" if len(buf) == 1 else " " + " ".join(buf[1:])))
            continue

        # anything structural passes straight through
        if is_block_start(line):
            out.append(line)
            i += 1
            continue

        # ordinary paragraph
        buf = [line.strip()]
        i += 1
        while i < len(lines):
            nxt = lines[i]
            if not nxt.strip() or is_block_start(nxt):
                break
            buf.append(nxt.strip())
            i += 1
        out.append(" ".join(buf))

    return "\n".join(out)


def main():
    changed = 0
    for path in sorted(glob.glob("labs/lab*/README.md")):
        src = io.open(path, encoding="utf-8").read()
        dst = unwrap(src)
        if dst != src:
            io.open(path, "w", encoding="utf-8").write(dst)
            before = sum(1 for l in src.split("\n") if l.strip())
            after = sum(1 for l in dst.split("\n") if l.strip())
            print(f"{path}: {before} -> {after} non-blank lines")
            changed += 1
    print(f"{changed} files rewrapped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
