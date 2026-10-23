# Cell 5.2 — Where does the right article rank?

## What this code does
- For the question *"My employer has not paid my salary for two months"*, it finds the **rank** of the right article (Labour Law Article 22, "Determining the Amount or Type of Wage and Paying It") in the top 50 of dense search and of BM25.
- It then tries the same question **in the law's words** ("wage", "non-payment of wages").

## Why we need it
A re-ranker only sees the **candidates** (top 10). If the right chunk is not among them, the re-ranker cannot fix it. We must know this before we trust re-ranking.

## Our result
```
Article 22 rank in dense top 50: 15     <- outside the 10 candidates
Article 22 rank in BM25  top 50: 35     <- far outside

Rewritten in legal terms:
  dense top 5: exec_regs:16, labour_law:9, labour_law:33, labour_law:22, labour_law:34   <- now rank 4
```
User words ("salary", "paid") ≠ law words ("wage", "paying"). Rewriting helps dense search.
