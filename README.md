# Word report templates

Four pandoc reference documents, built from one script. Style C keeps its original slate
blue and Calibri; styles A, B and D share a burgundy palette and the Aptos typeface, so
what separates them is structure, not colour.

    pandoc report.md --reference-doc=templates/chancery-reference.docx --toc -o report.docx

Then in Word: select all (Ctrl+A / Cmd+A) and press F9 to build the table of contents.
Pandoc writes a real TOC field, which stays empty until Word fills it.

Rebuild every template after a change:

    python3 templates/build_reference.py

The script starts from `pandoc --print-default-data-file reference.docx`, so the style
inventory always matches the installed pandoc (built and tested against pandoc 3.11).

## The four

| File | Style | Typeface | Accent | Headings | Tables | Density |
|---|---|---|---|---|---|---|
| `chancery-reference.docx` | A — classic executive | Aptos | Burgundy `8C1D34` | numbered 1.1.1, rule under H1 | hairline, rules only | medium, justified |
| `meridian-reference.docx` | B — modern and open | Aptos | Burgundy `8C1D34` | unnumbered, large and light | open, banded rows | low, much air |
| `atlas-reference.docx` | D — bold editorial | Aptos | Burgundy `8C1D34` | unnumbered, heavy, accent rule above H1 | charcoal header band | medium |
| `foundry-reference.docx` | C — dense technical | Calibri | Slate blue `21456E` | numbered 1.1.1, reversed H1 bar | full grid | high |

Differences that carry the identity: A justifies its text, numbers its headings and
keeps every rule hairline. B triples the white space, drops numbering and sets a 32 pt
light title. D reverses the title block out of burgundy and runs a charcoal header band
across its tables.

## Fonts

| Role | A, B, D | C | Ships with |
|---|---|---|---|
| Text, headings, tables | Aptos | Calibri | Aptos: Microsoft 365. Calibri: Office 2007 and later |
| Large titles | Aptos Display | Calibri | with Aptos |
| Code, inline code | Consolas | Consolas | Office, Windows and Mac |
| Equations | Cambria Math | Cambria Math | Word itself |

One caveat on Aptos, since it is newer than the rest: it arrived as the Microsoft 365
default in 2024 and is not present in the perpetual Office 2019 or 2021 releases, where
Word substitutes another face. If part of the estate still runs a perpetual licence,
change `sans="Aptos"` and `display="Aptos Display"` to `"Calibri"` in
`templates/build_reference.py` and rebuild.

Style A was originally a serif design. Under Aptos it reads as a sans document that
keeps its classical structure. `Aptos Serif` ships with the same family and restores the
serif character with a one-word change, if that matters more than the single typeface.

## Look before you choose

Open any of the four in Word. The body is a three-page specimen report using every
style: title block, headings to level six, lists, definitions, quote, note and caution
blocks, a table with caption and source note, a figure placeholder, an equation, a code
block, a footnote, and static table of contents entries.

Pandoc reads only styles, numbering, page setup and the running head and foot from these
files. The specimen text is discarded on every conversion.

The running head carries the classification alone; the foot carries the classification
and a page field. Both are placeholders — edit them once in the reference document.

## What the templates style

Every style below is one pandoc writes by itself. Nothing needs markup in the markdown.

| Markdown | Word style |
|---|---|
| `title:`, `subtitle:`, `author:`, `date:` | Title, Subtitle, Author, Date |
| `abstract:` | Abstract Title, Abstract |
| `#` … `######` | heading 1 … heading 6 |
| paragraph | Body Text, First Paragraph |
| list item, table cell | Compact |
| `>` quote | Block Text |
| definition list | Definition Term, Definition |
| table | Table (table style), Table Caption |
| image | Captioned Figure, Image Caption |
| `` `code` `` | Verbatim Char |
| fenced code block | Source Code + 31 token styles |
| footnote | Footnote Text, Footnote Reference |
| link | Hyperlink |
| `--toc` | TOC Heading, toc 1–3 |
| running head and foot | header, footer |
| `$math$`, `$$math$$` | native OMML, Cambria Math |

