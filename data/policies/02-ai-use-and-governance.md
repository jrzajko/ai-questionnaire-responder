---
doc_id: AIG
title: AI Use & Governance Statement
version: 2.0
owner: Head of AI Product
last_reviewed: 2026-10-01
---

# AI Use & Governance Statement

## AIG-1 Scope
This statement covers Acme Assist, the generative AI features in Acme Workspace: document summarisation, meeting-minutes drafting, and natural-language search across a customer's workspace. Acme does not use AI to make automated decisions that produce legal or similarly significant effects on individuals.

## AIG-2 Models and providers
Acme Assist uses third-party foundation models accessed via API. Acme does not train its own foundation models. The current model providers are listed in the Sub-processor List (SUB). Model details, intended use and limitations are documented in the Acme Assist Model Card (MC).

## AIG-3 Use of customer data for training
Customer data is never used to train, fine-tune or otherwise improve any AI model, whether Acme's or a third party's. Our agreements with model providers prohibit them from using customer prompts or outputs for training. Model providers retain prompts and outputs for no more than 30 days for abuse monitoring only, under zero-data-retention terms where offered.

## AIG-4 Customer control
AI features are disabled by default for new customer tenants. A customer workspace administrator must opt in at tenant level, and can turn Acme Assist off at any time. Administrators can also restrict AI features to specific user groups.

## AIG-5 Data boundaries
Acme Assist only retrieves content the requesting user already has permission to see. Permissions are enforced at retrieval time, before any content is sent to a model. Content is never shared between customer tenants.

## AIG-6 Human oversight
All AI outputs are presented as drafts that a user must review, edit or accept. Acme Assist cannot send, publish or approve content on its own. AI-generated content is labelled in the user interface.

## AIG-7 AI governance structure
An AI Governance Group (Head of AI Product, Head of Security, Data Protection Officer, General Counsel) approves every new AI feature and any change of model provider. Approval requires a completed AI impact assessment covering privacy, security, fairness and misuse risks. The group meets monthly.

## AIG-8 Framework alignment
Acme's AI governance programme is aligned with the NIST AI Risk Management Framework (Govern, Map, Measure, Manage). Acme is working towards ISO/IEC 42001 and has completed a gap assessment. Acme maintains an inventory of all AI systems in use, including internal tools.

## AIG-9 EU AI Act
Acme has assessed Acme Assist against the EU AI Act and classified it as a limited-risk system, as it is not used for any purpose listed in Annex III. Acme meets the transparency obligations by informing users when they interact with AI and by labelling AI-generated content.

## AIG-10 Testing and monitoring
Before release, every AI feature is evaluated against a held-out test set for accuracy and hallucination rate, and undergoes internal adversarial testing for prompt injection and data leakage. In production, Acme monitors user feedback (thumbs up/down) and samples outputs for quality review each month.

## AIG-11 Acceptable use
Customers may not use Acme Assist for unlawful purposes, to generate harmful content, or to make decisions about individuals without human review. Abuse may result in AI features being suspended for the tenant.
