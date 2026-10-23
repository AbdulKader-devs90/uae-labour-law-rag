# UAE Labour Law RAG Bot — Learnings Log

Running log of what we learned while building the Week 2 RAG project.
Used at the end for: (1) the "Learnings & observations" section of the Google Doc, (2) a LinkedIn post.

---

## Design decisions (and why)

| Decision | Chosen | Instead of | Why |
|---|---|---|---|
| Use case | UAE Labour Law Q&A (real public laws) | Solution-kit mock data (ACME) | Real corpus in my own domain; article structure enables citations; avoids copying the kit |
| Framework | LangChain (building blocks) + LangGraph (flow) | — | Matches the course; LangGraph allows branches (answer vs. refuse) |
| Observability | LangSmith | print() debugging | Traces every step, latency, tokens; runs dataset evals for the 15-question report |
| Vector store | Chroma (local) | Pinecone (cloud) | Small corpus; fast rebuilds for chunking comparisons; no network/index setup; same LangChain interface, so swapping is ~3 lines |
| LLM provider | Nebius Token Factory (course credits) | — | OpenAI-compatible API → provider is just a URL + key; open models |
| Generation model | Qwen3-30B-A3B-Instruct | Reasoning models (R1, gpt-oss) | "Instruct" answers directly; MoE (3B active) = fast and cheap; reasoning models add slow, verbose thinking text |
| Judge model (Step 8) | Bigger model (Qwen3-235B-Instruct) | Same model as generator | A model grading itself tends to be too generous |
| Embeddings / re-ranker | Local (bge-small, FlashRank) | API embeddings | Free, offline; LLM API only where language ability is needed |
| Python version | 3.12 | Newest (3.14/3.15) | ML libraries (torch, onnxruntime, chromadb) need time to support new Python; pick 1–2 versions behind latest |

---

## Step 1 — Setup

- Separate **code** (venv), **secrets** (`.env`, git-ignored) and **monitoring** (LangSmith).
- The model is just a setting: `get_llm()` + `LLM_PROVIDER` in `.env` switches providers with no code change.
- Pick the model by asking the API (`client.models.list()`) instead of guessing names from websites.
- LangSmith tracing needs **zero code**: 3 env vars and LangChain sends traces automatically. Failed calls are traced too (useful for debugging).

### Gotchas we hit (good "real-world" notes)
1. **`load_dotenv()` does not overwrite** values already loaded → after editing `.env`, old values stayed. Fix: `load_dotenv(find_dotenv(), override=True)` + restart the kernel.
2. **`NAME=NAME=value` in `.env`** → model name sent as `"NEBIUS_MODEL=Qwen/..."` → 404 Not Found. Found in one step by printing `repr(value)`. Lesson: check what goes *in* before blaming what comes *out*.
3. **LangSmith has separate US and EU regions.** Key created in US, but I was looking at the EU site → "no traces". Key, endpoint and website must be the same region (EU needs `LANGSMITH_ENDPOINT`).
4. Nebius renamed "AI Studio" → **Token Factory**; base URL `https://api.tokenfactory.nebius.com/v1/`. Old tutorials point to old pages.
5. LangSmith key type: **Personal Access Token**, not "Tracing Only" (write-only keys cannot create datasets/run evals later).

---

## Step 2 — Load & clean
- **Check the corpus before you code.** One "official" download link gave a different law than expected (Decree-Law 14/2022, an *amendment* to the Labour Law, not the Executive Regulations). Always open the source and confirm what it is.
- Amendments are a real-world corpus problem: the same article can exist in an old and a new version. Track this in metadata so answers use the current rule.
- Rename source files to short, stable names (no spaces/brackets) — they become IDs in code, metadata and citations.
- `PyPDFLoader` "ValueError" = file not found (wrong name/path). Print the folder contents first.
- **Headers can hide page numbers**: the header line ended with the page number ("...Labor Relations 1", "...2"), so exact-repeat detection missed it. Fix: strip trailing numbers before comparing lines. Removed ~6% noise.
- **Corpus spelling ≠ user spelling**: law says "Labor", users type "Labour". BM25 misses this, embeddings don't → argument for hybrid search.
- **Reversed brackets** in the Labour Law headings: `Article )2 (` instead of `Article (2)` (artifact of right-to-left PDF layout). The article splitter must accept both.
- Joined all pages into one text per law, because articles cross page boundaries.
- LangChain DeprecationWarning on `langchain_community` loaders is harmless today but signals the package will move.

