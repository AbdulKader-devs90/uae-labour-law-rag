# Cell 2.1 — Load the PDFs

## What this code does
- It opens each of the 4 PDF files in `data/raw/`.
- `PyPDFLoader` reads a PDF and gives back **one `Document` per page**. A `Document` is a LangChain object with two parts:
  - `page_content` — the text of the page
  - `metadata` — extra information, for example the file name and page number
- `SOURCES` is a dictionary. It connects each short file name to a readable title. We use the title later in citations.
- The loop counts the pages and the characters in each file, and prints the result.

## Why we need it
- The bot can only answer from text that we load. This is the first step of the indexing flow: **Load** → Clean → Chunk → Embed → Store.
- The page and character counts are a quick health check. If a file shows 0 characters, the PDF is a scanned image and we must use OCR.

## Small example
A PDF with 2 pages becomes a list of 2 `Document` objects:

```python
[
  Document(page_content="Article (1) Definitions ...",  metadata={"source": "labour_law.pdf", "page": 0}),
  Document(page_content="Article (2) Scope of ...",     metadata={"source": "labour_law.pdf", "page": 1}),
]
```

Our result:

| File | Pages | Characters |
|---|---|---|
| labour_law.pdf | 46 | 87,616 |
| exec_regs.pdf | 31 | 57,957 |
| labour_law_amendment_2022.pdf | 2 | 1,667 |
| pdpl.pdf | 29 | 44,032 |
