# Qanoon — UAE Labour Law RAG Assistant

A RAG assistant that answers UAE labour-law and personal-data questions from the official text of four UAE laws, with article-level citations.

**Project report:** [docs/PROJECT_REPORT.md](docs/PROJECT_REPORT.md) ([PDF](docs/PROJECT_REPORT.pdf)) · **Demo video:** [Loom](https://www.loom.com/share/e35ced4d508c4193853a76a896e4425c)

## Screenshots

![Annual leave answer with article-level sources](docs/screenshots/02_answer_annual_leave.jpg)

![Out-of-scope Golden Visa question routed to ICP](docs/screenshots/09_refusal_routed_icp.jpg)

## What it covers

- UAE Labour Law — Federal Decree-Law No. 33 of 2021.
- Executive Regulation — Cabinet Resolution No. 1 of 2022.
- Labour Law Amendment — Federal Decree-Law No. 14 of 2022.
- Personal Data Protection Law (PDPL) — Federal Decree-Law No. 45 of 2021.

Explains the law; not legal advice. Answers depend on the downloaded corpus, which is not automatically updated. Check the official text and cited article for your situation.

## Architecture

Indexing: **load PDFs → clean text → chunk by article → embed → Chroma + BM25**. Chroma stores local dense embeddings; BM25 is built from the article chunks at startup. Dense and keyword results are fused with reciprocal rank fusion (RRF), then re-ranked with FlashRank.

LangGraph: **rewrite → retrieve → evidence gate → generate → finalize/refuse**. A weak retrieval match is refused before generation. Generated answers are checked for citations, with a generation retry where needed. The UI groups parts of the same article and links citation tags to source cards.

![LangGraph pipeline](graph.png)

Models are cached once. Initialization and graph calls use one dedicated worker thread to keep the macOS Torch/ONNX runtime stable.

## Tech stack

| Component | Role |
| --- | --- |
| LangChain | Documents, model clients and retrieval integrations |
| LangGraph | Rewrite, retrieval, evidence gate and answer flow |
| LangSmith | Traces, feedback and evaluation |
| Chroma | Local vector index |
| BM25 + RRF | Keyword search and hybrid rank fusion |
| FlashRank | Local cross-encoder re-ranking |
| BAAI/bge-small-en-v1.5 | Local English embeddings |
| Nebius Qwen3 | OpenAI-compatible answer, rewrite and judge models; configurable in `.env` |
| Streamlit | Chat, sources, pipeline inspector and evaluation UI |

## Results

Source: [data/eval/final_summary.csv](data/eval/final_summary.csv), evaluated on 15 questions. Values below reproduce the stored aggregate.

| Version | Runs | Decision correct | Retrieval hit | Citation hit | Correctness | Faithfulness | Avg seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A_naive | 1 | 0.93 | 0.77 | 0.77 | 0.80 | 0.80 | 1.15 |
| B_hybrid | 1 | 0.93 | 0.85 | 0.85 | 0.80 | 0.93 | 1.17 |
| C_full | 1 | 1.00 | 0.92 | 0.92 | 1.00 | 0.93 | 1.97 |
| C_full_final_x3 | 3 | 1.00 | 1.00 | 1.00 | 1.00 | 0.93 | 1.90 |

A used fixed chunks and dense search. B added article chunks, hybrid search, re-ranking and a confidence cut-off. C added query rewriting and LangGraph orchestration. C final uses the corrected gold set and averages three runs. Retrieval and citation metrics apply to questions with expected articles; missing evaluations are excluded from their means. These results describe this small evaluation set.

### v3: guards found in live testing (18 questions × 3 runs)

Live testing found a near-scope question (golden visa) answered with outside knowledge and an invented condition ("unless agreed in writing"). v3 (`ask(question, strict=True)`, the default) adds a stricter prompt under weak evidence, rules against untagged facts and adopted assumptions, and a sentence-level citation check. Three questions were added to the test set.

| Version | Runs | Decision correct | Retrieval hit | Citation hit | Correctness | Faithfulness | Avg seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| C v1 (no guards) | 3 | 0.94 | 0.93 | 0.93 | 0.93 | 0.83 | 2.12 |
| C v3 (final) | 3 | 0.93 | 0.93 | 0.93 | 0.89 | 0.91 | 2.12 |

Source: [data/eval/d18_x3_C_full.csv](data/eval/d18_x3_C_full.csv) and [data/eval/d18_x3_C_v3.csv](data/eval/d18_x3_C_v3.csv). Analysis in the [project report](docs/PROJECT_REPORT.md).

## Setup

Use Python 3.12. From the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your provider credentials and model IDs. For Nebius, choose available Qwen3 model IDs for `NEBIUS_MODEL` and `JUDGE_MODEL`. Groq is supported through `LLM_PROVIDER=groq`. Enable LangSmith tracing only after configuring its API key and project. Evaluation requires a LangSmith account, the dataset named in `src/evaluation.py`, and a configured judge model; API usage may incur charges.

Download the four English PDFs from the official UAE Legislation portal into `data/raw/`, using these exact filenames:

| Law | Filename | Official PDF |
| --- | --- | --- |
| Labour Law 33/2021 | `labour_law.pdf` | [Download — 1541](https://uaelegislation.gov.ae/en/legislations/1541/download) |
| Executive Regulation 1/2022 | `exec_regs.pdf` | [Download — 1547](https://uaelegislation.gov.ae/en/legislations/1547/download) |
| Amendment 14/2022 | `labour_law_amendment_2022.pdf` | [Download — 1637](https://uaelegislation.gov.ae/en/legislations/1637/download) |
| PDPL 45/2021 | `pdpl.pdf` | [Download — 1972](https://uaelegislation.gov.ae/en/legislations/1972/download) |

Launch `jupyter lab`, select the `.venv` Python kernel and run all cells in notebooks **02 → 03 → 04**, in order, with the notebook working directory set to `notebooks/`:

1. `02_load_and_clean.ipynb` creates cleaned law text.
2. `03_chunking.ipynb` creates article and fixed chunks.
3. `04_retrieval.ipynb` builds the Chroma index and checks dense, keyword and hybrid retrieval.

The cleaned text and chunks are included in the repo, so you can skip notebooks 02–03 and only run notebook 04 to build the local Chroma index.

The first model load downloads embeddings and the FlashRank model. Later starts reuse local model files. Local indexes, downloaded re-ranker models and credentials are ignored by Git.

## Run the app

```bash
source .venv/bin/activate
streamlit run app/app.py
```

Open the local URL printed by Streamlit. The app shows a loading message while legal models warm up (about 10 seconds), then offers example questions. The sidebar includes appearance settings and a Markdown conversation download.

## Run the evaluation

```bash
python scripts/run_eval.py
```

This runs A, B and C sequentially and writes experiment CSVs plus `data/eval/summary.csv`. To run just C, use `python scripts/run_eval.py C_full`. See notebook `08_evaluation.ipynb` for dataset setup. The app reads the curated `final_summary.csv`; evaluation runs do not overwrite that file.

Offline UI checks:

```bash
python -m unittest discover -s tests -v
```

## Folder structure

```text
app/                  Streamlit app, presentation helpers and CSS
src/                  Retrieval, rewrite, graph, LLM and evaluation logic
scripts/              Terminal evaluation runner
notebooks/            Step-by-step corpus building and experiments
data/
  raw/                Four source PDFs
  clean/              Cleaned law text
  chunks/             Article and fixed chunks
  chroma/             Local vector index (ignored)
  models/             Local re-ranker files (ignored)
  eval/               Evaluation summaries and versioned results
  notes/              Step-by-step learning notes
docs/
  PROJECT_REPORT.md   Project report (also as PDF)
  screenshots/        App screenshots
.streamlit/           Streamlit theme configuration
tests/                Offline UI regressions and opt-in live smoke checks
```

## Known limitations

- Near-scope questions that share words with an article (e.g. "How can I get a golden visa?") can still get a narrow, circular answer from a related article instead of a refusal. v3 stops outside knowledge leaking in, but does not refuse these yet.
- Leading words ("ideal", "best") can derail retrieval: "What is my ideal notice period?" never retrieves Article 43. Planned fix: strip opinion words in the rewrite step and add an LLM relevance check before generating.
- The evaluation set is small (18 questions), so scores are directional.
- English text only; the corpus is a snapshot and not updated automatically.

## Learnings

See [LEARNINGS.md](LEARNINGS.md) and the detailed notes in [data/notes/](data/notes/).

## Course note

Week 2 project — Mastering Agentic AI (The Gen Academy).
