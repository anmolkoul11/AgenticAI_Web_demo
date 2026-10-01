# Production readiness and website coverage

Status: local prototype requiring user-run offline and live verification. Do not describe
this build as production ready or universally compatible with websites.

## Site coverage

The shared pipeline can process a captured page from normal Chrome/Edge, a compatible
Playwright browser page, static public HTML or authorized pasted text. Both LangGraph and
CrewAI use the same extraction, rules, approval, local storage and export services.
One captured page is not a full website: this release has no general pagination, link
crawling, PDF/OCR, shadow DOM or iframe extraction. Site-specific adapters are required
when a site needs an API, special navigation, data licensing or authenticated flow.
Rendered capture now prioritizes the main content and labels recognizable article,
table-row and property-card containers. Extraction rejects records whose supported
fields point to different labeled containers. Pages without those containers still
have only page-level quote validation; this is not proof that a record's fields belong
to the same real-world item.
Access-denied pages must stop at capture. Browser extension capture is user-assisted.
Read access does not itself grant permission to export or send content to a model.

## Release gates before shared or enterprise deployment

1. User runs the offline suite including `tests/test_topic_evidence.py` and verifies both
   framework paths, a quote-wrapped homepage capture, unrelated/uncertain records, rules,
   partial results, saved exports and NATS acknowledgements.
2. Choose at least one permitted external website with a documented access method.
   Run an end-to-end acceptance scenario with stable fixtures and current live content;
   record extraction precision/recall, omissions and model cost. Test a blocked site too.
3. Establish supported-site criteria and owner approvals. Where rights or automation
   restrictions apply, use authorized APIs or site adapters, or decline that target.
4. Replace local account and credential management for shared hosting with enterprise
   identity, a managed secret store, TLS, authorization checks and audit retention.
5. Replace in-process jobs and local-only SQLite/files with durable workers and storage;
   define concurrency, idempotency, failure recovery, backups and restore tests.
6. Apply deployment controls for browser isolation, outbound network access, data
   classification, model provider configuration, rate limits, costs and observability.
7. Test load, cross-account isolation, session expiry, export safety and incident recovery
   in the target environment. Complete security and privacy review before production data.

The current checkpoint fixes evidence wrapping and topic selection. It does not satisfy
the gates above. A successful model call or schema-valid response can still be factually
wrong; source-backed rows and human review remain required.
