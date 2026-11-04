---
doc_id: IR
title: Incident Response Policy
version: 3.2
owner: Head of Security
last_reviewed: 2026-07-10
---

# Incident Response Policy

## IR-1 Scope
This policy covers security incidents, personal data breaches and AI incidents affecting Acme systems or customer data.

## IR-2 Severity levels
- SEV1: confirmed breach of customer data or full platform outage.
- SEV2: suspected breach, or major degradation affecting multiple customers.
- SEV3: limited impact, contained, no customer data affected.

## IR-3 Response process
Incidents follow five phases: detection, triage, containment, eradication and recovery, and post-incident review. An incident commander is appointed for every SEV1 and SEV2 incident.

## IR-4 Customer notification
Acme notifies affected customers of a confirmed personal data breach without undue delay, and in any case within 48 hours of confirmation. Notification includes the nature of the breach, likely consequences and the measures taken.

## IR-5 AI incidents
AI incidents include outputs that expose data across permission boundaries, successful prompt injection, or materially harmful outputs. AI incidents are handled under this policy, with the Head of AI Product joining the response team. Acme can disable Acme Assist globally or per tenant within 15 minutes.

## IR-6 Testing
The incident response plan is tested at least annually through a tabletop exercise. Post-incident reviews are completed within 10 business days of every SEV1 and SEV2 incident.
