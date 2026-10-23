# Cell 4.2 — What an embedding is

## What this code does
- It loads the embedding model `BAAI/bge-small-en-v1.5`. It runs on the Mac, free, no API key.
- It turns 3 sentences into **vectors** (lists of numbers) and compares them.
- `normalize_embeddings=True` makes every vector length 1. Then a simple dot product (`@`) gives the **cosine similarity**: 1.0 = same meaning, near 0 = unrelated.

## Why we need it
- An embedding puts the **meaning** of a text into numbers. Texts with similar meaning get similar numbers, even with different words.
- This is the base of "meaning search" (dense retrieval).

## Small example (our result)
```
Each text becomes 384 numbers
question vs leave rule : 0.703   <- "annual leave / employee" vs "paid vacation / worker": different words, same meaning
question vs data breach: 0.444   <- different topic
```
The first pair shares almost no words, but the model still sees they are close.
