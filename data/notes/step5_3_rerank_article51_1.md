# Cell 5.3 — The re-ranker on "What does Article 51 say?"

## What this code does
- Hybrid search gives 10 candidates.
- The **re-ranker** (FlashRank, model `ms-marco-MiniLM-L-12-v2`) scores each (question, chunk) pair and sorts them.

## Why we need it
| | Bi-encoder (embeddings) | Cross-encoder (re-ranker) |
|---|---|---|
| Reads | question and chunk **separately** | question and chunk **together** |
| Speed | very fast, searches all chunks | slow, only top 10 |
| Precision | rough | high |

Two stages: **fast search finds candidates → precise re-ranker picks the best.**

## Our result
```
Hybrid order : amendment:1, labour_law:51, exec_regs:38, ...
After rerank :
   0.872  labour_law:51   End-of-Service Gratuity for Full-Time Workers   <- now first
   0.745  labour_law:51   (part 2)
   0.542  exec_regs:29    Deduction from End of Service Pay
   0.007  exec_regs:38
   0.007  labour_law:34
```
The re-ranker can **read** "Article (51)" in the chunk, so it fixes the RRF mistake.
