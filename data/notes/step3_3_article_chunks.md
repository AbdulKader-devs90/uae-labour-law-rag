# Cell 3.3 — Build one chunk per article

## What this code does
- It cuts each law at the article starts from Cell 3.2. One article = one chunk.
- Text before Article 1 (the preamble) becomes its own chunk (article = 0).
- It fixes reversed brackets: `Article )29 (` → `Article (29)`.
- If an article is longer than 1,500 characters, it splits the article into parts (150 characters overlap).
- It adds a **header line** to every chunk, and **metadata**: source, title, article, part, chunk_id.

## Why we need it
- **One topic per chunk** → the embedding of the chunk is "clean", so search finds it more easily.
- **The rule is not cut in half** → the model sees the full rule.
- **Citations for free** → the metadata already says "Labour Law, Article 29".
- **The header** (`[Labour Law — Article 29]`) is inside the text, so search knows which law the chunk comes from. Article 29 exists in more than one law. This technique is called a *contextual chunk header*.
- **Long articles are split** because the embedding model reads max 512 tokens. Text after that is silently ignored.

## Small example
```
[Labour Law — Article 29, part 1/2]
Article (29)
Annual leave
1. ... the Worker shall be entitled to an annual leave with full pay of not less than:
a. Thirty days for each year of his extended service.
b. Two days for each month if his service period is more than six months and less than one year.
...
metadata = {"source": "labour_law", "article": 29, "part": 1, "chunk_id": "labour_law-a29-p1"}
```

Result: **204 article chunks** (Labour Law 97, Executive Regulation 56, Amendment 4, PDPL 47).
