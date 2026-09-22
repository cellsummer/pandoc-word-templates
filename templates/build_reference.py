#!/usr/bin/env python3
"""Builds the pandoc reference documents for every approved style.

Each theme starts from pandoc's own default reference document, so the style
inventory always matches the installed pandoc version. The body of each file is a
specimen report; pandoc reads styles, numbering, page setup and the running head and
foot from the file and discards that body.
"""
import shutil, subprocess, sys, tempfile, zipfile
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
CM = 567                                  # twips per centimetre
EMU_PER_CM = 360000
PAGE_W, PAGE_H = 11906, 16838             # A4 portrait, twips

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
M = 'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"'

# Syntax colours. A light code panel and a dark one need different palettes.
DARK_TOKENS = {
    "keyword": ("7FB2FF", True), "type": ("7FD8C0", False), "number": ("FFB86B", False),
    "string": ("9EDE9B", False), "comment": ("7D8794", False), "function": ("E0A3FF", False),
    "plain": ("D6DBE3", False), "alert": ("FF8A6B", True),
}
LIGHT_TOKENS = {
    "keyword": ("0B4A7A", True), "type": ("0F6F6C", False), "number": ("8C2D18", False),
    "string": ("1D6F42", False), "comment": ("8A8F98", False), "function": ("6A3D9A", False),
    "plain": ("24292F", False), "alert": ("B3261E", True),
}

@dataclass
class Head:
    size: int                       # half-points
    color: str
    bold: bool = True
    italic: bool = False
    caps: bool = False
    shade: str = ""                 # paragraph fill, for reversed headings
    top: int = 0                    # top border weight, eighths of a point
    bottom: int = 0
    bottom_color: str = ""
    before: int = 280
    after: int = 80

@dataclass
class Theme:
    key: str
    label: str
    sans: str
    mono: str
    display: str
    accent: str
    accent_dark: str
    soft: str                       # accent tint, for callouts and title blocks
    ink: str
    muted: str
    rule: str
    hair: str
    band: str
    zebra: str
    warn: str                       # second accent, for the caution block
    warn_soft: str
    body_size: int
    body_line: int                  # 240 = single
    body_after: int
    justify: bool
    numbered: bool
    number_hang: bool               # hanging indent under the heading number
    title_kind: str                 # band | rule | open | reverse
    table_kind: str                 # grid | hairline | open | dark
    code_dark: bool
    code_bg: str
    code_fg: str
    meta_mono: bool                 # author, date and the running foot in the mono face
    margin_x: int
    margin_y: int
    title_size: int
    heads: list = field(default_factory=list)

    @property
    def text_w(self):
        return PAGE_W - 2 * self.margin_x

    @property
    def tokens(self):
        return DARK_TOKENS if self.code_dark else LIGHT_TOKENS

