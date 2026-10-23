# Step 7 — The LangGraph flow (src/graph.py, notebook 07)

## What this code does
It turns the `answer()` function into a **graph**:

| Part | What it is | In our bot |
|---|---|---|
| **State** | one shared dictionary that flows through every node | question, rewritten, results, top_score, draft, attempts, answer, sources, path |
| **Nodes** | steps that do work; each returns only the fields it changes | rewrite, retrieve, generate, finalize, refuse |
| **Edges** | what comes next | START → rewrite → retrieve |
| **Conditional edges** | small functions that **choose** the next node | after retrieve: enough evidence? → generate / refuse. After generate: NOT_FOUND → refuse; no [S#] tags → generate again (once); else → finalize |

```
START → rewrite → retrieve ─[enough evidence?]─ no → refuse → END
                               │ yes
                            generate ─[check]─ NOT_FOUND → refuse
                               ↑         │
                               └─ no [S#] tags (retry once)
                                         │ ok
                                     finalize → END
```

## Why we need it
- The logic is **visible** (we can draw it) instead of hidden in `if` statements.
- **Loops** are easy (the citation retry).
- **One LangSmith trace per question**, each node as a child with its own time.
- The same `graph` object is used by the evaluation (Step 8) and the UI (Step 9).

## Small example — the final state for "Can my employer keep my passport?"
```
question  : Can my employer keep my passport?
rewritten : Can an employer retain a worker's official documents?
results   : [('labour_law-a13-p1', 0.999), ('labour_law-a16-p1', 0.949), ('labour_law-a45-p1', 0.43), ...]
top_score : 0.999
attempts  : 1            <- generate ran once (no retry needed)
sources   : ['UAE Labour Law (Federal Decree-Law No. 33 of 2021), Article 13']
path      : answered
seconds   : 1.9
```

## Result
Same 6/6 correct answers as Step 6, 1.7–3.6 s each. Sources are now de-duplicated (Article 51 listed once). Golden Visa: `attempts=0` → refused before any generation.
