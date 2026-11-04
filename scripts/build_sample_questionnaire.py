"""Builds a deliberately messy prospect questionnaire (XLSX) + the golden answer key (CSV)."""
import csv
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.comments import Comment

OUT_XLSX = "data/questionnaires/globex_vendor_due_diligence_2026.xlsx"
OUT_KEY = "data/evals/golden_set.csv"

# Expected outcomes for evals:
#   high      - explicit answer in the pack, should auto-approve
#   medium    - only implied / partial; draft + human review
#   gap       - not covered: "Not covered by policy, escalate"
#   restricted- commitment/guarantee/liability/confidential: always human review
#   partial   - multi-part, one part covered and one part a gap: human review

SEC = [  # (ref, question, guidance, expected, sources, note) ; ref=None -> section header row
    (None, "1.1  Governance & Certifications"),
    ("1.1.1", "Do you hold a current ISO/IEC 27001 certification? If yes, state the scope of the certificate.", "Attach certificate.", "high", "ISP-3", ""),
    ("1.1.2", "Do you undergo an independent SOC 2 Type II audit? Which Trust Services Criteria are in scope?", "", "high", "ISP-3", ""),
    ("1.1.3", "Are you PCI DSS compliant? If so, state your merchant/service provider level.", "", "gap", "", "trap: PCI not in pack"),
    ("1.1.4", "Who is accountable for information security within your organisation, and to whom do they report?", "", "high", "ISP-2", ""),
    ("1.1.5", "Please provide a copy of your full, most recent penetration test report.", "Report must be dated within the last 12 months.", "restricted", "ISP-7", "only exec summary under NDA"),
    (None, "1.2  Access Control & Identity"),
    ("1.2.1", "Is multi-factor authentication enforced for all workforce accounts, including those with production access?", "", "high", "ISP-5", ""),
    ("1.2.2", "Within what timeframe is a leaver's access revoked?", "", "high", "ISP-5", ""),
    ("1.2.3", "Does the platform support SAML 2.0 single sign-on and SCIM 2.0 user provisioning?", "State any plan restrictions.", "high", "IAM-1;IAM-2", "SCIM is Enterprise-only"),
    ("1.2.4", "Can our administrators configure session timeouts? Please state the configurable range.", "", "high", "IAM-5", ""),
    (None, "1.3  Cryptography"),
    ("1.3.1", "Describe how customer data is encrypted in transit and at rest.\nInclude algorithms, protocol versions and the key management service used.", "", "high", "ISP-6", "multi-line cell"),
    ("1.3.2", "Do you support customer-managed encryption keys (BYOK / HYOK)?", "", "medium", "ISP-6", "'no' is implied, never stated"),
    (None, "1.4  Vulnerability Management"),
    ("1.4.1", "What are your remediation SLAs for critical and high severity vulnerabilities?", "", "high", "ISP-7", "'SLA' here is internal targets, keyword rule may over-flag"),
    ("1.4.2", "Do you operate a public bug bounty or responsible disclosure programme?", "", "gap", "", "trap"),
    ("1.4.3", "How often is an independent penetration test performed?", "", "high", "ISP-7", ""),
    (None, "1.5  Hosting, Resilience & Incident Response"),
    ("1.5.1", "In which country/region is customer data hosted? Can Globex require the data to be hosted in the United States?", "", "partial", "HA-1;HA-2", "first part covered, US hosting is a roadmap question"),
    ("1.5.2", "What are your RTO and RPO for a full loss of your primary hosting region?", "", "high", "BCP-1", ""),
    ("1.5.3", "Within what timeframe will you notify us of a confirmed personal data breach?", "", "high", "IR-4", ""),
    ("1.5.4", "Will you contractually commit to notifying Globex of ANY security incident within 24 hours?", "", "restricted", "IR-4", "policy says 48h for breaches"),
    ("1.5.5", "What is the limit of indemnity of your cyber insurance policy?", "", "gap", "", "trap"),
    ("1.5.6", "Do you offer source code escrow?", "", "gap", "", "trap"),
    ("1.10", "How frequently is your incident response plan tested?", "", "high", "IR-6", "ref '1.10' stored as text; out of sequence"),
]