# ---------------------------------------------------------------- xml helpers
def font(name, size=None, color=None, bold=False, italic=False,
         caps=False, shade=None, vert=None, track=None):
    p = [f'<w:rFonts w:ascii="{name}" w:hAnsi="{name}" w:cs="{name}"/>']
    if bold:   p.append("<w:b/>")
    if italic: p.append("<w:i/>")
    if caps:   p.append("<w:smallCaps/>")
    if color:  p.append(f'<w:color w:val="{color}"/>')
    if size:   p.append(f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>')
    if shade:  p.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{shade}"/>')
    if vert:   p.append(f'<w:vertAlign w:val="{vert}"/>')
    if track:  p.append(f'<w:spacing w:val="{track}"/>')   # letter spacing
    return "".join(p)

def border(edge, color, sz=4, space=0, style="single"):
    return f'<w:{edge} w:val="{style}" w:sz="{sz}" w:space="{space}" w:color="{color}"/>'

def pad(color, x=8, y=5):
    """Four same-colour borders: Word has no padding, so borders provide it."""
    return (border("top", color, sz=2, space=y) + border("bottom", color, sz=2, space=y) +
            border("left", color, sz=2, space=x) + border("right", color, sz=2, space=x))

def para(before=None, after=None, line=240, ind=None, hanging=None, borders="",
         shade=None, keep_next=False, keep_lines=False, numid=None, ilvl=0,
         contextual=False, tabs="", jc=None):
    p = []
    if keep_next:  p.append("<w:keepNext/>")
    if keep_lines: p.append("<w:keepLines/>")
    if numid is not None:
        p.append(f'<w:numPr><w:ilvl w:val="{ilvl}"/><w:numId w:val="{numid}"/></w:numPr>')
    if shade:   p.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{shade}"/>')
    if borders: p.append(f"<w:pBdr>{borders}</w:pBdr>")
    if tabs:    p.append(f"<w:tabs>{tabs}</w:tabs>")
    sp = []
    if before is not None: sp.append(f'w:before="{before}"')
    if after is not None:  sp.append(f'w:after="{after}"')
    if line:               sp.append(f'w:line="{line}" w:lineRule="auto"')
    if sp: p.append(f'<w:spacing {" ".join(sp)}/>')
    if ind is not None or hanging is not None:
        a = []
        if ind is not None:     a.append(f'w:left="{ind}"')
        if hanging is not None: a.append(f'w:hanging="{hanging}"')
        p.append(f'<w:ind {" ".join(a)}/>')
    if contextual: p.append("<w:contextualSpacing/>")
    if jc: p.append(f'<w:jc w:val="{jc}"/>')
    return "".join(p)

def style(sid, name, kind="paragraph", based="Normal", nxt=None, ppr="", rpr="",
          custom=False, quick=True, link=None):
    a = [f'w:type="{kind}"', f'w:styleId="{sid}"']
    if custom: a.insert(1, 'w:customStyle="1"')
    x = [f'<w:style {" ".join(a)}><w:name w:val="{name}"/>']
    if based:  x.append(f'<w:basedOn w:val="{based}"/>')
    if nxt:    x.append(f'<w:next w:val="{nxt}"/>')
    if link:   x.append(f'<w:link w:val="{link}"/>')
    if quick:  x.append("<w:qFormat/>")
    if ppr:    x.append(f"<w:pPr>{ppr}</w:pPr>")
    if rpr:    x.append(f"<w:rPr>{rpr}</w:rPr>")
    x.append("</w:style>")
    return "".join(x)

# ---------------------------------------------------------------- styles.xml
def title_block(t):
    """Title, Subtitle, Author and Date, as one visual unit per title treatment."""
    meta = t.mono if t.meta_mono else t.sans
    if t.title_kind == "band":
        skin = para(shade=t.band, borders=border("left", t.accent, sz=24, space=8) +
                    border("top", t.band, space=6) + border("bottom", t.band, space=6) +
                    border("right", t.band, space=8))
        title_c, sub_c, meta_c, name_c = t.accent, t.muted, t.muted, t.ink
    elif t.title_kind == "reverse":
        skin = para(shade=t.accent, borders=pad(t.accent, x=10, y=8))
        title_c, sub_c, meta_c, name_c = "FFFFFF", "F2E4E7", "EBD6DA", "FFFFFF"
        meta = t.sans
    elif t.title_kind == "rule":
        skin = ""
        title_c, sub_c, meta_c, name_c = t.accent, t.muted, t.muted, t.ink
    else:                                        # open
        skin = ""
        title_c, sub_c, meta_c, name_c = t.ink, t.muted, t.muted, t.ink

    top_rule = border("top", t.accent, sz=24, space=10) if t.title_kind == "rule" else ""
    s = [style("Title", "Title", nxt="Subtitle", link="TitleChar",
               ppr=skin + para(before=0, after=60, keep_next=True, borders=top_rule),
               rpr=font(t.display, t.title_size, title_c,
                        bold=t.title_kind != "open")),
         style("TitleChar", "Title Char", kind="character", based="DefaultParagraphFont",
               quick=False, rpr=font(t.display, t.title_size, title_c)),
         style("Subtitle", "Subtitle", nxt="Author", link="SubtitleChar",
               ppr=skin + para(before=0, after=160, keep_next=True),
               rpr=font(t.sans, 24, sub_c, italic=t.title_kind == "rule")),
         style("SubtitleChar", "Subtitle Char", kind="character",
               based="DefaultParagraphFont", quick=False, rpr=font(t.sans, 24, sub_c)),
         style("Author", "Author", nxt="Date",
               ppr=skin + para(before=0, after=0, keep_next=True,
                               borders=border("top", t.rule, space=6)
                               if t.title_kind in ("rule", "open") else ""),
               rpr=font(meta, 18, name_c, bold=True)),
         style("Date", "Date", nxt="BodyText",
               ppr=skin + para(before=0, after=280),
               rpr=font(meta, 18, meta_c))]
    return "".join(s)

def heading_styles(t):
    s = []
    for i, h in enumerate(t.heads, start=1):
        bdr = ""
        if h.top:
            bdr += border("top", t.accent, sz=h.top, space=6)
        if h.bottom:
            bdr += border("bottom", h.bottom_color or t.accent, sz=h.bottom, space=3)
        if h.shade:
            bdr += pad(h.shade)
        numbered = t.numbered and i <= 5
        hang = int((0.7 + 0.35 * i) * CM) if (numbered and t.number_hang) else None
        s.append(style(f"Heading{i}", f"heading {i}", nxt="BodyText",
                       link=f"Heading{i}Char",
                       ppr=para(before=h.before, after=h.after, keep_next=True,
                                keep_lines=True, shade=h.shade or None, borders=bdr,
                                numid=42 if numbered else None, ilvl=i - 1,
                                ind=hang, hanging=hang),
                       rpr=font(t.display if i == 1 else t.sans, h.size, h.color,
                                bold=h.bold, italic=h.italic, caps=h.caps)))
        s.append(style(f"Heading{i}Char", f"Heading {i} Char", kind="character",
                       based="DefaultParagraphFont", quick=False,
                       rpr=font(t.sans, h.size, h.color, bold=h.bold, italic=h.italic)))
    last = t.heads[-1]
    for n in (7, 8, 9):
        s.append(style(f"Heading{n}", f"heading {n}", based="Heading6", nxt="BodyText",
                       link=f"Heading{n}Char"))
        s.append(style(f"Heading{n}Char", f"Heading {n} Char", kind="character",
                       based="DefaultParagraphFont", quick=False,
                       rpr=font(t.sans, last.size, last.color, italic=True)))
    return "".join(s)

def table_style(t):
    cell = ('<w:tblCellMar><w:top w:w="60" w:type="dxa"/><w:left w:w="108" w:type="dxa"/>'
            '<w:bottom w:w="60" w:type="dxa"/><w:right w:w="108" w:type="dxa"/>'
            "</w:tblCellMar>")
    if t.table_kind == "grid":
        borders = (border("top", t.accent, sz=12) + border("bottom", t.accent, sz=12) +
                   border("left", t.hair) + border("right", t.hair) +
                   border("insideH", t.hair) + border("insideV", t.hair))
        head = (f'<w:rPr>{font(t.sans, t.body_size - 3, "FFFFFF", bold=True)}</w:rPr>'
                f'<w:tcPr><w:shd w:val="clear" w:color="auto" w:fill="{t.accent}"/>'
                f'<w:tcBorders>{border("bottom", t.accent, sz=12)}</w:tcBorders></w:tcPr>')
        banding = t.zebra
    elif t.table_kind == "hairline":
        borders = (border("top", t.accent, sz=12) + border("bottom", t.accent, sz=12) +
                   border("insideH", t.hair))
        head = (f'<w:rPr>{font(t.sans, t.body_size - 3, t.accent, bold=True)}</w:rPr>'
                f'<w:tcPr><w:tcBorders>{border("bottom", t.accent, sz=8)}'
                "</w:tcBorders></w:tcPr>")
        banding = ""
    elif t.table_kind == "open":
        borders = border("insideH", t.hair)
        head = (f'<w:rPr>{font(t.sans, t.body_size - 3, t.muted, bold=True, track=12)}</w:rPr>'
                f'<w:tcPr><w:tcBorders>{border("bottom", t.accent, sz=16)}'
                "</w:tcBorders></w:tcPr>")
        banding = t.zebra
    else:                                        # dark header band
        borders = border("insideH", t.hair) + border("bottom", t.accent, sz=12)
        head = (f'<w:rPr>{font(t.sans, t.body_size - 3, "FFFFFF", bold=True)}</w:rPr>'
                f'<w:tcPr><w:shd w:val="clear" w:color="auto" w:fill="{t.accent_dark}"/>'
                "</w:tcPr>")
        banding = ""
    band_pr = ('<w:tblStylePr w:type="band1Horz"><w:tcPr>'
               f'<w:shd w:val="clear" w:color="auto" w:fill="{banding}"/>'
               "</w:tcPr></w:tblStylePr>") if banding else ""
    return ('<w:style w:type="table" w:styleId="Table"><w:name w:val="Table"/>'
            '<w:basedOn w:val="TableNormal"/><w:qFormat/>'
            f'<w:pPr>{para(after=0, line=240)}</w:pPr>'
            f'<w:rPr>{font(t.sans, t.body_size - 2, t.ink)}</w:rPr>'
            f"<w:tblPr><w:tblBorders>{borders}</w:tblBorders>{cell}</w:tblPr>"
            f'<w:tblStylePr w:type="firstRow"><w:pPr><w:keepNext/></w:pPr>{head}'
            "</w:tblStylePr>" + band_pr +
            f'<w:tblStylePr w:type="lastRow"><w:rPr>{font(t.sans, t.body_size - 2, t.ink, bold=True)}</w:rPr>'
            f'<w:tcPr><w:shd w:val="clear" w:color="auto" w:fill="{t.soft}"/>'
            f'<w:tcBorders>{border("top", t.accent, sz=12)}</w:tcBorders></w:tcPr>'
            "</w:tblStylePr></w:style>"
            '<w:style w:type="table" w:default="1" w:styleId="TableNormal">'
            f"<w:name w:val=\"Normal Table\"/><w:tblPr>{cell}</w:tblPr></w:style>")

def styles_xml(t):
    s = []
    add = s.append
    jc = "both" if t.justify else None

    add(f'<w:docDefaults><w:rPrDefault><w:rPr>{font(t.sans, t.body_size, t.ink)}'
        '<w:lang w:val="en-GB"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>'
        f'{para(after=t.body_after, line=t.body_line)}</w:pPr></w:pPrDefault></w:docDefaults>')
    add('<w:latentStyles w:defLockedState="0" w:defUIPriority="0" w:defSemiHidden="0"'
        ' w:defUnhideWhenUsed="0" w:defQFormat="0" w:count="276"/>')
    add('<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        '<w:name w:val="Normal"/><w:qFormat/></w:style>')
    add('<w:style w:type="character" w:default="1" w:styleId="DefaultParagraphFont">'
        '<w:name w:val="Default Paragraph Font"/></w:style>')

    add(style("BodyText", "Body Text", nxt="BodyText",
              ppr=para(after=t.body_after, line=t.body_line, jc=jc)))
    add(style("FirstParagraph", "First Paragraph", based="BodyText", nxt="BodyText"))
    add(style("Compact", "Compact", based="BodyText",
              ppr=para(after=40, line=t.body_line, jc=None)))

    add(title_block(t))
    add(style("AbstractTitle", "Abstract Title", nxt="Abstract",
              ppr=para(before=240, after=60, keep_next=True),
              rpr=font(t.sans, t.body_size - 1, t.accent, bold=True, caps=True, track=20)))
    add(style("Abstract", "Abstract", based="BodyText", nxt="BodyText",
              ppr=para(after=160, ind=int(0.5 * CM), line=t.body_line),
              rpr=font(t.sans, t.body_size - 1, t.muted)))

    add(heading_styles(t))

    quote_shade = t.band if t.table_kind in ("grid", "hairline") else None
    add(style("BlockText", "Block Text", based="BodyText", nxt="BodyText",
              ppr=para(before=160, after=160, ind=int(0.4 * CM), shade=quote_shade,
                       line=t.body_line, jc=None,
                       borders=border("left", t.accent, sz=18, space=8)),
              rpr=font(t.sans, t.body_size + 1, t.accent_dark, italic=True)))
    add(style("FootnoteBlockText", "Footnote Block Text", based="BlockText"))
    add(style("DefinitionTerm", "Definition Term", nxt="Definition",
              ppr=para(before=140, after=0, keep_next=True),
              rpr=font(t.sans, t.body_size, t.accent, bold=True)))
    add(style("Definition", "Definition", based="BodyText", nxt="BodyText",
              ppr=para(after=100, ind=int(0.7 * CM), line=t.body_line,
                       borders=border("bottom", t.hair, space=3))))

    add(style("Caption", "Caption", nxt="BodyText", ppr=para(before=60, after=200),
              rpr=font(t.sans, t.body_size - 3, t.muted, bold=True)))
    add(style("TableCaption", "Table Caption", based="Caption", nxt="BodyText",
              ppr=para(before=160, after=60, keep_next=True),
              rpr=font(t.sans, t.body_size - 3, t.accent, bold=True, caps=True, track=16)))
    add(style("ImageCaption", "Image Caption", based="Caption", nxt="BodyText",
              ppr=para(before=60, after=200)))
    add(style("Figure", "Figure", based="BodyText", nxt="ImageCaption",
              ppr=para(before=140, after=60, keep_next=True, jc=None)))
    add(style("CaptionedFigure", "Captioned Figure", based="BodyText", nxt="BodyText",
              ppr=para(before=140, after=200, keep_next=True, jc=None)))

    code_border = pad(t.code_bg) if t.code_dark else \
        border("left", t.accent, sz=18, space=8) + pad(t.code_bg, x=8, y=6)
    add(style("SourceCode", "Source Code", nxt="BodyText", custom=True,
              ppr='<w:wordWrap w:val="off"/>' +
                  para(before=0, after=0, line=240, shade=t.code_bg,
                       borders=code_border, keep_lines=True, contextual=True),
              rpr=font(t.mono, t.body_size - 3, t.code_fg)))
    add(style("VerbatimChar", "Verbatim Char", kind="character",
              based="DefaultParagraphFont", custom=True,
              rpr=font(t.mono, t.body_size - 2, t.ink, shade=t.band)))
    palette = t.tokens
    groups = [
        ("keyword", ["KeywordTok", "ControlFlowTok", "ImportTok"]),
        ("type", ["DataTypeTok"]),
        ("number", ["DecValTok", "BaseNTok", "FloatTok", "ConstantTok", "SpecialCharTok",
                    "AttributeTok", "PreprocessorTok", "WarningTok"]),
        ("string", ["StringTok", "CharTok", "VerbatimStringTok", "SpecialStringTok"]),
        ("comment", ["CommentTok", "CommentVarTok", "DocumentationTok", "AnnotationTok",
                     "InformationTok", "RegionMarkerTok"]),
        ("function", ["FunctionTok", "BuiltInTok", "ExtensionTok"]),
        ("plain", ["NormalTok", "OperatorTok", "VariableTok", "OtherTok"]),
        ("alert", ["AlertTok", "ErrorTok"]),
    ]
    for role, ids in groups:
        color, bold = palette[role]
        italic = role == "comment"
        for sid in ids:
            add(style(sid, sid, kind="character", based="DefaultParagraphFont",
                      quick=False, custom=True,
                      rpr=font(t.mono, t.body_size - 3, color, bold=bold, italic=italic)))

    add(style("FootnoteText", "Footnote Text", nxt="FootnoteText",
              ppr=para(after=40, line=240), rpr=font(t.sans, t.body_size - 4, t.muted)))
    add(style("FootnoteReference", "Footnote Reference", kind="character",
              based="DefaultParagraphFont", quick=False,
              rpr=font(t.sans, t.body_size - 6, t.accent, bold=True, vert="superscript")))
    add(style("Hyperlink", "Hyperlink", kind="character", based="DefaultParagraphFont",
              quick=False, rpr=font(t.sans, None, t.accent) + '<w:u w:val="single"/>'))
    add(style("SectionNumber", "Section Number", kind="character",
              based="DefaultParagraphFont", quick=False, rpr=font(t.sans, None, t.muted)))
    add(style("Bibliography", "Bibliography", based="BodyText",
              ppr=para(after=100, ind=int(0.7 * CM), hanging=int(0.7 * CM))))

    add(style("TOCHeading", "TOC Heading", nxt="BodyText",
              ppr=para(before=240, after=120, keep_next=True,
                       borders=border("bottom", t.accent, sz=8, space=3)),
              rpr=font(t.display, t.body_size + 4, t.accent, bold=True, caps=True, track=24)))
    dot = f'<w:tab w:val="right" w:leader="dot" w:pos="{t.text_w}"/>'
    for n, (ind, col, bold) in enumerate([(0, t.ink, True), (int(0.6 * CM), t.muted, False),
                                          (int(1.2 * CM), t.muted, False)], start=1):
        add(style(f"TOC{n}", f"toc {n}", nxt="BodyText", quick=False,
                  ppr=para(after=40, ind=ind, tabs=dot),
                  rpr=font(t.sans, t.body_size - 1, col, bold=bold)))

    tabs = (f'<w:tab w:val="center" w:pos="{t.text_w // 2}"/>'
            f'<w:tab w:val="right" w:pos="{t.text_w}"/>')
    hf_font = t.mono if t.meta_mono else t.sans
    add(style("Header", "header", nxt="BodyText", quick=False,
              ppr=para(after=0, tabs=tabs, borders=border("bottom", t.accent, sz=12, space=4)),
              rpr=font(hf_font, t.body_size - 5, t.muted, track=14)))
    add(style("Footer", "footer", nxt="BodyText", quick=False,
              ppr=para(after=0, tabs=tabs, borders=border("top", t.accent, sz=12, space=4)),
              rpr=font(hf_font, t.body_size - 5, t.muted, track=14)))

    add(style("Lead", "Lead", based="BodyText", nxt="BodyText", custom=True,
              ppr=para(before=140, after=140, shade=t.warn_soft, jc=None,
                       borders=border("left", t.warn, sz=18, space=8) +
                               pad(t.warn_soft)),
              rpr=font(t.sans, t.body_size, t.ink, bold=True)))
    add(style("Note", "Note", based="BodyText", nxt="BodyText", custom=True,
              ppr=para(before=140, after=140, shade=t.soft, jc=None,
                       borders=border("left", t.accent, sz=18, space=8) + pad(t.soft)),
              rpr=font(t.sans, t.body_size - 1, t.ink)))
    add(style("Caution", "Caution", based="Note", nxt="BodyText", custom=True,
              ppr=para(before=140, after=140, shade=t.warn_soft, jc=None,
                       borders=border("left", t.warn, sz=18, space=8) + pad(t.warn_soft))))
    add(style("SourceNote", "Source Note", based="BodyText", nxt="BodyText", custom=True,
              ppr=para(before=0, after=160, jc=None),
              rpr=font(t.mono if t.meta_mono else t.sans, t.body_size - 4, t.muted)))

    add(table_style(t))
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:styles {W} {R}>'
            + "".join(s) + "</w:styles>")

# ---------------------------------------------------------------- numbering.xml
def heading_numbering(t):
    """Multilevel list bound to Heading 1-5, the way Word's numbered headings work."""
    lv = []
    for i in range(5):
        fmt = ".".join(f"%{n + 1}" for n in range(i + 1))
        hang = int((0.7 + 0.35 * (i + 1)) * CM) if t.number_hang else 0
        suff = "tab" if (t.number_hang and i) else "space"
        ind = (f'<w:pPr><w:ind w:left="{hang}" w:hanging="{hang}"/></w:pPr>'
               if hang else "")
        lv.append(f'<w:lvl w:ilvl="{i}"><w:start w:val="1"/><w:numFmt w:val="decimal"/>'
                  f'<w:pStyle w:val="Heading{i + 1}"/><w:suff w:val="{suff}"/>'
                  f'<w:lvlText w:val="{fmt}"/><w:lvlJc w:val="left"/>{ind}</w:lvl>')
    for i in range(5, 9):
        lv.append(f'<w:lvl w:ilvl="{i}"><w:numFmt w:val="none"/><w:lvlText w:val=""/>'
                  '<w:lvlJc w:val="left"/></w:lvl>')
    return ('<w:abstractNum w:abstractNumId="42"><w:multiLevelType w:val="multilevel"/>'
            + "".join(lv) + '</w:abstractNum><w:num w:numId="42">'
            '<w:abstractNumId w:val="42"/></w:num>')

def list_numbering():
    """Numbering for the specimen lists only. Converted reports use pandoc's own."""
    lv = []
    for i in range(9):
        text = ".".join(f"%{n + 1}" for n in range(min(i + 1, 2))) + "."
        left = 480 + i * 480
        lv.append(f'<w:lvl w:ilvl="{i}"><w:start w:val="1"/><w:numFmt w:val="decimal"/>'
                  f'<w:lvlText w:val="{text}"/><w:lvlJc w:val="left"/>'
                  f'<w:pPr><w:ind w:left="{left}" w:hanging="480"/></w:pPr></w:lvl>')
    dec = ('<w:abstractNum w:abstractNumId="43"><w:multiLevelType w:val="multilevel"/>'
           + "".join(lv) + '</w:abstractNum><w:num w:numId="43">'
           '<w:abstractNumId w:val="43"/></w:num>')
    marks = [("", "Symbol"), ("o", "Courier New"), ("", "Wingdings")]
    lv = []
    for i in range(9):
        glyph, fnt = marks[i % 3]
        left = 480 + i * 480
        lv.append(f'<w:lvl w:ilvl="{i}"><w:numFmt w:val="bullet"/>'
                  f'<w:lvlText w:val="{glyph}"/><w:lvlJc w:val="left"/>'
                  f'<w:pPr><w:ind w:left="{left}" w:hanging="480"/></w:pPr>'
                  f'<w:rPr><w:rFonts w:ascii="{fnt}" w:hAnsi="{fnt}" w:hint="default"/>'
                  "</w:rPr></w:lvl>")
    bullet = ('<w:abstractNum w:abstractNumId="44"><w:multiLevelType w:val="multilevel"/>'
              + "".join(lv) + '</w:abstractNum><w:num w:numId="44">'
              '<w:abstractNumId w:val="44"/></w:num>')
    return dec + bullet

# ---------------------------------------------------------------- header, foot, page
def hdr_ftr_xml(tag, parts):
    runs = []
    for i, (text, field_code) in enumerate(parts):
        if i:
            runs.append("<w:r><w:tab/></w:r>")
        runs.append(f'<w:r><w:t xml:space="preserve">{text}</w:t></w:r>')
        if field_code:
            runs.append('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
                        f'<w:r><w:instrText xml:space="preserve">{field_code}</w:instrText></w:r>'
                        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
                        '<w:r><w:t>1</w:t></w:r>'
                        '<w:r><w:fldChar w:fldCharType="end"/></w:r>')
    sid = "Header" if tag == "hdr" else "Footer"
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:{tag} {W} {R}>'
            f'<w:p><w:pPr><w:pStyle w:val="{sid}"/></w:pPr>{"".join(runs)}</w:p></w:{tag}>')

