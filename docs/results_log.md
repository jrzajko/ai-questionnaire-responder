# Results log

The experiment history behind the README's headline numbers, written as each run happened. Audit files for every run are in [`results/`](../results).

## Results: first full run (run 1)

All 60 Globex questions, Claude Opus 5.5 specialists and grounding, Claude Haiku 5.5 classifier. Full trail in [`results/run1_audit.csv`](../results/run1_audit.csv).

| Check | Result |
|---|---|
| Trap questions escalated (PCI DSS, bug bounty, cyber insurance, escrow, model version, ESG) | **6 / 6** |
| Restricted questions kept from auto-approve (guarantees, indemnity, liability, full pen-test report, 24h commitment) | **5 / 5** |
| Implied / partial questions sent to a human | **8 / 8** |
| Routed to the expected specialist | **100%** |
| Cited the expected policy section | **100%** |
| Clearly answerable questions auto-approved | 27 / 41 |
| Claims checked | 251 (223 explicit, 21 inferred, 7 unsupported) |

**No unsafe outcomes.** No trap or restricted question was auto-approved. Every miss was over-caution: answerable questions sent to review. The audit trail showed three causes:

1. **The classifier over-flagged commitments.** It treated "what is your breach-notification timeframe?" as a request for a new promise. The keyword rule already catches real commitment requests, so the classifier definition can be stricter.
2. **The answers over-answered.** Drafts added related facts nobody asked for, and each extra claim is another chance to be marked inferred.
3. **The grounding check was too literal.** It marked a bare "Yes." or a faithful rewording as inferred.

It also caught a genuine gap the answer key had missed. *"Is our data used to improve your products or train AI?"*: the policy rules out AI training but says nothing about product improvement. The answer key has been corrected.

## Results: prompt fixes (run 2)

Three prompt changes, all now in the notebook:
- a stricter definition of a "commitment request" for the classifier;
- drafting that answers only what was asked;
- grounding verdicts judged on meaning rather than wording, with the verbatim-quote check still enforced in code.

To save cost, run 2 re-ran only **21 questions**: the 14 answerable questions run 1 sent to review, the corrected 3.12, and 6 safety checks (traps, restricted and implied-only questions). Trail in [`results/run2_fixes_audit.csv`](../results/run2_fixes_audit.csv).

| On these 21 questions | Run 1 | Run 2 |
|---|---|---|
| Correct outcome | 7 / 21 | **14 / 21** |
| Answerable questions wrongly sent to review | 14 | **7** |
| Safety checks still held (traps escalated, restricted and implied-only kept from auto-approve) | 6 / 6 | **6 / 6** |
| Average claims per answer | 5.0 | **3.2** |
| Average answer length | 56 words | **40 words** |

**Half the misses recovered, with no loss of safety.**
- **Fixes that worked:** breach-notification timeframe and sub-processor notice are no longer treated as commitments, and answers are shorter and stick to the question.
- **Still sent to review (7):**
  - *Over-answering persists in places.* For example, the NIST answer still adds the AI Governance Group.
  - *Connecting phrases get marked inferred*, such as "because of these limitations".
  - *The classifier still reads "Will you provide a certificate of deletion?"* as a commitment.
  - *Two are arguably right to go to review.* "Independent" SOC 2 audit and "includes production access" are not literally stated in the policy.

