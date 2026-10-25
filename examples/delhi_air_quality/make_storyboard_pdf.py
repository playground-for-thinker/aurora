"""Copyright (c) Microsoft Corporation. Licensed under the MIT license.

Render STORYBOARD_kor.md (or any similar Markdown file) to a Korean PDF with ReportLab.

    python make_storyboard_pdf.py STORYBOARD_kor.md STORYBOARD_kor.pdf

Supports the Markdown subset used by the storyboard: headings, paragraphs, bullet and numbered
lists, pipe tables, block quotes, fenced code blocks, inline code, bold and links. Uses the Nanum
fonts shipped with Ubuntu (`fonts-nanum`, `fonts-nanum-coding`).
"""

from __future__ import annotations

import html
import re
import sys
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

FONT_DIR = Path("/usr/share/fonts/truetype/nanum")
pdfmetrics.registerFont(TTFont("Nanum", str(FONT_DIR / "NanumBarunGothic.ttf")))
pdfmetrics.registerFont(TTFont("Nanum-Bold", str(FONT_DIR / "NanumBarunGothicBold.ttf")))
pdfmetrics.registerFont(TTFont("NanumMono", str(FONT_DIR / "NanumGothicCoding.ttf")))
pdfmetrics.registerFontFamily("Nanum", normal="Nanum", bold="Nanum-Bold", italic="Nanum", boldItalic="Nanum-Bold")

INK = colors.HexColor("#16212b")
MUTED = colors.HexColor("#5a6875")
ACCENT = colors.HexColor("#0b6e8f")
LINE = colors.HexColor("#d6dee5")
SOFT = colors.HexColor("#eef3f6")

S = {
    "title": ParagraphStyle("title", fontName="Nanum-Bold", fontSize=22, leading=30, textColor=INK, spaceAfter=6),
    "subtitle": ParagraphStyle("subtitle", fontName="Nanum", fontSize=11, leading=16, textColor=MUTED, spaceAfter=14),
    "h1": ParagraphStyle("h1", fontName="Nanum-Bold", fontSize=18, leading=24, textColor=INK, spaceBefore=6, spaceAfter=8),
    "h2": ParagraphStyle("h2", fontName="Nanum-Bold", fontSize=14, leading=20, textColor=ACCENT, spaceBefore=16, spaceAfter=6),
    "h3": ParagraphStyle("h3", fontName="Nanum-Bold", fontSize=11.5, leading=16, textColor=INK, spaceBefore=10, spaceAfter=4),
    "body": ParagraphStyle("body", fontName="Nanum", fontSize=9.8, leading=15.5, textColor=INK, alignment=TA_LEFT, spaceAfter=5),
    "quote": ParagraphStyle("quote", fontName="Nanum", fontSize=9.6, leading=15, textColor=INK, leftIndent=10, borderPadding=(6, 8, 6, 8), backColor=SOFT, spaceAfter=6),
    "cell": ParagraphStyle("cell", fontName="Nanum", fontSize=8.4, leading=12, textColor=INK),
    "cellh": ParagraphStyle("cellh", fontName="Nanum-Bold", fontSize=8.4, leading=12, textColor=MUTED),
    "code": ParagraphStyle("code", fontName="NanumMono", fontSize=7.4, leading=10.2, textColor=INK, backColor=SOFT, borderPadding=(6, 6, 6, 6), spaceAfter=8),
    "li": ParagraphStyle("li", fontName="Nanum", fontSize=9.8, leading=15.5, textColor=INK),
    "small": ParagraphStyle("small", fontName="Nanum", fontSize=8, leading=11, textColor=MUTED),
}


