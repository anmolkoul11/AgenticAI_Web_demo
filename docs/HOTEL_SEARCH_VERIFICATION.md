# Hotel search: manual verification

This checkpoint adds a separate **Complete hotel search** workflow: review the goal
once, then re-inspect and prepare the destination, dates and occupancy before one
Search submission. The individual paid action planner remains available. This is
not a claim that
every Booking.com widget or every hotel website is fully automated. No reservation
or payment actions are supported. LangGraph and CrewAI share the corrected path.

## First run

1. Restart the dashboard using your usual launcher, then refresh with **Ctrl+F5**.
   Start a new browser session; do not reuse an earlier proposal.
2. In Website Studio, select **Open a website**, `https://www.booking.com/`, your
   framework, and Normal networking. Confirm the session permissions. If public
   results are sufficient, choose **No login needed**.
3. Use this complete baseline request:

   > Find hotels in Boston with check-in 2026-10-28 and check-out 2026-10-30,
   > for 2 adults, 1 room. Include name, URL, nightly price, currency, tax basis and guest
   > rating with its scale. Keep nightly prices between 150 and 250 USD inclusive
   > and guest ratings at least 8 out of 10. Do not reserve or pay.

   The 8/10 threshold is explicit for this test, not an automatic conversion of a
   4/5 score. Choose whatever score/scale you actually want to evaluate.
4. Wait for the standard form to render, then choose **Prepare complete hotel search
   · no API call**. **Search in your own words** is not rejected just because of its
   label: it can be used for the literal destination when its destination metadata
   and surrounding date/guest/search controls identify a hotel search form. A
   standalone free-text box without that context still needs a standard form.
   Review all targets, including
   the explicit year. Destination must be **Boston**, never the complete prompt.
5. Tick the target confirmation and choose either:

   - **Approve & run search only**: no model-planning calls. Inspect the results,
     then use the existing current-page or linked-page extraction options.
   - **Approve, search & extract · paid API**: the same form workflow, followed by
     capture and the usual paid extraction only after listing elements appear.
     Review the resulting preview before approving storage/export.

   The workflow selects an unambiguous destination suggestion when needed, opens
   the calendar, navigates months with full-date evidence, adjusts labelled adult
   and room counters, reads the values back and submits Search once. It re-inspects
   the DOM between actions rather than requiring a new model call for each widget.
   Progress shows destination → dates → occupancy → submit → results. Cancel stops
   subsequent actions; an already submitted search cannot be undone.
6. Check **Search action evidence**. It distinguishes values read back, remaining
   criteria and submission. A submission-capable plan that cannot establish its
   prerequisites stops before changing fields. A successful partial step never
   claims a completed search.
   With the individual paid action planner, known request values that are not yet
   confirmed stay **pending**; they do not require a new session. Replan in the same
   session. That older path intentionally remains a sequence of reviewed steps.
   Only values genuinely missing from the original request need an edited request
   and new session. A matching default occupancy requires no redundant action.
7. After Search, inspect the browser: destination, dates, occupancy, currency and
   displayed listings must match. Price/rating constraints may be deferred to
   extraction if the website lacks supported controls; that is not a site filter.
8. Capture the results page or review relevant detail links. Review extracted
   prices and units, taxes, ratings and URLs before saving. Download CSV/Excel and
   compare it with the preview. Matching records are limited to captured content,
   not all listings on the website. Repeat with the other framework.

## Additional scenarios

- **Exact New York regression:** use "give me hotels in New York with price ranging
  from 250-350 USD per night, with checking in and checking out date as 28-30 October
  2026 for 2 adults, 1 room". Both full dates and named occupancy must be retained.
  Use **Complete hotel search** to continue through all form widgets in one goal.
  Then repeat with **3 adults, 2 rooms** to exercise non-default counters. With a summary of
  "2 adults · 0 children · 1 room", guests should be verified, not missing. The
  dates must be read back before Search. Check the calendar year yourself as well.
- **Natural wording:** repeat with "October 28 to October 30, 2026" instead of ISO
  dates. Both endpoints should be grounded without using a price or guest count as
  a year. Explicit ranges crossing months are also recognized.
- **Missing year:** omit 2026. The dashboard should preserve that clarification,
  and Complete hotel search must reject the goal without entering any fields or
  calling the model. It never selects guessed dates or submits. Cancel the browser,
  edit the request and start a new session.
  Replanning the existing session retains its original request.