## Step 3 — Chunking
- **Chunk by structure** (one chunk per article) instead of fixed size: one topic per chunk, rules not cut in half, citations come for free from metadata.
- **Contextual chunk header** (`[Labour Law — Article 29]`) added to the chunk text, so embeddings and BM25 know which law a chunk belongs to (Article 29 exists in several laws).
- Long articles are sub-split (1,500 chars, 150 overlap) because the embedding model reads max 512 tokens; longer text is silently cut.
- **Parsing lessons (3 iterations):**
  1. Strict "next number only" rule: one missing heading (PDPL Article 21) made everything after it rejected → one bad heading broke the whole document.
  2. A *mention* ("Article (5) of the Decree-Law...") was accepted as a heading, so the real Article 5 was rejected. Fix: a real heading stands **alone on its line**; a mention continues on the same line.
  3. Allow small gaps and **report missing numbers** instead of failing silently. This exposed PDPL Article 21 written as `Article 21` (no brackets) → brackets made optional.
- A rule that is perfect for one document (Labour Law: 74/74) can fail on another. Check every document, not only the main one.
- **Measure in tokens, not characters**: checked with the embedding model's own tokenizer. Article chunks: 204, avg 187 tokens, max 345; fixed: 262, avg 149, max 182; none over the 512-token limit.
- **Side-by-side evidence**: the fixed chunk holding the rule ("thirty days" annual leave) lost its heading — "Article 29 / Annual leave" sat in the previous chunk, together with the end of Article 27 and all of Article 28. The article chunk kept heading + rule together.
- Fixed chunks still record the article they start in, so both versions can be scored the same way in Step 8.
## Step 4 — Embeddings + hybrid search
- Embeddings capture meaning, not words: "annual leave / employee" vs "paid vacation / worker" = 0.703; vs "data breach" = 0.444.
- Embed once at indexing time (Chroma persists to disk); only the question is embedded at query time.
- BM25 needs a proper tokenizer (lowercase, strip punctuation), otherwise "Leave," ≠ "leave".
- Wrote RRF (Reciprocal Rank Fusion) by hand (~10 lines): rank-based, so cosine and BM25 score scales don't need to match. Also avoids LangChain v1 package moves (EnsembleRetriever moved to langchain-classic).
- **Probe results (5 questions):**
  - "What does Article 51 say?" → dense returned 3 wrong laws; BM25 found Article 51 → **embeddings don't understand numbers**.
  - "Share my personal data" → BM25 returned PDPL Article 1 (Definitions) 3 times → **BM25 is fooled by keyword-dense chunks**.
  - Plain-language "salary not paid for two months" → all 3 methods returned wrong articles (Probation, Maternity Leave, Suspension of Work). The right one is Labour Law Art. 22 "Determining the Amount or Type of Wage and Paying It". **Vocabulary gap**: user says "salary/paid", law says "wage/paying". A re-ranker can't fix a chunk that was never retrieved → candidate fix: LLM query rewriting into legal terms.
  - **RRF is rank-only**: a chunk ranked #1 by only one method can still come first (amendment:1 for "Article 51"). → motivates a re-ranker (Step 5).
