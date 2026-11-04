---
doc_id: BCP
title: Business Continuity & Disaster Recovery
version: 1.9
owner: Head of Engineering
last_reviewed: 2026-05-20
---

# Business Continuity & Disaster Recovery

## BCP-1 Objectives
For a full loss of the primary region, the recovery time objective (RTO) is 8 hours and the recovery point objective (RPO) is 24 hours.

## BCP-2 Disaster recovery
Recovery uses encrypted backups replicated to the Ireland region (see DR-3). Infrastructure is defined as code so the platform can be rebuilt in the recovery region.

## BCP-3 Testing
A disaster recovery restore test is performed at least annually, and backup restores are tested quarterly. Results are reviewed by the Security Steering Committee.

## BCP-4 Business continuity
Acme staff can work fully remotely, and no critical business process depends on a single office or a single person.
