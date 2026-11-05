"""Streamlit front end for the questionnaire responder.

Demo mode (default, free): explore saved runs, the scorecard, the policy pack and the review flow.
Live mode (password): upload a questionnaire, answer it with Jev + Claude, review with LangGraph interrupt().

Streamlit Cloud secrets: ANTHROPIC_API_KEY, TYPESAFE_API_KEY, APP_PASSWORD.
"""
import json
import os
import pathlib
import sqlite3
import sys
import uuid

import pandas as pd
import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from responder.evals import EXPECT  # noqa: E402

RESULTS, DATA = ROOT / "results", ROOT / "data"
GOLDEN = DATA / "evals" / "golden_set.csv"
RUNS = {   # label: (audit file, cost per 60-question run, note)
    "C: Jev hybrid + review & library (run 7)": ("run7_library_reuse_audit.csv", 0.2044, "measured"),
    "C: Jev hybrid, tuned (run 4)": ("run4_C_tuned_audit.csv", 0.16901, "measured"),
    "C: Jev hybrid (run 3)": ("run3_C_full_audit.csv", 0.15553, "measured"),
    "B: Haiku + Sonnet (run 3)": ("run3_B_full_audit.csv", 0.33652, "measured"),
    "A: Opus baseline (run 1)": ("run1_audit.csv", 2.20, "estimated"),
}
ICON = {"auto_approve": "🟢", "human_review": "🟡", "escalate": "🔴", "error": "⚠️"}
LABEL = {"auto_approve": "Auto-approved", "human_review": "Needs review", "escalate": "Escalated", "error": "Error"}

st.set_page_config(page_title="Questionnaire Responder", page_icon="🛡️", layout="wide")


# ------------------------------------------------------------------ data
@st.cache_data
def load_run(name: str) -> pd.DataFrame:
    a = pd.read_csv(RESULTS / name, dtype=str).fillna("")
    if "category" not in a and "specialist" in a:
        a["category"] = a["specialist"]
    g = pd.read_csv(GOLDEN, dtype=str).fillna("")
    return a.merge(g[["sheet", "ref", "expected_outcome", "expected_category", "expected_sources"]],
                   on=["sheet", "ref"], how="left").fillna("")


def run_metrics(df: pd.DataFrame, cost: float) -> dict:
    exp = df["expected_outcome"]
    auto = df["status"] == "auto_approve"
    hi = exp == "high"
    return {"Correct outcome": f"{sum(s in EXPECT.get(e, set()) for s, e in zip(df.status, exp))}/{len(df)}",
            "Answerable auto-approved": f"{(auto & hi).sum()}/{hi.sum()}",
            "Unsafe auto-approvals": int((auto & ~hi).sum()),
            "Traps escalated": f"{((exp == 'gap') & (df.status == 'escalate')).sum()}/{(exp == 'gap').sum()}",
            "Restricted held": f"{((exp == 'restricted') & ~auto).sum()}/{(exp == 'restricted').sum()}",
            "Cost per run": f"${cost:.2f}"}


@st.cache_data
def policy_docs() -> dict:
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted((DATA / "policies").glob("*.md"))}


@st.cache_data
def sections() -> dict:
    from responder.retrieval import parse_doc
    return {c["section_id"]: c for p in sorted((DATA / "policies").glob("*.md")) for c in parse_doc(p)}


def secret(key: str) -> str:
    """st.secrets raises when no secrets file exists (e.g. running locally), so fall back to env vars."""
    try:
        return st.secrets[key]
    except Exception:
        return os.environ.get(key, "")


def loads(s, default):
    try:
        return json.loads(s) if s else default
    except Exception:
        return default


