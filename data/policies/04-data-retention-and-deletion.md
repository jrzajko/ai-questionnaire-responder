---
doc_id: DR
title: Data Retention & Deletion Policy
version: 3.0
owner: Data Protection Officer
last_reviewed: 2026-08-15
---

# Data Retention & Deletion Policy

## DR-1 Customer content
Customer content is retained for the duration of the subscription. Customers can delete individual items at any time; deleted items move to a recycle bin and are permanently deleted after 30 days.

## DR-2 End of contract
On termination, customers have 30 days to export their data. Customer data is then deleted from production systems within 30 days, and from backups within a further 35 days as backups expire. A certificate of deletion is available on request.

## DR-3 Backups
Production databases are backed up daily. Backups are encrypted, stored in a separate AWS region within the same jurisdiction, and retained for 35 days.

## DR-4 AI interaction data
Acme Assist prompts and outputs are stored in the customer's tenant for 90 days to provide conversation history, then deleted automatically. Administrators can shorten this period or disable history. See AIG-3 for model provider retention.

## DR-5 Logs
Application and security logs are retained for 12 months. Logs are designed to exclude customer content.

## DR-6 Legal holds
Retention may be suspended where required by law or a legal hold, and the customer will be informed where legally permitted.
