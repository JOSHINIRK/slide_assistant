"""Command-line interface.

Examples
--------
  python generate.py "Make a 5-slide deck on EV trends" --provider claude
  python generate.py "Pitch deck for a meal-kit startup" --provider openai --slides 8 --theme sunset
  python generate.py "Intro to cybersecurity" --provider demo            # offline, no API key
  python generate.py --from-spec samples/specs/ev_trends.json --theme fresh
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

from slide_assistant.llm import ProviderError, get_provider
from slide_assistant.pipeline import generate_deck, load_spec, render_deck, save_spec
from slide_assistant.themes import THEMES


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:50] or "deck"


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    ap = argparse.ArgumentParser(description="Generate PowerPoint decks from a prompt using LLMs.")
    ap.add_argument("prompt", nargs="?", help='e.g. "Make a 5-slide deck on EV trends"')
    ap.add_argument("--provider", default="claude", choices=["claude", "openai", "demo"])
    ap.add_argument("--model", default=None, help="override the provider's default model")
    ap.add_argument("--slides", type=int, default=None, help="slide count (else parsed from prompt)")
    ap.add_argument("--audience", default=None)
    ap.add_argument("--tone", default=None)
    ap.add_argument("--no-charts", action="store_true")
    ap.add_argument("--single-stage", action="store_true", help="skip the outline planning step")
    ap.add_argument("--theme", default="midnight", choices=sorted(THEMES))
    ap.add_argument("--out", default=None, help="output .pptx path (default: output/<topic>.pptx)")
    ap.add_argument("--save-spec", action="store_true", help="also write the deck JSON next to the .pptx")
    ap.add_argument("--from-spec", default=None, help="render an existing deck JSON without calling an LLM")
    args = ap.parse_args(argv)

    if args.from_spec:
        deck = load_spec(args.from_spec)
        out = Path(args.out or f"output/{Path(args.from_spec).stem}.pptx")
        print(render_deck(deck, out, args.theme))
        return 0

    if not args.prompt:
        ap.error("a prompt is required unless --from-spec is given")

    try:
        provider = get_provider(args.provider, args.model)
        print(f"Generating with {provider.name} ({provider.model})...", file=sys.stderr)
        deck, log = generate_deck(
            args.prompt, provider,
            num_slides=args.slides, audience=args.audience, tone=args.tone,
            include_charts=not args.no_charts, two_stage=not args.single_stage,
        )
    except ProviderError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    out = Path(args.out or f"output/{_slug(deck.title)}.pptx")
    render_deck(deck, out, args.theme)
    if args.save_spec:
        save_spec(deck, out.with_suffix(".json"))
    for w in log.warnings:
        print(f"  note: {w}", file=sys.stderr)
    print(f"{len(deck.slides)} slides, {log.seconds}s, {log.repairs} repair(s) -> {out}", file=sys.stderr)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
