# Cell 2.2 — Look at the raw text

## What this code does
- It takes the pages of the Labour Law.
- It prints the first 1,200 characters of page 0 and page 5.

## Why we need it
- This is the most important habit in RAG: **read what the machine reads**.
- A PDF looks clean on screen, but the extracted text often has noise:
  - page headers and footers on every page
  - page numbers
  - words broken across two lines
  - strange characters or reversed brackets
- If we do not look, we do not know what to clean. Bad text in = bad answers out.

## Small example
What we found on page 0:

```
Federal Decree by Law No. (33) of 2021 Concerning Regulating Labor Relations 1
```

- This line is the **page header**. The `1` at the end is the **page number**.
- On page 2 the same line ends with `2`, on page 3 with `3`, and so on.
- So the line is a little different on every page. A simple "remove identical lines" rule does not catch it. Cell 2.3 handles this.

We also saw that the law uses **"Labor"** (US spelling). Users in the UAE usually type **"Labour"**. Keyword search (BM25) will not match these two words. This is one reason we use hybrid search in Step 4.