- Dense relevance scores sit close together (0.72–0.81 for top 5), so a raw similarity score is a weak "confidence" signal for refusing.
## Step 5 — Re-ranking + refusal
- Moved all search code into `src/retrieval.py` (notebook → module). Chroma is opened from disk, no re-embedding.
- **Bi-encoder vs cross-encoder**: embeddings encode question and chunk separately (fast, rough, searches everything); the re-ranker (FlashRank ms-marco-MiniLM-L-12-v2) reads them together (slow, precise, only top 10 candidates).
- Re-ranker fixed "What does Article 51 say?": hybrid had amendment:1 first → after re-rank labour_law:51 scores 0.872, wrong chunks ≤ 0.007.
- **A re-ranker can't rescue what search never found**: for the salary question, the right article (Labour Law Art. 22) ranked 15th (dense) and 35th (BM25) — outside the 10 candidates.
- Rewriting the salary question in the law's words ("wage", "non-payment of wages") moved Art. 22 into dense top 5 → evidence for a query-rewrite step.
- **Refusal cut-off from data**: out-of-scope questions (Golden Visa, IRS 401k, World Cup, Emirates ID) scored ≤ 0.001; in-scope 0.54–1.00. Large gap → cut-off ~0.10.
- **False refusal found**: "Can my employer keep my passport?" scored 0.002 although the Labour Law covers it ("official documents"). Same vocabulary gap → the cut-off alone would wrongly refuse. Another reason for query rewriting.
- **Query rewriting (LLM, LCEL chain `prompt | llm | parser`)**: passport → "retain the official documents of a worker" → Art. 13 Employer's Obligations scored 0.998 (was 0.002). Annual leave stayed correct, Golden Visa stayed refused (0.004).
- Salary question still misses Art. 22 even with 20 candidates per search ("NOT IN POOL") → kept 10 candidates, recorded as a **known hard case** instead of tuning the whole system for one question.
## Step 6 — Answer with citations
- Design: refuse BEFORE the LLM when top re-rank score < 0.10 (free, fast); numbered sources [S1]..[S4] in the prompt; model must tag every fact; code turns tags into readable citations; model can also reply NOT_FOUND (second refusal path).
- All answers 0.7–2.4 s (target < 8 s).
- **Over-strict model**: "What does Article 51 say?" was refused (NOT_FOUND) although Article 51 was retrieved with score 0.997. Fix: prompt rules "summarise an article when asked" and "if no law is named, use the law in the sources that has that article".
- **LangSmith debugging**: each `.invoke()` was a separate trace → one question was scattered over 4–6 traces. Fix: `@traceable` on `answer()` = one parent trace per question.
- **Side effect of query rewriting (found by re-running all tests)**: the rewriter added the full law title ("Federal Decree-Law No. 33 of 2021 concerning...") to the query. Chunks that only *mention* that title (Preambles, Amendment Art. 1, Regulation Art. 1) then scored 0.995–0.998 and pushed Article 51 out of the top 4 → wrong citation (Preamble), then a refusal.
  Fixes: (1) rewrite prompt: never add law names/numbers the user didn't write; (2) drop Preamble chunks (no rules in them); (3) re-rank every chunk against BOTH the original and the rewritten question and keep the best score, so a bad rewrite can't push out a chunk matching the user's own words.
- Lesson: **every fix can have a side effect**; only re-running all test questions (regression testing) reveals it.
- After the fixes all 6 test questions pass (1.5–2.7 s each); PDPL "share my data" improved from score 0.50 to 0.83 because of re-ranking against both questions.
- Design principle: **never let one LLM step have the final say on retrieval** — the rewriter can help or hurt, so the original question always stays in the loop.
- Remaining small issue: the rewriter sometimes invents a topic for short questions ("Article 51" → "...regarding termination"); the safety net absorbs it.
## Step 7 — LangGraph flow
- Function → graph: 5 nodes (rewrite, retrieve, generate, finalize, refuse), 2 conditional edges (evidence gate; draft check with NOT_FOUND → refuse and a one-time citation-retry loop).
- **State** = one TypedDict; each node returns only the fields it changes. Printing the final state shows exactly what each node did.
- LangGraph gives one LangSmith trace per question with every node as a child, so `@traceable` is no longer needed.
- Same 6/6 results as Step 6 (1.7–3.6 s); duplicate citations (Article 51 part 1 + part 2) removed in `finalize`.
- `graph.get_graph().draw_mermaid_png()` draws the flow — used in the doc and video.
## Step 8 — Evaluation
- Gold set: 15 questions (10 normal, 5 edge cases), every reference answer checked by hand against the law text before scoring.
- 3 versions × 5 evaluators (3 code: decision, retrieval hit, citation hit; 2 LLM judge with a bigger model: correctness, faithfulness), run with LangSmith `evaluate()`.
- **Kernel crash on macOS** with `max_concurrency=3`: torch + onnxruntime each load OpenMP; parallel threads crash the process with no Python error. Fix: `OMP_NUM_THREADS=1`, `KMP_DUPLICATE_LIB_OK=TRUE`, run from a terminal script with `max_concurrency=1`.
- **Results:**

| Version | Decision | Retrieval hit | Citation hit | Correctness | Faithfulness | Avg s |
|---|---|---|---|---|---|---|
| A naive (fixed chunks, dense) | 0.93 | 0.77 | 0.77 | 0.80 | 0.80 | 1.15 |
| B hybrid + re-rank + cut-off | 0.93 | 0.85 | 0.85 | 0.80 | 0.93 | 1.17 |
| C full (+ rewrite, LangGraph) | **1.00** | **0.92** | **0.92** | **1.00** | **0.93** | 1.97 |

- Each step adds value: article chunks + hybrid + re-rank lift faithfulness 0.80 → 0.93; rewriting + graph lifts correctness 0.80 → 1.00 and makes every answer/refuse decision right. Cost: +0.8 s per question (one extra LLM call), still far below the 8 s target.
- Caveat: 15 questions → one question = ~7 points. Directional, not statistically strong.
- **Failure analysis highlights** (full table in notes/step8_evaluation_and_failure_analysis.md):
  - A: fixed chunks gave a *wrong citation from wrong metadata* (maternity answer cited Art. 29 because the chunk started there), mixed rules across articles, refused "Article 51".
  - B: refused the passport question (vocabulary gap); narrow answer for "Tell me about leave".
  - C: rewriter changed "maternity leave" → "annual leave" and still answered right thanks to dual re-ranking; one small invented condition ("in writing"); salary answer was correct from Exec. Regulation Art. 16, which the gold set had missed.
  - LLM judge gave A's wrong salary answer correctness 1 — faithfulness caught it. Use several metrics and read outputs.
