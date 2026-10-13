#!/usr/bin/env python3
"""Sets every table in a .docx to Word's "AutoFit Window".

Pandoc writes the table width onto each table itself, so a reference document cannot
control it: direct formatting beats the table style. Run this over the converted file.

    pandoc report.md --reference-doc=templates/foundry-reference.docx -o report.docx
    python3 scripts/autofit_tables.py report.docx

Pandoc produces one of two layouts, neither of which is AutoFit Window:

    markdown table with column widths     width 100%, fixed layout
    markdown table without them           width auto, columns sized to their contents

Both become width 100% with an automatic layout, which is what the Word menu calls
AutoFit Window. Column proportions from the markdown stay as the starting point; Word
adjusts them to the content and to the text column.
"""
import re, shutil, sys, zipfile
from pathlib import Path

TABLE_WIDTH = '<w:tblW w:w="5000" w:type="pct"/>'
AUTOFIT = '<w:tblLayout w:type="autofit"/>'
PARTS = ("word/document.xml", "word/header1.xml", "word/footer1.xml")

def fit_tables(xml):
    """Rewrite the width and layout of every table in one document part."""
    count = 0

    def fix(match):
        nonlocal count
        props = match.group(1)
        if "<w:tblW" in props:
            props = re.sub(r"<w:tblW[^>]*/>", TABLE_WIDTH, props, count=1)
        else:
            props = re.sub(r"(<w:tblStyle[^>]*/>)", r"\1" + TABLE_WIDTH, props, count=1) \
                if "<w:tblStyle" in props else TABLE_WIDTH + props
        if "<w:tblLayout" in props:
            props = re.sub(r"<w:tblLayout[^>]*/>", AUTOFIT, props, count=1)
        else:
            props = props.replace(TABLE_WIDTH, TABLE_WIDTH + AUTOFIT, 1)
        count += 1
        return f"<w:tblPr>{props}</w:tblPr>"

    return re.sub(r"<w:tblPr>(.*?)</w:tblPr>", fix, xml, flags=re.S), count

def process(path):
    src = Path(path)
    if not src.is_file():
        sys.exit(f"no such file: {src}")
    tmp = src.with_suffix(".autofit.tmp")
    total = 0
    with zipfile.ZipFile(src) as zin, \
         zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename in PARTS:
                xml, found = fit_tables(data.decode("utf-8"))
                data = xml.encode("utf-8")
                total += found
            zout.writestr(item, data)
    shutil.move(tmp, src)
    print(f"{src.name}: {total} table{'' if total == 1 else 's'} set to AutoFit Window")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for arg in sys.argv[1:]:
        process(arg)
