# Cell 4.6 — Hybrid search with Reciprocal Rank Fusion (RRF)

## What this code does
- It runs **both** searches (top 10 each) and merges the two ranked lists with **RRF**.
- Every chunk gets `1 / (60 + rank)` from each list it appears in. The scores are added. The highest total wins.

## Why we need it
- Dense and BM25 make **different** mistakes. Together they catch more.
- The two score types are on different scales (cosine 0–1 vs BM25 0–20+). RRF uses only the **rank**, so we do not need to compare scores.
- We wrote it ourselves (about 10 lines), so we know exactly how it works.

## Small example
| Chunk | Dense rank | BM25 rank | RRF score |
|---|---|---|---|
| A | 1 | 3 | 1/61 + 1/63 = 0.0323 |
| B | 2 | — | 1/62 = 0.0161 |
| C | — | 1 | 1/61 = 0.0164 |

A is in **both** lists, so it wins. B and C are each found by only one search.
