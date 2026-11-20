"""Render a validated ``Deck`` into a .pptx file with python-pptx.

All visuals are drawn in code (shapes, native charts) on a blank 16:9 layout, so the
output looks the same regardless of the default template, and every chart is a real,
editable PowerPoint chart (right-click -> Edit Data works).
"""

from __future__ import annotations

import io
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_MARKER_STYLE
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

from .schema import ChartSpec, Deck, Slide
from .themes import Theme, get_theme

SLIDE_W, SLIDE_H = Inches(13.333), Inches(7.5)
MARGIN = 0.6  # inches

_CHART_TYPES = {
    "bar": XL_CHART_TYPE.BAR_CLUSTERED,
    "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
    "line": XL_CHART_TYPE.LINE_MARKERS,
    "pie": XL_CHART_TYPE.PIE,
    "doughnut": XL_CHART_TYPE.DOUGHNUT,
}


def _rgb(hex_: str) -> RGBColor:
    return RGBColor.from_string(hex_)


# ---------------------------------------------------------------------------
# Primitive helpers
# ---------------------------------------------------------------------------

def _rect(slide, x, y, w, h, color: str, shape=MSO_SHAPE.RECTANGLE, alpha: int | None = None):
    shp = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.fill.solid()
    shp.fill.fore_color.rgb = _rgb(color)
    shp.line.fill.background()
    shp.shadow.inherit = False
    if alpha is not None:  # 0-100 opacity
        clr = shp.fill._xPr.find(qn("a:solidFill")).find(qn("a:srgbClr"))
        etree.SubElement(clr, qn("a:alpha")).set("val", str(alpha * 1000))
    return shp


def _text(slide, x, y, w, h, text: str, *, size: int, color: str, font: str,
          bold: bool = False, italic: bool = False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.05)
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    f = run.font
    f.size, f.bold, f.italic, f.name = Pt(size), bold, italic, font
    f.color.rgb = _rgb(color)
    return box


def _bullet_size(bullets: list[str], base: int = 22, floor: int = 14) -> int:
    chars = sum(len(b) for b in bullets)
    size = base
    if len(bullets) > 4 or chars > 260:
        size -= 2
    if len(bullets) > 5 or chars > 380:
        size -= 2
    if chars > 520:
        size -= 2
    return max(floor, size)


