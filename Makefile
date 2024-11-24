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
	docker run \
		-u $(shell id -u):$(shell id -g) \
		-v $(shell pwd):/data \
		-w /data/labs/$* \
		minlag/mermaid-cli \
		-i README.md -o README-out.md --outputFormat png \
		--scale 10

# Step 2: Generate PDFs from README-out.md using pandoc
$(BUILD_FOLDER)/%.pdf: labs/header.tex labs/%/README-out.md
	docker run \
		-u $(shell id -u):$(shell id -g) \
		-w /data/labs/$* \
		-v $(shell pwd):/data \
		ghcr.io/ethan42/pandoctex \
		pandoc README-out.md -f gfm -s \
		-H ../header.tex \
		--pdf-engine=xelatex \
		-o "../../$(BUILD_FOLDER)/$*.pdf" \
		-V mainfont="Linux Libertine O" \
		-V monofont="Noto Mono" \
		-V fontsize=12pt \
		-V colorlinks=true -V linkcolor=darkgray -V urlcolor=blue -V toccolor=gray

# Step 3: Merge all PDFs into one
$(ALL): $(TARGETS)
	docker run \
		-u $(shell id -u):$(shell id -g) \
		-v $(shell pwd):/data \
		-w /data/ \
		minidocks/poppler \
		pdfunite $(TARGETS) $(ALL)