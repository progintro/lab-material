# Automatically generate PDFs from lab READMEs

BUILD_FOLDER ?= build

PDFs = $(foreach n, $(shell seq -w 0 10), lab$(n).pdf)

TARGETS = $(PDFs:%=$(BUILD_FOLDER)/%)
ALL = $(BUILD_FOLDER)/all.pdf

all: $(BUILD_FOLDER) $(TARGETS) $(ALL)

# Step 0: Create build folder
$(BUILD_FOLDER):
	mkdir -p $(BUILD_FOLDER)

# Step 1: Convert mermaid graphs into pngs and generate README-out.md
labs/%/README-out.md: labs/%/README.md
	docker run --rm \
		-u $(shell id -u):$(shell id -g) \
		-v $(shell pwd):/data \
		-w /data/labs/$* \
		minlag/mermaid-cli \
		-i README.md -o README-out.md --outputFormat png \
		--scale 10

# Step 2: Generate PDFs from README-out.md using pandoc
#
# tools/pdf-prep.py strips the injected <!-- toc --> block (it carries GitHub-style
# anchors, which pandoc does not generate, so it would render as a list of dead links -
# the PDF gets a native, page-numbered contents list from --toc instead) and resolves
# the short <a id=...> section anchors, which the LaTeX writer would otherwise drop.
$(BUILD_FOLDER)/%.pdf: labs/header.tex labs/%/README-out.md tools/pdf-prep.py tools/anchors.py
	python3 tools/pdf-prep.py labs/$*/README-out.md > labs/$*/README-pdf.md
	docker run --rm \
		-u $(shell id -u):$(shell id -g) \
		-w /data/labs/$* \
		-v $(shell pwd):/data \
		-e LANG=C.UTF-8 \
		-e HOME=/tmp \
		ghcr.io/ethan42/pandoctex:20260825 \
		pandoc README-pdf.md -f gfm -s --toc --toc-depth=2 \
		-H ../header.tex \
		-V header-includes='\def\labtitle{$(shell grep -m1 "^# " labs/$*/README.md | sed -e "s/^# //" -e "s/:.*//" -e "s/#//g")}' \
		--pdf-engine=xelatex \
		-o "../../$(BUILD_FOLDER)/$*.pdf" \
		-V mainfont="Linux Libertine O" \
		-V monofont="Noto Mono" \
		-V fontsize=12pt \
		-V lang=el -V babel-lang= \
		-V colorlinks=true -V linkcolor=ditcharcoal -V urlcolor=ditcyan -V toccolor=ditcharcoal
	rm -f labs/$*/README-pdf.md

# Step 3: Build the combined book.
#
# This is a single pandoc compile over the concatenated sources rather than a
# pdfunite of the finished PDFs, which is what makes a cover page, a book-wide
# contents list and continuous page numbering possible at all.
OUTS = $(foreach n, $(shell seq -w 0 10), labs/lab$(n)/README-out.md)

$(ALL): $(BUILD_FOLDER) labs/header.tex labs/cover.tex tools/anchors.py $(OUTS)
	python3 tools/build-all.py
	docker run --rm \
		-u $(shell id -u):$(shell id -g) \
		-v $(shell pwd):/data \
		-w /data \
		-e LANG=C.UTF-8 \
		-e HOME=/tmp \
		ghcr.io/ethan42/pandoctex:20260825 \
		pandoc build/all.md -f gfm -s --toc --toc-depth=2 \
		-H labs/header.tex \
		-H labs/cover.tex \
		-V header-includes='\def\labtitle{Συλλογή Εργαστηρίων}' \
		--pdf-engine=xelatex \
		-o "$(ALL)" \
		-V mainfont="Linux Libertine O" \
		-V monofont="Noto Mono" \
		-V fontsize=12pt \
		-V lang=el -V babel-lang= \
		-V colorlinks=true -V linkcolor=ditcharcoal -V urlcolor=ditcyan -V toccolor=ditcharcoal
# Regenerate the per-lab tables of contents (and verify them in CI)
.PHONY: toc check-toc lint
toc:
	python3 tools/gen-toc.py

check-toc:
	python3 tools/gen-toc.py --check

lint:
	python3 tools/lint.py