def sect_pr(t):
    return ('<w:sectPr>'
            '<w:headerReference r:id="rIdHeader" w:type="default"/>'
            '<w:footerReference r:id="rIdFooter" w:type="default"/>'
            '<w:footnotePr><w:numRestart w:val="continuous"/></w:footnotePr>'
            f'<w:pgSz w:w="{PAGE_W}" w:h="{PAGE_H}"/>'
            f'<w:pgMar w:top="{t.margin_y}" w:right="{t.margin_x}" w:bottom="{t.margin_y}" '
            f'w:left="{t.margin_x}" w:header="{int(1.1 * CM)}" w:footer="{int(1.1 * CM)}" '
            'w:gutter="0"/><w:cols w:space="708"/><w:docGrid w:linePitch="360"/></w:sectPr>')

# ---------------------------------------------------------------- specimen body
def esc(x):
    return x.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def run(text, rstyle=None, bold=False):
    rpr = ""
    if rstyle or bold:
        rpr = "<w:rPr>" + (f'<w:rStyle w:val="{rstyle}"/>' if rstyle else "") \
              + ("<w:b/>" if bold else "") + "</w:rPr>"
    return f'<w:r>{rpr}<w:t xml:space="preserve">{esc(text)}</w:t></w:r>'

def p(sid, runs, ppr=""):
    body = runs if isinstance(runs, str) else "".join(runs)
    return f'<w:p><w:pPr><w:pStyle w:val="{sid}"/>{ppr}</w:pPr>{body}</w:p>'

