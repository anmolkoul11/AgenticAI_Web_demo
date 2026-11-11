# Article collection fixes

These changes address the saved NYTimes/BBC runs without changing hotel search
or stay verification. They have been reviewed in source only. Tests and live
workflows have not been run by the assistant.

## What changed

- BBC-style headline links can be captured in batches without requiring an
  `article` element or a class containing `card` or `story`.
- Article sources follow page order. Literal request-topic and section cues can
  move likely relevant sources ahead of general stories within the same cap.
  This is prioritization, not a keyword acceptance filter. The model still
  assesses meaning and record type; source validation remains in place.
- Once a current-page article source is captured on the same settled document,
  the agent can hand it to extraction instead of repeating Capture or attempting
  unwanted section navigation. Batched collection still runs when selected.
- **Why articles were excluded** shows AI classification, reason and captured
  quote. This is separate from business-rule filtering and does not claim the
  classification is always right. Old previews have no reconstructed audit.
- Exact paragraph-based headlines count toward article extraction coverage.
- The extractor distinguishes an item's actual headline from a programme or
  category heading on the same card. It selects exact source block IDs during
  the existing model call; validation binds them to that card and URL. A
  programme name cannot silently stand in for an unresolved headline. Relevant
  items with audio remain included, with programme/media labels separate when
  captured. The application does not assume that an H2 is always the headline
  or that a longer H3 is always correct.

The existing source record cap still applies. Fifty captured candidates do not
guarantee fifty accepted articles, and a capped preview cannot prove whole-site
coverage. No extra navigation model call or automatic retry was added.

## Update before manual testing

1. Stop any active task and restart the backend from the updated project.
2. Refresh the dashboard. Its UI version is `2026-11-10.1`.
3. Reload Browser Companion **0.5.23** in Edge/Chrome's extension manager.
4. Refresh the website tab and start a fresh task. Do not use an old paused run
   or a previously frozen preview to judge the new collector.

## Live checks

| Website | Task | Expected behavior |
| --- | --- | --- |
| NYTimes homepage | `find me articles related to sports` | Collect starting-page headlines without wandering into sections. Likely sports sources precede general stories within the cap. Accepted records retain actual titles/URLs. Review excluded candidates' reasons and quotes. |
| BBC homepage | Same prompt | Capture headline links even without card wrappers, then proceed through collection/extraction without the repeated Capture loop or empty-window failure. |
| Either news site | Request an uncommon topic with no visible matches | Report no matches or uncertain coverage; do not invent articles or treat games/section links as stories. |
| Booking.com | `Find hotels in Edison from 28-30 November 2026 for 6 adults and 4 rooms and 0 children` | Preserve the existing destination/date/guest workflow, explicit Search, returned-stay checks, collection and review. |
| Tripadvisor | Same hotel prompt | Preserve the existing live result updates and collection; do not require a separate Booking-style Search. |

If an article appears wrongly excluded, share its source URL, displayed headline,
AI reason and quote from the new panel. This distinguishes a topic decision
from a missed source or the source cap. Do not share credentials or cookies.

## Local regression commands to run yourself

Offline cases use mocked tools/model responses:

```powershell
uv run --locked pytest tests/test_current_page_agent_handoff.py tests/test_topic_review.py tests/test_result_extraction_batches.py -v
```

Opt-in local browser fixtures cover wrapper-free headlines, mixed headline
layouts, topic options through extension dispatch, hotel cards, date/counter
contracts, and safe review rendering. They do not contact live websites/models:

```powershell
uv run --locked pytest tests/test_article_capture_windows.py tests/test_calendar_capture_dom.py tests/test_extension_executor_contract.py tests/test_workflow_review_ui.py --run-browser -v
```

Live website behavior remains unverified until manual checks are completed.

## Programme/episode headline regression cases

Extractor `website-extractor-v19` needs a backend restart and a fresh extraction.
It does not rewrite old results. For the BBC layout in the supplied screenshot,
compare the bold content headline with `article_title`: **Football Daily** is
the programme name, while **Carrick still in limbo & are Brighton title challengers?**
is one item's actual headline. Include relevant items with audio as requested;
do not substitute the programme label or merge different episodes.

Block IDs ground the model's source-role choice. They do not independently
prove that its semantic interpretation is right. Review any remaining ambiguity
against the source, without guessing a title from heading rank or a URL.

Additional offline source cases:

```powershell
uv run --locked pytest tests/test_record_headline_roles.py tests/test_headline_role_extraction.py tests/test_result_extraction_batches.py tests/test_source_quality.py tests/test_link_label_capture.py -v
```
