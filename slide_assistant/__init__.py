"""Generative Slide Assistant: prompt -> structured deck spec (LLM) -> PowerPoint (.pptx)."""

from .schema import Deck, Slide, ChartSpec, Series, Stat
from .pipeline import generate_deck, render_deck

__all__ = ["Deck", "Slide", "ChartSpec", "Series", "Stat", "generate_deck", "render_deck"]
__version__ = "1.0.0"
