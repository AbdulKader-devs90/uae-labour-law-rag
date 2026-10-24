"""
Run the Step 8 evaluation from the terminal (more stable than a notebook, and errors are visible).

Usage, from the project folder with the venv active:
    python scripts/run_eval.py                              # A, B, C on the 15 questions (v1 evaluation)
    python scripts/run_eval.py C_full                       # only one version
    python scripts/run_eval.py --d18 --reps 3 C_full C_v3   # v1 vs v3 on 18 questions, 3 runs each

Results: LangSmith experiments + CSV files in data/eval/ + a summary table.
"""
import os
import sys

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pandas as pd                                   # noqa: E402
from langsmith import evaluate                        # noqa: E402

from src.evaluation import (DATASET_NAME, DATASET_NAME_18, EVALUATORS, TARGETS,  # noqa: E402
                            upload_dataset_18)

METRICS = ["decision_correct", "retrieval_hit", "citation_hit", "correctness", "faithfulness"]
OUT = os.path.join(ROOT, "data", "eval")
os.makedirs(OUT, exist_ok=True)

# Usage:  python scripts/run_eval.py [--d18] [--reps N] [TARGET ...]
#   --d18     use the 18-question dataset (15 + 3 near-scope/leading questions)
#   --reps N  repeat each question N times (average), e.g. --reps 3
args = sys.argv[1:]
use18 = "--d18" in args
reps = int(args[args.index("--reps") + 1]) if "--reps" in args else 1
names = [a for a in args if a in TARGETS] or ["A_naive", "B_hybrid", "C_full"]
dataset = DATASET_NAME_18 if use18 else DATASET_NAME
if use18:
    upload_dataset_18()                                   # creates it only if missing
tag = ("d18_" if use18 else "") + (f"x{reps}_" if reps > 1 else "")
summary = {}
for name in names:
    print(f"\n=== Running {name} ===", flush=True)
    res = evaluate(TARGETS[name], data=dataset, evaluators=EVALUATORS, num_repetitions=reps,
                   experiment_prefix=tag + name, max_concurrency=1)      # one at a time = stable
    df = res.to_pandas()
    df.to_csv(os.path.join(OUT, f"{tag}{name}.csv"), index=False)
    summary[name] = {m: df[f"feedback.{m}"].mean() for m in METRICS if f"feedback.{m}" in df}
    summary[name]["avg_seconds"] = df["execution_time"].mean()
    print(pd.Series(summary[name]).round(2).to_string(), flush=True)

table = pd.DataFrame(summary).T.round(2)
table.to_csv(os.path.join(OUT, f"{tag}summary.csv"))
print("\n=== SUMMARY ===\n" + table.to_string())
