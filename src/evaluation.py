"""
Evaluation for the UAE Labour Law RAG bot (Step 8), run with LangSmith.

  - DATASET: 15 test questions (10 normal, 5 edge cases) with reference answers
    and the article(s) that should be found.
  - 3 pipeline versions to compare:
        A_naive     fixed-size chunks, dense search only, no re-rank, no rewrite
        B_hybrid    article chunks, hybrid search + re-rank + cut-off, no rewrite
        C_full      the LangGraph flow (rewrite + hybrid + re-rank + cut-off + citation check)
  - 5 evaluators:
        decision_correct   (code)  answered when it should, refused when it should
        retrieval_hit      (code)  an expected article was among the sources sent to the LLM
        citation_hit       (code)  an expected article is in the final citations
        correctness        (LLM)   answer agrees with the reference answer
        faithfulness       (LLM)   every claim is supported by the retrieved sources
"""
import os
import re

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langsmith import Client

from src.graph import CUTOFF, REFUSAL, TOP_N, answer_chain, ask, cite, format_context
from src.llm import get_llm
from src.retrieval import dense_search, hybrid_search, label, rerank

DATASET_NAME = "uae-labour-rag-eval-15"

# ── 1. The 15 test questions ───────────────────────────────────────────────
# expected: article labels that count as "found" ("source:article"). Empty = out of scope.
# Check every reference against the law text (notebook cell 8.1) before running.
DATASET = [
    # ---- normal questions (10)
    {"q": "How many days of annual leave do I get?", "cat": "direct",
     "expected": ["labour_law:29"],
     "ref": "30 days of paid annual leave per year after one year of service; 2 days per month if service is more than 6 months but less than 1 year."},
    {"q": "Can I carry forward my unused annual leave to next year?", "cat": "multi-doc",
     "expected": ["exec_regs:19", "labour_law:29"],
     "ref": "Yes. The worker may carry forward up to half of the annual leave into the following year, or agree with the employer to receive its cash equivalent; on termination the balance is paid in cash."},
    {"q": "How long is maternity leave?", "cat": "direct",
     "expected": ["labour_law:30"],
     "ref": "60 days of maternity leave: 45 days with full pay and 15 days with half pay."},
    {"q": "How many sick leave days am I entitled to, and are they paid?", "cat": "direct",
     "expected": ["labour_law:31"],
     "ref": "Up to 90 days per year after probation: the first 15 days with full pay, the next 30 days with half pay, and the remaining days unpaid."},
    {"q": "What is the maximum probation period?", "cat": "direct",
     "expected": ["labour_law:9"],
     "ref": "The probation period may not exceed 6 months."},
    {"q": "How much notice must be given to end an employment contract?", "cat": "direct",
     "expected": ["labour_law:43"],
     "ref": "Written notice of at least 30 days and not more than 90 days, as agreed in the contract."},
    {"q": "What does Article 51 say?", "cat": "exact-number",
     "expected": ["labour_law:51"],
     "ref": "Article 51 sets the end-of-service gratuity: for foreign full-time workers with 1+ year of service, 21 days' basic wage per year for the first 5 years and 30 days per year after that, capped at 2 years' wage; national workers follow pension law."},
    {"q": "Can my employer keep my passport?", "cat": "vocabulary-gap",
     "expected": ["labour_law:13"],
     "ref": "No. The employer may not retain the worker's official documents (such as the passport)."},
    {"q": "Do I have to pay court fees to file a labour lawsuit?", "cat": "direct",
     "expected": ["labour_law:55"],
     "ref": "No. Labour lawsuits are exempt from judicial fees at all stages of litigation and execution, together with requests by workers (or their heirs) valued up to AED 100,000."},
    {"q": "Can my company send my personal data to another country?", "cat": "other-law",
     "expected": ["pdpl:22", "pdpl:23"],
     "ref": "Only under the PDPL conditions: the receiving country must have adequate data protection, or an exception applies (e.g. explicit consent, necessity for a contract, legal obligations)."},
    # ---- edge cases (5)
    {"q": "What did the 2022 amendment change in the Labour Law?", "cat": "edge-freshness",
     "expected": ["labour_law_amendment_2022:1"],
     "ref": "Decree-Law No. 14 of 2022 replaced clause (3) of Article 8 of the Labour Law: the employment contract is concluded for a definite period, renewable by agreement of the parties."},
    {"q": "My employer has not paid my salary for two months. What does the law say?", "cat": "edge-hard",
     "expected": ["labour_law:22", "labour_law:45", "exec_regs:16"],   # exec_regs:16 added after review: implements Art. 22
     "ref": "The employer is obliged to pay wages on their due dates, according to the systems approved by the Ministry (Labour Law Article 22). Mentioning the worker's right to leave without notice when the employer breaks its obligations (Article 45) is a plus, not required."},
    {"q": "Tell me about leave.", "cat": "edge-ambiguous",
     "expected": ["labour_law:29", "labour_law:30", "labour_law:31", "labour_law:32", "exec_regs:18"],
     "ref": "A short overview of leave types in the Labour Law (annual, sick, maternity and other leaves) or a request to clarify which leave."},
    {"q": "What is the fee for a UAE Golden Visa?", "cat": "edge-out-of-scope",
     "expected": [],
     "ref": "REFUSE: not covered by these laws."},
    {"q": "What is the IRS 401k contribution limit for 2026?", "cat": "edge-hallucination-bait",
     "expected": [],
     "ref": "REFUSE: not covered by these laws (US tax rule)."},
]


