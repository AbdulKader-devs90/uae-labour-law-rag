# Cell 3.7 — Save both versions as JSONL

## What this code does
- It writes every chunk to a file, **one chunk per line**, as JSON:
  - `data/chunks/article_chunks.jsonl` (204 lines)
  - `data/chunks/fixed_chunks.jsonl` (262 lines)

## Why we need it
- Step 4 (embeddings and search) loads these files. It does not run Steps 2 and 3 again.
- JSONL is easy to read, easy to load line by line, and easy to check in a text editor.

## Small example
One line of `article_chunks.jsonl`:
```json
{"text": "[Labour Law — Article 29, part 1/2]\nArticle (29)\nAnnual leave\n1. ...",
 "metadata": {"source": "labour_law", "title": "UAE Labour Law (Federal Decree-Law No. 33 of 2021)",
              "article": 29, "part": 1, "chunk_id": "labour_law-a29-p1"}}
```
