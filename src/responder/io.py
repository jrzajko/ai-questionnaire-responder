"""Read messy questionnaires (XLSX/CSV) and write completed ones back in the prospect's own layout."""
from __future__ import annotations

import csv
import json
import pathlib
import re

import openpyxl
from openpyxl.styles import Alignment, PatternFill

Q_HDR = re.compile(r"^\s*(question|questions|question text|requirement|control question)\b", re.I)
REF_HDR = re.compile(r"^\s*(ref\.?|reference|q\s*#|q\s*no\.?|#|id|no\.?|item|question id|control id)\s*$", re.I)
ANS_HDRS = [r"supplier response", r"vendor response", r"\banswer\b", r"supporting comments", r"\bcomments?\b",
            r"\bresponse\b"]                                   # first match wins
CHOICE_HDR = re.compile(r"^\s*(response|yes\s*/\s*no|y\s*/\s*n|compliant\??)\s*$", re.I)
EVID_HDR = re.compile(r"evidence|supporting doc", re.I)
NOT_OURS = re.compile(r"reviewer|internal|office use|assessor|score|weight", re.I)   # columns we must not fill
SUBQ = re.compile(r"^\s*\(?([a-h]|i{1,3}|iv|v)\)\s+")
DEFAULT_CHOICES = ["Yes", "No", "Partial", "N/A"]
FILL = {"auto_approved": "E2EFDA", "approved": "E2EFDA", "edited": "E2EFDA", "rejected": "F8CBAD"}


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _read_grid(path: pathlib.Path) -> dict:
    """{sheet: {"rows": {r: [values]}, "merged": {r: text}, "choices": {(r, c): [options]}}}"""
    if path.suffix.lower() == ".csv":
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        return {"csv": {"rows": {i + 1: r for i, r in enumerate(rows)}, "merged": {}, "choices": {}}}
    wb = openpyxl.load_workbook(path)
    out = {}
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            continue
        rows = {r: [c.value for c in row] for r, row in enumerate(ws.iter_rows(), start=1)}
        merged = {}
        for rng in ws.merged_cells.ranges:
            if rng.max_col > rng.min_col:
                for r in range(rng.min_row, rng.max_row + 1):
                    merged[r] = _txt(ws.cell(rng.min_row, rng.min_col).value)
        choices = {}
        for dv in ws.data_validations.dataValidation:              # dropdown lists such as "Yes,No,N/A,Partial"
            if dv.type == "list" and dv.formula1 and dv.formula1.startswith('"'):
                opts = [o.strip() for o in dv.formula1.strip('"').split(",") if o.strip()]
                for rng in dv.sqref.ranges:
                    for r in range(rng.min_row, rng.max_row + 1):
                        for c in range(rng.min_col, rng.max_col + 1):
                            choices[(r, c - 1)] = opts
        out[ws.title] = {"rows": rows, "merged": merged, "choices": choices}
    return out


def _find_layout(rows: dict, scan: int = 25):
    for r in sorted(rows)[:scan]:
        hdr = {c: _txt(v) for c, v in enumerate(rows[r]) if _txt(v)}
        q_col = next((c for c, h in hdr.items() if Q_HDR.search(h) and not NOT_OURS.search(h)), None)
        if q_col is None:
            continue
        ans_col = None
        for pat in ANS_HDRS:
            ans_col = next((c for c, h in hdr.items()
                            if c != q_col and re.search(pat, h, re.I) and not NOT_OURS.search(h)), None)
            if ans_col is not None:
                break
        if ans_col is None:
            continue
        return {"header_row": r, "q": q_col, "answer": ans_col, "headers": hdr,
                "ref": next((c for c, h in hdr.items() if REF_HDR.match(h)), None),
                "choice": next((c for c, h in hdr.items() if c not in (ans_col, q_col) and CHOICE_HDR.match(h)), None),
                "evidence": next((c for c, h in hdr.items()
                                  if c != ans_col and EVID_HDR.search(h) and not NOT_OURS.search(h)), None)}
    return None


