# Cell 5.7 — Why is the salary question still wrong?

## What this code does
It checks if Labour Law Article 22 is **in the candidate pool** at all, with 10 and with 20 candidates per search.

## Why we need it
Two different problems need two different fixes:
- **Not in the pool** → a search problem (more candidates, better query).
- **In the pool but ranked low** → a re-ranker problem.

## Our result
```
candidates=10: pool 13 chunks | Article 22: NOT IN POOL
candidates=20: pool 27 chunks | Article 22: NOT IN POOL
```
- More candidates did **not** help → we keep **10** (faster, same result).
- We record this as a **known hard case** for the evaluation report. The practical answer to "my employer has not paid me" is spread over several articles (wage payment, the worker's right to leave without notice, complaints), so it is a genuinely hard question for retrieval.
- Do not tune the whole system for one question. Measure it in Step 8 with the other questions.
