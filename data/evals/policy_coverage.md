# Policy pack coverage map

Ground truth for evals: what the Acme SaaS policy pack answers, what it only implies, and what it deliberately leaves out. Not loaded into retrieval.

## Documents
| ID | Document | Main specialist |
|---|---|---|
| ISP | Information Security Policy | security |
| AIG | AI Use & Governance Statement | ai_governance |
| MC | Acme Assist Model Card | ai_governance |
| DR | Data Retention & Deletion | privacy |
| SUB | Sub-processor List | privacy |
| IR | Incident Response | security |
| HA | Hosting & Architecture | security |
| IAM | Identity, SSO & SCIM | security |
| PRV | Privacy & Data Protection | privacy |
| BCP | Business Continuity & DR | security |

## 1. Explicitly covered (expected: High)
Examples: ISO 27001 (ISP-3), SOC 2 Type II (ISP-3), encryption at rest/in transit (ISP-6), MFA (ISP-5), no training on customer data (AIG-3), AI off by default (AIG-4), human review of AI output (AIG-6), hosting region (HA-1), RTO/RPO (BCP-1), sub-processor notice period (SUB-3), deletion after termination (DR-2).

## 2. Inferred or partial (expected: Medium)
| Question | Why it is only partial |
|---|---|
| Do you support customer-managed encryption keys (BYOK)? | ISP-6 says keys are managed by Acme; "no BYOK" is implied, never stated. |
| Do you perform AI red-teaming by an external party? | AIG-10 covers internal adversarial testing only. |
| Do you test AI for bias? | AIG-7 impact assessment covers fairness risk; no bias testing is described. |
| Is Acme Assist available in French or German? | MC-2 says intended for English; MC-6 says non-English is weaker. Not a firm no. |
| Is ISO 42001 certification held? | AIG-8: working towards it, gap assessment done. Answer is "no, in progress". |

## 3. Restricted categories (expected: always route to human, even with evidence)
| Question | Evidence | Why restricted |
|---|---|---|
| Will you commit to breach notification within 24 hours in the contract? | IR-4 says 48 hours | Contractual commitment that differs from policy |
| Do you guarantee 99.99% uptime with service credits? | HA-5 says 99.9% target | SLA / financial commitment |
| Do you guarantee AI outputs are accurate? | MC-6 says they can be wrong | Guarantee |
| Will you accept unlimited liability for data breaches? | none | Liability |
| Can you share the full penetration test report? | ISP-7: executive summary under NDA | Disclosure under NDA |

## 4. Deliberate gaps / traps (expected: "Not covered by policy, escalate")
1. Do you have a public bug bounty programme?
2. What is the limit of your cyber insurance cover?
3. Are you PCI DSS compliant?
4. Do you hold FedRAMP authorisation?
5. Can data be hosted in the United States or Australia? (HA-2 says no other regions are offered "currently" — escalate for roadmap)
6. When will you achieve ISO 42001 certification? (no date committed)
7. Do you watermark AI-generated content? (labelling in UI is covered, watermarking is not)
8. Do you offer source code escrow?
9. What is your carbon footprint / do you have a net-zero target?
10. Which specific LLM version powers Acme Assist? (MC-4 says versions are pinned, but no model is named)

## Notes
- Fictional sub-processors (Northwind AI, Vectorly, Postmark Mail Co., HelpDeskly) avoid naming real vendors.
- Section IDs (e.g. `AIG-3`) are the citation unit. The chunker should split on `## ` headings.