def li(text, numid, ilvl=0):
    return p("Compact", run(text),
             f'<w:numPr><w:ilvl w:val="{ilvl}"/><w:numId w:val="{numid}"/></w:numPr>')

def toc_line(level, text, page):
    return p(f"TOC{level}", run(text) + "<w:r><w:tab/></w:r>" + run(page))

def specimen_table(t):
    weights = [17, 15, 15, 17, 14, 18]          # columns share the text width
    widths = [round(t.text_w * w / sum(weights)) for w in weights]
    widths[-1] += t.text_w - sum(widths)
    rows = [(("Region", "Volume (m)", "Revenue", "Cost per txn", "Change", "Status"), True),
            (("Northern", "412.8", "1,204.5", "0.284", "−8.1%", "Complete"), False),
            (("Eastern", "318.2", "987.1", "0.311", "−5.2%", "In progress"), False),
            (("Southern", "204.6", "612.4", "0.377", "+1.9%", "Under review"), False),
            (("Western", "289.9", "845.0", "0.298", "−6.8%", "Complete"), False),
            (("Group", "1,225.5", "3,649.0", "0.312", "−6.4%", "—"), False)]
    out = []
    for values, head in rows:
        cells = []
        for i, (v, w_) in enumerate(zip(values, widths)):
            jc = '<w:jc w:val="right"/>' if 1 <= i <= 4 else ""
            cells.append(f'<w:tc><w:tcPr><w:tcW w:w="{w_}" w:type="dxa"/></w:tcPr>'
                         f'{p("Compact", run(v), jc)}</w:tc>')
        trpr = '<w:trPr><w:tblHeader w:val="on"/></w:trPr>' if head else ""
        out.append(f"<w:tr>{trpr}{''.join(cells)}</w:tr>")
    grid = "".join(f'<w:gridCol w:w="{w_}"/>' for w_ in widths)
    return ('<w:tbl><w:tblPr><w:tblStyle w:val="Table"/>'
            f'<w:tblW w:w="{sum(widths)}" w:type="dxa"/><w:tblLayout w:type="fixed"/>'
            '<w:tblLook w:firstRow="1" w:lastRow="0" w:firstColumn="0" w:lastColumn="0"'
            ' w:noHBand="0" w:noVBand="1" w:val="0020"/></w:tblPr>'
            f"<w:tblGrid>{grid}</w:tblGrid>" + "".join(out) + "</w:tbl>")

