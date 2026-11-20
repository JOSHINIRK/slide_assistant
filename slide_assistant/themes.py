"""Colour/typography themes for rendered decks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    name: str
    background: str      # content slide background
    hero_bg: str         # title / section / closing background
    hero_text: str
    title: str           # slide title colour on content slides
    text: str            # body text
    muted: str           # footers, source notes
    accent: str          # bars, bullet markers
    card: str            # card / panel fill
    chart_colors: tuple[str, ...]
    heading_font: str = "Segoe UI Semibold"
    body_font: str = "Segoe UI"


THEMES: dict[str, Theme] = {
    "midnight": Theme(
        name="midnight", background="FFFFFF", hero_bg="0F1B2D", hero_text="FFFFFF",
        title="0F1B2D", text="2B3445", muted="7A8599", accent="00A6A6", card="EEF3F8",
        chart_colors=("0F6E8C", "00A6A6", "F2A541", "8E6BBF", "E4572E", "6C7A89"),
    ),
    "corporate": Theme(
        name="corporate", background="FFFFFF", hero_bg="1F3A93", hero_text="FFFFFF",
        title="1F3A93", text="333333", muted="808080", accent="F39C12", card="F2F4F8",
        chart_colors=("1F3A93", "F39C12", "27AE60", "8E44AD", "C0392B", "7F8C8D"),
        heading_font="Calibri", body_font="Calibri",
    ),
    "fresh": Theme(
        name="fresh", background="FBFCF8", hero_bg="1E5631", hero_text="FFFFFF",
        title="1E5631", text="2F3B2F", muted="7D8A7D", accent="7FB800", card="EEF4E6",
        chart_colors=("1E5631", "7FB800", "FFB400", "00A6ED", "F6511D", "6B7B6B"),
    ),
    "sunset": Theme(
        name="sunset", background="FFFFFF", hero_bg="3D1E6D", hero_text="FFFFFF",
        title="3D1E6D", text="352F44", muted="8A8499", accent="FF6F59", card="F5F0FA",
        chart_colors=("3D1E6D", "FF6F59", "FFB547", "43AA8B", "4D9DE0", "8A8499"),
    ),
}

DEFAULT_THEME = "midnight"


def get_theme(name: str | None) -> Theme:
    return THEMES.get((name or DEFAULT_THEME).lower(), THEMES[DEFAULT_THEME])
