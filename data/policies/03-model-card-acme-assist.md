---
doc_id: MC
title: Acme Assist Model Card
version: 1.3
owner: Head of AI Product
last_reviewed: 2026-10-01
---

# Acme Assist Model Card

## MC-1 System overview
Acme Assist is a retrieval-augmented generation (RAG) system. When a user makes a request, Acme Assist retrieves relevant passages from the user's workspace, passes them to a large language model with a system prompt, and returns a draft with links to the source documents.

## MC-2 Intended use
Acme Assist is intended to help professional users summarise long documents, draft meeting minutes from notes, and find information in their workspace. It is intended for use in English.

## MC-3 Out-of-scope uses
Acme Assist is not intended for legal, medical or financial advice, for decisions about employment or creditworthiness, or for any use where outputs are relied on without human review.

## MC-4 Underlying models
Generation uses a third-party large language model provided by the model providers listed in SUB. Retrieval uses a third-party text embedding model. Acme pins model versions and tests every version change before rollout.

## MC-5 Evaluation
Each release is evaluated on an internal benchmark of 500 workspace tasks. Metrics include factual consistency with source documents, citation accuracy and refusal behaviour. Release requires factual consistency of at least 95% on the benchmark.

## MC-6 Known limitations
Acme Assist can produce inaccurate or incomplete summaries, particularly for long tables, scanned documents and non-English content. It may miss information in documents the user cannot access. Outputs should always be checked against the source.

## MC-7 Safety mitigations
Mitigations include permission-aware retrieval, source citations in every answer, a system prompt that instructs the model to say when information is not available, input filtering for known prompt-injection patterns, and output length limits.