def specimen_code():
    lines = [[("SELECT", "KeywordTok"), (" region,", None)],
             [("       SUM", "FunctionTok"), ("(weighted_cost) / ", None),
              ("NULLIF", "FunctionTok"), ("(", None), ("SUM", "FunctionTok"),
              ("(settled_volume), ", None), ("0", "DecValTok"), (") ", None),
              ("AS", "KeywordTok"), (" cost_per_txn", None)],
             [("  FROM", "KeywordTok"), (" ledger.settlement_fact", None)],
             [(" WHERE", "KeywordTok"), (" period ", None), ("BETWEEN", "KeywordTok"),
              (" ", None), ("'2025-09-01'", "StringTok"), (" ", None),
              ("AND", "KeywordTok"), (" ", None), ("'2026-08-31'", "StringTok")],
             [("   AND", "KeywordTok"), (" amount >= ", None), ("25000", "DecValTok"),
              ("   ", None), ("-- materiality threshold", "CommentTok")],
             [(" GROUP BY", "KeywordTok"), (" region", None)],
             [(" ORDER BY", "KeywordTok"), (" cost_per_txn ", None),
              ("DESC", "KeywordTok"), (";", None)]]
    return "".join(p("SourceCode", [run(txt, st) for txt, st in line]) for line in lines)

