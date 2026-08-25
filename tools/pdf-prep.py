#!/usr/bin/env python3
"""Prepare a lab's post-mermaid Markdown for the pandoc/PDF pass.

Two transformations, both of which exist because the PDF is a different renderer from
GitHub and the Pages site rather than a third copy of them:

  * the injected `<!-- toc -->` block carries GitHub-style anchors that pandoc does not
    generate, so it would compile to a list of dead links; the PDF gets a native,
    page-numbered contents list from `--toc` instead;
  * short `<a id=...>` section anchors are resolved to real heading slugs, because the
    LaTeX writer drops raw HTML (see tools/anchors.py).

Usage: tools/pdf-prep.py labs/labNN/README-out.md > labs/labNN/README-pdf.md
"""

import io
import re
import sys

import anchors


def prepare(text):
    text = re.sub(r"<!-- toc -->.*?<!-- /toc -->\n*", "", text, flags=re.S)
    return anchors.resolve(text)


if __name__ == "__main__":
    sys.stdout.write(prepare(io.open(sys.argv[1], encoding="utf-8").read()))