- **Unsupported widget:** when date values cannot be read independently, expect an
  explicit stop, not a fabricated success or automatic extraction. Manually prepare
  the form if needed, then review a fresh goal or individual action plan.
- **Cancel / changed form / access challenge:** cancel while a widget is open, or
  verify that ambiguous suggestions, disabled dates and unexpected counter changes
  stop before submission. Failed goals do not repeat clicks or extraction. Inspect
  the tab before approving another goal. MFA remains a manual handoff.
- **Destination detection:** repeat with a destination box labelled **Search in
  your own words**. When it has `name="ss"` (or destination metadata) and belongs to
  a hotel form, only the destination should be entered—not the complete prompt.
  A separate generic header search must not make the hotel form ambiguous. If two
  hotel forms genuinely match, the run must stop rather than select arbitrarily.
  **Destination field detection** in the evidence lists recognized/excluded field
  metadata and matching counts, never entered values. Missing/late-rendering fields
  and multiple matches now have distinct guidance.
- **Autocomplete:** a result's wrapper and nested option must count as one row.
  Text highlighting must retain the full title (e.g. **New** York is New York,
  not just New). A linked input popup takes precedence over other page options.
  The workflow observes suggestions for up to eight seconds and requires a stable
  unique match before clicking. It recognizes the explicit New York/New York City/
  NYC alias, but performs no broad substring or fuzzy place matching. A uniquely
  identified city result takes precedence over a same-named state/district result;
  two matching cities or untyped sibling rows remain ambiguous. No option is picked
  simply because it is first. **Destination suggestion matching** shows visible
  candidates, location types and counts. A failed selection records the text entry
  separately from a verified destination; dates/guests remain pending. You may
  choose the intended option in the same browser, then prepare a fresh goal review.
- **Search-only cost boundary:** Search should run without additional planning API
  calls. It must not start extraction or save records until you choose that action.
  The browser-session setup still uses the existing account API configuration and
  consent; the new form driver itself does not call the model.
- **Ordinary keyword search:** try a news website with "battery research". Reviewed
  generic text discovery should still work; hotel-specific fields are not imposed.

## Remaining limitations

The goal driver supports recognizable English destination inputs, matching autocomplete
options, native date inputs or fully dated calendar cells, labelled adults/rooms
steppers or numeric inputs, and an unambiguous Search button. It uses a 64-action /
120-second budget and at most 12 month hops per date. No arbitrary LLM-selected
JavaScript or reservation/payment actions are executed.

A yearless date summary is not proof by itself. If full dates were independently
verified from selected calendar cells during this goal, the driver can retain that
proof while the exact summary stays unchanged; conflicting dates invalidate it.
No year is borrowed from the request to invent read-back evidence. Positive child
counts require age selection and are not supported by this goal driver. If children
are omitted, the existing child count is unchanged and must be reviewed by the user.

Localized/custom widgets, multiple identical destination suggestions, differently
named destination labels, unlabeled steppers, changing layouts and access restrictions
may still need manual completion or a connector. Listing-element observation is not
proof of matching dates, guests, nightly units, price, currency, taxes or ratings.
Price/rating rules remain in the original request for source-verified extraction,
not as automatically applied website filters. A no-results page or unrecognized card
layout stops for attention instead of automatically extracting unrelated content.
The model can still omit or misinterpret constraints;
human review of the complete request and actual results remains necessary.

## Tests (you run these)

Offline guards and mocked model responses; local browser fixtures are skipped:

```powershell
uv run --locked pytest tests/test_hotel_autocomplete.py tests/test_hotel_destination_detection.py tests/test_complete_hotel_search.py tests/test_complete_hotel_dashboard.py tests/test_navigation_semantics.py tests/test_hotel_form_continuation.py -v
```

Isolated local browser fixtures, with Chromium installed; no external websites,
credentials or paid API calls:

```powershell
uv run --locked pytest tests/test_hotel_autocomplete.py tests/test_hotel_destination_detection.py tests/test_complete_hotel_search.py tests/test_complete_hotel_dashboard.py tests/test_browser_navigation.py tests/test_navigation_verification.py tests/test_navigation_semantics.py tests/test_hotel_form_continuation.py tests/test_navigation_dashboard.py tests/test_dashboard_ui_structure.py --run-browser -v
```

The assistant ran static lint/format and JavaScript syntax checks only, not these
tests, browser sessions or paid model calls. Live website compatibility requires
your manual acceptance run.
