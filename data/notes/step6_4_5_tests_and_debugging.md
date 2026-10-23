# Cells 6.4–6.5 — Test answers and debug with LangSmith

## What this code does
- 6.4 runs 6 test questions (normal, article number, vocabulary gap, other law, amendment, out of scope).
- 6.5 prints the exact sources `[S1]..[S4]` the model saw for one question.

## Why we need it
To find problems **and** to check that a fix did not break other answers (**regression check**).

## What happened (3 rounds)
| Round | Article 51 result | Cause | Fix |
|---|---|---|---|
| 1 | Refused, although Art. 51 was found (0.997) | Model over-strict for "What does Article X say?" | Prompt rules 7–8 |
| 2 | Answered, but cited the **Preamble** | Rewriter added the full law title → chunks that *mention* the title won | — investigate with 6.5 |
| 2b | Art. 51 not even in top 4 (Preambles, Amendment Art. 1 at 0.997) | Same cause, re-ranker scored against the rewritten question | Stricter rewrite prompt, drop Preambles, re-rank against **both** questions (keep best score) |
| 3 | ✅ Answered, cites **Labour Law Article 51** | | |

## Final result (all 6 pass)
| Question | Path | Sources | Time |
|---|---|---|---|
| Annual leave | answered | Labour Law Art. 29 + Exec. Regulation | 2.2 s |
| What does Article 51 say? | answered | Labour Law Art. 51 | 2.7 s |
| Keep my passport? | answered | Labour Law Art. 13 | 1.5 s |
| Share personal data | answered (score 0.83, was 0.50) | PDPL Art. 23 + others | 2.1 s |
| 2022 amendment | answered | Amendment Art. 1 (changes Labour Law Art. 8, clause 3) | 1.7 s |
| Golden Visa fee | refused_low_score (0.005) | — | 0.9 s |

Lesson: **every fix can have a side effect**. Only re-running all questions shows it.
