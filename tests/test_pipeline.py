"""Offline tests: retrieval, questionnaire parsing, the per-question graph, review with interrupt(), the library."""
import json
import sqlite3

import openpyxl
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from conftest import ROOT
from responder import ESCALATE_TEXT
from responder.agents import keyword_flags, numbers_match
from responder.graph import decision, review_queue
from responder.io import audit_rows, extract_questions, write_completed
from responder.library import AnswerLibrary

GLOBEX = ROOT / "data" / "questionnaires" / "globex_vendor_due_diligence_2026.xlsx"


# ------------------------------------------------------------------ building blocks
def test_index_and_search(index):
    assert len(index) == 67
    assert index.search("Is customer data encrypted at rest?")[0]["section_id"] == "ISP-6"
    assert index.search("Do you train AI models on customer data?")[0]["section_id"] == "AIG-3"
    assert index.search("") == []


def test_extract_questions_from_messy_workbook():
    items, report = extract_questions(GLOBEX)
    assert len(items) == 60
    assert not any("Cover" in r and "->" in r for r in report)            # cover/instruction tabs skipped
    sub = next(i for i in items if i["ref"] == "3.4(b)")
    assert sub["model_question"].startswith("Data retention and deletion:")  # sub-question gets parent context
    assert next(i for i in items if i["ref"] == "1.10")["ref"] == "1.10"    # not read as the number 1.1
    infosec = next(i for i in items if i["ref"] == "1.1.1")
    assert infosec["choice_col"] is not None and set(infosec["choice_options"]) == {"Yes", "No", "N/A", "Partial"}
    assert next(i for i in items if i["ref"] == "AI-01")["choice_col"] is None


def test_rule_checks():
    assert numbers_match("within 48 hours", "within 48 hours of confirmation")
    assert not numbers_match("within 24 hours", "within 48 hours of confirmation")
    assert keyword_flags("Can you guarantee 99.99% uptime?") == ["keyword rule: guarantee"]
    assert keyword_flags("What is your breach notification timeframe?") == []


# ------------------------------------------------------------------ per-question graph
def test_answerable_question_is_auto_approved(make_responder):
    r = make_responder().answer("Is customer data encrypted at rest with AES-256?")
    assert r["status"] == "auto_approve" and r["confidence"] == "High"
    assert r["sources"] == ["ISP-6"] and r["claims"][0]["quote_found"]


def test_trap_escalates_without_any_claude_call(make_responder):
    resp = make_responder()
    r = resp.answer("Do you operate a public bug bounty programme?")
    assert r["status"] == "escalate" and r["answer"] == ESCALATE_TEXT
    assert resp.claude.calls == []                                          # the Jev gate stopped it first


def test_restricted_question_never_auto_approves(make_responder):
    r = make_responder().answer("Can you guarantee that data at rest is encrypted with AES-256?")
    assert r["status"] != "auto_approve" and r["signals"]["restricted"]


def test_reviewer_note_asking_for_a_check_holds_the_answer(make_responder):
    held = make_responder(note="Confirm the key rotation date before sending.").answer(
        "Is customer data encrypted at rest with AES-256?")
    info = make_responder(note="The policy does not name the cipher mode.").answer(
        "Is customer data encrypted at rest with AES-256?")
    assert held["status"] == "human_review" and any("reviewer note" in x for x in held["reasons"])
    assert info["status"] == "auto_approve"


def test_claim_checks_reject_fabricated_quotes_and_wrong_numbers(make_responder):
    resp = make_responder()
    state = {"draft": {"covered": True, "cited_section_ids": ["IR-4"], "answer": "x"},
             "passages": {"IR-4": {**resp.index.by_id["IR-4"], "score": 5.0}}}

    class Extract:
        def __init__(self, claims): self.claims = claims
    from responder.state import ExtractedClaim
    claims = [ExtractedClaim(claim="Acme notifies customers.", cited_section_id="", evidence_quote=""),
              ExtractedClaim(claim="Acme notifies customers.", cited_section_id="IR-4", evidence_quote="made up words"),
              ExtractedClaim(claim="Acme notifies customers within 24 hours.", cited_section_id="IR-4",
                             evidence_quote="Acme notifies affected customers")]
    resp.claude.structured = lambda *a: Extract(claims)
    verdicts = [(c["verdict"], c.get("note", "")) for c in resp.verify(state)["grounding"]["claims"]]
    assert verdicts[0] == ("inferred", "no quote given; Jev judged the whole section")   # blank source -> fallback
    assert verdicts[1] == ("unsupported", "quote not found in the section")
    assert verdicts[2] == ("unsupported", "a number in the claim isn't in the section")