Code blocks use a light panel in all four templates, with an accent rule down the left
edge. Keyword colour follows each theme's accent; inline code shares the panel colour.

See *Heading numbers* below for how A and C number their headings. B and D do not
number.

## Heading numbers

A and C number headings from a multilevel list bound to Heading 1–5. Word keeps
style-linked numbering only when the file is written the way Word itself writes it, so
the definition is a matched set:

- a numbering style, `Heading Numbers`, that owns the list;
- the list definition that declares it (`w:styleLink`), carrying the levels and their
  `w:pStyle` links, with `w:nsid` and `w:tmpl` present;
- a second definition that points back at the style (`w:numStyleLink`), which is what
  the heading styles reference.

Written any looser — the levels alone, with numbering set directly on the heading styles
— Word discards the numbering the first time the template is opened and saved, and every
report made afterwards comes out unnumbered.

If your Word build still strips it, there is a route that cannot be stripped, because
the numbers become ordinary text rather than a list:

    pandoc report.md --reference-doc=templates/chancery-reference.docx --number-sections -o report.docx

Pandoc then writes each number as a run in the `Section Number` character style,
followed by a tab. That style carries no formatting of its own, so numbers inherit the
heading they sit in, and every numbered heading style has a tab stop at the matching
indent.

Use one route or the other, never both: with style numbering still active,
`--number-sections` produces headings that read `1 1 Executive summary`. To switch a
template to the pandoc route, set `numbered=False` on its theme in
`templates/build_reference.py` and rebuild.

## Four extra styles, applied from markdown

```markdown
::: {custom-style="Lead"}
Recommendation: approve the second phase of the platform migration.
:::

::: {custom-style="Note"}
**Note.** The figures in this section are unaudited.
:::

::: {custom-style="Caution"}
**Caution.** Vendor concentration breaches the group risk appetite statement.
:::

::: {custom-style="Source Note"}
Source: consolidated ledger extract, 31 August 2026.
:::
```

## Things to do by hand in Word

- Update the TOC field (F9). Pandoc cannot fill it.
- Edit the header and foot placeholder text in the reference document, not in reports.
- Switch on *Table Design → Total Row* for a totals row; the accent rule and bold text
  are already defined in each table style.
- List bullet and number glyphs come from pandoc's own numbering, not from the reference
  document. They cannot be restyled through these templates.
- Equation numbers need a right-aligned tab stop on the equation paragraph. Markdown has
  no syntax for them.
- Style D had a drop cap in the HTML preview. Pandoc cannot apply one per paragraph, so
  it is not in the template.

## Repository

    templates/build_reference.py       all four templates, as one parameterised script
    templates/*-reference.docx         the built reference documents
    test/sample.md                     exercises every supported element
    preview/                           the eight HTML style proposals from the review round

Rendered proofs and converted output are not tracked. To produce them:

    python3 templates/build_reference.py
    cd test && pandoc sample.md --reference-doc=../templates/atlas-reference.docx --toc -o out.docx

## Verification

Each template converts `test/sample.md` without a single undefined style, and none leaks
its specimen body, footnote or figure into the output. All four were rendered to PDF
with LibreOffice and read page by page.

The numbering fix was checked as far as this machine allows: the XML now matches Word's
linked-style form, and an open-and-save round trip through LibreOffice keeps numbering on
the heading styles. LibreOffice is not Word, so the real test is opening a template in
Word, saving, and converting again.

Two limits on that check. The files have not been opened in Word itself — confirm the
header, foot, heading numbers and TOC field there. And Aptos, Calibri and Consolas are not installed on
the machine that produced the proofs, so LibreOffice substituted metric-compatible
faces: the layout and colour in the PDFs are right, the letterforms are not.
