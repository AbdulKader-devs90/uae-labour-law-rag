# Cell 3.5 — Compare chunk sizes in tokens

## What this code does
- It loads the **tokenizer** of our embedding model (`BAAI/bge-small-en-v1.5`).
- It counts the tokens in every chunk, and prints the average, minimum, maximum, and how many chunks are over 512 tokens.

## Why we need it
- Models do not count characters. They count **tokens** (word pieces).
- The embedding model reads **max 512 tokens**. If a chunk is longer, the end is cut off without any error. Search then cannot "see" that part.
- The handout tip: *"Pick chunk size and the embedding model together."* This cell proves that our chunks fit the model.

## Small example
```
"Annual leave"       -> ["annual", "leave"]                 = 2 tokens
"remuneration"       -> ["rem", "##uner", "##ation"]        = 3 tokens
Rule of thumb: 1 token ≈ 4 characters of English.
```

## Our result
| Version | Chunks | Avg tokens | Min | Max | Over 512 |
|---|---|---|---|---|---|
| Article | 204 | 187 | 28 | 345 | 0 |
| Fixed | 262 | 149 | 49 | 182 | 0 |

Both fit the model. Article chunks are bigger on average and vary more (a short article is small, a long one is split at 1,500 chars).

(The "HF_TOKEN" and "TqdmWarning" messages are harmless warnings.)
