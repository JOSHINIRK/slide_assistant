# Prompting Framework for Slide Content

The code lives in [`slide_assistant/prompts.py`](../slide_assistant/prompts.py). The framework version is `PROMPT_VERSION = "1.0"`, and it is recorded in every generation log.

## Design principle: the LLM writes content, code does layout

The model never produces PowerPoint XML, coordinates or styling. It fills in a **typed deck spec** (title, slides, layout name, bullets, stats, chart data, speaker notes). The spec is validated with Pydantic, and python-pptx renders it the same way every time. Splitting the work like this:

- **makes output reliable:** a JSON Schema constrains the output, so it always parses.
- **makes output consistent:** themes, fonts and spacing are decided by code, not by the model.
- **keeps decks editable:** charts are native PowerPoint charts, not images.
- **keeps it portable:** the same prompts work with Claude and GPT.

```
User prompt ──► 1. Request parsing ──► 2. System prompt + 3a. Outline (Stage 1)
                                            │
                                            ▼
                                   3b. Content (Stage 2) ──► Pydantic validation
                                                                 │ fail
                                                                 ▼
                                                       4. Repair prompt (≤2×)
                                                                 │ pass
                                                                 ▼
                                                5. Quality lint ──► python-pptx render
```

## Layer 1: Request parsing (`parse_request`)

This layer turns a free-form request into a `DeckRequest`:

| Field | Source |
|---|---|
| `num_slides` | Regex on the prompt (`5-slide`, `8 slides`, `seven slide`). An explicit UI/CLI value wins. Clamped to 3–15. |
| `topic` | The prompt with the command scaffolding removed (`Make a 5-slide deck on …`). |
| `audience`, `tone` | UI/CLI settings (default: business professionals, professional and concise). |
| `include_charts` | UI/CLI toggle. Changes the chart instruction block. |
| `extra_instructions` | Free text appended verbatim (e.g. "focus on India"). |

Parsing the slide count in code, instead of leaving it to the model, gives a deterministic target that later stages can check.

## Layer 2: System prompt (`SYSTEM_PROMPT`)

This is a stable block that is the same for every request (so it also benefits from prompt caching). It is organised in XML-tagged sections:

1. **Role:** "expert presentation designer and analyst".
2. **`<storytelling>`:** the narrative arc (context → evidence → implications → takeaways). It also requires *one point per slide* and **insight titles** ("Battery costs fell 85% since 2013", not "Battery costs").
3. **`<slide_writing_rules>`:** 3–5 bullets, 6–14 words each, parallel grammar, specifics over adjectives, no markdown inside strings, and 2–4 sentences of speaker notes.
4. **`<layouts>`:** a catalogue of the 9 layouts and when to use each one. This is how the model "chooses visuals".
5. **`<chart_rules>`:** match the chart type to the message (time series → column/line, ranking → bar, part-of-whole → pie with ≤6 slices). Units go in the axis label, and values are plain numbers.
6. **Data honesty:** every chart must name a source and year, or be labelled "Illustrative data". The model may never present invented numbers as fact.

## Layer 3: Stage prompts

### Stage 1: Outline (`build_outline_prompt`, optional, on by default)
- The model returns the deck title, a storyline, and for each slide `{title, layout, purpose}`.
- Constraints: exactly N slides, the first is `title`, the last is `closing`, and there are never more than two `bullets` slides in a row (this keeps the layouts varied).
- **Why two stages?** Planning first improves narrative flow and layout variety. It also gives a reviewable artefact, shown in the UI under *Generation details*. It costs one extra call. You can turn it off with `--single-stage` or with the UI toggle.

### Stage 2: Content (`build_content_prompt`)
- Includes the request block and the approved outline (if there is one).
- Includes **one few-shot example slide** (`bullets_chart` about solar costs) that shows the expected density, the insight title, chart field usage, a source note and speaker notes. The prompt explicitly says not to reuse the example's topic.
- Request parameters are wrapped in tags (`<topic>`, `<slide_count>`, `<audience>`, `<charts>`…) so the model can tell instructions apart from user data.

## Layer 4: Structured output + repair loop

- **Claude:** `output_config.format = {type: "json_schema", schema: …}` (structured outputs).
- **OpenAI:** `response_format = {type: "json_schema", strict: true, …}`.
- In strict mode every property must be `required` with `additionalProperties: false`, so "optional" fields are written as `""`, `[]` or `null` (see `schema.deck_json_schema`).
- The JSON Schema guarantees the *shape*. Pydantic then checks the *semantics* that JSON Schema can't express: series length equals category count, a `chart` layout must have a chart, a pie chart has exactly one non-negative series, and so on.
- On a validation failure, `build_repair_prompt` sends back the previous answer plus the exact validation errors and asks for a corrected deck that changes only what's broken. The loop allows up to 2 repairs, then raises a clear error.

## Layer 5: Quality lint (`quality.py`)

These deterministic fixes run after validation. Each one is reported as a warning in the UI and CLI:

- Trims surplus slides (the closing slide is kept).
- Forces slide 1 to use the `title` layout.
- Trims bullet lists to ≤ 6 items and shortens bullets to ≤ 25 words.
- A chart on a non-chart layout is promoted to `bullets_chart` or `chart`.
- A pie chart with more than 8 slices becomes a bar chart.
- A chart with no source note is stamped "Illustrative data – verify before use".
- Charts are stripped if the user disabled them.

## Tuning knobs

| Knob | Where |
|---|---|
| Model | UI sidebar / `--model` / `CLAUDE_MODEL`, `OPENAI_MODEL` env vars |
| Claude effort (`low`–`max`, default `medium`) | `ClaudeProvider(effort=…)` |
| Slide count, audience, tone, charts, extra instructions | UI sidebar / CLI flags |
| Single- vs two-stage | UI toggle / `--single-stage` |
| Writing rules, layout catalogue, chart rules | `SYSTEM_PROMPT` in `prompts.py` |
| Lint thresholds | constants at the top of `quality.py` |

## Example: what the model receives (Stage 2, abbreviated)

```text
<request>Make a 5-slide deck on EV trends</request>
<topic>EV trends</topic>
<slide_count>5</slide_count>
<audience>business professionals</audience>
<tone>professional and concise</tone>
<charts>Include about 2 slide(s) with a chart (layouts chart or bullets_chart), and use a stats slide if headline numbers matter.</charts>

Write the full deck following this approved outline. …
<outline>{ "title": "...", "storyline": "...", "slides": [ ... ] }</outline>

Here is one well-formed content slide, for the expected quality and field usage only …
<example_slide>{ "layout": "bullets_chart", "title": "Solar is now the cheapest new power in most markets", ... }</example_slide>
```
