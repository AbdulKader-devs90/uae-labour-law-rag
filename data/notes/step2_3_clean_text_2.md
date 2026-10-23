# Cell 2.3 — Clean the text

## What this code does
It has 3 small functions:

1. **`norm(line)`** — removes a page number at the end of a line.
   `"Federal Decree ... Labor Relations 7"` → `"Federal Decree ... Labor Relations"`
2. **`find_repeating_lines(pages)`** — finds lines that appear on at least half of the pages (after `norm`). These lines are headers or footers.
3. **`clean_pages(pages)`** — goes through every line and:
   - removes empty lines
   - removes header/footer lines
   - removes lines that are only a page number (`7`, `Page 7`, `7 of 46`)
   - joins all pages into **one text** per law
   - joins words that were split with a hyphen at the end of a line
   - changes many spaces into one space

## Why we need it
- **Embeddings:** if every chunk contains the same header, all chunks look similar. Search becomes less precise.
- **BM25 (keyword search):** the header words appear everywhere, so they give false matches.
- **One text per law:** an article can start on one page and end on the next page. If we keep pages separate, we cut articles in half.

## Small example

Before (2 pages):
```
Federal Decree by Law No. (33) of 2021 Concerning Regulating Labor Relations 7
Article (29)
The worker is entitled to an annual leave of 30 days
Federal Decree by Law No. (33) of 2021 Concerning Regulating Labor Relations 8
for each year of service ...
```

After:
```
Article (29)
The worker is entitled to an annual leave of 30 days
for each year of service ...
```

Our result:

| File | Before | After | Removed |
|---|---|---|---|
| labour_law.pdf | 87,616 | 82,351 | page header |
| exec_regs.pdf | 57,957 | 53,018 | page header |
| labour_law_amendment_2022.pdf | 1,667 | 1,605 | nothing (only 2 pages) |
| pdpl.pdf | 44,032 | 41,127 | page header |

About 6% of the text was noise.
