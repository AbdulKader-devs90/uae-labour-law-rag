# Step 8 — Evaluation and failure analysis

## Set-up
- **Gold set:** 15 questions (10 normal, 5 edge cases). Every reference answer was checked by hand against the law text before scoring.
- **3 versions:**

| Version | Chunks | Search | Re-rank + cut-off | Query rewrite | Flow |
|---|---|---|---|---|---|
| A_naive | fixed 800 chars | dense only | no | no | function |
| B_hybrid | one per article | dense + BM25 (RRF) | yes | no | function |
| C_full | one per article | dense + BM25 (RRF) | yes | yes (dual re-rank) | LangGraph |

- **5 scores:** decision_correct, retrieval_hit, citation_hit (code); correctness, faithfulness (LLM judge, Qwen3-235B — a bigger model than the bot's Qwen3-30B).
- Run with LangSmith `evaluate()`, one question at a time (`scripts/run_eval.py`).

## Results

| Version | Decision | Retrieval hit | Citation hit | Correctness | Faithfulness | Avg time |
|---|---|---|---|---|---|---|
| A_naive | 0.93 | 0.77 | 0.77 | 0.80 | 0.80 | 1.15 s |
| B_hybrid | 0.93 | 0.85 | 0.85 | 0.80 | 0.93 | 1.17 s |
| **C_full** | **1.00** | **0.92** | **0.92** | **1.00** | **0.93** | 1.97 s |

One-liner target: ≥ 90 % faithfulness, < 8 s → **C_full: 93 %, ~2 s ✅**

## Failure analysis — question by question

### A_naive (fixed chunks, dense only)
| Question | What went wrong | Root cause |
|---|---|---|
| What does Article 51 say? | **Refused** a covered question. Top chunks: Labour Law Art. 65, PDPL Art. 23, PDPL preamble | Embeddings do not understand numbers; fixed chunks have no `[Labour Law — Article 51]` header to match |
| How much notice…? | Mixed Art. 43 with Art. 65 (old indefinite contracts) and Art. 9 (probation); wrong overall rule (correctness 0) | Fixed chunks mix several articles; the model blends them |
| Carry forward annual leave? | Missed the Executive Regulation's "max half" rule (correctness 0) | Regulation Art. 19 never retrieved — dense-only search found only Labour Law Art. 29 |
| What did the 2022 amendment change? | Cited the **Preamble**; added a claim not in the text ("previous wording allowed indefinite contracts") — faithfulness 0 | Fixed chunks of the amendment start with the title/preamble; no article label |
| Tell me about leave | Claimed "termination during leave is not allowed" citing a source that did not exist ([S5] with 4 sources) — faithfulness 0 | Hallucinated citation |
| Salary not paid | Linked non-payment to Art. 47 compensation (Art. 47 is about unlawful dismissal) — faithfulness 0 | Wrong article retrieved, model "connected the dots" |
| How long is maternity leave? | Correct answer, but cited **Article 29** | A fixed chunk is labelled with the article it *starts* in; it started in Art. 29 and contained Art. 30 → **wrong citation from wrong metadata** |

### B_hybrid (article chunks, hybrid, re-rank, cut-off — no rewrite)
| Question | What went wrong | Root cause |
|---|---|---|
| Can my employer keep my passport? | **Refused** (top score 0.002) | Vocabulary gap: "passport" vs "official documents" |
| Tell me about leave | Listed only mourning/parental/study/unpaid leave — no annual, sick, maternity (correctness 0) | Vague question; nothing pulls the main leave articles |
| Salary not paid | Answered from Art. 9 (probation) with invented claims — correctness 0, faithfulness 0 | Vocabulary gap ("salary" vs "wage"); right article never found |

Everything else correct. Faithfulness jumps 0.80 → 0.93 because each chunk is one clean article with its label.

### C_full (B + query rewrite + LangGraph)
| Question | Observation | Verdict |
|---|---|---|
| Passport | Rewritten "Can an employer retain a worker's official documents?" → Art. 13 ✅ | Fixed by rewrite |
| Tell me about leave | Rewritten "Entitlement to annual leave…" → good answer on annual leave + Regulation detail (correctness 1) | Better, but narrowed to annual leave only |
| Salary not paid | Retrieved **Executive Regulation Art. 16 "Wages"** ("pay on due dates… through the Wage Protection System"; Ministry may take legal measures) — a correct, grounded answer. retrieval_hit = 0 only because the gold set listed Labour Law Art. 22/45 | **Gold-set gap**: Regulation Art. 16 implements Labour Law Art. 22. Found by reading the outputs |
| Carry forward annual leave | Correct "max half" rule, but added "**unless agreed upon in writing**" — not in the sources → faithfulness 0 | Small hallucination (invented condition) |
| How long is maternity leave? | Rewriter changed the topic to "**annual** leave"! Still answered correctly (Art. 30) | **Dual re-ranking safety net worked**: the original question kept Art. 30 on top |
| IRS 401k limit | Rewriter turned it into a UAE pension question | Still refused (score below cut-off) — cut-off saved it |
| What does Article 51 say? | Rewriter added "regarding termination of employment" (invented topic) | Safety net kept Art. 51; correct answer |

## Lessons
1. **Structure-aware chunking is the biggest single win** (faithfulness 0.80 → 0.93). Fixed chunks cause wrong citations, mixed rules and missed regulation details.
2. **Query rewriting fixes vocabulary gaps** (passport, salary) but is **unreliable on its own**: it changed maternity → annual leave and invented topics. Keeping the original question in retrieval and re-ranking (dual re-rank) makes it safe.
3. **Refusal design works**: both trap questions refused in all versions; C never refused a covered question.
4. **LLM judges are imperfect**: in A, the salary answer got correctness 1 although it cited the wrong article for the wrong reason; faithfulness caught it. Use several metrics, read the outputs.
5. **The gold set needs review too**: the "failed" retrieval in C was a correct answer from a better article (Regulation Art. 16) that the gold set did not list.
6. 15 questions = ~7 points per question → results are directional, not statistically strong.

## Remaining weaknesses / next steps
- Rewriter can change the topic → add "do not change the topic" rule (done in v2) or skip rewriting for already-clear questions.
- Small invented conditions ("in writing") → stricter faithfulness check node (re-generate if the judge finds an unsupported claim).
- Vague questions → ask a clarifying question instead of guessing.
- Bigger gold set (50+ questions) for reliable numbers.

## Iteration v2 and repeat runs (noise check)

**Change:** rewrite prompt v2 ("do not change the topic", "never turn maternity leave into annual leave", "change as little as possible") + gold-set fix (salary question also accepts Exec. Regulation Art. 16).

| C_full | Runs | Decision | Retrieval | Citation | Correctness | Faithfulness | Time |
|---|---|---|---|---|---|---|---|
| v1 | 1 | 1.00 | 0.92 | 0.92 | 1.00 | 0.93 | 1.97 s |
| v2 | 1 | 1.00 | 0.92 | 0.92 | 0.93 | 0.87 | 1.76 s |
| v2 | 3 (avg) | 1.00 | 0.92 | 0.92 | 0.96 | 0.87 | ~1.9 s |
| **v1 (final)** | **3 (avg)** | **1.00** | **1.00** | **1.00** | **1.00** | **0.93** | ~1.9 s |

**What changed between v1 and v2 — only one question:** the salary question.
- v1 rewrite → found Exec. Regulation Art. 16 (Wages) → correct, grounded answer.
- v2 rewrite ("...non-payment of wage by an employer...") → found Art. 39/9/47/40 → wrong, ungrounded answer.
- The rewrite wording differs from run to run, so this hard question passes in some runs and fails in others → **unstable, not a prompt regression**.

**The v2 prompt rules were ignored by the small model:** "maternity leave" was still rewritten as "annual leave", "Article 51" still got "regarding termination", and the IRS question still became a pension question — although the prompt now says exactly not to do that. Likely cause: the example "vacation → annual leave" in the same prompt primes the model. Lesson: **a small model follows examples more than negative instructions**; the dual re-rank safety net, not the prompt, is what keeps these answers correct.

**Stable faithfulness failure (every run):** carry-forward answer adds "unless agreed upon in writing" (not in the law).

**Decision:** v1 rewrite prompt is final. Over 3 runs it found the right article for the salary question every time (retrieval 1.00 with the corrected gold set), while v2 missed it every time (0.92). The extra v2 rules had no effect on the rewrites they targeted, so they were removed.

**Honest conclusion for the report (final, v1 × 3 runs):**
- All 15 questions: correct decision, right article retrieved and cited, correct answer.
- Faithfulness **93 %** (target ≥ 90 % ✅), stable across 3 runs. The one failure is the same every time: the carry-forward answer adds "unless agreed upon in writing".
- Avg ~1.9 s per question (target < 8 s ✅).

**Earlier draft conclusion (before the v1 × 3 run):**
- Faithfulness target (≥ 90 %) is met on a single run (93 %) but **not reliably**: 87 % over 3 runs. The 2 remaining failures are one stable invented condition and one unstable hard question.
- One run of 15 questions cannot separate a real improvement from noise; repeat runs (`num_repetitions=3`) are needed.
- Next fixes (not done): a faithfulness-check node that regenerates when a claim is unsupported; rewrite with a bigger model or without the priming example; skip rewriting for already-clear questions.

## Iteration v3 — guards from live UI testing (18 questions × 3 runs)

**Why:** live testing found failures the 15-question set missed: a near-scope question ("How can I get a golden visa?") answered with outside knowledge, and a leading question ("What is my *ideal* notice period?").

**Changes (src/graph.py, strict mode):**
1. Weak evidence (top score < 0.5) → stricter prompt: answer only if the sources directly answer the question, else NOT_FOUND.
2. Rule 9: every factual sentence needs a tag; never add facts (fees, authorities, eligibility) not in the sources. Plus a sentence-level check: an untagged long sentence with < 60 % word overlap with the sources triggers one retry, then is removed.
3. Rule 10: do not adopt an assumption the sources do not support.

**Test set:** 15 original + 3 new (golden visa → refuse, investor licence → refuse, ideal notice → Art. 43 without an "ideal").

| 18 questions, 3 runs | Decision | Retrieval | Citation | Correctness | Faithfulness | Avg s |
|---|---|---|---|---|---|---|
| C v1 | 0.94 | 0.93 | 0.93 | 0.93 | 0.83 | 2.12 |
| **C v3** | 0.93 | 0.93 | 0.93 | 0.89 | **0.91** | 2.12 |

**Per question:**
- **Carry-forward annual leave — fixed.** v1 added the invented condition "unless agreed in writing" in 3/3 runs (faithfulness 0); v3 in 0/3 runs (faithfulness 1.0). Rule 9 did this.
- **Golden visa — leak removed, but still not refused.** v1 added outside knowledge ("high-net-worth individual, skilled professional, investor") in 2/3 runs; v3 in 0/3. But v3 still answers, circularly ("to get a golden visa you must hold golden residency", from Exec. Reg. Art. 6 on work permits). The weak-evidence note did not make the model reply NOT_FOUND. Still scored 0 (gold = refuse).
- **Ideal notice period — a retrieval failure, not a generation failure.** The rewriter keeps "ideal … private sector" and only Labour Law Art. 1 (Definitions) is retrieved (top score 0.23); **Art. 43 is never retrieved**, so no prompt rule can fix it. v1 and v3 both say "typically 30 days" (wrong); v3 once refused. The same question without the word "ideal" retrieves Art. 43 perfectly.
- **Investor licence** — refused by the score gate in both versions ✅.
- The sentence-level remover never had to remove anything (removed = [] in all 54 runs): the prompt rule plus the retry was enough.

**Decision:** keep v3. It meets the faithfulness target on the larger set (0.91 vs 0.83) and stops outside knowledge leaking into answers. The correctness drop (0.93 → 0.89) is one question (ideal notice), whose root cause is retrieval.

**Remaining known limitations:** near-scope topics that share words with an article (golden residency) still get a narrow, circular answer; leading words ("ideal", "best") can derail retrieval. Next fixes: strip opinion words in the rewrite step; an LLM relevance check ("does this source answer *this* question?") before generating.
