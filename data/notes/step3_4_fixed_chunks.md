# Cell 3.4 — Fixed-size chunks (the baseline)

## What this code does
- It cuts each law every **800 characters**, with **100 characters overlap**, and ignores the article structure.
- `add_start_index=True` saves where each chunk starts in the text.
- With that position, it records the article in which the chunk **starts**. We use this only for scoring in Step 8.
- No header is added. The chunk has only raw text.

## Why we need it
- This is the most common default in RAG tutorials.
- We build it to **compare**. In Step 8 we ask the same questions on both versions and measure which one finds the right article more often. Then our claim "article chunks are better" has numbers behind it.

## Small example
Text: `AAAAAAAAAA BBBBBBBBBB CCCCCCCCCC` with size 12 and overlap 3:
```
chunk 1: "AAAAAAAAAA B"
chunk 2: "B BBBBBBBBBB"   <- starts with the last part of chunk 1 (overlap)
chunk 3: ...
```
The cut does not care where a sentence or an article ends.

Result: **262 fixed chunks**.
