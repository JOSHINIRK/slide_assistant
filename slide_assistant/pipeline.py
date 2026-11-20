"""End-to-end pipeline: prompt -> (outline) -> deck JSON -> validate/repair -> lint -> .pptx"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from .builder import save_presentation
from .llm import LLMProvider, ProviderError
from .prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    DeckRequest,
    build_content_prompt,
    build_outline_prompt,
    build_repair_prompt,
    parse_request,
)
from .quality import lint_deck
from .schema import Deck, Outline, deck_json_schema, outline_json_schema


@dataclass
class GenerationLog:
    provider: str
    model: str
    prompt_version: str = PROMPT_VERSION
    request: dict = field(default_factory=dict)
    outline: dict | None = None
    repairs: int = 0
    warnings: list[str] = field(default_factory=list)
    seconds: float = 0.0


def generate_deck(
    prompt: str,
    provider: LLMProvider,
    *,
    num_slides: int | None = None,
    audience: str | None = None,
    tone: str | None = None,
    include_charts: bool = True,
    extra_instructions: str = "",
    two_stage: bool = True,
    max_repairs: int = 2,
) -> tuple[Deck, GenerationLog]:
    """Turn a natural-language request into a validated ``Deck``."""
    t0 = time.perf_counter()
    req: DeckRequest = parse_request(
        prompt, num_slides=num_slides, audience=audience, tone=tone,
        include_charts=include_charts, extra_instructions=extra_instructions,
    )
    log = GenerationLog(provider=provider.name, model=provider.model, request={
        "topic": req.topic, "num_slides": req.num_slides, "audience": req.audience,
        "tone": req.tone, "include_charts": req.include_charts, "two_stage": two_stage,
    })
    log.warnings.extend(req.notes)

    outline_json = None
    if two_stage:
        raw_outline = provider.generate_json(
            SYSTEM_PROMPT, build_outline_prompt(req), outline_json_schema(), "deck_outline"
        )
        try:
            outline = Outline.model_validate(raw_outline)
            log.outline = outline.model_dump()
            outline_json = json.dumps(log.outline, indent=2)
        except ValidationError as e:  # outline is advisory; fall back to single stage
            log.warnings.append(f"Outline invalid, continuing without it: {e.error_count()} error(s).")

    user_prompt = build_content_prompt(req, outline_json)
    raw = provider.generate_json(SYSTEM_PROMPT, user_prompt, deck_json_schema(), "slide_deck")

    deck = None
    for attempt in range(max_repairs + 1):
        try:
            deck = Deck.model_validate(raw)
            break
        except ValidationError as e:
            if attempt == max_repairs:
                raise ProviderError(
                    f"Model output failed validation after {max_repairs} repair attempt(s):\n{e}"
                ) from e
            log.repairs += 1
            raw = provider.generate_json(
                SYSTEM_PROMPT,
                build_repair_prompt(user_prompt, json.dumps(raw, indent=2), str(e)),
                deck_json_schema(),
                "slide_deck",
            )

    log.warnings.extend(lint_deck(deck, expected_slides=req.num_slides, allow_charts=include_charts))
    log.seconds = round(time.perf_counter() - t0, 2)
    return deck, log


def render_deck(deck: Deck, out_path: str | Path, theme: str | None = None) -> Path:
    return save_presentation(deck, out_path, theme)


def load_spec(path: str | Path) -> Deck:
    return Deck.model_validate_json(Path(path).read_text(encoding="utf-8"))


def save_spec(deck: Deck, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(deck.model_dump_json(indent=2), encoding="utf-8")
    return path