AI = [  # (ref, control area, framework mapping, question, mandatory, expected, sources, note)
    ("AI-01", "System description", "NIST AI RMF MAP 1.1; EU AI Act Art. 13", "Describe the AI-enabled features in your product and their intended use.", "Y", "high", "AIG-1;MC-2", ""),
    ("AI-02", "Training data", "ISO 42001 A.7.2; NIST MAP 4.1", "Do you train, fine-tune or otherwise improve any AI model using customer data, including prompts and outputs?", "Y", "high", "AIG-3", "duplicate of 3.12"),
    ("AI-03", "Third parties", "ISO 42001 A.10.3; NIST GOVERN 6.1", "Which third-party AI model providers process our data, and in which locations?", "Y", "high", "SUB-1;AIG-2", "answer is in privacy doc"),
    ("AI-04", "Third parties", "NIST MAP 4.1", "Which specific foundation model(s) and version(s) power your AI features?", "Y", "gap", "", "trap: MC-4 says versions pinned, none named"),
    ("AI-05", "Data retention", "ISO 42001 A.7.3", "How long do your model providers retain our prompts and outputs, and for what purpose?", "Y", "high", "AIG-3", ""),
    ("AI-06", "Data retention", "ISO 42001 A.7.3", "How long are AI prompts and outputs stored within your platform? Can we shorten or disable this?", "Y", "high", "DR-4", "answer is in retention doc"),
    ("AI-07", "Customer control", "EU AI Act Art. 26; NIST MANAGE 2.4", "Are AI features enabled by default? Can our administrators disable them or restrict them to specific user groups?", "Y", "high", "AIG-4", ""),
    ("AI-08", "Security", "NIST MEASURE 2.7; ISO 42001 A.6.2.6", "How do you prevent AI features from exposing content to users who are not authorised to see it?", "Y", "high", "AIG-5;MC-7", ""),
    ("AI-09", "Human oversight", "EU AI Act Art. 14; NIST MANAGE 2.2", "Describe the human oversight applied to AI-generated outputs before they are used.", "Y", "high", "AIG-6", ""),
    ("AI-10", "Governance", "ISO 42001 5.3; NIST GOVERN 2.1", "Do you have a body responsible for AI governance? Describe its membership, cadence and approval process.", "Y", "high", "AIG-7", ""),
    ("AI-11", "Certification", "ISO 42001", "Are you certified to ISO/IEC 42001? If not, by what date do you expect to achieve certification?", "Y", "partial", "AIG-8", "in progress; no date"),
    ("AI-12", "Framework alignment", "NIST AI RMF", "How does your AI programme align to the NIST AI Risk Management Framework?", "N", "high", "AIG-8", ""),
    ("AI-13", "Regulatory", "EU AI Act Art. 6, 50", "How have you classified your AI system(s) under the EU AI Act, and which obligations apply to you?", "Y", "high", "AIG-9", ""),
    ("AI-14", "Inventory", "ISO 42001 A.4.2; NIST GOVERN 1.6", "Do you maintain an inventory of AI systems, including internally used AI tools?", "N", "high", "AIG-8", ""),
    ("AI-15", "Testing & evaluation", "NIST MEASURE 2.5; ISO 42001 A.6.2.4", "How do you evaluate AI outputs for accuracy and hallucination before release? Please include any acceptance thresholds.", "Y", "high", "AIG-10;MC-5", "95% threshold in MC-5"),
    ("AI-16", "Testing & evaluation", "NIST MEASURE 2.7", "Do you engage independent third parties to red-team your AI systems?", "N", "medium", "AIG-10", "internal adversarial testing only"),
    ("AI-17", "Fairness", "NIST MEASURE 2.11; EU AI Act Art. 10", "How do you test for and mitigate bias in AI outputs?", "Y", "medium", "AIG-7", "impact assessment covers fairness; no testing described"),
    ("AI-18", "Transparency", "NIST MAP 2.2; EU AI Act Art. 13", "What are the known limitations of your AI features?", "Y", "high", "MC-6", ""),
    ("AI-19", "Transparency", "EU AI Act Art. 50(2)", "Do you watermark or otherwise machine-mark AI-generated content?", "N", "medium", "AIG-6", "UI labelling covered; watermarking not"),
    ("AI-20", "Accuracy", "", "Can you guarantee that AI-generated summaries and minutes are accurate and complete?", "Y", "restricted", "MC-6", "guarantee"),
    ("AI-21", "Incident response", "NIST MANAGE 4.3; ISO 42001 A.8.4", "If an AI incident occurs, how quickly can AI features be disabled?", "Y", "high", "IR-5", "answer is in IR doc"),
    ("AI-22", "Impact assessment", "ISO 42001 6.1.4; GDPR Art. 35", "Do you perform an AI impact assessment and/or DPIA before launching new AI features?", "Y", "high", "AIG-7;PRV-5", "two docs"),
    ("AI-23", "Language support", "", "Are AI features supported in languages other than English (e.g. French, German)?", "N", "medium", "MC-2;MC-6", ""),
    ("AI-24", "Legal", "", "Will you indemnify Globex against third-party intellectual property claims arising from AI-generated output?", "Y", "restricted", "", "indemnity"),
    ("AI-25", "Automated decisions", "GDPR Art. 22", "Are your AI features used to make automated decisions that have legal or similarly significant effects on individuals?", "Y", "high", "AIG-1", ""),
]

