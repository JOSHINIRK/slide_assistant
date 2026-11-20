"""Post-generation quality checks ("lint") applied after the LLM output validates.

The schema guarantees *shape*; these rules enforce *slide hygiene* the model may drift on.
Fixes are applied in place and each one is reported as a warning so it is visible in the UI.
"""

from __future__ import annotations

from .schema import Deck

MAX_BULLETS = 6
MAX_BULLET_WORDS = 25
MAX_STATS = 4
MAX_PIE_SLICES = 8


def _trim_words(text: str, limit: int) -> str:
    words = text.split()
    return text if len(words) <= limit else " ".join(words[:limit]).rstrip(",;:") + "…"


def lint_deck(deck: Deck, expected_slides: int | None = None, allow_charts: bool = True) -> list[str]:
    warnings: list[str] = []

    if expected_slides and len(deck.slides) != expected_slides:
        warnings.append(f"Model returned {len(deck.slides)} slides (requested {expected_slides}).")
        if len(deck.slides) > expected_slides:
            # keep the closing slide, drop surplus middle slides
            closing = deck.slides[-1]
            deck.slides = deck.slides[: expected_slides - 1] + [closing]

    if deck.slides[0].layout != "title":
        warnings.append("First slide was not a title slide; layout changed to 'title'.")
        deck.slides[0].layout = "title"

    for i, s in enumerate(deck.slides, start=1):
        for attr in ("bullets", "left_bullets", "right_bullets"):
            items = getattr(s, attr)
            if len(items) > MAX_BULLETS:
                warnings.append(f"Slide {i}: {len(items)} {attr} trimmed to {MAX_BULLETS}.")
                items = items[:MAX_BULLETS]
            fixed = [_trim_words(b, MAX_BULLET_WORDS) for b in items]
            if fixed != items:
                warnings.append(f"Slide {i}: long {attr} shortened to {MAX_BULLET_WORDS} words.")
            setattr(s, attr, fixed)

        if len(s.stats) > MAX_STATS:
            warnings.append(f"Slide {i}: {len(s.stats)} stats trimmed to {MAX_STATS}.")
            s.stats = s.stats[:MAX_STATS]

        if s.layout in ("bullets", "closing") and not s.bullets:
            warnings.append(f"Slide {i}: '{s.layout}' slide has no bullets.")

        if s.layout == "bullets_chart" and not s.bullets:
            warnings.append(f"Slide {i}: no bullets beside chart; switched to full-width chart.")
            s.layout = "chart"

        if s.chart is not None:
            c = s.chart
            if not allow_charts:
                warnings.append(f"Slide {i}: chart removed (charts disabled).")
                s.chart = None
                if s.layout in ("chart", "bullets_chart"):
                    s.layout = "bullets"
            else:
                if c.type in ("pie", "doughnut") and len(c.categories) > MAX_PIE_SLICES:
                    warnings.append(f"Slide {i}: pie with {len(c.categories)} slices switched to bar chart.")
                    c.type = "bar"
                if not c.source_note.strip():
                    c.source_note = "Illustrative data - verify before use"
                    warnings.append(f"Slide {i}: chart had no source note; marked as illustrative.")
            if s.layout not in ("chart", "bullets_chart") and s.chart is not None:
                # chart attached to a non-chart layout would be silently dropped by the renderer
                s.layout = "bullets_chart" if s.bullets else "chart"
                warnings.append(f"Slide {i}: layout changed to '{s.layout}' to show its chart.")

    return warnings
