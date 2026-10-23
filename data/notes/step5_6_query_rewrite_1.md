# Cell 5.6 — Query rewriting (our first LangChain chain)

## What this code does
- An LLM rewrites the user's question into the **vocabulary of the law** (salary → wage, passport → official documents, employee → worker).
- We search with **both** the original and the rewritten question, merge them with RRF, and re-rank against the rewritten question.
- `prompt | llm | parser` is an **LCEL chain**: the `|` passes the output of one step to the next.

## Why we need it
Users and laws use different words. Search cannot match words that are not there. The LLM is good at "translating" between them.

## Our result
| Question | Rewritten as | Result |
|---|---|---|
| Keep my passport? | "May an employer **retain the official documents** of a worker?" | ✅ Labour Law Art. 13 "Employer's Obligations" **0.998** (was 0.002) |
| Annual leave | formal wording | ✅ Art. 29, 0.996 |
| Golden Visa fee | formal wording | ✅ still low, 0.004 → refused |
| Salary not paid | "...not paid the worker's **wage**..." | ⚠️ Art. 9, 47, 29 — Art. 22 still missing |

The passport false refusal is fixed.