PRV = [  # (question, ref, expected, sources, note) ; ref "3.4" parent row has no answer
    ("Please confirm your role (controller or processor) in respect of Globex personal data.", "3.1", "high", "PRV-1", ""),
    ("Which data protection laws and regulations does your processing comply with?", "3.2", "high", "PRV-2", ""),
    ("Please provide the contact details of your Data Protection Officer.", "3.3", "high", "PRV-3", ""),
    ("Data retention and deletion", "3.4", None, None, "parent row, not a question"),
    ("    a) How long after contract termination is our data deleted from (i) production and (ii) backups?", "3.4(a)", "high", "DR-2;DR-3", "sub-question"),
    ("    b) Will you provide a certificate of deletion?", "3.4(b)", "high", "DR-2", "sub-question"),
    ("    c) What happens to items our users delete during the subscription?", "3.4(c)", "high", "DR-1", "sub-question"),
    ("How much notice do you give before engaging a new sub-processor, and can we object?", "3.5", "high", "SUB-3", ""),
    ("Is any personal data transferred outside the UK/EEA? If so, which transfer mechanisms are used?", "3.6", "high", "SUB-4", ""),
    ("How will you support Globex in responding to data subject requests?", "3.7", "high", "PRV-4", ""),
    ("Is the platform designed for storing special category personal data (e.g. health data)?", "3.8", "high", "PRV-7", ""),
    ("Is production customer data ever used in development or test environments?", "3.9", "high", "ISP-8", "answer is in security doc"),
    ("What is your organisation's carbon footprint, and do you have a net-zero target?", "3.10", "gap", "", "trap: off-topic ESG question"),
    ("Do you accept unlimited liability for breaches of data protection obligations?", "3.11", "restricted", "", "liability"),
    ("Is Globex data used to improve your products or to train AI models?", "3.12", "medium", "AIG-3", "duplicate-ish of AI-02; product improvement not covered"),
]

# ---------- styling
F = "Arial"
title_font = Font(name=F, size=14, bold=True, color="FFFFFF")
hdr_font = Font(name=F, size=10, bold=True, color="FFFFFF")
body = Font(name=F, size=10)
bold = Font(name=F, size=10, bold=True)
ital = Font(name=F, size=9, italic=True, color="555555")
navy = PatternFill("solid", fgColor="1F3864")
teal = PatternFill("solid", fgColor="2F5597")
sect = PatternFill("solid", fgColor="D9E1F2")
inp = PatternFill("solid", fgColor="FFF2CC")
thin = Side(style="thin", color="BFBFBF")
box = Border(left=thin, right=thin, top=thin, bottom=thin)
wrap = Alignment(wrap_text=True, vertical="top")

def cell(ws, ref, value, font=body, fill=None, align=wrap, border=box):
    c = ws[ref]; c.value = value; c.font = font
    if fill: c.fill = fill
    if align: c.alignment = align
    if border: c.border = border
    return c

wb = Workbook()

# ---------- Cover
ws = wb.active; ws.title = "Cover"
ws.sheet_view.showGridLines = False
ws.column_dimensions["A"].width = 3; ws.column_dimensions["B"].width = 34; ws.column_dimensions["C"].width = 60
ws.merge_cells("B2:C2"); cell(ws, "B2", "GLOBEX HOLDINGS PLC", title_font, navy, Alignment(vertical="center"), None)
ws.merge_cells("B3:C3"); cell(ws, "B3", "Third-Party Supplier Security & AI Due Diligence Questionnaire (v3.2, 2026)", Font(name=F, size=11, bold=True, color="FFFFFF"), navy, None, None)
ws.row_dimensions[2].height = 28
rows = [("Supplier name", ""), ("Product / service assessed", ""), ("Completed by (name, role)", ""),
        ("Date completed", ""), ("Globex contact", "Third-Party Risk Team (tprm@globex.example)"),
        ("Return by", "4 weeks from date of issue"), ("Classification", "CONFIDENTIAL when completed")]
