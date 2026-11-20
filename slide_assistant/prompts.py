"""Prompting framework for slide content.

The framework has four layers (see docs/PROMPTING_FRAMEWORK.md for the rationale):

1. Request parsing   - turn a free-form ask ("Make a 5-slide deck on EV trends")
                       into a structured ``DeckRequest`` (topic, slide count, audience...).
2. System prompt     - a stable role + rules block: storytelling, slide-writing
                       rules, the layout catalogue, and data-honesty rules for charts.
3. Stage prompts     - Stage 1 plans an outline (storyline + one layout per slide);
                       Stage 2 writes the full content for that outline.
                       Single-stage mode skips straight to Stage 2.
4. Repair prompt     - if the JSON fails validation, the exact validation errors are
                       sent back so the model can fix only what is wrong.

All output is constrained by a JSON Schema (structured outputs), so the prompts focus
on *content quality* rather than on formatting instructions.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

PROMPT_VERSION = "1.0"

DEFAULT_SLIDES = 6
MIN_SLIDES, MAX_SLIDES = 3, 15

_NUMBER_WORDS = {
    "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}


@dataclass
class DeckRequest:
    prompt: str
    topic: str
    num_slides: int = DEFAULT_SLIDES
    audience: str = "business professionals"
    tone: str = "professional and concise"
    include_charts: bool = True
    extra_instructions: str = ""
    notes: list[str] = field(default_factory=list)


def parse_request(
    prompt: str,
    *,
    num_slides: int | None = None,
    audience: str | None = None,
    tone: str | None = None,
    include_charts: bool = True,
    extra_instructions: str = "",
) -> DeckRequest:
    """Extract slide count and topic from a natural-language request.

    Explicit keyword arguments win over anything detected in the prompt.
    """
    text = prompt.strip()
    if not text:
        raise ValueError("prompt is empty")

    detected = None
    m = re.search(r"(\d{1,2})\s*[- ]?\s*(?:slides?|pages?)\b", text, re.I)
    if m:
        detected = int(m.group(1))
    else:
        m = re.search(r"\b(" + "|".join(_NUMBER_WORDS) + r")\s*[- ]?\s*(?:slides?|pages?)\b", text, re.I)
        if m:
            detected = _NUMBER_WORDS[m.group(1).lower()]

    n = num_slides or detected or DEFAULT_SLIDES
    req_notes = []
    if not (MIN_SLIDES <= n <= MAX_SLIDES):
        clamped = max(MIN_SLIDES, min(MAX_SLIDES, n))
        req_notes.append(f"Slide count {n} clamped to {clamped}.")
        n = clamped

    # Topic: strip the command scaffolding ("make a 5-slide deck on ...").
    topic = re.sub(
        r"^(please\s+)?(make|create|generate|build|prepare|draft|write)\s+(me\s+)?(an?\s+)?"
        r"((\d{1,2}|\w+)\s*[- ]?\s*slides?\s+)?(slide\s+)?(deck|presentation|ppt|slides?|pitch)\s*"
        r"(on|about|for|covering|regarding)?\s*",
        "",
        text,
        flags=re.I,
    ).strip(" .") or text

    return DeckRequest(
        prompt=text,
        topic=topic,
        num_slides=n,
        audience=audience or "business professionals",
        tone=tone or "professional and concise",
        include_charts=include_charts,
        extra_instructions=extra_instructions.strip(),
        notes=req_notes,
    )


# ---------------------------------------------------------------------------
# Layer 2: system prompt
# ---------------------------------------------------------------------------

LAYOUT_CATALOGUE = """\
- title: opening slide. Fill title + subtitle only.
- section: divider between parts of a long deck. Title + short subtitle.
- bullets: the default content slide. 3-5 bullets.
- chart: one full-width chart that carries the message on its own. Title states the insight.
- bullets_chart: 2-4 bullets interpreting a chart shown beside them. Best for "data + so-what".
- two_column: compare/contrast (before vs after, pros vs cons, option A vs B). Fill left_/right_ heading and bullets, 2-4 bullets each.
- stats: 2-4 headline numbers (stats[].value is short, e.g. "17M", "+25%", "$115/kWh"; label explains it). May add up to 2 bullets.
- quote: a single memorable statement in title; attribution or context in subtitle.
- closing: key takeaways / recommendations / next steps. 3-5 bullets."""

SYSTEM_PROMPT = f"""\
You are an expert presentation designer and analyst who writes executive-quality slide decks.
You turn a short request into a clear, well-structured deck that a presenter could use as-is.

<storytelling>
- Build a narrative arc: context -> key insights/evidence -> implications -> takeaways.
- Every slide makes one point. Write slide titles as the point itself ("Battery costs fell 80% in a decade"),
  not as a label ("Battery costs").
- Each slide must add new information; never repeat a bullet from another slide.
</storytelling>

