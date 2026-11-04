---
doc_id: HA
title: Hosting & Architecture Overview
version: 2.4
owner: Head of Engineering
last_reviewed: 2026-09-05
---

# Hosting & Architecture Overview

## HA-1 Hosting
Acme Workspace is hosted on Amazon Web Services. The primary region is London (eu-west-2). Backups and disaster recovery are in Ireland (eu-west-1). Acme does not operate its own data centres.

## HA-2 Data residency
All customer content is stored in the UK, with backup copies in the EU. Acme does not currently offer hosting in other regions.

## HA-3 Tenancy model
Acme Workspace is a multi-tenant application. Each customer's data is logically separated by a tenant identifier enforced at the application and database layers, and every query is scoped to a single tenant.

## HA-4 Network security
Production runs in private subnets behind a web application firewall and load balancer. Administrative access is only possible through an SSO-protected bastion. DDoS protection is provided by AWS Shield.

## HA-5 Availability
The platform runs across three availability zones in the primary region. Target availability is 99.9% monthly, excluding scheduled maintenance. Current status and incident history are published on a public status page.

## HA-6 AI architecture
Acme Assist runs as a separate service inside the same AWS environment. Prompts are sent to the model provider over TLS through a private gateway that strips account identifiers and logs request metadata only. Embedding indexes are stored per tenant.