# ------------------------------------------------------------------ shared widgets
def question_card(r: dict, show_decision: bool = True):
    status = r["status"]
    st.markdown(f"#### {ICON.get(status, '')} [{r['sheet']} {r['ref']}] {r['question']}")
    facts = [f"**Status:** {LABEL.get(status, status)}", f"**Confidence:** {r.get('confidence', '')}"]
    if r.get("category"):
        facts.append(f"**Specialist:** {r['category'].replace('_', ' ')}")
    if show_decision and r.get("decision"):
        who = f" by {r['reviewer']}" if r.get("reviewer") else ""
        facts.append(f"**Decision:** {r['decision'].replace('_', ' ')}{who}")
    st.markdown("  ·  ".join(facts))
    answer = r.get("final_answer") or r.get("answer") or r.get("draft_answer")
    st.markdown("**Answer**")
    st.info(answer or "_(no answer: the policy pack does not cover this)_")
    if r.get("reviewer_note"):
        st.markdown(f"**Note for the reviewer** (never sent to the customer): {r['reviewer_note']}")
    reasons = [x for x in r.get("reasons", "").split(" | ") if x]
    if reasons:
        st.markdown("**Why it got this status**\n" + "\n".join(f"- {x}" for x in reasons))
    claims = loads(r.get("claims", ""), [])
    if claims:
        st.markdown("**Claim-by-claim check**")
        st.dataframe(pd.DataFrame([{"verdict": c.get("verdict"), "claim": c.get("claim"), "section": c.get("cited_section_id"),
                                    "quote found": c.get("quote_found"), "Jev": c.get("jev_relation", ""),
                                    "Jev conf.": c.get("jev_confidence", ""), "note": c.get("note", "")} for c in claims]),
                     hide_index=True, use_container_width=True)
    srcs = [s.strip() for s in r.get("sources", "").split(";") if s.strip()]
    for sid in srcs:
        sec = sections().get(sid)
        if sec:
            with st.expander(f"📄 {sid}: {sec['doc_title']}, {sec['heading']}"):
                st.write(sec["text"])
    sig = loads(r.get("signals", ""), {})
    gate = sig.get("gate")
    if gate:
        with st.expander("Jev's relevance gate: which sections reached the writer"):
            st.dataframe(pd.DataFrame([{"section": k, "on topic (p)": v[0], "has evidence (p)": v[1]} for k, v in gate.items()]),
                         hide_index=True)
    if sig:
        with st.expander("All signals (raw)"):
            st.json(sig)


# ------------------------------------------------------------------ demo pages
FINAL_RUN = "C: Jev hybrid + review & library (run 7)"


def what_to_do(text: str):
    """One consistent 'what to do here' box at the top of every page."""
    st.info(f"**What to do here:** {text}", icon="👉")


def go_to_question(ref: str):
    st.session_state["browse_run"] = FINAL_RUN
    st.session_state["browse_ref"] = ref
    st.switch_page(P_BROWSE)


