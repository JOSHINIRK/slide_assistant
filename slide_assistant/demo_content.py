"""Template content for the offline ``demo`` provider (no LLM involved)."""

from __future__ import annotations

import re


def parse_demo_request(user_prompt: str) -> tuple[str, int, bool]:
    def tag(name: str, default: str) -> str:
        m = re.search(rf"<{name}>(.*?)</{name}>", user_prompt, re.S)
        return m.group(1).strip() if m else default

    topic = tag("topic", "Your Topic")
    n = int(tag("slide_count", "6"))
    charts = "Do not use chart" not in tag("charts", "")
    return topic, n, charts


def _t(topic: str) -> str:
    return topic[:1].upper() + topic[1:]


def _middle_slides(topic: str, charts: bool) -> list[dict]:
    T = _t(topic)
    empty = {"subtitle": "", "bullets": [], "left_heading": "", "left_bullets": [],
             "right_heading": "", "right_bullets": [], "stats": [], "chart": None}

    def slide(**kw) -> dict:
        d = dict(empty)
        d.update(kw)
        d.setdefault("speaker_notes", "")
        return d

    pool = [
        slide(layout="bullets", title=f"Why {topic} matters now",
              bullets=[f"{T} is moving from early adoption to mainstream",
                       "Costs are falling while capabilities keep improving",
                       "Regulation and customer expectations are accelerating change",
                       "Early movers are already capturing measurable value"],
              speaker_notes=f"Set the context: why should this audience care about {topic} today?"),
    ]
    if charts:
        pool += [
            slide(layout="bullets_chart", title="Adoption is compounding year over year",
                  bullets=["Growth rate has stayed above 20% for four years",
                           "Momentum is strongest in early-adopter segments",
                           "Forecasts point to continued expansion"],
                  chart={"type": "column", "title": f"{T}: adoption index",
                         "categories": ["2021", "2022", "2023", "2024", "2025"],
                         "series": [{"name": "Adoption index", "values": [100, 128, 161, 204, 251]}],
                         "y_axis_label": "Index (2021 = 100)", "source_note": "Illustrative data"},
                  speaker_notes="Walk through the trend line and highlight the inflection point."),
            slide(layout="stats", title="The numbers at a glance",
                  stats=[{"value": "2.5x", "label": "growth since 2021"},
                         {"value": "+26%", "label": "average annual growth"},
                         {"value": "3 of 5", "label": "leaders investing this year"}],
                  bullets=["Figures are illustrative - replace with sourced data"],
                  speaker_notes="Pause on each number; these are the headline facts to remember."),
            slide(layout="chart", title="Three segments account for most of the market",
                  chart={"type": "pie", "title": "Share by segment",
                         "categories": ["Segment A", "Segment B", "Segment C", "Other"],
                         "series": [{"name": "Share", "values": [42, 27, 19, 12]}],
                         "y_axis_label": "% share", "source_note": "Illustrative data"},
                  speaker_notes="Concentration means focus: the top segments are where to start."),
        ]
    pool += [
        slide(layout="two_column", title="Opportunities outweigh the risks",
              left_heading="Opportunities",
              left_bullets=["New revenue streams and business models",
                            "Lower operating costs at scale", "Stronger customer loyalty"],
              right_heading="Risks",
              right_bullets=["Upfront investment and skills gaps",
                             "Evolving regulation", "Execution and integration complexity"],
              speaker_notes="Be balanced: acknowledge the risks and show how they can be managed."),
        slide(layout="bullets", title="What leading organisations are doing",
              bullets=["Starting with focused, high-value pilots",
                       "Building internal capability alongside partners",
                       "Measuring outcomes and scaling what works",
                       "Embedding governance from day one"],
              speaker_notes="Share examples of what good looks like."),
        slide(layout="quote", title=f"The question is no longer whether to act on {topic}, but how fast.",
              subtitle="Key message for decision makers",
              speaker_notes="Let this land before moving to the takeaways."),
        slide(layout="section", title="Implementation roadmap", subtitle="From pilot to scale",
              speaker_notes="Transition to the practical part of the deck."),
    ]
    return pool


def demo_deck(topic: str, n: int, charts: bool = True) -> dict:
    T = _t(topic)
    middle = _middle_slides(topic, charts)
    k = max(0, n - 2)
    chosen = (middle * ((k // len(middle)) + 1))[:k]
    slides = [{
        "layout": "title", "title": T, "subtitle": "Trends, insights and next steps",
        "bullets": [], "left_heading": "", "left_bullets": [], "right_heading": "",
        "right_bullets": [], "stats": [], "chart": None,
        "speaker_notes": "Generated by the offline demo provider - connect Claude or OpenAI for real content.",
    }]
    slides += [dict(s) for s in chosen]
    slides.append({
        "layout": "closing", "title": "Key takeaways",
        "bullets": [f"{T} is a strategic priority, not an experiment",
                    "Start small with measurable pilots", "Invest in skills and partnerships",
                    "Review progress quarterly and scale winners"],
        "subtitle": "", "left_heading": "", "left_bullets": [], "right_heading": "",
        "right_bullets": [], "stats": [], "chart": None,
        "speaker_notes": "Summarise and invite questions.",
    })
    return {"title": T, "subtitle": "Trends, insights and next steps", "slides": slides[:n]}


def demo_outline(topic: str, n: int, charts: bool = True) -> dict:
    deck = demo_deck(topic, n, charts)
    return {
        "title": deck["title"], "subtitle": deck["subtitle"],
        "storyline": "Context, evidence, trade-offs, then a call to action.",
        "slides": [{"title": s["title"], "layout": s["layout"], "purpose": "Template slide"}
                   for s in deck["slides"]],
    }
