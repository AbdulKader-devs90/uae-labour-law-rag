"""
Query rewriting for the UAE Labour Law RAG bot (proven in notebook 05).

Users say "salary", "passport", "fired"; the laws say "wage", "official documents",
"termination". The LLM rewrites the question into the law's vocabulary, then we
search with BOTH versions, merge with RRF, and re-rank.
"""
import logging

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from src.llm import get_llm
from src.retrieval import hybrid_search, rerank, rrf

for _name in ("httpx", "httpx2"):                          # hide per-request INFO logs
    logging.getLogger(_name).setLevel(logging.WARNING)

REWRITE_SYSTEM = """You turn a user's question about UAE employment or personal data into a search query
written in the formal vocabulary of UAE legislation.
Examples of word changes: salary -> wage; boss/company -> employer; employee/staff -> worker;
passport/visa papers -> official documents; fired -> termination of employment; vacation -> annual leave.
Keep the meaning. Keep any article number the user wrote.
Do NOT add the names, numbers or years of laws or decrees unless the user wrote them.
Do not answer the question. Return ONLY the rewritten query on one line."""

rewrite_chain = (
    ChatPromptTemplate.from_messages([("system", REWRITE_SYSTEM), ("human", "{question}")])
    | get_llm()
    | StrOutputParser()
)


def rewrite(question: str) -> str:
    return rewrite_chain.invoke({"question": question}).strip()


def retrieve_with_rewrite(question, candidates=10, top_n=5, rewritten=None):
    """Search with the original AND the rewritten question, merge (RRF), re-rank.
    Each chunk is re-ranked against BOTH questions and keeps its best score, so a bad
    rewrite cannot push out a chunk that matches the user's own words (and vice versa).
    Returns (rewritten_question, [(doc, score), ...])."""
    q2 = rewritten or rewrite(question)
    pool = rrf([hybrid_search(question, top_n=candidates),
                hybrid_search(q2, top_n=candidates)],
               top_n=candidates * 2)
    pool = [d for d in pool if d.metadata["article"] != 0]      # preambles hold no rules

    best = {}
    for q in (question, q2):
        for d, s in rerank(q, pool, top_n=len(pool)):
            cid = d.metadata["chunk_id"]
            if cid not in best or s > best[cid][1]:
                best[cid] = (d, s)
    ranked = sorted(best.values(), key=lambda x: x[1], reverse=True)
    return q2, ranked[:top_n]