def page_overview():
    st.title("🛡️ AI Security Questionnaire Responder")
    with st.container(border=True):
        st.markdown("#### 👋 Start here: a 2-minute tour")
        st.markdown("""This is a **read-only demo** built from real runs of the tool, so nothing you click costs anything or
changes anything. The tool answers a prospect's security questionnaire from the vendor's policies, and only asks a
human when it isn't sure. Four stops show how:

1. 🔎 **Browse answers, one with evidence:** follow an answer back to the exact policy clause behind it.
2. 🔎 **Browse answers, a trap:** the policy doesn't cover this question, so the tool escalated instead of guessing.
3. 🧑‍⚖️ **Review queue:** play the reviewer on the answers the tool wasn't sure about. Approve, edit or reject each one.
4. 📚 **Policy pack:** the only documents the tool is allowed to use.""")
        b = st.columns(4)
        if b[0].button("Browse answers: evidence", icon="🔎", use_container_width=True):
            go_to_question("1.5.3")
        if b[1].button("Browse answers: a trap", icon="🔎", use_container_width=True):
            go_to_question("AI-04")
        if b[2].button("Review queue", icon="🧑‍⚖️", use_container_width=True):
            st.switch_page(P_REVIEW)
        if b[3].button("Policy pack", icon="📚", use_container_width=True):
            st.switch_page(P_POLICY)
        st.caption("The same pages are in the menu on the left. Or read on for the results.")
    st.subheader("What it is")
    st.markdown("""Prospects send B2B SaaS vendors long security and AI due-diligence questionnaires. This tool drafts every
answer from the vendor's own policy pack, cites the exact clause, scores confidence from **measured signals**, and hands
anything uncertain or risky to a human. Everything here is fictional: the vendor is **Acme SaaS** and the prospect is **Globex**.

**How it's built:** LangGraph runs the pipeline. Claude writes the answers (Sonnet) and extracts claims (Haiku).
**Jev**, a decision model from TypeSafe AI, makes every yes/no and pick-one judgement with calibrated probabilities.
LangGraph's `interrupt()` handles human review, and an answer library learns from what reviewers approve.""")
    df = load_run(RUNS["C: Jev hybrid + review & library (run 7)"][0])
    m = run_metrics(df, 0.2044)
    c = st.columns(4)
    c[0].metric("Answerable questions auto-approved", m["Answerable auto-approved"], "+6 vs Opus baseline")
    c[1].metric("Unsafe auto-approvals", m["Unsafe auto-approvals"], help="Zero in every run so far.")
    c[2].metric("Cost per 60-question run", m["Cost per run"], "-91% vs Opus (est. $2.20)", delta_color="inverse")
    c[3].metric("Reused from the answer library", int((df.library_hit == "True").sum()))
    st.subheader("Scorecard: same 60 questions, same answer key")
    st.markdown("Each row is one version of the pipeline, run on the same questionnaire and checked against an answer key "
                "written in advance. Read across: **unsafe auto-approvals must be 0**, then more auto-approved is better, "
                "then cheaper is better.")
    rows = []
    for label, (f, cost, note) in RUNS.items():
        rows.append({"Pipeline": label, **run_metrics(load_run(f), cost),
                     "Cost note": note})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption("“Unsafe” = auto-approved although the answer key says a human must see it. Thresholds were tuned on these "
               "60 questions; see the held-out evals in the README for fresh questions.")
    st.subheader("Pipeline")
    st.code("""question → Jev classify (specialist + 4 commitment checks) → library lookup ──hit──▶ reuse approved answer
                                                   └─miss─▶ FTS search → Jev relevance gate → Sonnet draft
                                                            → Haiku claims + verbatim quote & number checks → Jev supports/contradicts
                                                            → Jev reviewer-note check → confidence score
all questions (LangGraph Send, in parallel) → review: interrupt() per uncertain answer → finalise → library learns""", language="text")


def page_browse():
    st.title("🔎 Browse answers")
    what_to_do("pick a question to see the answer, why it got its status, the claim-by-claim check, the cited policy "
               "text and Jev's probabilities. Good ones to try: **1.5.3** (auto-approved with evidence), **AI-04** "
               "(a trap it refused to answer) and **1.5.4** (a contractual commitment held for a human).")
    runs = list(RUNS)
    label = st.selectbox("Run", runs, index=runs.index(st.session_state.get("browse_run", FINAL_RUN)))
    df = load_run(RUNS[label][0])
    counts = df["status"].value_counts()
    st.markdown("  ·  ".join(f"{ICON.get(k, '')} {LABEL.get(k, k)}: **{v}**" for k, v in counts.items()))
    status = st.multiselect("Show", list(LABEL), default=[s for s in LABEL if s in counts], format_func=lambda s: LABEL[s])
    view = df[df.status.isin(status)]
    options = list(view.index)
    want = st.session_state.get("browse_ref")
    start = next((n for n, i in enumerate(options) if view.ref[i] == want), 0)
    choice = st.selectbox("Question", options, index=start if options else None,
                          format_func=lambda i: f"{ICON.get(view.status[i], '')} [{view.ref[i]}] {view.question[i][:90]}")
    if choice is not None:
        question_card(df.loc[choice].to_dict())


