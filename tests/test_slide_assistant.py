import json
from pathlib import Path

import pytest
from pptx import Presentation
from pydantic import ValidationError

from slide_assistant.builder import build_presentation
from slide_assistant.llm import DemoProvider, ProviderError
from slide_assistant.pipeline import generate_deck, load_spec
from slide_assistant.prompts import build_content_prompt, build_outline_prompt, parse_request
from slide_assistant.quality import lint_deck
from slide_assistant.schema import ChartSpec, Deck, deck_json_schema

ROOT = Path(__file__).resolve().parents[1]
SPECS = sorted((ROOT / "samples" / "specs").glob("*.json"))


# --- request parsing --------------------------------------------------------

@pytest.mark.parametrize("prompt,n,topic", [
    ("Make a 5-slide deck on EV trends", 5, "EV trends"),
    ("Create a presentation about remote work, 8 slides", 8, None),
    ("generate a seven slide deck on solar energy", 7, "solar energy"),
    ("Deck on cybersecurity basics", 6, None),
    ("Make a 40-slide deck on AI", 15, None),
])
def test_parse_request(prompt, n, topic):
    req = parse_request(prompt)
    assert req.num_slides == n
    if topic:
        assert req.topic == topic


def test_explicit_slide_count_wins():
    assert parse_request("Make a 5-slide deck on EVs", num_slides=9).num_slides == 9


def test_prompts_contain_request_fields():
    req = parse_request("Make a 5-slide deck on EV trends", audience="investors")
    for p in (build_outline_prompt(req), build_content_prompt(req)):
        assert "<slide_count>5</slide_count>" in p and "investors" in p


# --- schema -----------------------------------------------------------------

def test_chart_shape_validation():
    with pytest.raises(ValidationError):
        ChartSpec(type="column", categories=["a", "b"], series=[{"name": "s", "values": [1]}])
    with pytest.raises(ValidationError):
        ChartSpec(type="pie", categories=["a"], series=[{"name": "x", "values": [1]},
                                                         {"name": "y", "values": [2]}])


def test_chart_layout_requires_chart():
    with pytest.raises(ValidationError):
        Deck(title="t", slides=[{"layout": "chart", "title": "x"}])


def test_json_schema_is_strict():
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(deck_json_schema())


# --- quality lint -----------------------------------------------------------

def test_lint_fixes_common_issues():
    deck = Deck(title="t", slides=[
        {"layout": "bullets", "title": "intro", "bullets": ["a"]},
        {"layout": "bullets", "title": "x", "bullets": [f"b{i}" for i in range(9)]},
        {"layout": "bullets", "title": "y", "bullets": ["z"],
         "chart": {"type": "column", "categories": ["a"], "series": [{"name": "s", "values": [1]}]}},
        {"layout": "closing", "title": "end", "bullets": ["done"]},
    ])
    warnings = lint_deck(deck, expected_slides=4)
    assert deck.slides[0].layout == "title"
    assert len(deck.slides[1].bullets) == 6
    assert deck.slides[2].layout == "bullets_chart"
    assert deck.slides[2].chart.source_note.startswith("Illustrative")
    assert len(warnings) >= 4


# --- pipeline + rendering ---------------------------------------------------

@pytest.mark.parametrize("two_stage", [True, False])
def test_demo_pipeline_end_to_end(tmp_path, two_stage):
    deck, log = generate_deck("Make a 7-slide deck on EV trends", DemoProvider(), two_stage=two_stage)
    assert len(deck.slides) == 7
    assert deck.slides[0].layout == "title" and deck.slides[-1].layout == "closing"
    prs = build_presentation(deck)
    out = tmp_path / "d.pptx"
    prs.save(out)
    prs = Presentation(out)
    assert len(prs.slides) == 7
    assert any(sh.has_chart for s in prs.slides for sh in s.shapes)


def test_no_charts_option():
    deck, _ = generate_deck("Make a 6-slide deck on EV trends", DemoProvider(), include_charts=False)
    assert all(s.chart is None and s.layout not in ("chart", "bullets_chart", "stats") for s in deck.slides)


class _FlakyProvider:
    """Returns an invalid deck first, then a valid one: exercises the repair loop."""
    name, model = "flaky", "test"

    def __init__(self):
        self.calls = 0

    def generate_json(self, system, user, schema, schema_name):
        self.calls += 1
        if self.calls == 1:
            return {"title": "T", "subtitle": "", "slides": [{"layout": "chart", "title": "no chart"}]}
        assert "validation_errors" in user
        return DemoProvider().generate_json(system, user, schema, schema_name)


def test_repair_loop():
    p = _FlakyProvider()
    deck, log = generate_deck("Make a 5-slide deck on EV trends", p, two_stage=False)
    assert log.repairs == 1 and len(deck.slides) == 5


def test_repair_gives_up():
    class Bad:
        name, model = "bad", "test"
        def generate_json(self, *a):
            return {"title": "T", "slides": []}
    with pytest.raises(ProviderError):
        generate_deck("Make a 5-slide deck on X", Bad(), two_stage=False, max_repairs=1)


@pytest.mark.parametrize("spec", SPECS, ids=[p.stem for p in SPECS])
def test_sample_specs_render(spec, tmp_path):
    deck = load_spec(spec)
    for theme in ("midnight", "corporate", "fresh", "sunset"):
        build_presentation(deck, theme).save(tmp_path / f"{theme}.pptx")
    prs = Presentation(tmp_path / "midnight.pptx")
    assert len(prs.slides) == len(deck.slides)
    # speaker notes carried over
    assert prs.slides[0].notes_slide.notes_text_frame.text == deck.slides[0].speaker_notes


# --- Streamlit UI (headless) ------------------------------------------------

def test_streamlit_app_demo_flow():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception
    at.sidebar.selectbox[0].set_value("Demo (offline, no key)").run()
    next(b for b in at.button if "Generate" in b.label).click().run()
    assert not at.exception
    assert at.session_state.deck is not None
    assert len(at.session_state.deck.slides) == 5