def specimen_equation():
    def mr(x):
        return f"<m:r><m:t>{esc(x)}</m:t></m:r>"
    frac = ("<m:f><m:fPr><m:ctrlPr/></m:fPr>"
            f"<m:num>{mr('allocated cost')}</m:num>"
            f"<m:den>{mr('settled volume × (1 − seasonal factor)')}</m:den></m:f>")
    return ('<w:p><w:pPr><w:pStyle w:val="BodyText"/></w:pPr><m:oMathPara><m:oMath>'
            f"{mr('cost per transaction = ')}{frac}</m:oMath></m:oMathPara></w:p>")

def specimen_figure(t):
    """Direct formatting, not a style: an image in a real report must stay unboxed."""
    box = (f'<w:shd w:val="clear" w:color="auto" w:fill="{t.band}"/>'
           f'<w:pBdr>{border("top", t.hair, space=28)}{border("bottom", t.hair, space=28)}'
           f'{border("left", t.hair, space=8)}{border("right", t.hair, space=8)}</w:pBdr>'
           '<w:jc w:val="center"/>')
    txt = ('<w:r><w:rPr>' + font(t.mono, t.body_size - 4, t.muted) + "</w:rPr>"
           '<w:t xml:space="preserve">CHART OR PHOTOGRAPH — an image sits here, '
           'unframed, at the width of the text</w:t></w:r>')
    return f'<w:p><w:pPr><w:pStyle w:val="CaptionedFigure"/>{box}</w:pPr>{txt}</w:p>'