def extract_questions(path) -> tuple[list[dict], list[str]]:
    """Find every unanswered question on every tab, whatever the layout. Returns (items, report lines)."""
    path = pathlib.Path(path)
    items, report = [], []
    for sheet, g in _read_grid(path).items():
        rows, merged = g["rows"], g["merged"]
        lay = _find_layout(rows)
        if not lay:
            report.append(f"{sheet}: no question table found, skipped")
            continue
        h = lay["headers"]
        report.append(f"{sheet}: header row {lay['header_row']}, question='{h[lay['q']]}', answer='{h[lay['answer']]}'"
                      + (f", dropdown='{h[lay['choice']]}'" if lay["choice"] is not None else ""))
        section, n, prefilled = "", 0, 0
        for r in sorted(rows):
            if r <= lay["header_row"]:
                continue
            vals = list(rows[r]) + [None] * 30
            if r in merged:                                        # section header or footer row
                section = merged[r]
                continue
            q = _txt(vals[lay["q"]])
            if len(q) < 10 or not re.search(r"[A-Za-z]{3}", q):
                continue
            if _txt(vals[lay["answer"]]):
                prefilled += 1
                continue
            ref = _txt(vals[lay["ref"]]) if lay["ref"] is not None else ""
            model_q = re.sub(r"\s+", " ", q)
            if SUBQ.match(q) and section:                          # a) b) c) get their parent's context
                model_q = f"{re.sub(r'^[\d.]+\s*', '', section)}: {SUBQ.sub('', model_q)}"
            choice_col = lay["choice"]
            items.append({"sheet": sheet, "row": r, "ref": ref or f"{sheet}!{r}", "question": q,
                          "model_question": model_q, "section": section, "answer_col": lay["answer"],
                          "evidence_col": lay["evidence"], "choice_col": choice_col,
                          "choice_options": (g["choices"].get((r, choice_col), DEFAULT_CHOICES)
                                             if choice_col is not None else None)})
            n += 1
        report[-1] += f" -> {n} questions" + (f" ({prefilled} already answered)" if prefilled else "")
    return items, report


def write_completed(src_path, final: list[dict], out_path) -> str:
    """Write final answers into the prospect's own cells, keeping their formatting, tabs and dropdowns."""
    src_path = pathlib.Path(src_path)
    if src_path.suffix.lower() == ".csv":
        rows = list(csv.reader(open(src_path, newline="", encoding="utf-8-sig")))
        by_row = {r["row"]: r for r in final}
        for i, row in enumerate(rows, start=1):
            if i in by_row:
                r = by_row[i]
                row += [""] * (r["answer_col"] + 1 - len(row))
                row[r["answer_col"]] = r["final_answer"] or "[NEEDS SME]"
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
        return str(out_path)
    wb = openpyxl.load_workbook(src_path)
    for r in final:
        ws = wb[r["sheet"]]
        c = ws.cell(r["row"], r["answer_col"] + 1, r["final_answer"] or "[NEEDS SME]")
        c.fill = PatternFill("solid", fgColor=FILL.get(r["decision"], "F8CBAD"))
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if r.get("evidence_col") is not None and r["final_answer"] and r.get("source_titles"):
            ws.cell(r["row"], r["evidence_col"] + 1, "; ".join(r["source_titles"]))
        choice = (r.get("response_choice") or {}).get("choice")
        if choice and r.get("choice_col") is not None:
            ws.cell(r["row"], r["choice_col"] + 1, choice)
    wb.save(out_path)
    return str(out_path)


AUDIT_COLUMNS = ["sheet", "ref", "row", "question", "category", "confidence", "status", "library_hit", "draft_answer",
                 "reviewer_note", "final_answer", "response_choice", "decision", "edited", "reviewer", "decided_at",
                 "review_comment", "sources", "reasons", "signals", "claims", "run_id"]


def audit_rows(final: list[dict], run_id: str = "") -> list[dict]:
    return [{"sheet": r["sheet"], "ref": r["ref"], "row": r["row"], "question": r["question"],
             "category": r["category"], "confidence": r["confidence"], "status": r["status"],
             "library_hit": bool(r["signals"].get("library_match")), "draft_answer": r["draft_answer"],
             "reviewer_note": r.get("reviewer_note", ""), "final_answer": r["final_answer"],
             "response_choice": (r.get("response_choice") or {}).get("choice", ""), "decision": r["decision"],
             "edited": r["decision"] == "edited", "reviewer": r.get("reviewer", ""), "decided_at": r.get("decided_at", ""),
             "review_comment": r.get("review_comment", ""), "sources": "; ".join(r["sources"]),
             "reasons": " | ".join(r["reasons"]), "signals": json.dumps(r["signals"]), "claims": json.dumps(r["claims"]),
             "run_id": run_id} for r in final]
