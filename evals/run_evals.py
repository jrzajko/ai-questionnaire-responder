"""Run the Jev hybrid pipeline against an answer key and write a scorecard.

    python evals/run_evals.py --set heldout          # 26 fresh questions, never used for tuning
    python evals/run_evals.py --set golden           # the 60 Globex questions
    python evals/run_evals.py --set heldout --no-judge

Needs ANTHROPIC_API_KEY and TYPESAFE_API_KEY. Writes results/eval_<set>.{md,json,csv}.
"""
import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from responder import PolicyIndex, Responder, Settings  # noqa: E402
from responder.config import OPUS  # noqa: E402
from responder.evals import EXPECT, load_eval_set, run_eval, write_outputs  # noqa: E402

SETS = {
    "heldout": (ROOT / "data/evals/heldout_set.csv", None),
    "golden": (ROOT / "data/evals/golden_set.csv", ROOT / "data/questionnaires/globex_vendor_due_diligence_2026.xlsx"),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", choices=sorted(SETS), default="heldout")
    ap.add_argument("--judge-model", default=OPUS, help="LLM judge for faithfulness (a different model from the drafter)")
    ap.add_argument("--no-judge", action="store_true", help="skip the faithfulness judge")
    ap.add_argument("--out", default=str(ROOT / "results"))
    args = ap.parse_args()

    key_csv, questionnaire = SETS[args.set]
    rows = load_eval_set(key_csv, questionnaire)
    responder = Responder(PolicyIndex(ROOT / "data/policies"), Settings())
    print(f"Evaluating {len(rows)} questions from '{args.set}'...")
    results, m = run_eval(responder, rows, judge_model=None if args.no_judge else args.judge_model)
    md = write_outputs(results, m, args.out, args.set)
    print(md.read_text())
    misses = [r for r in results if r["status"] not in EXPECT[r["expected_outcome"]]]
    for r in misses:
        print(f"  miss [{r['ref']}] expected {r['expected_outcome']}, got {r['status']}: {' | '.join(r['reasons'])[:140]}")


if __name__ == "__main__":
    main()