def inline(md: str) -> str:
    """Convert inline Markdown to ReportLab paragraph markup."""
    text = html.escape(md, quote=False)
    text = re.sub(r"`([^`]+)`", r'<font face="NanumMono" size="8.6">\1</font>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: f'<link href="{m.group(2)}" color="#0b6e8f"><u>{m.group(1)}</u></link>', text)
    return text


def table_flowable(rows: list[list[str]], avail_width: float) -> Table:
    ncol = max(len(r) for r in rows)
    rows = [r + [""] * (ncol - len(r)) for r in rows]
    data = [[Paragraph(inline(c), S["cellh"] if i == 0 else S["cell"]) for c in r] for i, r in enumerate(rows)]
    # Column widths proportional to the longest text in each column, bounded.
    lens = [max(len(re.sub(r"[`*\[\]()]", "", r[j])) for r in rows) for j in range(ncol)]
    lens = [min(max(l, 10), 60) for l in lens]
    lens[0] = max(lens[0], 16)
    widths = [avail_width * l / sum(lens) for l in lens]
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), SOFT),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, LINE),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))  # fmt: skip
    return t


def flow_table(avail_width: float) -> Table:
    """The system diagram of section 2 as a four-column flow (monospaced art does not align with
    Korean glyphs)."""
    cols = [
        ("데이터 소스", ["CAMS 전지구 분석 0.4°<br/>PM1/2.5/10, NO2, SO2, O3, CO + 기상 변수", "ERA5 또는 IFS HRES T0 0.25°<br/>26개 표면 변수, 13개 기압면"]),
        ("Aurora 모델", ["<b>Aurora 0.4° Air Pollution</b><br/>12시간 간격 × 4 = 48 h<br/>로컬 GPU 또는 Foundry \"Aurora\" 엔드포인트", "<b>Aurora 1.5</b><br/>6시간 × 8 + 시간별 서브스텝 = 48개 시간별 예측<br/>(경계층 높이, 10 m 풍속, 기온, 이슬점, 강수, 돌풍)"]),
        ("델리 후처리", ["10개 지점 보간 (아난드 비하르, ITO, 드와르카 …)", "CPCB AQI → GRAP 단계 → 정체 진단"]),
        ("시민", ["메시지 생성 ko/en/hi, short/long", "푸시 · SMS · WhatsApp · 앱"]),
    ]  # fmt: skip
    data = [[Paragraph(h, S["cellh"]) for h, _ in cols]]
    for r in range(2):
        data.append([Paragraph(("→ " if c > 0 else "") + cols[c][1][r], S["cell"]) for c in range(4)])
    t = Table(data, colWidths=[avail_width * w for w in (0.26, 0.32, 0.24, 0.18)], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), SOFT), ("LINEBELOW", (0, 0), (-1, 0), 0.6, LINE),
        ("BOX", (1, 1), (1, -1), 0.8, ACCENT), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))  # fmt: skip
    return t


