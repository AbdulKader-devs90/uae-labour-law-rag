# Cell 5.1 — Import the retrieval module

## What this code does
- `sys.path.insert(0, "..")` lets the notebook find the `src/` folder.
- It imports the search functions from `src/retrieval.py`.

## Why we need it
- Steps 5, 6, 7 and the app all need the same search code. One module = one place to change it.
- This is the normal path: **experiment in a notebook → move working code into a module → reuse it.**
- The module opens Chroma **from disk**, so nothing is embedded again.

## Small example
```python
from src.retrieval import retrieve
retrieve("How many days of annual leave do I get?", top_n=1)
# [(Document(labour_law:29 ...), 0.987)]
```