<slide_writing_rules>
- Bullets: 3-5 per slide, ideally 6-14 words each, parallel grammar, no trailing periods.
- Lead with the specific: numbers, names, timeframes beat vague adjectives.
- No markdown, emojis, numbering or bullet characters inside strings - the renderer adds formatting.
- speaker_notes: 2-4 sentences the presenter can say aloud, adding context not on the slide.
- Leave fields that a layout does not use as empty strings, empty arrays, or null (chart).
</slide_writing_rules>

<layouts>
{LAYOUT_CATALOGUE}
</layouts>

<chart_rules>
- Use a chart only when numbers make the point better than words. Match type to message:
  column/line = change over time, bar = ranking/comparison across categories, pie/doughnut = parts of a whole (<= 6 slices, one series).
- categories and every series' values must have the same length; values are plain numbers (no units, no % signs).
- Put units in y_axis_label (e.g. "Million units", "% share", "USD per kWh").
- Data honesty: use figures you are confident are approximately right from reputable public sources and name the
  source plus year in source_note (e.g. "Source: IEA Global EV Outlook 2024 (approx.)"). If you are not confident,
  or the data is hypothetical, write "Illustrative data" in source_note. Never present invented numbers as fact.
</chart_rules>"""


# ---------------------------------------------------------------------------
# Layer 3: stage prompts
# ---------------------------------------------------------------------------

_EXAMPLE_SLIDE = {
    "layout": "bullets_chart",
    "title": "Solar is now the cheapest new power in most markets",
    "subtitle": "",
    "bullets": [
        "Utility-scale solar cost fell roughly 90% between 2010 and 2023",
        "New solar undercuts new coal and gas in most major economies",
        "Cost declines now driven by scale, not technology breakthroughs",
    ],
    "left_heading": "", "left_bullets": [], "right_heading": "", "right_bullets": [],
    "stats": [],
    "chart": {
        "type": "line",
        "title": "Global avg. levelised cost of utility-scale solar",
        "categories": ["2010", "2015", "2020", "2023"],
        "series": [{"name": "Solar PV", "values": [0.46, 0.12, 0.06, 0.04]}],
        "y_axis_label": "USD per kWh",
        "source_note": "Source: IRENA Renewable Power Generation Costs (approx.)",
    },
    "speaker_notes": "Solar's cost curve is the single biggest reason the energy transition accelerated. "
                     "The point for us is that the economics now work without subsidies.",
}


def _request_block(req: DeckRequest) -> str:
    lines = [
        f"<request>{req.prompt}</request>",
        f"<topic>{req.topic}</topic>",
        f"<slide_count>{req.num_slides}</slide_count>",
        f"<audience>{req.audience}</audience>",
        f"<tone>{req.tone}</tone>",
    ]
    if req.include_charts:
        n_charts = max(1, round(req.num_slides / 3))
        lines.append(
            f"<charts>Include about {n_charts} slide(s) with a chart (layouts chart or bullets_chart), "
            "and use a stats slide if headline numbers matter.</charts>"
        )
    else:
        lines.append("<charts>Do not use chart, bullets_chart or stats layouts.</charts>")
    if req.extra_instructions:
        lines.append(f"<extra_instructions>{req.extra_instructions}</extra_instructions>")
    return "\n".join(lines)


def build_outline_prompt(req: DeckRequest) -> str:
    """Stage 1: plan the storyline and pick a layout for each slide."""
    return f"""{_request_block(req)}

Plan the deck before any content is written.
- Exactly {req.num_slides} slides. Slide 1 uses layout "title"; the last slide uses layout "closing".
- Choose the layout for each middle slide from the catalogue so the deck has visual variety
  (avoid more than two "bullets" slides in a row).
- For each slide give the insight-style title and a one-sentence purpose describing what it must prove.
- storyline: 1-2 sentences describing the narrative arc."""


def build_content_prompt(req: DeckRequest, outline_json: str | None = None) -> str:
    """Stage 2: write full slide content (optionally following a Stage 1 outline)."""
    if outline_json:
        plan = (
            "Write the full deck following this approved outline. Keep the slide order, layouts and "
            "the intent of each title (you may sharpen wording).\n"
            f"<outline>\n{outline_json}\n</outline>"
        )
    else:
        plan = (
            f"Write the full deck: exactly {req.num_slides} slides. Slide 1 uses layout \"title\"; "
            "the last slide uses layout \"closing\". Vary layouts across the middle slides."
        )
    example = json.dumps(_EXAMPLE_SLIDE, indent=2)
    return f"""{_request_block(req)}

{plan}

Here is one well-formed content slide, for the expected quality and field usage only (do not reuse its topic):
<example_slide>
{example}
</example_slide>"""


# ---------------------------------------------------------------------------
# Layer 4: repair prompt
# ---------------------------------------------------------------------------

def build_repair_prompt(original_user_prompt: str, bad_json: str, errors: str) -> str:
    return f"""{original_user_prompt}

Your previous answer failed validation. Return the complete corrected deck. Fix only what the errors
describe and keep everything else unchanged.
<previous_answer>
{bad_json}
</previous_answer>
<validation_errors>
{errors}
</validation_errors>"""