- Iteration after evaluation: rewrite prompt v2 ("do not change the topic") and gold set fix (add exec_regs:16, disclosed as a post-review correction).
- **v2 result**: single run correctness 0.93 / faithfulness 0.87 (v1: 1.00 / 0.93). Per-question diff: only the salary question changed — its rewrite varies between runs, so it passes or fails by chance. 3 repetitions: correctness 0.96, faithfulness 0.87.
- **Small models ignore negative instructions**: v2 said "never turn maternity leave into annual leave" — it still did (probably primed by the "vacation → annual leave" example). The dual re-rank safety net, not the prompt, kept the answer right.
- **Evaluation lesson**: one run of 15 questions can't separate improvement from noise → use repetitions. Faithfulness ≥ 90 % met on one run, not reliably (87 % over 3).
- **Final (v1 prompt, 3 runs)**: decision 1.00, retrieval 1.00, citation 1.00, correctness 1.00, faithfulness 0.93, ~1.9 s. v1 was stable on the salary question in all 3 runs; v2 failed it in all 3 → v1 kept. Target ≥ 90 % faithfulness and < 8 s met reliably.
- **My mistake**: `upload_dataset()` deleted and re-created the dataset, which deleted all earlier experiments in LangSmith. Results were recovered from saved CSVs; function now only creates the dataset if missing. Lesson: never make a setup step destructive by default.
## Step 9 — UI
- Built with Codex in VS Code from a project-context file (CLAUDE.md / AGENTS.md) + 4 staged prompts; rule: never change the evaluated `src/` pipeline. Prompt 1 → `app/backend.py` (+112 lines, streams graph node updates) and `app/app.py` (+60), `src/` unchanged.
- **New failure type found while testing the UI — leading question**: "What is my *ideal* notice period?" → model said "the ideal notice period is 30 days" and misstated the waiver rule. Retrieval was right (Art. 43: 30–90 days as agreed); generation accepted the question's false assumption. Next step: prompt rule "if the question assumes something the law does not say, say so"; add leading questions to the test set.
- **Near-scope questions leak outside knowledge** (found in live UI testing, missed by the 15-question set):
  - "How can I get a golden visa?" passed the 0.10 cut-off because Exec. Regulation Art. 6 mentions a "Work Permit for Holders of Golden Residency". Sentence 1 was cited (and circular); sentences 2–3 ("investment, professional qualifications…") had **no [S#] tag** = outside knowledge. `finalize` accepts an answer if *at least one* tag exists, so untagged sentences slip through.
  - Notice-period question (re-asked): cited Labour Law Art. 1 (Definitions) while the text says "as stated in Article 43" — Art. 43 was not in the sources → citation/answer mismatch, confidence Low.
  - The eval set only had clearly out-of-scope traps ("Golden Visa *fee*", "IRS 401k") → all refused. Lesson: **test near-scope questions** (topics that share words with the corpus) and leading questions, not only obvious ones.
  - Fix ideas: sentence-level citation check (drop or regenerate untagged factual sentences); raise the cut-off or warn on Low confidence; faithfulness-check node.
- **Domain knowledge beats a generic refusal**: the refusal card sent a Golden Visa question to MOHRE, but residency/visas belong to ICP (federal) or GDRFA (Dubai); MOHRE handles work permits, labour contracts and establishment matters. Fix (UI only): route the refusal by topic keywords to the right authority, with u.ae as fallback.
- **Browser test of the UI (Claude in Chrome)**: 10 checks passed (start screen, answer + chips, sidebar, pipeline inspector, 👍 → LangSmith user_rating on the exact run, low-confidence warning, work-permit answer from Exec. Reg. Art. 7, refusal routed to ICP/GDRFA, evaluation tab). Bug found: the sidebar's open button has zero size (hidden by the custom CSS) → users can't open the sidebar. Golden-visa answer again had an untagged first sentence and wrongly named MOHRE as the visa authority → confirms the need for the v3 sentence-level citation check.
- "Confidence: Medium" on a correct gratuity answer: confidence = how well the question wording matched the article (re-rank score), not whether the answer is right.
## Step 10 — Submission