def page_review_demo():
    st.title("🧑‍⚖️ Review queue")
    what_to_do("you're the reviewer. For each answer, read *Why it got this status* to see what the tool wasn't sure "
               "about, then choose ✅ **Approve** if the draft is right, ✏️ **Edit** to change it first, or ❌ **Reject** "
               "to pass it to a subject-matter expert. Your choices stay in your browser and change nothing.")
    st.caption("These are the 27 answers the final run sent to a person, most important first: commitments, then "
               "questions the policy doesn't cover, then the less certain answers. In the real tool each decision "
               "resumes a paused LangGraph graph through `Command(resume=...)`.")
    df = load_run(RUNS["C: Jev hybrid + review & library (run 7)"][0])
    rank = lambda r: (0 if '"restricted": true' in r["signals"] else 1 if r["status"] == "escalate" else
                      2 if r["confidence"] == "Low" else 3)
    queue = df[df.status != "auto_approve"].copy()
    queue["_rank"] = [rank(r) for _, r in queue.iterrows()]
    queue = queue.sort_values(["_rank", "sheet", "row"], key=lambda c: c.astype(int) if c.name == "row" else c).reset_index(drop=True)
    ss = st.session_state
    ss.setdefault("demo_decisions", {})
    done = len(ss.demo_decisions)
    st.progress(done / len(queue), text=f"{done} of {len(queue)} reviewed")
    pending = [i for i in range(len(queue)) if i not in ss.demo_decisions]
    if not pending:
        st.success("Queue cleared.")
        st.dataframe(pd.DataFrame([{"ref": queue.ref[i], **d} for i, d in ss.demo_decisions.items()]), hide_index=True)
        if st.button("Start again"):
            ss.demo_decisions = {}
            st.rerun()
        return
    i = pending[0]
    r = queue.loc[i].to_dict()
    question_card(r, show_decision=False)
    edited = st.text_area("Edit the answer (for ✏️ Edit)", value=r["draft_answer"], key=f"edit_{i}")
    b = st.columns(4)
    if b[0].button("✅ Approve", disabled=not r["draft_answer"], use_container_width=True):
        ss.demo_decisions[i] = {"action": "approve", "answer": r["draft_answer"]}; st.rerun()
    if b[1].button("✏️ Edit", use_container_width=True):
        ss.demo_decisions[i] = {"action": "edit", "answer": edited}; st.rerun()
    if b[2].button("❌ Reject", use_container_width=True):
        ss.demo_decisions[i] = {"action": "reject", "answer": ""}; st.rerun()
    if b[3].button("⏭️ Skip to end", use_container_width=True):
        for j in pending:
            ss.demo_decisions[j] = {"action": "reject", "answer": ""}
        st.rerun()


def page_policies():
    st.title("📚 Policy pack")
    what_to_do("pick a document to read. These fictional policies are the tool's only source of truth, and every "
               "answer cites a section ID from them, such as `ISP-6`. Some topics are deliberately missing (a bug bounty, "
               "PCI DSS, cyber insurance) to test that the tool refuses to guess.")
    docs = policy_docs()
    name = st.selectbox("Document", list(docs))
    st.markdown(docs[name].split("---", 2)[-1])


