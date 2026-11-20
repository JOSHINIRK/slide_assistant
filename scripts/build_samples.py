"""Build the sample decks in samples/decks/.

Default: render the committed specs in samples/specs/ (no API key needed).
With --provider claude|openai: regenerate each spec from its prompt with a live LLM first.

    python scripts/build_samples.py
    python scripts/build_samples.py --provider claude
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from slide_assistant.llm import get_provider  # noqa: E402
from slide_assistant.pipeline import generate_deck, load_spec, render_deck, save_spec  # noqa: E402

SAMPLES = [
    # (spec name, theme, prompt used to (re)generate it)
    ("ev_trends", "midnight", "Make a 5-slide deck on EV trends"),
    ("saas_quarterly_review", "corporate",
     "Create a 7-slide quarterly business review for Nimbus Analytics, a fictional B2B SaaS company. "
     "Use clearly illustrative numbers."),
    ("cloud_migration", "fresh",
     "Prepare a 6-slide cloud migration strategy deck for a mid-size enterprise's leadership team"),
]


def main() -> None:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["claude", "openai"], default=None)
    args = ap.parse_args()

    for name, theme, prompt in SAMPLES:
        spec_path = ROOT / "samples" / "specs" / f"{name}.json"
        if args.provider:
            deck, log = generate_deck(prompt, get_provider(args.provider))
            spec_path = ROOT / "samples" / "specs" / f"{name}.{args.provider}.json"
            save_spec(deck, spec_path)
            print(f"[{name}] generated in {log.seconds}s; warnings: {log.warnings}")
        else:
            deck = load_spec(spec_path)
        out = render_deck(deck, ROOT / "samples" / "decks" / f"{spec_path.stem}.pptx", theme)
        print(out.relative_to(ROOT))


if __name__ == "__main__":
    main()