def upload_dataset(client: Client | None = None, force: bool = False):
    """Create the dataset in LangSmith if it does not exist.
    WARNING: force=True deletes the dataset AND all its experiments, then recreates it."""
    client = client or Client()
    if client.has_dataset(dataset_name=DATASET_NAME):
        if not force:
            return client.read_dataset(dataset_name=DATASET_NAME)
        client.delete_dataset(dataset_name=DATASET_NAME)
    ds = client.create_dataset(DATASET_NAME, description="15 UAE labour-law questions incl. 5 edge cases")
    for row in DATASET:
        client.create_example(
            dataset_id=ds.id,
            inputs={"question": row["q"]},
            outputs={"reference": row["ref"], "expected": row["expected"], "category": row["cat"]},
        )
    return ds


# ── 2. The 3 pipeline versions (targets) ──────────────────────────────────
def _generate(question, results):
    """Shared generation step for versions A and B (same prompt as the graph)."""
    if not results:
        return {"answer": REFUSAL, "sources": [], "path": "refused_low_score"}
    draft = answer_chain.invoke({"context": format_context(results), "question": question,
                                 "retry_note": ""}).strip()
    if draft.startswith("NOT_FOUND"):
        return {"answer": REFUSAL, "sources": [], "path": "refused_by_llm"}
    used = sorted({int(n) for n in re.findall(r"\[S(\d+)\]", draft)})
    sources = list(dict.fromkeys(cite(results[i - 1][0]) for i in used if 0 < i <= len(results)))
    cited = list(dict.fromkeys(label(results[i - 1][0]) for i in used if 0 < i <= len(results)))
    return {"answer": draft, "sources": sources, "cited": cited,
            "path": "answered" if used else "answered_no_citation"}


def _pack(out, results):
    """Make the output JSON-friendly for LangSmith (no Document objects)."""
    out["retrieved"] = [label(d) for d, _ in results]
    out["context"] = [d.page_content for d, _ in results]
    out.setdefault("cited", [])
    return out


def target_A_naive(inputs: dict) -> dict:
    q = inputs["question"]
    results = [(d, None) for d in dense_search(q, name="fixed", k=TOP_N)]
    return _pack(_generate(q, results), results)


def target_B_hybrid(inputs: dict) -> dict:
    q = inputs["question"]
    ranked = rerank(q, hybrid_search(q, name="article", top_n=10), top_n=TOP_N)
    results = [(d, s) for d, s in ranked if s >= CUTOFF and d.metadata["article"] != 0]
    return _pack(_generate(q, results), results)