for i, (k, v) in enumerate(rows, start=5):
    cell(ws, f"B{i}", k, bold)
    cell(ws, f"C{i}", v, body, inp if not v else None)
ws["B13"] = "Cells shaded yellow are for the supplier to complete."; ws["B13"].font = ital

# ---------- Instructions
ws = wb.create_sheet("Instructions")
ws.sheet_view.showGridLines = False
ws.column_dimensions["A"].width = 3; ws.column_dimensions["B"].width = 110
ws.merge_cells("B2:B2"); cell(ws, "B2", "Instructions for suppliers", title_font, navy, None, None)
text = [
    "1. Answer every question on tabs '1. InfoSec', '2. AI Governance' and '3. Data Protection'. Responses go in the yellow cells.",
    "2. Where a Yes/No/N/A response is requested, select from the drop-down AND provide supporting detail in the comments column.",
    "3. Questions marked Mandatory = Y must be answered; incomplete questionnaires will be returned.",
    "4. Do not change question wording, add rows or delete rows. Reference supporting evidence by document name and section.",
    "5. Statements made in this questionnaire may be incorporated into the contract. Do not make commitments you cannot meet.",
    "",
    "Example of a completed row (tab 1):",
    "   Ref 1.0.0 | Question: Do you have a documented information security policy? | Response: Yes | Comments: Our Information Security Policy (v4.1) is reviewed annually and approved by the Head of Security. | Evidence: ISP §1-2",
]
for i, t in enumerate(text, start=4):
    cell(ws, f"B{i}", t, bold if t.startswith("Example") else body, None, Alignment(wrap_text=True), None)

yesno = lambda: DataValidation(type="list", formula1='"Yes,No,N/A,Partial"', allow_blank=True)

# ---------- 1. InfoSec : title block rows 1-4, header row 6, cols A Ref | B Question | C Guidance | D Response | E Comments | F Evidence | G Weight (hidden)
ws = wb.create_sheet("1. InfoSec")
ws.sheet_view.showGridLines = False
for col, w in zip("ABCDEFG", (9, 62, 26, 12, 55, 18, 8)):
    ws.column_dimensions[col].width = w
ws.merge_cells("A1:F1"); cell(ws, "A1", "Section 1 — Information Security", title_font, navy, Alignment(vertical="center"), None)
ws.merge_cells("A2:F2"); cell(ws, "A2", "Please complete all yellow cells. Evidence may be requested for any 'Yes' response.", ital, None, None, None)
ws.row_dimensions[1].height = 24
hdrs = ["Ref", "Question", "Guidance for supplier", "Response", "Supporting comments", "Evidence ref.", "Wt"]
for j, h in enumerate(hdrs):
    cell(ws, f"{'ABCDEFG'[j]}6", h, hdr_font, teal, Alignment(wrap_text=True, vertical="center"))
dv = yesno(); ws.add_data_validation(dv)
r = 7
for item in SEC:
    if item[0] is None:
        r += 1  # blank spacer row before each section
        ws.merge_cells(f"A{r}:F{r}"); cell(ws, f"A{r}", item[1], bold, sect, Alignment(vertical="center"))
        r += 1; continue
    ref, q, guide, *_ = item
    cell(ws, f"A{r}", ref); ws[f"A{r}"].number_format = "@"
    cell(ws, f"B{r}", q); cell(ws, f"C{r}", guide or None, ital)
    cell(ws, f"D{r}", None, body, inp); cell(ws, f"E{r}", None, body, inp); cell(ws, f"F{r}", None, body, inp)
    cell(ws, f"G{r}", 3 if ref.startswith(("1.1", "1.5")) else 2, ital)
    dv.add(f"D{r}")
    r += 1