def _bullets(slide, x, y, w, h, bullets: list[str], theme: Theme, *, size: int | None = None,
             color: str | None = None, marker: str | None = None, spacing: int = 12,
             anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    size = size or _bullet_size(bullets)
    for i, text in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(spacing)
        p.line_spacing = 1.1
        run = p.add_run()
        run.text = text
        run.font.size, run.font.name = Pt(size), theme.body_font
        run.font.color.rgb = _rgb(color or theme.text)
        # Real PowerPoint bullets with a hanging indent and an accent-coloured marker.
        pPr = p._p.get_or_add_pPr()
        indent = int(Emu(Inches(0.32)))
        pPr.set("marL", str(indent))
        pPr.set("indent", str(-indent))
        clr = etree.SubElement(pPr, qn("a:buClr"))
        etree.SubElement(clr, qn("a:srgbClr")).set("val", marker or theme.accent)
        etree.SubElement(pPr, qn("a:buSzPct")).set("val", "90000")
        etree.SubElement(pPr, qn("a:buFont")).set("typeface", "Arial")
        etree.SubElement(pPr, qn("a:buChar")).set("char", "■")
    return box


def _background(slide, color: str):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = _rgb(color)


def _title_size(title: str) -> int:
    n = len(title)
    return 32 if n <= 45 else 28 if n <= 70 else 24


def _header(slide, s: Slide, theme: Theme):
    _text(slide, MARGIN, 0.4, 12.1, 0.95, s.title, size=_title_size(s.title), color=theme.title,
          font=theme.heading_font, bold=True, anchor=MSO_ANCHOR.BOTTOM)
    _rect(slide, MARGIN + 0.05, 1.42, 1.1, 0.07, theme.accent)


def _footer(slide, deck: Deck, idx: int, theme: Theme):
    _text(slide, MARGIN, 6.95, 9, 0.35, deck.title, size=10, color=theme.muted, font=theme.body_font)
    _text(slide, 11.7, 6.95, 1.03, 0.35, str(idx), size=10, color=theme.muted,
          font=theme.body_font, align=PP_ALIGN.RIGHT)


def _notes(slide, s: Slide):
    if s.speaker_notes:
        slide.notes_slide.notes_text_frame.text = s.speaker_notes


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def _chart(slide, spec: ChartSpec, x, y, w, h, theme: Theme):
    data = CategoryChartData()
    data.categories = spec.categories
    for s in spec.series:
        data.add_series(s.name, [float(v) for v in s.values])

    gframe = slide.shapes.add_chart(_CHART_TYPES[spec.type], Inches(x), Inches(y), Inches(w),
                                    Inches(h - 0.35), data)
    chart = gframe.chart
    chart.font.size = Pt(12)
    chart.font.name = theme.body_font
    chart.font.color.rgb = _rgb(theme.text)

    if spec.title:
        chart.has_title = True
        tf = chart.chart_title.text_frame
        tf.text = spec.title
        r = tf.paragraphs[0].runs[0]
        r.font.size, r.font.bold = Pt(14), True
        r.font.color.rgb = _rgb(theme.title)
    else:
        chart.has_title = False

    colors = theme.chart_colors
    plot = chart.plots[0]
    is_pie = spec.type in ("pie", "doughnut")
    multi = len(spec.series) > 1

    if is_pie:
        plot.vary_by_categories = True
        for i, point in enumerate(plot.series[0].points):
            point.format.fill.solid()
            point.format.fill.fore_color.rgb = _rgb(colors[i % len(colors)])
            point.format.line.color.rgb = _rgb("FFFFFF")
        plot.has_data_labels = True
        dl = plot.data_labels
        dl.show_percentage, dl.show_value, dl.show_category_name = True, False, False
        dl.number_format, dl.number_format_is_linked = "0%", False
        dl.font.size, dl.font.bold = Pt(12), True
        dl.font.color.rgb = _rgb("FFFFFF")
        if spec.type == "pie":  # doughnut charts reject dLblPos; PowerPoint won't open the file
            dl.position = XL_LABEL_POSITION.CENTER
    else:
        for i, series in enumerate(plot.series):
            c = _rgb(colors[i % len(colors)])
            if spec.type == "line":
                series.format.line.color.rgb = c
                series.format.line.width = Pt(2.75)
                series.smooth = False
                series.marker.style = XL_MARKER_STYLE.CIRCLE
                series.marker.size = 7
                series.marker.format.fill.solid()
                series.marker.format.fill.fore_color.rgb = c
                series.marker.format.line.color.rgb = c
            else:
                series.format.fill.solid()
                series.format.fill.fore_color.rgb = c
        if spec.type in ("bar", "column"):
            plot.gap_width = 70 if not multi else 90
            if multi:
                plot.overlap = -10
        if not multi and len(spec.categories) <= 10:
            plot.has_data_labels = True
            dl = plot.data_labels
            dl.font.size = Pt(11)
            dl.font.color.rgb = _rgb(theme.text)
            all_int = all(float(v).is_integer() for s in spec.series for v in s.values)
            dl.number_format = "#,##0" if all_int else "#,##0.0#"
            dl.number_format_is_linked = False
            dl.position = XL_LABEL_POSITION.ABOVE if spec.type == "line" else XL_LABEL_POSITION.OUTSIDE_END

        va = chart.value_axis
        va.has_major_gridlines = True
        va.major_gridlines.format.line.color.rgb = _rgb("E3E7ED")
        va.format.line.fill.background()
        va.tick_labels.font.size = Pt(11)
        va.tick_labels.font.color.rgb = _rgb(theme.muted)
        if spec.y_axis_label:
            va.has_title = True
            va.axis_title.text_frame.text = spec.y_axis_label
            r = va.axis_title.text_frame.paragraphs[0].runs[0]
            r.font.size, r.font.bold = Pt(11), False
            r.font.color.rgb = _rgb(theme.muted)
        ca = chart.category_axis
        ca.tick_labels.font.size = Pt(11)
        ca.format.line.color.rgb = _rgb("C9D1DC")
        ca.has_major_gridlines = False
        if spec.type == "bar":
            # horizontal bars draw bottom-up by default; flip so the first category is on top
            ca.reverse_order = True
            # keep the value axis at the bottom: it must cross the (reversed) category axis at max
            va._element.find(qn("c:crosses")).set("val", "max")

    chart.has_legend = is_pie or multi
    if chart.has_legend:
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(11)

    if spec.source_note:
        _text(slide, x, y + h - 0.32, w, 0.3, spec.source_note, size=10, color=theme.muted,
              font=theme.body_font, italic=True)
    return chart


# ---------------------------------------------------------------------------
# Layout renderers
# ---------------------------------------------------------------------------

def _hero_decor(slide, theme: Theme):
    _rect(slide, 9.4, -1.6, 5.6, 5.6, theme.accent, MSO_SHAPE.OVAL, alpha=18)
    _rect(slide, 10.9, 3.9, 4.2, 4.2, theme.accent, MSO_SHAPE.OVAL, alpha=10)


def _render_title(slide, s: Slide, deck: Deck, theme: Theme, idx: int):
    _background(slide, theme.hero_bg)
    _hero_decor(slide, theme)
    _rect(slide, 0.75, 2.45, 0.12, 2.2, theme.accent)
    size = 44 if len(s.title) <= 40 else 36 if len(s.title) <= 70 else 30
    _text(slide, 1.1, 2.2, 9.5, 1.6, s.title, size=size, color=theme.hero_text,
          font=theme.heading_font, bold=True, anchor=MSO_ANCHOR.BOTTOM)
    sub = s.subtitle or deck.subtitle
    if sub:
        _text(slide, 1.1, 3.9, 9.5, 0.9, sub, size=20, color=theme.accent, font=theme.body_font)


def _render_section(slide, s: Slide, deck: Deck, theme: Theme, idx: int):
    _background(slide, theme.hero_bg)
    _hero_decor(slide, theme)
    _text(slide, 1.1, 2.0, 3, 0.8, f"{idx:02d}", size=28, color=theme.accent,
          font=theme.heading_font, bold=True)
    _text(slide, 1.1, 2.8, 10, 1.3, s.title, size=40, color=theme.hero_text,
          font=theme.heading_font, bold=True)
    if s.subtitle:
        _text(slide, 1.1, 4.1, 10, 0.8, s.subtitle, size=20, color=theme.accent, font=theme.body_font)


def _render_bullets(slide, s: Slide, deck: Deck, theme: Theme, idx: int):
    _background(slide, theme.background)
    _header(slide, s, theme)
    _rect(slide, MARGIN, 1.8, 12.1, 4.9, theme.card)
    _rect(slide, MARGIN, 1.8, 0.08, 4.9, theme.accent)
    top = 2.15
    if s.subtitle:
        _text(slide, MARGIN + 0.45, 1.95, 11.3, 0.5, s.subtitle, size=16, color=theme.muted,
              font=theme.body_font, italic=True)
        top = 2.55
    _bullets(slide, MARGIN + 0.45, top, 11.2, 6.5 - top, s.bullets, theme,
             size=_bullet_size(s.bullets, base=26), spacing=18, anchor=MSO_ANCHOR.MIDDLE)


def _render_chart(slide, s: Slide, deck: Deck, theme: Theme, idx: int):
    _background(slide, theme.background)
    _header(slide, s, theme)
    _chart(slide, s.chart, MARGIN, 1.75, 12.1, 5.05, theme)


def _render_bullets_chart(slide, s: Slide, deck: Deck, theme: Theme, idx: int):
    _background(slide, theme.background)
    _header(slide, s, theme)
    _rect(slide, MARGIN, 1.8, 4.85, 4.9, theme.card)
    _bullets(slide, MARGIN + 0.3, 2.0, 4.3, 4.5, s.bullets, theme,
             size=_bullet_size(s.bullets, base=20, floor=13), spacing=14, anchor=MSO_ANCHOR.MIDDLE)
    _chart(slide, s.chart, 5.75, 1.75, 6.95, 5.05, theme)


def _render_two_column(slide, s: Slide, deck: Deck, theme: Theme, idx: int):
    _background(slide, theme.background)
    _header(slide, s, theme)
    cols = [(s.left_heading, s.left_bullets, theme.accent, MARGIN),
            (s.right_heading, s.right_bullets, theme.title, MARGIN + 6.2)]
    size = _bullet_size(s.left_bullets + s.right_bullets, base=22, floor=14)
    for heading, bullets, color, x in cols:
        _rect(slide, x, 1.8, 5.9, 4.9, theme.card)
        _rect(slide, x, 1.8, 5.9, 0.08, color)
        hsize = 22 if len(heading) <= 30 else 18
        _text(slide, x + 0.35, 2.05, 5.2, 0.75, heading, size=hsize, color=color,
              font=theme.heading_font, bold=True)
        _bullets(slide, x + 0.35, 2.95, 5.2, 3.6, bullets, theme, size=size, marker=color, spacing=16)


def _render_stats(slide, s: Slide, deck: Deck, theme: Theme, idx: int):
    _background(slide, theme.background)
    _header(slide, s, theme)
    stats = s.stats[:4]
    n = len(stats)
    gap = 0.3
    w = (12.1 - gap * (n - 1)) / n
    card_h = 2.6 if s.bullets else 3.6
    for i, st in enumerate(stats):
        x = MARGIN + i * (w + gap)
        _rect(slide, x, 1.85, w, card_h, theme.card)
        _rect(slide, x, 1.85 + card_h - 0.08, w, 0.08, theme.chart_colors[i % len(theme.chart_colors)])
        # fit the number on one line: ~0.62em average glyph width for bold digits
        vsize = int(min(54, (w - 0.5) * 72 / (max(len(st.value), 1) * 0.62)))
        _text(slide, x + 0.2, 2.05, w - 0.4, 1.3, st.value, size=vsize, color=theme.accent,
              font=theme.heading_font, bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        _text(slide, x + 0.25, 3.35, w - 0.5, card_h - 1.6, st.label, size=16, color=theme.text,
              font=theme.body_font, align=PP_ALIGN.CENTER)
    if s.bullets:
        _bullets(slide, MARGIN + 0.1, 4.8, 12, 1.9, s.bullets[:3], theme, size=18)


def _render_quote(slide, s: Slide, deck: Deck, theme: Theme, idx: int):
    _background(slide, theme.card)
    _rect(slide, 0, 0, 0.25, 7.5, theme.accent)
    _text(slide, 1.0, 0.9, 2, 1.8, "“", size=160, color=theme.accent,
          font="Georgia", bold=True)
    size = 34 if len(s.title) <= 90 else 28 if len(s.title) <= 160 else 24
    _text(slide, 1.6, 2.3, 10.4, 2.9, s.title, size=size, color=theme.title,
          font=theme.heading_font, italic=True, anchor=MSO_ANCHOR.MIDDLE)
    if s.subtitle:
        _text(slide, 1.6, 5.3, 10.4, 0.6, f"— {s.subtitle}", size=18, color=theme.muted,
              font=theme.body_font)


def _render_closing(slide, s: Slide, deck: Deck, theme: Theme, idx: int):
    _background(slide, theme.hero_bg)
    _hero_decor(slide, theme)
    _text(slide, 1.1, 0.75, 10.5, 1.0, s.title, size=36, color=theme.hero_text,
          font=theme.heading_font, bold=True, anchor=MSO_ANCHOR.BOTTOM)
    _rect(slide, 1.15, 1.85, 1.1, 0.07, theme.accent)
    if s.bullets:
        _bullets(slide, 1.1, 2.25, 10.0, 4.4, s.bullets, theme, color=theme.hero_text,
                 size=_bullet_size(s.bullets, base=24), spacing=16)
    elif s.subtitle:
        _text(slide, 1.1, 2.3, 10, 1, s.subtitle, size=22, color=theme.accent, font=theme.body_font)


_RENDERERS = {
    "title": _render_title,
    "section": _render_section,
    "bullets": _render_bullets,
    "chart": _render_chart,
    "bullets_chart": _render_bullets_chart,
    "two_column": _render_two_column,
    "stats": _render_stats,
    "quote": _render_quote,
    "closing": _render_closing,
}
_NO_FOOTER = {"title", "section", "closing", "quote"}


def build_presentation(deck: Deck, theme_name: str | None = None) -> Presentation:
    theme = get_theme(theme_name)
    prs = Presentation()
    prs.slide_width, prs.slide_height = SLIDE_W, SLIDE_H
    blank = prs.slide_layouts[6]
    prs.core_properties.title = deck.title
    prs.core_properties.subject = deck.subtitle
    prs.core_properties.author = "Generative Slide Assistant"

    for idx, s in enumerate(deck.slides, start=1):
        slide = prs.slides.add_slide(blank)
        _RENDERERS[s.layout](slide, s, deck, theme, idx)
        if s.layout not in _NO_FOOTER:
            _footer(slide, deck, idx, theme)
        _notes(slide, s)
    return prs


def save_presentation(deck: Deck, path: str | Path, theme_name: str | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    build_presentation(deck, theme_name).save(path)
    return path


def presentation_bytes(deck: Deck, theme_name: str | None = None) -> bytes:
    buf = io.BytesIO()
    build_presentation(deck, theme_name).save(buf)
    return buf.getvalue()