def target_C_full(inputs: dict) -> dict:
    r = ask(inputs["question"])
    results = r.get("results", [])
    cited_labels = [label(d) for d, _ in results if cite(d) in r.get("sources", [])]
    out = {"answer": r["answer"], "sources": r.get("sources", []), "cited": cited_labels,
           "path": r["path"], "rewritten": r.get("rewritten")}
    return _pack(out, results)


TARGETS = {"A_naive": target_A_naive, "B_hybrid": target_B_hybrid, "C_full": target_C_full}


# ── 3. Code evaluators (free, exact) ──────────────────────────────────────
def _refused(outputs):
    return outputs["path"].startswith("refused")


def decision_correct(inputs, outputs, reference_outputs):
    should_refuse = not reference_outputs["expected"]
    return {"key": "decision_correct", "score": int(_refused(outputs) == should_refuse)}


def retrieval_hit(inputs, outputs, reference_outputs):
    exp = set(reference_outputs["expected"])
    if not exp:                                     # out of scope: nothing to find
        return {"key": "retrieval_hit", "score": None}
    return {"key": "retrieval_hit", "score": int(bool(exp & set(outputs["retrieved"])))}


def citation_hit(inputs, outputs, reference_outputs):
    exp = set(reference_outputs["expected"])
    if not exp:
        return {"key": "citation_hit", "score": None}
    return {"key": "citation_hit", "score": int(bool(exp & set(outputs["cited"])))}


# ── 4. LLM-as-judge evaluators ─────────────────────────────────────────────
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "Qwen/Qwen3-235B-A22B-Instruct-2507")   # bigger than the bot's model
_judge_llm = get_llm(model=JUDGE_MODEL)

CORRECTNESS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You grade answers of a UAE labour-law assistant against a reference answer.
Score 1 if the assistant's answer contains the key facts of the reference and does not contradict it.
Score 0 if it misses a key fact, states a wrong number/period, or contradicts the reference.
If the reference starts with "REFUSE", score 1 only if the assistant declined to answer.
Small extra details are fine. Reply as JSON only: {{"score": 0 or 1, "reason": "<one sentence>"}}"""),
    ("human", "Question: {question}\n\nReference answer: {reference}\n\nAssistant answer: {answer}"),
])

FAITHFULNESS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You check if an answer is grounded in the given source texts.
Score 1 if EVERY factual claim in the answer is supported by the sources (a refusal or "not found" answer scores 1).
Score 0 if any claim (number, period, condition, right) is not in the sources.
Reply as JSON only: {{"score": 0 or 1, "reason": "<one sentence naming any unsupported claim>"}}"""),
    ("human", "Sources:\n{context}\n\nAnswer:\n{answer}"),
])

_correctness_chain = CORRECTNESS_PROMPT | _judge_llm | JsonOutputParser()
_faithfulness_chain = FAITHFULNESS_PROMPT | _judge_llm | JsonOutputParser()


def correctness(inputs, outputs, reference_outputs):
    try:
        r = _correctness_chain.invoke({"question": inputs["question"],
                                       "reference": reference_outputs["reference"],
                                       "answer": outputs["answer"]})
        return {"key": "correctness", "score": int(r["score"]), "comment": r.get("reason", "")}
    except Exception as e:                         # judge output not parseable
        return {"key": "correctness", "score": None, "comment": f"judge error: {e}"}


def faithfulness(inputs, outputs, reference_outputs):
    if _refused(outputs):
        return {"key": "faithfulness", "score": 1, "comment": "refusal"}
    try:
        r = _faithfulness_chain.invoke({"context": "\n\n---\n\n".join(outputs["context"]),
                                        "answer": outputs["answer"]})
        return {"key": "faithfulness", "score": int(r["score"]), "comment": r.get("reason", "")}
    except Exception as e:
        return {"key": "faithfulness", "score": None, "comment": f"judge error: {e}"}


EVALUATORS = [decision_correct, retrieval_hit, citation_hit, correctness, faithfulness]