"""Deck data model.

The LLM never writes PowerPoint directly. It fills in this structured spec, which is
validated with Pydantic and then rendered deterministically by ``builder.py``.
Keeping content (LLM) and layout (code) separate is what makes the output reliable.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

Layout = Literal[
    "title",          # opening slide: deck title + subtitle
    "section",        # section divider
    "bullets",        # heading + 3-6 bullets
    "chart",          # heading + full-width native chart
    "bullets_chart",  # heading + bullets on the left, chart on the right
    "two_column",     # heading + two titled bullet columns (compare / contrast)
    "stats",          # heading + 2-4 big-number callouts (+ optional bullets)
    "quote",          # a single highlighted statement
    "closing",        # key takeaways / next steps
]

ChartType = Literal["bar", "column", "line", "pie", "doughnut"]

LAYOUTS: tuple[str, ...] = Layout.__args__  # type: ignore[attr-defined]
CHART_TYPES: tuple[str, ...] = ChartType.__args__  # type: ignore[attr-defined]


class Series(BaseModel):
    name: str
    values: list[float]


class ChartSpec(BaseModel):
    type: ChartType
    title: str = ""
    categories: list[str]
    series: list[Series]
    y_axis_label: str = ""
    source_note: str = ""

    @model_validator(mode="after")
    def _check_shape(self) -> "ChartSpec":
        if not self.categories:
            raise ValueError("chart needs at least one category")
        if not self.series:
            raise ValueError("chart needs at least one series")
        n = len(self.categories)
        for s in self.series:
            if len(s.values) != n:
                raise ValueError(
                    f"series '{s.name}' has {len(s.values)} values but there are {n} categories"
                )
        if self.type in ("pie", "doughnut"):
            if len(self.series) != 1:
                raise ValueError(f"{self.type} charts take exactly one series")
            if any(v < 0 for v in self.series[0].values):
                raise ValueError(f"{self.type} chart values must be non-negative")
        return self


class Stat(BaseModel):
    value: str  # e.g. "17M", "+35%", "$115/kWh"
    label: str


class Slide(BaseModel):
    layout: Layout
    title: str
    subtitle: str = ""
    bullets: list[str] = Field(default_factory=list)
    left_heading: str = ""
    left_bullets: list[str] = Field(default_factory=list)
    right_heading: str = ""
    right_bullets: list[str] = Field(default_factory=list)
    stats: list[Stat] = Field(default_factory=list)
    chart: Optional[ChartSpec] = None
    speaker_notes: str = ""

    @field_validator("bullets", "left_bullets", "right_bullets")
    @classmethod
    def _strip(cls, v: list[str]) -> list[str]:
        return [b.strip().lstrip("-•* ").strip() for b in v if b and b.strip()]

    @model_validator(mode="after")
    def _check_layout(self) -> "Slide":
        if self.layout in ("chart", "bullets_chart") and self.chart is None:
            raise ValueError(f"layout '{self.layout}' requires a chart")
        if self.layout == "stats" and not self.stats:
            raise ValueError("layout 'stats' requires at least one stat")
        if self.layout == "two_column" and not (self.left_bullets or self.right_bullets):
            raise ValueError("layout 'two_column' requires left_bullets/right_bullets")
        return self


class Deck(BaseModel):
    title: str
    subtitle: str = ""
    slides: list[Slide]

    @field_validator("slides")
    @classmethod
    def _non_empty(cls, v: list[Slide]) -> list[Slide]:
        if not v:
            raise ValueError("deck has no slides")
        return v


class OutlineItem(BaseModel):
    title: str
    layout: Layout
    purpose: str


class Outline(BaseModel):
    title: str
    subtitle: str = ""
    storyline: str = ""
    slides: list[OutlineItem]


# ---------------------------------------------------------------------------
# JSON Schemas handed to the LLM APIs (structured outputs).
# Strict mode on both OpenAI and Anthropic wants every property listed in
# ``required`` and ``additionalProperties: false``; "optional" fields are
# therefore expressed as empty strings / empty arrays / null.
# ---------------------------------------------------------------------------

def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": props,
        "required": required if required is not None else list(props),
        "additionalProperties": False,
    }


_STR = {"type": "string"}
_STR_LIST = {"type": "array", "items": _STR}


def chart_json_schema() -> dict:
    return _obj({
        "type": {"type": "string", "enum": list(CHART_TYPES)},
        "title": _STR,
        "categories": _STR_LIST,
        "series": {
            "type": "array",
            "items": _obj({"name": _STR, "values": {"type": "array", "items": {"type": "number"}}}),
        },
        "y_axis_label": _STR,
        "source_note": _STR,
    })


def deck_json_schema() -> dict:
    slide = _obj({
        "layout": {"type": "string", "enum": list(LAYOUTS)},
        "title": _STR,
        "subtitle": _STR,
        "bullets": _STR_LIST,
        "left_heading": _STR,
        "left_bullets": _STR_LIST,
        "right_heading": _STR,
        "right_bullets": _STR_LIST,
        "stats": {"type": "array", "items": _obj({"value": _STR, "label": _STR})},
        "chart": {"anyOf": [chart_json_schema(), {"type": "null"}]},
        "speaker_notes": _STR,
    })
    return _obj({"title": _STR, "subtitle": _STR, "slides": {"type": "array", "items": slide}})


def outline_json_schema() -> dict:
    item = _obj({
        "title": _STR,
        "layout": {"type": "string", "enum": list(LAYOUTS)},
        "purpose": _STR,
    })
    return _obj({
        "title": _STR,
        "subtitle": _STR,
        "storyline": _STR,
        "slides": {"type": "array", "items": item},
    })
