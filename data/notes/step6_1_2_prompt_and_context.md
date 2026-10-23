# Cells 6.1–6.2 — The answer prompt and the source format

## What this code does
- Imports the LLM (`src/llm.py`) and retrieval with rewriting (`src/rewrite.py`).
- `CUTOFF = 0.10` and a fixed `REFUSAL` message.
- `ANSWER_SYSTEM` is the **system prompt** with 8 rules (only use the sources, tag every fact `[S1]`, reply `NOT_FOUND` if not covered, include Regulation detail, follow the 2022 amendment, short answers, no personal legal advice, how to handle "What does Article X say?").
- `format_context()` numbers the chunks:
```
[S1] UAE Labour Law (Federal Decree-Law No. 33 of 2021), Article 29
<chunk text>

[S2] Executive Regulation (Cabinet Resolution No. 1 of 2022), Article 18
<chunk text>
```

## Why we need it
- **Grounding**: the model may only use what we give it → fewer invented facts (faithfulness).
- **Citations**: numbered tags are easy for a model to copy and easy for code to check.
- **Refusal path**: `NOT_FOUND` is a fixed word, so code can detect it reliably.