def specimen_document(t):
    b = []
    add = b.append
    add(p("Title", run("Operational Resilience and Capital Efficiency")))
    add(p("Subtitle", run("Consolidated findings for fiscal year 2026 across the four "
                          "operating regions")))
    add(p("Author", run("Strategy & Analytics")))
    add(p("Date", run("21 September 2026")))

    add(p("AbstractTitle", run("Abstract")))
    add(p("Abstract", run("The group completed the year with a stable cost base and an "
                          "improved capital position. Throughput increased in three of the "
                          "four regions, and the cost per transaction decreased by 6.4 per "
                          "cent.")))
    add(p("TOCHeading", run("Table of Contents")))
    add(toc_line(1, "Executive summary", "3"))
    add(toc_line(2, "Method and scope", "5"))
    add(toc_line(3, "Data sources", "6"))
    add(p("SourceNote", run("The entries above are specimen text. A converted report "
                            "carries a live field here; update it in Word with F9.")))

    add(p("Heading1", run("Executive summary")))
    add(p("FirstParagraph", run("The group completed the year with a stable cost base and "
                                "an improved capital position. Throughput increased in three "
                                "of the four regions, while the cost per transaction "
                                "decreased by 6.4 per cent.")))
    add(p("BodyText", run("Two conditions limit the conclusions. First, the reconciliation "
                          "of the Southern region ledger was not complete at the reporting "
                          "date. Second, the new settlement platform was live for only seven "
                          "months, so the annualised figures are estimates.")))
    add(p("Lead", run("Recommendation: approve the second phase of the platform migration "
                      "and release the contingency reserve of 12.4 million.")))

    add(p("Heading2", run("Method and scope")))
    add(p("FirstParagraph", run("The analysis covers all entities consolidated at 31 August "
                                "2026. Transactions below the materiality threshold of "
                                "25,000 were excluded, except where they formed part of a "
                                "recurring series.")))
    add(p("Heading3", run("Data sources")))
    add(p("FirstParagraph", [run("Three systems supplied the primary records. Where the "
                                 "systems disagreed, the general ledger was used as the "
                                 "reference. Manual adjustments are identified with the "
                                 "marker "),
                             run("ADJ-", "VerbatimChar"),
                             run(" followed by the sequence number."),
                             '<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr>'
                             '<w:footnoteReference w:id="31"/></w:r>']))
    add(p("Heading4", run("Reconciliation procedure")))
    add(p("FirstParagraph", run("Each regional controller confirmed the closing balance in "
                                "writing. The confirmation was matched against the automated "
                                "extract before the figures entered this report.")))
    add(p("Heading5", run("Exception handling")))
    add(p("FirstParagraph", run("An exception was raised when the difference was more than "
                                "0.5 per cent of the regional total. Fourteen exceptions "
                                "were raised, and twelve were closed before the reporting "
                                "date.")))
    add(p("Heading6", run("Residual items")))
    add(p("FirstParagraph", run("The two open items relate to a currency translation in the "
                                "Southern region and to an unposted supplier credit.")))

    add(p("Heading2", run("Findings")))
    add(p("FirstParagraph", run("The review produced four findings. They are given in order "
                                "of financial effect.")))
    add(li("Settlement cycles decreased from four days to one day in the regions that use "
           "the new platform.", 44, 0))
    add(li("Northern region: full migration completed in March.", 44, 1))
    add(li("Eastern region: partial migration, two legacy queues remain.", 44, 1))
    add(li("Manual intervention rates stay above target in high-value corridors.", 44, 0))
    add(li("Vendor concentration increased. One supplier now provides 38 per cent of "
           "processing capacity.", 44, 0))
    add(p("BodyText", run("The proposed actions follow the same order.")))
    add(li("Complete the Eastern region migration before the end of the first quarter.", 43, 0))
    add(li("Decommission the legacy queues.", 43, 1))
    add(li("Transfer the reconciliation rules to the new engine.", 43, 1))
    add(li("Introduce a second processing supplier for corridors above 50 million per "
           "month.", 43, 0))
    add(li("Rehearse the ledger recovery procedure each quarter.", 43, 0))

    add(p("DefinitionTerm", run("Cost per transaction")))
    add(p("Definition", run("Total processing cost divided by the number of settled "
                            "transactions in the period.")))
    add(p("DefinitionTerm", run("Recovery time objective")))
    add(p("Definition", run("The maximum time permitted between the loss of a service and "
                            "its return to operation.")))
    add(p("BlockText", run("The control environment is adequate for the current volume. It "
                           "will not be adequate at twice the current volume without further "
                           "automation.")))
    add(p("Note", [run("Note. ", bold=True),
                   run("The figures in this section are unaudited. The audited figures will "
                       "be released with the statutory accounts in November.")]))
    add(p("Caution", [run("Caution. ", bold=True),
                      run("Vendor concentration above 35 per cent breaches the group risk "
                          "appetite statement and needs board acknowledgement.")]))

    add(p("Heading2", run("Regional performance")))
    add(p("FirstParagraph", run("Table 1 gives the principal measures for each region. "
                                "Amounts are in millions of euro unless stated otherwise.")))
    add(p("TableCaption", run("Table 1 — Principal measures by region, fiscal year 2026")))
    add(specimen_table(t))
    add(p("SourceNote", run("Source: consolidated ledger extract, 31 August 2026. Southern "
                            "region figures are provisional.")))
    add(specimen_figure(t))
    add(p("ImageCaption", run("Figure 1 — Cost per transaction by region, euro per "
                              "settled transaction")))

    add(p("Heading2", run("Model definition")))
    add(p("FirstParagraph", run("The cost per transaction is the ratio of allocated cost to "
                                "settled volume, adjusted for the seasonal factor.")))
    add(specimen_equation())

    add(p("Heading2", run("Reproduction of the calculation")))
    add(p("FirstParagraph", [run("The extract is produced with the query below. Run it with "
                                 "the "), run("--reconcile", "VerbatimChar"),
                             run(" flag to include the manual adjustments.")]))
    add(specimen_code())
    add(p("BodyText", [run("The procedure is described in "),
                       run("Method and scope", "Hyperlink"),
                       run(". A verbatim path is written as "),
                       run("/srv/reports/gor-2026/extract.csv", "VerbatimChar"),
                       run(".")]))
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<w:document {W} {R} {M}><w:body>{"".join(b)}{sect_pr(t)}</w:body></w:document>')

SPECIMEN_FOOTNOTES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    f'<w:footnotes {W} {R}>'
    '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
    '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r>'
    '<w:continuationSeparator/></w:r></w:p></w:footnote>'
    '<w:footnote w:id="31"><w:p><w:pPr><w:pStyle w:val="FootnoteText"/></w:pPr>'
    '<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr><w:footnoteRef/></w:r>'
    '<w:r><w:t xml:space="preserve"> The Southern region ledger reconciliation was 94 per '
    'cent complete at the reporting date. The residual difference is 1.2 million.</w:t>'
    "</w:r></w:p></w:footnote></w:footnotes>")

# ---------------------------------------------------------------- build
def build(t, base_docx):
    work = Path(tempfile.mkdtemp())
    src = work / "ref"
    with zipfile.ZipFile(base_docx) as z:
        z.extractall(src)

    (src / "word/styles.xml").write_text(styles_xml(t), encoding="utf-8")

    num = (src / "word/numbering.xml").read_text(encoding="utf-8")
    extra = (heading_numbering(t) if t.numbered else "") + list_numbering()
    (src / "word/numbering.xml").write_text(
        num.replace("</w:numbering>", extra + "</w:numbering>"), encoding="utf-8")

    (src / "word/header1.xml").write_text(
        hdr_ftr_xml("hdr", [("", None), ("", None),
                            ("CONFIDENTIAL — INTERNAL USE ONLY", None)]),
        encoding="utf-8")
    (src / "word/footer1.xml").write_text(
        hdr_ftr_xml("ftr", [("", None), ("CONFIDENTIAL", None), ("PAGE ", "PAGE")]),
        encoding="utf-8")

    rels_path = src / "word/_rels/document.xml.rels"
    ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    rels_path.write_text(rels_path.read_text(encoding="utf-8").replace(
        "</Relationships>",
        f'<Relationship Id="rIdHeader" Type="{ns}/header" Target="header1.xml"/>'
        f'<Relationship Id="rIdFooter" Type="{ns}/footer" Target="footer1.xml"/>'
        "</Relationships>"), encoding="utf-8")

    ct_path = src / "[Content_Types].xml"
    wml = "application/vnd.openxmlformats-officedocument.wordprocessingml"
    ct_path.write_text(ct_path.read_text(encoding="utf-8").replace(
        "</Types>",
        f'<Override PartName="/word/header1.xml" ContentType="{wml}.header+xml"/>'
        f'<Override PartName="/word/footer1.xml" ContentType="{wml}.footer+xml"/>'
        "</Types>"), encoding="utf-8")

    # The body is a specimen of every style. Pandoc reads styles, numbering, page setup
    # and the running head and foot from here, and discards this content.
    (src / "word/document.xml").write_text(specimen_document(t), encoding="utf-8")
    (src / "word/footnotes.xml").write_text(SPECIMEN_FOOTNOTES, encoding="utf-8")

    out = HERE / f"{t.key}-reference.docx"
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(src.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(src).as_posix())
    shutil.rmtree(work)
    return out

