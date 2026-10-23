# Cell 4.3 — Store the vectors in Chroma

## What this code does
- It deletes the old Chroma folder, so there are no old or duplicate vectors.
- For each chunk version (article, fixed), it embeds every chunk and stores the vector + text + metadata in a Chroma **collection**.
- It uses the `chunk_id` as the ID, and **cosine** distance.
- The data is saved in `data/chroma/`, so we can reuse it without embedding again.

## Why we need it
- Embedding is the slow part. We do it **once** at indexing time, not for every question.
- At question time, only the question is embedded (fast), and Chroma finds the nearest stored vectors.
- Two collections (`uae_article`, `uae_fixed`) let us compare both chunk versions with the same search.

## Small example
```
article  stored 204 vectors
fixed    stored 262 vectors
```
Think of Chroma as a table: `chunk_id | vector (384 numbers) | text | metadata`, plus a fast "find nearest vectors" function.
