# Cell 2.4 — Save the clean text and find the article headings

## What this code does
- It writes each clean text to `data/clean/<name>.txt`, so we can open it and read it.
- It makes **one `Document` per law**, with metadata:
  - `source` — the file name, for example `labour_law.pdf`
  - `title` — the readable name, for example `UAE Labour Law (Federal Decree-Law No. 33 of 2021)`
- It uses a **regular expression (regex)** to find lines that start with the word `Article`, and prints how many there are and the first 4.

## Why we need it
- **Saving to `.txt`** lets us check the result with our own eyes.
- **Metadata** travels with the text into every chunk. Later, the bot uses it to cite the source: *"Article 29, UAE Labour Law"*.
- **Finding the headings** prepares Step 3. We want to cut the text into **one chunk per article**, so we must know exactly how a heading looks.

## Small example
The regex `^Article\b.*$` means: "a line that starts with the word Article, and the rest of that line".

```
Article (29)                   -> match
Annual Leave                   -> no match
the Article above applies      -> no match (does not start with "Article")
```

## What we found (important for Step 3)

| File | Heading lines | Format |
|---|---|---|
| labour_law.pdf | 76 | `Article (1)`, then **`Article )2 (`**, `Article )3 (` … |
| exec_regs.pdf | 40 | `Article (1)`, `Article (2)` … |
| labour_law_amendment_2022.pdf | 3 | `Article (1)` … |
| pdpl.pdf | 31 | `Article (1)`, `Article (2)` … |

In the Labour Law, most brackets are **reversed**: `)2 (` instead of `(2)`. This often happens when a PDF was made from a right-to-left (Arabic) layout. Our article splitter in Step 3 must accept both forms.