def main():
    work = Path(tempfile.mkdtemp())
    base = work / "base.docx"
    with base.open("wb") as fh:
        subprocess.run(["pandoc", "--print-default-data-file", "reference.docx"],
                       check=True, stdout=fh)
    for t in THEMES:
        out = build(t, base)
        print(f"built {out.name:28} {t.label}")
    shutil.rmtree(work)

# ---------------------------------------------------------------- the themes
BURGUNDY = dict(accent="8C1D34", accent_dark="5E1323", soft="F7EDEF",
                warn="8A5A00", warn_soft="FDF6EA")

THEMES = [
    Theme(key="foundry", label="C — dense technical, slate blue and amber",
          sans="Calibri", mono="Consolas", display="Calibri",
          accent="21456E", accent_dark="16304F", soft="EEF1F4",
          warn="A35A00", warn_soft="FDF6EE",
          ink="16191D", muted="565C63", rule="B4BAC1", hair="D9DDE1",
          band="EEF1F4", zebra="F7F9FA",
          body_size=20, body_line=240, body_after=100, justify=False,
          numbered=True, number_hang=True, title_kind="band", table_kind="grid",
          code_dark=True, code_bg="1E2430", code_fg="D6DBE3", meta_mono=True,
          margin_x=int(2.2 * CM), margin_y=int(2.0 * CM), title_size=40,
          heads=[Head(28, "FFFFFF", shade="21456E", before=360, after=140),
                 Head(24, "21456E", bottom=4, bottom_color="D9DDE1"),
                 Head(21, "16191D", before=240, after=60),
                 Head(20, "565C63", before=200, after=50),
                 Head(19, "565C63", italic=True, before=180, after=40),
                 Head(19, "565C63", bold=False, italic=True, before=160, after=40)]),

    Theme(key="chancery", label="A — classic executive, burgundy and Aptos",
          sans="Aptos", mono="Consolas", display="Aptos Display",
          ink="1A1A1A", muted="5A5F66", rule="C8CDD6", hair="DDD9D6",
          band="F7EDEF", zebra="FAF6F7",
          body_size=22, body_line=276, body_after=120, justify=True,
          numbered=True, number_hang=False, title_kind="rule", table_kind="hairline",
          code_dark=False, code_bg="F6F7F9", code_fg="24292F", meta_mono=False,
          margin_x=int(2.5 * CM), margin_y=int(2.3 * CM), title_size=52,
          heads=[Head(36, "8C1D34", bold=False, bottom=12, before=480, after=180),
                 Head(28, "8C1D34", before=380, after=110),
                 Head(24, "1A1A1A", before=300, after=90),
                 Head(22, "1A1A1A", italic=True, before=260, after=70),
                 Head(20, "5A5F66", caps=True, before=240, after=60),
                 Head(21, "5A5F66", bold=False, italic=True, before=220, after=60)],
          **BURGUNDY),

    Theme(key="meridian", label="B — modern and open, burgundy and Aptos",
          sans="Aptos", mono="Consolas", display="Aptos Display",
          ink="202226", muted="6B7280", rule="E2E5E9", hair="E6E2E2",
          band="F7EDEF", zebra="FBFAFA",
          body_size=22, body_line=312, body_after=200, justify=False,
          numbered=False, number_hang=False, title_kind="open", table_kind="open",
          code_dark=False, code_bg="F8F7F7", code_fg="24292F", meta_mono=False,
          margin_x=int(2.8 * CM), margin_y=int(2.5 * CM), title_size=64,
          heads=[Head(44, "202226", bold=False, bottom=24, before=620, after=200),
                 Head(30, "202226", before=440, after=130),
                 Head(24, "5E1323", before=340, after=100),
                 Head(22, "202226", before=280, after=80),
                 Head(19, "6B7280", caps=True, before=260, after=70),
                 Head(21, "6B7280", bold=False, italic=True, before=220, after=60)],
          **BURGUNDY),

    Theme(key="atlas", label="D — bold editorial, burgundy and Aptos",
          sans="Aptos", mono="Consolas", display="Aptos Display",
          ink="1B1B1D", muted="6A6A70", rule="D8D5D2", hair="DFDBD8",
          band="F7EDEF", zebra="FAF6F7",
          body_size=22, body_line=292, body_after=140, justify=False,
          numbered=False, number_hang=False, title_kind="reverse", table_kind="dark",
          code_dark=True, code_bg="2C2C30", code_fg="E8E6E3", meta_mono=False,
          margin_x=int(2.4 * CM), margin_y=int(2.2 * CM), title_size=60,
          heads=[Head(42, "2C2C30", top=24, before=560, after=180),
                 Head(29, "8C1D34", before=420, after=120),
                 Head(23, "2C2C30", before=320, after=90),
                 Head(20, "8C1D34", caps=True, before=280, after=80),
                 Head(20, "6A6A70", before=250, after=70),
                 Head(22, "6A6A70", bold=False, italic=True, before=220, after=60)],
          **BURGUNDY),
]

if __name__ == "__main__":
    sys.exit(main())
