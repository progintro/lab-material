#!/usr/bin/env python3
"""Concatenate the labs into one Markdown document for the combined build/all.pdf.

all.pdf used to be `pdfunite` over the finished per-lab PDFs, which made three things
impossible: a cover page, a contents list spanning the whole book, and page numbers
that run continuously instead of restarting at every lab. Compiling one document
instead of stitching eleven gets all three, plus PDF bookmarks.

Each lab's post-mermaid `README-out.md` needs three fixes before it can be glued to
its neighbours:

  * Jekyll front matter is only front matter at the very top of a file. Left in the
    middle of a concatenation it renders as a horizontal rule followed by the literal
    text `layout: lab`.
  * The injected table-of-contents block carries GitHub-style anchors that pandoc does
    not generate, so it would become a list of dead links.
  * Image paths are relative to the lab directory. They are rewritten to be relative
    to the repository root rather than passing `--resource-path`, because image
    basenames collide across labs - nearly every lab has an `image1.png` - and a
    search path would silently resolve to whichever lab came first.
"""

import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anchors

LABS = [f"lab{n:02d}" for n in range(11)]
OUT = "build/all.md"

# The eleven labs are three arcs, not eleven equal chapters, and until this was
# emitted the shape of the course was invisible in the book. The divider is raw LaTeX
# in a ```{=latex} block, which is why the all.pdf recipe reads gfm+raw_attribute; the
# lab sources stay plain Markdown, so GitHub and the Pages site are unaffected.
PARTS = {
    "lab00": "Μέρος Α - Τα εργαλεία",
    "lab03": "Μέρος Β - Τα θεμέλια της C",
    "lab06": "Μέρος Γ - Μνήμη, δομές και αρχεία",
}


def divider(title):
    return "```{=latex}\n\\part{%s}\n```\n" % title


def prepare(lab):
    path = f"labs/{lab}/README-out.md"
    if not os.path.exists(path):
        raise SystemExit(f"missing {path} - run the mermaid stage first")
    text = io.open(path, encoding="utf-8").read()

    # drop YAML front matter
    if text.startswith("---\n"):
        end = text.find("\n---\n", 3)
        if end != -1:
            text = text[end + 5:]

    # drop the injected TOC block
    text = re.sub(r"<!-- toc -->.*?<!-- /toc -->\n*", "", text, flags=re.S)

    # resolve short <a id=...> section anchors; the LaTeX writer drops raw HTML
    text = anchors.resolve(text)

    # make image paths relative to the repository root
    text = text.replace("](./img/", f"](labs/{lab}/img/")
    text = text.replace("](./README-out-", f"](labs/{lab}/README-out-")

    return text.strip() + "\n"


def main():
    os.makedirs("build", exist_ok=True)
    parts = []
    for lab in LABS:
        if lab in PARTS:
            parts.append(divider(PARTS[lab]))
        parts.append(prepare(lab))
    io.open(OUT, "w", encoding="utf-8").write("\n\n".join(parts))

    body = io.open(OUT, encoding="utf-8").read()
    missing = [m for m in re.findall(r"\]\((labs/[^)]+)\)", body) if not os.path.exists(m)]
    if missing:
        print("image paths that do not resolve:", file=sys.stderr)
        for m in sorted(set(missing)):
            print(f"  {m}", file=sys.stderr)
        return 1

    imgs = len(re.findall(r"\]\(labs/[^)]+\)", body))
    print(f"{OUT}: {len(LABS)} labs, {len(body.splitlines())} lines, {imgs} images all resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
