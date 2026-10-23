# Cell 5.5 — The "not found" cut-off

## What this code does
It takes the **best re-ranker score** for questions the laws cover (in scope) and for questions they do not cover (out of scope).

## Why we need it
The handout: *"Your 'I don't know' path matters more than your happy path."*
If even the best chunk scores low, the laws probably do not cover the question. Then the bot must say "not found", not guess. We choose the cut-off **from data**, not by feeling.

## Our result
| In scope | Score | Out of scope | Score |
|---|---|---|---|
| Annual leave | 0.987 | Golden Visa fee | 0.001 |
| Article 51 | 0.872 | IRS 401k limit | 0.000 |
| Salary not paid | 0.544 | World Cup 2022 | 0.000 |
| Gratuity | 1.000 | Renew Emirates ID | 0.000 |
| Share personal data | 0.827 | | |
| Probation period | 0.994 | | |
| **Keep my passport** | **0.002** ⚠️ | | |

- Big gap between the groups → **CUTOFF = 0.10**.
- ⚠️ **False refusal:** the Labour Law covers the passport question (it says "official documents"), but the score is 0.002. Same vocabulary gap as the salary question.
