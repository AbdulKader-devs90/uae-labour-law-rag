# Cell 4.7 — Compare dense, BM25 and hybrid

## What this code does
It runs 5 test questions through all 3 search methods and prints the top 3 results of each.

## Why we need it
To see **where each method fails**. This tells us what to fix next.

## Our result
| Question | Dense | BM25 | Hybrid | Lesson |
|---|---|---|---|---|
| Annual leave days | 29, 29, 32 ✅ | 29, 29, regs 19 ✅ | 29, 29, regs 18 ✅ | Easy: all methods agree |
| "What does Article 51 say?" | amendment 1, regs 38, pdpl 23 ❌ | **51, 51** ✅ | amendment 1, **51** ⚠️ | Embeddings do not understand **numbers** |
| Salary not paid for 2 months | 9, 40, 47 ? | 30, 32, 54 ? | 9, 30, 40 ? | Plain-language question: hard for both |
| End-of-service gratuity | 51, 51 ✅ | 51, 51, 52 ✅ | 51, 51, 52 ✅ | Legal keywords: all good |
| Share my personal data | pdpl 22, 23, 14 | pdpl 1, 1, 1 ❌ | pdpl 22, 5, 7 | BM25 is fooled by the **Definitions** article (it contains every keyword) |

## Follow-up check: what were the "?" results?
| Result | Real article title | Relevant? |
|---|---|---|
| labour_law:9 | Probation Period | ❌ |
| labour_law:30 | Maternity Leave | ❌ |
| labour_law:40 | Suspension of Work | ❌ |
| amendment:1 | "The text of clause (3) ..." (replaces a clause) | ❌ for "Article 51" |
| **labour_law:22** | **Determining the Amount or Type of Wage and Paying It** | ✅ the right answer — not found |
| **labour_law:23** | **Method of Calculating Wages** | ✅ related — not found |

The salary question **failed in all three methods**. The user says "salary" and "paid"; the law says "wage" and "paying". This is a **vocabulary gap**. A re-ranker cannot fix it if the right article is not among the candidates. Possible fix later: let the LLM **rewrite the question into legal terms** before searching (query rewriting).

## Lessons
1. **Dense fails on exact numbers**, BM25 fails on keyword-heavy chunks (Definitions). Hybrid covers some of both.
2. **RRF is rank-only.** A chunk that is #1 in only one list can still end up first (amendment:1 for "Article 51"). RRF cannot tell which list was right.
3. Fix → **Step 5: a re-ranker** that reads the question and each chunk **together** and scores how well the chunk answers the question.