def md_to_story(md: str, avail_width: float) -> list:
    lines = md.splitlines()
    story: list = []
    i = 0
    para: list[str] = []

    def flush_para() -> None:
        nonlocal para
        if para:
            story.append(Paragraph(inline(" ".join(para)), S["body"]))
            para = []

    while i < len(lines):
        ln = lines[i]
        st = ln.strip()
        if st.startswith("```"):
            flush_para()
            j = i + 1
            block = []
            while j < len(lines) and not lines[j].strip().startswith("```"):
                block.append(lines[j])
                j += 1
            if any("[데이터 소스]" in b for b in block):
                story.append(flow_table(avail_width))
            else:
                story.append(Preformatted("\n".join(block), S["code"]))
            i = j + 1
            continue
        if st.startswith("|"):
            flush_para()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in re.split(r"\|(?=(?:[^`]*`[^`]*`)*[^`]*$)", lines[i].strip().strip("|"))]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells if c):
                    rows.append(cells)
                i += 1
            story.append(table_flowable(rows, avail_width))
            story.append(Spacer(1, 6))
            continue
        if st.startswith(">"):
            flush_para()
            q = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                q.append(lines[i].strip()[1:].strip())
                i += 1
            story.append(Paragraph("<br/>".join(inline(x) for x in q if x), S["quote"]))
            continue
        m = re.match(r"^(#{1,3})\s+(.*)", st)
        if m:
            flush_para()
            level = len(m.group(1))
            text = inline(m.group(2))
            if level == 1:
                story.append(Paragraph(text, S["h1"]))
            elif level == 2:
                story.append(KeepTogether([Paragraph(text, S["h2"])]))
            else:
                story.append(Paragraph(text, S["h3"]))
            i += 1
            continue
        if re.match(r"^(\d+\.|[-*])\s+", st):
            flush_para()
            items = []
            ordered = bool(re.match(r"^\d+\.", st))
            while i < len(lines) and re.match(r"^(\d+\.|[-*])\s+", lines[i].strip()):
                text = re.sub(r"^(\d+\.|[-*])\s+", "", lines[i].strip())
                i += 1
                # continuation lines
                while i < len(lines) and lines[i].strip() and not re.match(r"^(\d+\.|[-*]|#|\||>|```)", lines[i].strip()):
                    text += " " + lines[i].strip()
                    i += 1
                items.append(ListItem(Paragraph(inline(text), S["li"]), leftIndent=14))
            story.append(ListFlowable(items, bulletType="1" if ordered else "bullet", start="1" if ordered else None,
                                      bulletFontName="Nanum", bulletFontSize=9, leftIndent=14, spaceAfter=6))  # fmt: skip
            continue
        if st == "---":
            flush_para()
            story.append(Spacer(1, 8))
            i += 1
            continue
        if not st:
            flush_para()
            i += 1
            continue
        para.append(st)
        i += 1
    flush_para()
    return story


def build(md_path: Path, pdf_path: Path, title: str, subtitle: str, links: list[tuple[str, str]]) -> None:
    doc = SimpleDocTemplate(
        str(pdf_path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
        title=title, author="Aurora Delhi air-quality example", subject=subtitle,
    )
    avail = A4[0] - doc.leftMargin - doc.rightMargin
    md = md_path.read_text(encoding="utf-8")
    # Drop the Markdown H1 (the cover carries the title).
    md = re.sub(r"^# .*\n", "", md, count=1)

    cover = [
        Spacer(1, 60 * mm),
        Paragraph(title, S["title"]),
        Paragraph(subtitle, S["subtitle"]),
        Paragraph(f"생성일 {date.today():%Y년 %m월 %d일} · Aurora 1.5 + Aurora Air Pollution · 델리 NCR", S["small"]),
        Spacer(1, 14),
    ]
    for label, url in links:
        cover.append(Paragraph(f'{label}: <link href="{url}" color="#0b6e8f"><u>{url}</u></link>', S["small"]))
    cover.append(PageBreak())

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Nanum", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(doc_.leftMargin, 11 * mm, title)
        canvas.drawRightString(A4[0] - doc_.rightMargin, 11 * mm, f"{doc_.page}")
        canvas.restoreState()

    doc.build(cover + md_to_story(md, avail), onFirstPage=lambda c, d: None, onLaterPages=footer)


if __name__ == "__main__":
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "STORYBOARD_kor.md")
    dst = Path(sys.argv[2] if len(sys.argv) > 2 else src.with_suffix(".pdf"))
    build(
        src, dst,
        title="스토리보드: Aurora 기반 뉴델리 대기질 조기경보",
        subtitle="Aurora 1.5(시간별 확산 기상)와 Aurora Air Pollution(오염 농도)을 결합해 CPCB AQI·GRAP 단계와 시민용 경보 메시지를 만들기까지",
        links=[
            ("스토리 맵 (한국어/English)", "https://claude.ai/artifact/PKH8XS3B3Nb85WaVMbmZSW"),
            ("스토리보드 (한국어/English)", "https://claude.ai/artifact/6GkTNUq54pqXGZBVx7BGSE"),
            ("코드", "https://github.com/playground-for-thinker/aurora/tree/main/examples/delhi_air_quality"),
        ],
    )  # fmt: skip
    print(f"wrote {dst} ({dst.stat().st_size // 1024} KB)")
