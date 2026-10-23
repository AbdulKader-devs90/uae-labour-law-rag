# Cell 4.4 — Meaning search (dense) on its own

## What this code does
- It embeds the question and asks Chroma for the 5 closest chunks, with a **relevance score** (higher = closer).
- `label(d)` prints a short ID such as `labour_law:29` (law : article).

## Why we need it
To see what meaning search finds, and how confident it is, before we add anything else.

## Our result for "How many days of annual leave do I get?"
```
0.809  labour_law:29   Annual leave (part 1)        <- correct
0.782  labour_law:29   Annual leave (part 2)        <- correct
0.762  labour_law:32   Various holidays
0.741  exec_regs:18    Annual Leave of Workers      <- the Regulation's detail on the same topic
0.716  labour_law:28   Official holidays
```
Note: the scores are close together (0.72–0.81). A score alone does not clearly separate "right" from "nearly right". This is why we add a re-ranker in Step 5.