# ------------------------------------------------------------------ live mode
def page_live():
    st.title("⚡ Live run")
    what_to_do("this is the real tool. It calls Claude and Jev with the owner's API keys, so it's password-protected. "
               "Without the password, the demo pages show the results of real runs.")
    password = secret("APP_PASSWORD")
    if not password:
        st.warning("Live mode is switched off: no APP_PASSWORD is configured.")
        return
    if not st.session_state.get("authed"):
        pw = st.text_input("Password", type="password")
        if pw and pw == password:
            st.session_state.authed = True
            st.rerun()
        elif pw:
            st.error("Wrong password.")
        st.info("Live mode calls Claude and Jev with the owner's API keys, so it's password-protected. Demo mode is free.")
        return
    for k in ("ANTHROPIC_API_KEY", "TYPESAFE_API_KEY"):
        if secret(k):
            os.environ[k] = secret(k)

    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.types import Command
    from responder import PolicyIndex, Responder, Settings
    from responder.graph import decision
    from responder.io import audit_rows, extract_questions, write_completed
    from responder.library import AnswerLibrary

    ss = st.session_state
    work = pathlib.Path("/tmp/responder")
    work.mkdir(exist_ok=True)
    reviewer = st.text_input("Reviewer name", value=ss.get("reviewer", ""), key="reviewer")
    lib_up = st.file_uploader("Answer library (optional, answer_library.db from an earlier run)", type=["db"])
    q_up = st.file_uploader("Questionnaire (XLSX or CSV)", type=["xlsx", "csv"])
    if not q_up:
        q_path = DATA / "questionnaires" / "globex_vendor_due_diligence_2026.xlsx"
        st.caption(f"No upload: using the sample questionnaire ({q_path.name}).")
    else:
        q_path = work / q_up.name
        q_path.write_bytes(q_up.getvalue())
    limit = st.slider("Questions to answer (keep it small to save cost)", 5, 60, 10)

    if st.button("▶️ Answer the questionnaire", type="primary", disabled=not reviewer.strip()):
        lib_path = work / "answer_library.db"
        if lib_up:
            lib_path.write_bytes(lib_up.getvalue())
        responder = Responder(PolicyIndex(DATA / "policies"), Settings(), library=AnswerLibrary(str(lib_path)))
        thread = f"app-{uuid.uuid4().hex[:8]}"
        graph = responder.build_run_graph(SqliteSaver(sqlite3.connect(work / "checkpoints.db", check_same_thread=False)),
                                          reviewer=reviewer, run_id=thread)
        items = extract_questions(q_path)[0][:limit]
        with st.spinner(f"Answering {len(items)} questions in parallel..."):
            graph.invoke({"items": items, "results": [], "decisions": [], "final": [], "summary": {}},
                         {"configurable": {"thread_id": thread}, "max_concurrency": 6})
        ss.update(live_graph=graph, live_config={"configurable": {"thread_id": thread}}, live_responder=responder,
                  live_qpath=str(q_path), live_lib=str(lib_path))
        st.rerun()

    graph = ss.get("live_graph")
    if not graph:
        return
    config = ss.live_config
    pending = graph.get_state(config).interrupts
    st.caption(f"Cost so far: ${ss.live_responder.usage.cost:.4f}")
    if pending:
        p = pending[0].value
        st.subheader(f"Review {p['n']} of {p['total']}")
        question_card({**p, "answer": p["draft"], "draft_answer": p["draft"], "category": "",
                       "reasons": " | ".join(p["reasons"]), "sources": "; ".join(s.split("§")[-1] for s in p["sources"]),
                       "claims": json.dumps([{"verdict": c.split(":")[0], "claim": c.split(":", 1)[1]} for c in p["claims"]])})
        edited = st.text_area("Answer to send (for ✏️ Edit)", value=p["draft"], key=f"live_edit_{p['n']}")
        comment = st.text_input("Comment for the audit trail (optional)", key=f"live_comment_{p['n']}")
        b = st.columns(3)
        act = None
        if b[0].button("✅ Approve", disabled=not p["draft"], use_container_width=True):
            act = decision("approve", reviewer, comment=comment)
        if b[1].button("✏️ Edit", use_container_width=True):
            act = decision("edit", reviewer, answer=edited, comment=comment)
        if b[2].button("❌ Reject", use_container_width=True):
            act = decision("reject", reviewer, comment=comment)
        if act:
            graph.invoke(Command(resume=act), config)
            st.rerun()
        return
    values = graph.get_state(config).values
    st.success(f"Review complete. {values['summary']['added_to_library']} answers added to the library, "
               f"{values['summary']['library_reuses']} reused from it.")
    out = write_completed(ss.live_qpath, values["final"], pathlib.Path("/tmp/responder") / "completed.xlsx")
    audit = pd.DataFrame(audit_rows(values["final"], config["configurable"]["thread_id"]))
    st.dataframe(audit[["ref", "status", "decision", "final_answer", "response_choice"]], hide_index=True)
    d = st.columns(3)
    d[0].download_button("Completed questionnaire", open(out, "rb").read(), "completed.xlsx")
    d[1].download_button("Audit trail (CSV)", audit.to_csv(index=False), "audit.csv")
    d[2].download_button("Answer library", open(ss.live_lib, "rb").read(), "answer_library.db")


# ------------------------------------------------------------------ navigation
P_OVERVIEW = st.Page(page_overview, title="Overview", icon="🏠", default=True)
P_BROWSE = st.Page(page_browse, title="Browse answers", icon="🔎")
P_REVIEW = st.Page(page_review_demo, title="Review queue", icon="🧑‍⚖️")
P_POLICY = st.Page(page_policies, title="Policy pack", icon="📚")
pages = {"Demo (saved runs)": [P_OVERVIEW, P_BROWSE, P_REVIEW, P_POLICY],
         "Live (password)": [st.Page(page_live, title="Live run", icon="⚡")]}
st.navigation(pages).run()
