#!/usr/bin/env python3
"""Short section anchors, resolved for the PDF pass.

A lab heading should be descriptive, but a link to it should stay short and survive a
retitling, so sections carry an explicit anchor above the heading:

    <a id="webmail"></a>

    ## Βήμα 1: Το ακαδημαϊκό σας email (webmail)

GitHub and the Pages site honour that `id` directly, so `[Webmail](#webmail)` works on
both. The LaTeX writer, however, drops raw HTML: the anchor disappears and every link
to it becomes an undefined hyper-reference. pandoc's `header_attributes` extension
(`## Heading {#webmail}`) would be the obvious fix, but it is not available for the
`gfm` reader - `pandoc -f gfm+header_attributes` errors out - and GitHub would render
the braces literally anyway.

So the anchors are resolved on the way to the PDF: each `<a id="X">` is matched with
the heading that follows it, links to `#X` are rewritten to that heading's own slug,
and the raw HTML is dropped.
"""

import re

ANCHOR = re.compile(r'^<a\s+id="([^"]+)"\s*></a>\s*$')


def slug(text):
    """pandoc's auto_identifiers, close enough for the headings this repo uses.

    Greek letters are alphanumeric and survive, which is why str.isalnum() is used
    rather than an ASCII character class.
    """
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_]{1,3}([^*_]*)[*_]{1,3}", r"\1", text)
    text = text.strip().lower()
    text = "".join(c for c in text if c.isalnum() or c in " -_")
    return text.replace(" ", "-")


def resolve(text):
    """Drop `<a id=...>` lines and repoint every link that targeted them."""
    lines = text.split("\n")
    mapping = {}
    for i, line in enumerate(lines):
        m = ANCHOR.match(line.strip())
        if not m:
            continue
        for nxt in lines[i + 1:]:
            hm = re.match(r"^#{1,6}\s+(.*)", nxt)
            if hm:
                mapping[m.group(1)] = slug(hm.group(1))
                break

    kept = [l for l in lines if not ANCHOR.match(l.strip())]
    out = "\n".join(kept)
    for short, full in mapping.items():
        out = out.replace("](#%s)" % short, "](#%s)" % full)
    # An anchor line leaves a blank line behind; collapse the resulting triples.
    return re.sub(r"\n{3,}", "\n\n", out)
