# Cell 4.5 — Keyword search (BM25)

## What this code does
- It builds a **BM25** index for each chunk version. BM25 scores a chunk higher when it contains the question's words, and gives **rare** words more weight than common words.
- Our own `tokenize` function makes all text lowercase and splits on anything that is not a letter or digit.

## Why we need it
- Meaning search is weak with **exact** terms: article numbers, names, codes.
- BM25 is very good at them.
- Without our tokenizer, `Leave,` and `leave` (or `Article` and `article`) are different words to BM25.

## Small example (our result for "Article 51 gratuity")
```
labour_law:51   End-of-Service Gratuity (part 2)
labour_law:51   End-of-Service Gratuity (part 1)
labour_law:52   End-of-Service Gratuity for Workers ...
```
BM25 matched "51" and "gratuity" exactly. The chunk header `[Labour Law — Article 51]` from Step 3 helps here.

(The DeprecationWarning means `BM25Retriever` will move to another package later. It works today.)