r += 1
ws.merge_cells(f"A{r}:F{r}"); cell(ws, f"A{r}", "— End of Section 1 —", ital, None, Alignment(horizontal="center"), None)
ws.column_dimensions["G"].hidden = True
ws["A6"].comment = Comment("Internal: weights used by Globex TPRM scoring. Do not edit.", "Globex TPRM")
ws.freeze_panes = "C7"

# ---------- 2. AI Governance : header row 3, different column order
ws = wb.create_sheet("2. AI Governance")
ws.sheet_view.showGridLines = False
for col, w in zip("ABCDEFG", (8, 18, 24, 60, 11, 55, 16)):
    ws.column_dimensions[col].width = w
ws.merge_cells("A1:G1"); cell(ws, "A1", "Section 2 — Artificial Intelligence (complete if your service uses AI/ML)", title_font, navy, Alignment(vertical="center"), None)
ws.row_dimensions[1].height = 24
hdrs = ["Q#", "Control area", "Framework mapping", "Question", "Mandatory?", "Supplier response", "Attachments"]
for j, h in enumerate(hdrs):
    cell(ws, f"{'ABCDEFG'[j]}3", h, hdr_font, teal, Alignment(wrap_text=True, vertical="center"))
r = 4
for i, (ref, area, fw, q, mand, *_rest) in enumerate(AI):
    if ref in ("AI-10", "AI-20"):
        r += 1  # stray blank rows mid-table
    cell(ws, f"A{r}", ref); cell(ws, f"B{r}", area); cell(ws, f"C{r}", fw or None, ital)
    cell(ws, f"D{r}", q); cell(ws, f"E{r}", mand, body, None, Alignment(horizontal="center", vertical="top"))
    cell(ws, f"F{r}", None, body, inp); cell(ws, f"G{r}", None, body, inp)
    r += 1
cell(ws, f"A{r+1}", "Note: framework mappings are indicative only.", ital, None, None, None)
ws.freeze_panes = "E4"

# ---------- 3. Data Protection : header row 2, question in col A, ref in col B
ws = wb.create_sheet("3. Data Protection")
ws.sheet_view.showGridLines = False
for col, w in zip("ABCD", (70, 9, 55, 30)):
    ws.column_dimensions[col].width = w
cell(ws, "A1", "Section 3 — Data Protection & Privacy", title_font, navy, Alignment(vertical="center"), None)
ws.merge_cells("A1:D1"); ws.row_dimensions[1].height = 24
for j, h in enumerate(["Question", "Ref", "Answer", "Globex reviewer comment"]):
    cell(ws, f"{'ABCD'[j]}2", h, hdr_font, teal, Alignment(wrap_text=True, vertical="center"))
r = 3
for q, ref, exp, *_ in PRV:
    if exp is None:  # parent row
        ws.merge_cells(f"A{r}:D{r}")
        cell(ws, f"A{r}", f"{ref}  {q}", bold, sect)
    else:
        cell(ws, f"A{r}", q); cell(ws, f"B{r}", ref); ws[f"B{r}"].number_format = "@"
        cell(ws, f"C{r}", None, body, inp); cell(ws, f"D{r}", None, ital, PatternFill("solid", fgColor="EDEDED"))
    r += 1
ws.freeze_panes = "A3"

wb.save(OUT_XLSX)

# ---------- golden set
# Where a question sits on one tab but belongs to another specialist, accept either ("a|b").
CAT_OVERRIDE = {"3.9": "privacy|security", "3.12": "ai_governance|privacy", "3.10": "privacy|security",
                "1.5.3": "security|privacy", "AI-22": "ai_governance|privacy", "AI-06": "ai_governance|privacy",
                "AI-21": "ai_governance|security", "AI-24": "ai_governance|privacy"}
with open(OUT_KEY, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["sheet", "ref", "question", "expected_category", "expected_outcome", "expected_sources", "note"])
    for item in SEC:
        if item[0] is None: continue
        ref, q, _g, exp, src, note = item
        w.writerow(["1. InfoSec", ref, q.replace("\n", " "), CAT_OVERRIDE.get(ref, "security"), exp, src, note])
    for ref, area, fw, q, mand, exp, src, note in AI:
        w.writerow(["2. AI Governance", ref, q, CAT_OVERRIDE.get(ref, "ai_governance"), exp, src, note])
    for q, ref, exp, src, note in PRV:
        if exp is None: continue
        w.writerow(["3. Data Protection", ref, q.strip(), CAT_OVERRIDE.get(ref, "privacy"), exp, src, note])
print("ok")