**Projected over the full 60** (the other 39 weren't re-run): about 34 / 41 answerable questions auto-approved, an auto-answer rate of roughly 57% against 45% in run 1.

## Results: three pipelines compared (run 3)

The same 60 questions and the same answer key, run through `notebooks/cost_comparison.ipynb`:

- **A:** Opus does everything (run 1).
- **B:** Haiku classifies, searches and checks; Sonnet writes.
- **C:** a hybrid. [Jev](https://docs.typesafe.ai), a *decision model* from TypeSafe AI, makes every yes/no and pick-one judgement with calibrated probabilities. Claude only writes (Sonnet) and extracts claims (Haiku). Code checks quotes and numbers.

| | A: Opus | B: Claude tiered | **C: Jev hybrid** |
|---|---|---|---|
| Correct outcome | 46 / 60 | 46 / 60 | 45 / 60 |
| Answerable questions auto-approved | 27 / 41 | 30 / 41 | **31 / 41** |
| **Unsafe auto-approvals** | **0** | **0** | **0** |
| Traps escalated / restricted held back | 6/6, 5/5 | 6/6, 5/5 | 6/6, 5/5 |
| Cost per 60-question run | ≈ $2.20 (estimated) | $0.34 (measured) | **$0.16 (measured)** |
| Wall-clock time | minutes | 107 s | **38 s** |

Files: [`run3_B_full_audit.csv`](../results/run3_B_full_audit.csv), [`run3_C_full_audit.csv`](../results/run3_C_full_audit.csv), plus measured token usage in the matching `_cost.json` files. A ran before the run 2 prompt fixes; B and C include them.

**What the comparison shows**

- **Safety holds at a fraction of the cost.** Both cheaper pipelines escalated every trap and held back every restricted question. C did slightly more useful work than A for about 7% of the cost.
- **Why C is cheapest.**
  - Jev's relevance gate passes Sonnet only the sections that matter, usually one. In total, B's Sonnet read about 2.3× more input than C's.
  - Questions where no section passes are escalated with no Claude call at all: 15 of 60 in C.
  - Jev's 551 requests cost about a third of a cent in total.
- **The strongest argument for the hybrid is tunability, not price.**
  - B's misses come from Haiku's word-based verdicts (17 "inferred" claims, two over-flagged commitments). Changing that means rewriting prompts and paying for another run.
  - C's misses come mostly from **thresholds on saved probabilities**, which can be re-scored for free. Jev rated every restricted question 0.83–0.96 for asking a commitment, and every other question 0.38 or lower, apart from one borderline wording at 0.62.
  - Moving two thresholds ("uncertain" from 0.3 to 0.4; completeness from 0.7 to 0.6) re-scores the same run to **50 / 60 correct, 36 / 41 auto-approved, still 0 unsafe**, with no new API calls. *Caveat: those thresholds were tuned on the same 60 questions, so a held-out set is needed to confirm them (Phase 4).*
- **What thresholds can't fix in C.**
  - The relevance gate is too strict on two-part questions ("SAML **and** SCIM?"), because each section answers only half.
  - Five implied-only questions were escalated without a draft. That's safe, but less helpful.
  - One answer lost its citation in Haiku's claim extraction.

## Results: tuned Jev hybrid (run 4)

Pipeline C re-run on all 60 questions with three changes:
- the tuned thresholds;
- a gate question that accepts passages answering *part* of a question;
- a fallback for claims Haiku returns without a source.

Trail in [`run4_C_tuned_audit.csv`](../results/run4_C_tuned_audit.csv).

| | A: Opus | C: Jev hybrid (run 3) | **C: tuned (run 4)** |
|---|---|---|---|
| Correct outcome | 46 / 60 | 45 / 60 | **50 / 60** |
| Answerable questions auto-approved | 27 / 41 | 31 / 41 | **36 / 41** |
| Unsafe auto-approvals | 0 | 0 | **0** |
| Cost per run | ≈ $2.20 (est.) | $0.16 | **$0.17** |
| Time | minutes | 38 s | **33 s** |

**The re-scored prediction held exactly:** 50 / 60 and 36 / 41, confirmed by a real run with zero unsafe outcomes. Against the Opus baseline, that's 9 more answers ready to send without human review, at about 8% of the cost.

**What's left (10 questions, all routed to a human, so none unsafe):**
- **Five implied-only questions are escalated rather than drafted.** BYOK, external red-teaming, bias testing, watermarking and language support: the policy only hints at an answer, and Sonnet declined to draft one.
- **Jev's literal reading (a known limitation in TypeSafe's docs).** Drafts that named the prospect ("Globex is the data controller") were judged to **contradict** a policy that says "the customer is the data controller". This caused 2 of the 10 misses. Planned fix: answers should say "the customer", never the prospect's name. That also makes approved answers reusable across prospects in the Phase 3 answer library.
- **Two-part questions on the relevance line.** For "SAML **and** SCIM?", the evidence check now passes (0.92), but the SSO section scored 0.41 on relevance, against a 0.45 floor.
- **One borderline commitment wording.** "Will you provide a certificate of deletion?" scored 0.61, so it was held for review.

*Caveat: the thresholds were tuned on these same 60 questions. A held-out question set (Phase 4) is needed to confirm they generalise.*

## Phase 3: human review and the answer library

`notebooks/review_and_library.ipynb` builds on the Jev hybrid and adds the two things a real team needs:

- **Review inside the graph.** One LangGraph graph answers every question in parallel (`Send`), then pauses on each one that needs a human, using `interrupt()`. Restricted questions come first, then escalations, Low and Medium. The reviewer can **approve**, **edit** or **reject**, and every decision is recorded with their name, the time and an optional comment.
  - A **SQLite checkpointer** saves the graph after every decision. The reviewer can stop half-way and resume later, even from a fresh graph object, and nothing is answered or paid for twice.
  - The `review` node only *collects* decisions. LangGraph replays them on each resume, so every write happens once, in `finalise`.
- **An answer library that learns from reviewers.** Approved and edited answers are stored with their policy sections **and those sections' versions**. On the next questionnaire, each question is checked against the library first:
  1. full-text search finds the closest approved questions;
  2. any answer whose policy section has changed version since approval is discarded as stale;
  3. Jev judges whether the new question asks for *the same information*.

  A hit reuses the approved answer with **no Claude call**. Commitment questions are the exception: their reused answer becomes a draft for a human, because commitments always get a fresh look.
- **Two drafting changes from run 4.**
  - Answers say "the customer", never the prospect's name. That keeps them reusable, and fixes Jev's literal-reading misses.
  - Caveats go in a separate **reviewer note**, never in customer-facing text.
- **Outputs:**
  - the prospect's questionnaire with the *final* answers;
  - an audit CSV with draft vs final answer, decision, reviewer, time and evidence;
  - the library itself (`answer_library.db`), to re-upload next time.

**First live run (smoke, 10 questions; [`run5_review_smoke_audit.csv`](../results/run5_review_smoke_audit.csv)):**
- 4 answers were auto-approved and 6 went to review. The reviewer rejected all 6 to test the flow, and each rejection was recorded with name and time.
- No draft named the prospect.
- Caveats stayed in reviewer notes, never in the answer.

One gap it exposed: two *auto-approved* answers carried reviewer notes that no human would see. For example: *"confirm the certificate is in date before sending."* Notes on auto-approved answers need to reach a person. **Fixed:** a new `note_check` step asks Jev whether the note says something must be checked before sending. If so, the answer is held for a human. Purely informational notes, like *"SUB-3 doesn't say what happens after an objection"*, don't hold anything up.

*Earlier offline testing covered a review paused and resumed, a second run reusing approved answers with zero Claude calls for them, a restricted reuse routed to a human, and a stale answer refused after its policy version changed.*

**Note check confirmed live (second smoke run):** the ISO 27001 answer, auto-approved before, now goes to review with *"reviewer note asks for a check before sending (p=0.95)"*. The sub-processor answer, whose note is only informational, stays auto-approved. One effect to measure on a full run: the drafter writes cautious notes often, so the auto-approval rate may drop.

**Full run with review (run 6; [`run6_full_review_audit.csv`](../results/run6_full_review_audit.csv)):**
- All 60 questions, then 31 reviewed. One answer was approved and one edited, and both went into the library. The other 29 were rejected as a test.
- 0 unsafe auto-approvals, and no draft named the prospect.
- The "customer" wording fixed both run-4 contradictions caused by Jev's literal reading.
- **But auto-approvals fell from 36 to 29 of 41.** The note check alone held back 7 answerable questions. Sonnet wrote a note on nearly every answer, and the hold line (0.4) was too low.
  - Notes on answers that stayed auto-approved scored 0.10–0.39.
  - The 7 held scored 0.45–0.95. The highest were the genuinely useful ones: *"confirm the certificate is current"* (0.71), and *"the policy doesn't say when the 15-minute clock starts"* (0.95).
  - Raising the hold line to 0.7 would have released the 3 informational notes, re-scoring to 32 / 41 with no new API calls. The drafting prompt now also asks for a note only when the reviewer should act on something.
  - That's the precision/recall trade-off of an extra safety layer, and the saved probabilities make it measurable.

**Library reuse and the tightened note check (run 7; [`run7_library_reuse_audit.csv`](../results/run7_library_reuse_audit.csv)):**

| | Run 6 | **Run 7** |
|---|---|---|
| Correct outcome | 43 / 60 | **47 / 60** |
| Answerable questions auto-approved | 29 / 41 | **33 / 41** |
| Unsafe auto-approvals | 0 | **0** |
| Drafts carrying a reviewer note | almost all | **16 of 44** |
| Answers reused from the library | 0 | **2** |
| Cost | $0.23 | **$0.20** |

- **The library reused answers live.**
  - ISO 27001, approved by the reviewer in run 6, matched with Jev same-question p=0.99. It was auto-approved with no Claude call and no review.
  - The 24-hour commitment, edited in run 6, matched at p=0.98. Because it's a commitment, it came back to the reviewer as a draft rather than going out. Re-approving it didn't create a duplicate entry.
- **The tightened note check held only notes that matter**, e.g. *"The policy is ambiguous on whether the 30-day production deletion window starts at termination or at the end of the 30-day export period"* (p=0.95). It no longer held routine commentary.
- *Tested offline only:* refusing a stale library answer when its policy section changes version.

**Phase 3 is complete.** Next is Phase 4: a Streamlit review screen, held-out evals, the `src/` package, and filling in Yes/No dropdown columns.