# ------------------------------------------------------------------ review graph + library
def run_and_review(resp, items, tmp_path, run_id, choose):
    graph = resp.build_run_graph(SqliteSaver(sqlite3.connect(tmp_path / "ck.db", check_same_thread=False)),
                                 reviewer="Tester", run_id=run_id)
    config = {"configurable": {"thread_id": run_id}}
    graph.invoke({"items": items, "results": [], "decisions": [], "final": [], "summary": {}}, config)
    seen = []
    while (pending := graph.get_state(config).interrupts):
        p = pending[0].value
        seen.append(p["ref"])
        graph.invoke(Command(resume=choose(p)), config)
    return graph.get_state(config).values, seen


def test_review_library_reuse_and_dropdowns(make_responder, tmp_path):
    items = [i for i in extract_questions(GLOBEX)[0] if i["ref"] in {"1.1.1", "1.4.2", "1.5.4", "1.3.1"}]
    lib = AnswerLibrary(str(tmp_path / "lib.db"))

    # Run 1: answer, then review. Approve nothing automatic; write answers for the rest.
    def choose(p):
        if not p["draft"]:
            return decision("edit", "Tester", answer=f"Written by a human for {p['ref']}.")
        return decision("approve", "Tester")
    resp = make_responder(library=lib)
    values, seen = run_and_review(resp, items, tmp_path, "run-1", choose)
    assert set(seen) == {"1.4.2", "1.5.4"}                                  # trap + restricted went to a human
    final = {f["ref"]: f for f in values["final"]}
    assert final["1.4.2"]["decision"] == "edited" and final["1.5.4"]["decision"] == "approved"
    assert final["1.1.1"]["decision"] == "auto_approved"
    assert values["summary"]["added_to_library"] == 2 and len(lib) == 2

    # Dropdown column on the InfoSec tab gets a Jev-picked value; the file keeps Globex's own layout.
    out = write_completed(GLOBEX, values["final"], tmp_path / "out.xlsx")
    ws = openpyxl.load_workbook(out)["1. InfoSec"]
    row = final["1.1.1"]
    assert ws.cell(row["row"], row["choice_col"] + 1).value in {"Yes", "No", "Partial", "N/A"}
    assert ws.cell(row["row"], row["answer_col"] + 1).value == row["final_answer"]
    assert len(audit_rows(values["final"], "run-1")) == 4

    # Run 2: the approved answers come back from the library; no Claude call for them.
    resp2 = make_responder(library=lib)
    values2, seen2 = run_and_review(resp2, items, tmp_path, "run-2", lambda p: decision("approve", "Tester"))
    final2 = {f["ref"]: f for f in values2["final"]}
    assert final2["1.4.2"]["signals"]["library_match"] and final2["1.4.2"]["status"] == "auto_approve"
    assert final2["1.5.4"]["signals"]["library_match"] and "1.5.4" in seen2   # commitments always re-checked
    assert values2["summary"] == {**values2["summary"], "added_to_library": 0, "library_reuses": 2}
    assert len(resp2.claude.calls) == 4                                      # only the 2 non-library questions
    assert {e["question"]: e["times_reused"] for e in lib.all()}[final["1.4.2"]["model_question"]] == 1


def test_stale_library_answer_is_not_reused(index, tmp_path):
    lib = AnswerLibrary(str(tmp_path / "lib.db"))
    lib.add("How fast do you notify breaches?", "Within 48 hours.", ["IR-4"], "security", "approved", "T", index.versions)
    same = lambda a, b: 0.99
    assert lib.lookup("How fast do you notify breaches?", index.versions, same, 0.8)["match"] is not None
    changed = {**index.versions, "IR-4": "9.9"}                             # the policy was updated
    hit = lib.lookup("How fast do you notify breaches?", changed, same, 0.8)
    assert hit["match"] is None and hit["checked"][0]["stale"] == ["IR-4"]


def test_review_queue_order():
    mk = lambda ref, status, conf, restricted=False: {"ref": ref, "status": status, "confidence": conf, "sheet": "s",
                                                       "row": int(ref), "signals": {"restricted": restricted}}
    q = review_queue([mk("1", "human_review", "Medium"), mk("2", "escalate", "Low"), mk("3", "auto_approve", "High"),
                      mk("4", "human_review", "Low", restricted=True)])
    assert [r["ref"] for r in q] == ["4", "2", "1"]


# ------------------------------------------------------------------ eval runner
def test_eval_runner_scores_both_sets(make_responder, tmp_path):
    from responder.evals import load_eval_set, run_eval, write_outputs
    for key, questionnaire in [(ROOT / "data/evals/heldout_set.csv", None),
                               (ROOT / "data/evals/golden_set.csv", GLOBEX)]:
        rows = load_eval_set(key, questionnaire)
        results, m = run_eval(make_responder(), rows, judge_model="judge", max_parallel=4)
        assert m["questions"] == len(rows) and m["errors"] == 0
        assert set(m) >= {"unsafe_auto_approvals", "precision_of_high", "faithfulness", "citation_coverage", "cost_usd"}
        md = write_outputs(results, m, tmp_path, key.stem).read_text()
        assert "Unsafe auto-approvals" in md
    assert len(load_eval_set(ROOT / "data/evals/golden_set.csv", GLOBEX)) == 60
