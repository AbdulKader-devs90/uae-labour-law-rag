# Cell 4.1 — Load the chunks

## What this code does
- It reads the two JSONL files from Step 3 and turns each line back into a LangChain `Document`.
- `CHUNKS["article"]` = 204 article chunks, `CHUNKS["fixed"]` = 262 fixed chunks.
- `load_dotenv(..., override=True)` loads the keys, so LangSmith tracing stays on.

## Why we need it
Step 4 starts from the saved chunks. We do not run Steps 2 and 3 again.

## Small example
```
article  204 chunks
fixed    262 chunks
```
