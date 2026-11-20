# Summary Video Walkthrough: Script & Shot List

Target length is **about 5 minutes**. Record it on Windows with **Win + Alt + R** (Xbox Game Bar) or with OBS Studio, at 1920×1080.

## Before recording
1. `pip install -r requirements.txt`, then put your API key in `.env` (copy it from `.env.example`).
2. `streamlit run app.py`, and keep the browser tab open.
3. Open `samples/decks/ev_trends.pptx` in PowerPoint, minimised.
4. In VS Code, open these tabs: `prompts.py`, `schema.py`, `builder.py`, `docs/PROMPTING_FRAMEWORK.md`.

---

| # | Time | On screen | Narration |
|---|---|---|---|
| 1 | 0:00–0:20 | Streamlit app home page | "This is the Generative Slide Assistant. You describe a deck in plain English, an LLM writes the content, and the tool builds a ready-to-edit PowerPoint with headings, bullets and charts." |
| 2 | 0:20–0:50 | Architecture diagram in README | "The key design decision: the LLM never writes PowerPoint directly. It fills in a typed JSON deck spec. We validate that spec, then python-pptx renders it deterministically. So the content is AI-generated, but the layout is always clean and consistent." |
| 3 | 0:50–1:40 | Sidebar → choose **Claude**, theme *midnight*. Type "Make a 5-slide deck on EV trends", then click **Generate** | "I pick a provider. Claude and OpenAI GPT are both supported, plus an offline demo mode. Notice the app already detected the topic and the slide count from my prompt. Generation is two-stage: first an outline, then the content." |
| 4 | 1:40–2:30 | Preview tab: scroll through the slides, open the speaker notes, point at the chart and the source note | "Every slide title states an insight, not just a label. The model chose layouts itself: a bullets-plus-chart slide, a pie chart, a line chart. Each chart cites a source, or is marked as illustrative. That's enforced by the prompt and by a quality check. Each slide also gets speaker notes." |
| 5 | 2:30–2:55 | *Generation details* tab: the Stage 1 outline, any warnings | "Here's the Stage 1 outline the model planned, plus the generation log: model, time, any automatic repairs or lint fixes." |
| 6 | 2:55–3:25 | *Edit JSON* tab: change a bullet and a chart value, then **Apply**. Switch the theme to *sunset* | "Everything is editable before export. I can tweak text or numbers in the spec, or switch the theme, without calling the model again." |
| 7 | 3:25–4:00 | Click **Download .pptx** and open it in PowerPoint. Right-click the chart → *Edit Data* | "And here's the PowerPoint. The charts are native PowerPoint charts, so the data is fully editable, and the speaker notes are in the notes pane." |
| 8 | 4:00–4:40 | VS Code: `prompts.py` (system prompt sections), `schema.py` (JSON Schema), the repair loop in `pipeline.py` | "The prompting framework has five layers: request parsing, a system prompt with storytelling, writing and chart-honesty rules, two-stage outline and content prompts with a few-shot example, structured outputs plus a repair loop, and finally a quality lint. It's documented in docs/PROMPTING_FRAMEWORK.md." |
| 9 | 4:40–5:00 | Terminal: `python generate.py "Make a 5-slide deck on EV trends" --provider openai`, then `pytest -q` | "There's also a CLI for batch use, three sample decks in the samples folder, and a test suite of 24 tests, including mocked API tests for both providers. Thanks for watching." |

## Tips
- If the live API call is slow, do the take in shot 3 with the *Demo (offline)* provider, then load the `ev_trends` sample for shots 4–7.
- Zoom the browser to 110–125% so text is readable in the recording.
- Export: MP4, H.264. Save it as `docs/walkthrough.mp4`, or upload it and link it from the README.
