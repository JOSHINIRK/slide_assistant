"""Streamlit UI for the Generative Slide Assistant.

Run:  streamlit run app.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from pydantic import ValidationError

from slide_assistant.builder import presentation_bytes
from slide_assistant.llm import ProviderError, get_provider
from slide_assistant.pipeline import generate_deck
from slide_assistant.prompts import parse_request
from slide_assistant.schema import ChartSpec, Deck

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

st.set_page_config(page_title="Generative Slide Assistant", page_icon="📊", layout="wide")

EXAMPLES = [
    "Make a 5-slide deck on EV trends",
    "Create a 7-slide pitch deck for a meal-kit startup targeting busy professionals",
    "Prepare a 6-slide training deck on phishing awareness for new employees",
    "Build an 8-slide deck on the impact of generative AI on the IT services industry",
]

# ---------------------------------------------------------------------------
# Sidebar: settings
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Settings")
    provider_label = st.selectbox(
        "LLM provider",
        ["Claude (Anthropic)", "GPT (OpenAI)", "Demo (offline, no key)"],
        help="Demo mode uses template content so you can try the app without an API key.",
    )
    provider_name = {"Claude (Anthropic)": "claude", "GPT (OpenAI)": "openai"}.get(provider_label, "demo")
    api_key = None
    if provider_name != "demo":
        env_var = "ANTHROPIC_API_KEY" if provider_name == "claude" else "OPENAI_API_KEY"
        api_key = st.text_input(f"API key (optional if {env_var} is set)", type="password")

# Fixed generation settings (the sidebar only asks for provider + key).
# The slide count is read from the prompt, e.g. "Make a 5-slide deck ..." (default 6).
model = None                      # provider default: claude-opus-5-5 / gpt-4o
theme = "midnight"
audience = "business professionals"
tone = "professional and concise"
include_charts = True
two_stage = True                  # plan an outline first, then write the content
override_count, slide_count = False, None
extra = ""

# ---------------------------------------------------------------------------
# Main: prompt
# ---------------------------------------------------------------------------
st.title("📊 Generative Slide Assistant")
st.caption("Describe a deck in plain English → the LLM writes structured slide content → "
           "python-pptx renders a PowerPoint with headings, bullets and native charts.")

if "prompt" not in st.session_state:
    st.session_state.prompt = EXAMPLES[0]

cols = st.columns(len(EXAMPLES))
for c, ex in zip(cols, EXAMPLES):
    if c.button(ex, use_container_width=True):
        st.session_state.prompt = ex

prompt = st.text_area("What deck do you need?", key="prompt", height=90)
if prompt.strip():
    req = parse_request(prompt, num_slides=slide_count if override_count else None)
    st.caption(f"Detected → topic: **{req.topic}** · slides: **{req.num_slides}**")

c1, c2 = st.columns([1, 1])
generate = c1.button("✨ Generate deck", type="primary", use_container_width=True)
sample_files = sorted((ROOT / "samples" / "specs").glob("*.json"))
sample = c2.selectbox("…or load a sample deck", ["—"] + [p.stem for p in sample_files])

if generate and prompt.strip():
    try:
        provider = get_provider(provider_name, model, api_key)
        with st.spinner(f"Generating with {provider.name} ({provider.model})…"):
            deck, log = generate_deck(
                prompt, provider,
                num_slides=slide_count if override_count else None,
                audience=audience, tone=tone, include_charts=include_charts,
                extra_instructions=extra, two_stage=two_stage,
            )
        st.session_state.deck = deck
        st.session_state.log = log
    except ProviderError as e:
        st.error(str(e))
    except Exception as e:  # unexpected - show it rather than a blank page
        st.exception(e)
elif sample != "—" and st.session_state.get("loaded_sample") != sample:
    path = ROOT / "samples" / "specs" / f"{sample}.json"
    st.session_state.deck = Deck.model_validate_json(path.read_text(encoding="utf-8"))
    st.session_state.log = None
    st.session_state.loaded_sample = sample

deck: Deck | None = st.session_state.get("deck")
if deck is None:
    st.info("Enter a prompt and click **Generate deck**, or load a sample.")
    st.stop()

# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
log = st.session_state.get("log")
if log:
    m = st.columns(4)
    m[0].metric("Slides", len(deck.slides))
    m[1].metric("Time", f"{log.seconds}s")
    m[2].metric("Repairs", log.repairs)
    m[3].metric("Model", log.model)
    for w in log.warnings:
        st.warning(w, icon="⚠️")

slug = re.sub(r"[^a-z0-9]+", "_", deck.title.lower()).strip("_")[:50] or "deck"
d1, d2 = st.columns(2)
d1.download_button(
    "⬇️ Download PowerPoint (.pptx)", data=presentation_bytes(deck, theme), file_name=f"{slug}.pptx",
    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    type="primary", use_container_width=True,
)
d2.download_button("⬇️ Download deck spec (.json)", data=deck.model_dump_json(indent=2),
                   file_name=f"{slug}.json", mime="application/json", use_container_width=True)


def chart_preview(spec: ChartSpec):
    rows = [{"category": c, "series": s.name, "value": v, "order": i}
            for s in spec.series for i, (c, v) in enumerate(zip(spec.categories, s.values))]
    df = pd.DataFrame(rows)
    sort = alt.SortField("order")
    if spec.type in ("pie", "doughnut"):
        return alt.Chart(df).mark_arc(innerRadius=60 if spec.type == "doughnut" else 0).encode(
            theta="value:Q", color=alt.Color("category:N", sort=spec.categories), tooltip=["category", "value"])
    if spec.type == "line":
        return alt.Chart(df).mark_line(point=True).encode(
            x=alt.X("category:N", sort=sort, title=None), y=alt.Y("value:Q", title=spec.y_axis_label),
            color="series:N", tooltip=["series", "category", "value"])
    if spec.type == "bar":
        return alt.Chart(df).mark_bar().encode(
            y=alt.Y("category:N", sort=sort, title=None), x=alt.X("value:Q", title=spec.y_axis_label),
            color="series:N", yOffset="series:N", tooltip=["series", "category", "value"])
    return alt.Chart(df).mark_bar().encode(
        x=alt.X("category:N", sort=sort, title=None), y=alt.Y("value:Q", title=spec.y_axis_label),
        color="series:N", xOffset="series:N", tooltip=["series", "category", "value"])


tab_preview, tab_edit, tab_debug = st.tabs(["Preview", "Edit JSON", "Generation details"])

with tab_preview:
    st.subheader(deck.title)
    if deck.subtitle:
        st.caption(deck.subtitle)
    for i, s in enumerate(deck.slides, start=1):
        with st.container(border=True):
            st.markdown(f"**{i}. {s.title}**  ·  `{s.layout}`")
            if s.subtitle:
                st.caption(s.subtitle)
            if s.stats:
                for col, stat in zip(st.columns(len(s.stats)), s.stats):
                    col.metric(stat.label, stat.value)
            if s.layout == "two_column":
                a, b = st.columns(2)
                a.markdown(f"**{s.left_heading}**\n" + "\n".join(f"- {x}" for x in s.left_bullets))
                b.markdown(f"**{s.right_heading}**\n" + "\n".join(f"- {x}" for x in s.right_bullets))
            if s.chart:
                left, right = st.columns([2, 3]) if s.bullets else (None, st.container())
                if left is not None:
                    left.markdown("\n".join(f"- {b}" for b in s.bullets))
                right.altair_chart(chart_preview(s.chart).properties(title=s.chart.title, height=260),
                                   use_container_width=True)
                right.caption(s.chart.source_note)
            elif s.bullets:
                st.markdown("\n".join(f"- {b}" for b in s.bullets))
            if s.speaker_notes:
                with st.expander("Speaker notes"):
                    st.write(s.speaker_notes)

with tab_edit:
    st.caption("Tweak any text or numbers, then apply - the .pptx download updates immediately.")
    edited = st.text_area("Deck spec", value=deck.model_dump_json(indent=2), height=500)
    if st.button("Apply edits"):
        try:
            st.session_state.deck = Deck.model_validate(json.loads(edited))
            st.success("Deck updated.")
            st.rerun()
        except (json.JSONDecodeError, ValidationError) as e:
            st.error(f"Invalid deck spec:\n\n{e}")

with tab_debug:
    if log:
        st.json({"provider": log.provider, "model": log.model, "prompt_version": log.prompt_version,
                 "request": log.request, "repairs": log.repairs, "seconds": log.seconds})
        if log.outline:
            st.markdown("**Stage 1 outline**")
            st.json(log.outline)
    else:
        st.write("Loaded from a saved spec - no generation details.")
