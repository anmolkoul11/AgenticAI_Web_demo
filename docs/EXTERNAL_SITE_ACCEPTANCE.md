# External-site acceptance scenarios (operator-run)

These scenarios define what the local prototype should demonstrate. They are not
claims that BBC News or Booking.com currently permits or supports this workflow.
Use them only when your organization has approved automated access, exporting the
content, and sending captured page text to the configured model provider. Do not
enter website or API credentials into an issue report.

## BBC News: relevant article details and export

1. Start the local dashboard, sign in, and configure your own API key. In **Custom
   Website**, choose **Chromium browser** and either LangGraph or CrewAI.
2. Enter `https://www.bbc.com/news` and a request such as: `Find sports-related
   articles visible from this BBC News page. For each relevant article, include
   its headline, article URL, sport or theme when supported by the article text,
   and a source-quoted context excerpt. Do not invent missing details.`
3. Confirm authorization and model consent. Inspect the visible page. If it is an
   access-denied page or has not rendered content, stop and record page health,
   blocked origins and a redacted screenshot. A `complete` document and HTTP 200
   do not mean the BBC scripts loaded. Review blocked script/style origins; only
   add trusted resource origins in a new session. Do not extract a challenge page.
4. Select **Find relevant article links**, not **Extract current page only**.
   The latter returns index headlines without opening their articles. If no
   relevant articles are visible, the
   agent may instead propose one relevant section (for example Sport, then
   Football). Approve each section hop separately and request discovery again;
   a section page is not an extracted article. The flow permits at most two
   section hops. Once actual article links are proposed, review the URLs and
   approve up to five. If a suitable section is absent, navigate manually or
   report that the requested content was not visible; do not claim a full-site search.
5. Review the extracted preview. Each kept record should have a real article
   URL, a headline and a supporting quote from its own article page. A theme
   without source support should be null and visibly marked for review. Check
   **Captured pages** counts as load indicators, then inspect the quoted body
   passage; paragraph counts alone do not prove article content was captured.
   An absent article excerpt means the captured page did
   not supply verified body context; do not infer it from the headline. Check
   cleared optional fields as well as rejected or uncaptured articles before
   approving a partial result.
6. Approve the preview and download CSV, XLSX or JSON. Open the file and verify
   links, source quotes, article count and columns. Repeat with the other
   framework after the first path works.

Pass criteria: approved article pages are opened; relevant records have working
source URLs and article-specific evidence; irrelevant/unsupported rows are not
silently included; exports match the approved preview. Five links are a bounded
sample, not complete BBC coverage.

## Booking.com: bounded form search and listing preview

1. In **Custom Website**, open `https://www.booking.com/` in Chromium with a
   complete request such as: `Search Boston, check in 2026-10-15, check out
   2026-10-17, two adults. Extract hotel name, property URL, displayed price,
   currency, price basis and guest rating. Keep hotels at or below 250 USD per
   night including taxes and rated at least 8 out of 10, but only when those
   units and values are visible and comparable.` Adjust the future dates before
   running.
2. If the page is usable, select **Suggest search actions**. Review each proposed
   control and value before approval. Inspect the final result page and its
   visible search criteria before capture. Do not assume a generic text box
   applied dates, occupancy, price or rating.
   If only Destination and Search are detectable, a destination-only
   **partial form** proposal may fill the exact city. It must not submit Search;
   inspect the resulting suggestions and date controls, then request another
   reviewed plan. Price/rating filters may require the results page, but the
   requested stay dates must be applied before comparing hotel prices.
3. If destination suggestions, calendar widgets or other controls are not
   supported, use only documented manual input or an approved site-specific
   adapter/API. Do not treat a partial search as satisfying the prompt.
4. If access is restricted or a robot check appears, stop. Record page health,
   blocked origins and a redacted screenshot. Do not bypass the restriction.
5. On a usable result page, review each listing's name, URL, price basis,
   currency, rating scale and evidence together. Do not convert total-stay
   price into nightly price or a 10-point rating into a 5-point rating without
   an explicit, reviewed rule. Export only approved results.

Pass criteria: the site confirms the requested destination/dates/occupancy;
captured listings actually correspond to that search; extracted fields and
units are supported by the same listing; the approved preview and download
agree. A robot/access restriction is a documented unsupported outcome, not a
reason to weaken browser safety controls.

## Offline checks before either paid/manual scenario

Run these yourself from the project root after restarting the dashboard:

```powershell
uv run --locked pytest tests/test_capture_handoff.py tests/test_browser_navigation.py tests/test_browser_links.py tests/test_custom_website.py tests/test_exports.py -v
```

These tests do not establish acceptance on either live website. Save the exact
prompt, approved links/search steps, page-health diagnostics, rejected-record
reasons, model usage, resulting export and a redacted screenshot for each live
run. Do not include credentials, cookies, tokens or personal account details.
