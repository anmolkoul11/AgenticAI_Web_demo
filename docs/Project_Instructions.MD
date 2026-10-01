1. Start the project
First-time setup—or after dependency changes
Open PowerShell in VS Code:
"
cd D:\Projects\AgenticAI_Web_demo
uv sync --locked
uv run --locked playwright install chromium
"
Each time you want to run a demo

i. Start Docker Desktop and wait for its engine.
ii. Run:
   .\scripts\Start-Demo.ps1
iii. Enter a synthetic hotel-portal password of at least 12 characters.
iv. Keep this terminal open.
The launcher starts like this:

Service	                   Address/purpose
Dashboard	               http://127.0.0.1:8120
Synthetic hotel portal	   http://127.0.0.1:8110
NATS	                   Local event delivery

The launcher’s password is for hotel browser automation—not your dashboard account or API key.

2. Sign in and configure your account
Open http://127.0.0.1:8120 (or the one linked with your dashboard).
i. Register a local account if you don’t already have one.
ii. Sign in.
iii. For AI-assisted paths, open API connection:
   - Enter your API key.
   - Enter your configured model ID.
   - Confirm billing authorization.
   - Optionally select Remember my key on this computer.
The guided hotel form needs no model key. All Custom Website extraction paths currently need one. Merely saving a key or receiving an extension capture does not make a model call.

3. Choose your path
Framework choice is separate: select LangGraph or CrewAI within the relevant workspace.

Path	                                       Best use	                                                Model needed?
Hotel demo (Guided Form)               →       Repeatable synthetic demo with explicit criteria	             No
Hotel demo (Natural Language)          →       Turn a written hotel request into a reviewed plan	         Yes
Custom Website (Browser Capture)       →       Content accessible in your normal signed-in browser	    Yes, after transfer
Custom Website (Chromium/Playright)    →       Rendered pages and compatible automated login	        Yes, after capture
Custom Website  (static HTML)          →       static HTML	Public pages whose content is in the HTML	     Yes
Custom Website  (Pasted Text)          →       pasted text	Manually supplied, authorized page content	     Yes


Path A: Hotel demo with the guided form
Use this first to verify the complete local workflow.
1. Select Hotel demo.
2. Choose LangGraph or CrewAI.
3. Select guided/structured input.
4. Enter:
   - A city, such as New York.
   - Future check-in and check-out dates.
   - Maximum nightly price.
   - Minimum rating.
5. Create the proposal.
6. Review the criteria and target.
7. Check the approval box and select Approve & execute.
The workflow logs into the synthetic portal, extracts listings, saves them, evaluates rules, publishes matching events and verifies receipts.
The Hotel demo retains its configured policy restrictions. The catalogue contains 100 synthetic listings across 10 cities, but one city search does not return all 100.

Path B: Hotel demo with natural language
1. Select Hotel demo → natural-language/model-assisted mode.
2. Choose a framework.
3. Enter a complete request, for example:
   Find New York hotels from October 15 to October 17, 2026, at most USD 200 per night including taxes, rated at least 4 out of 5.
4. Confirm paid-model consent and create the proposal.
5. Compare the interpreted fields against your request.
6. Approve and execute only if correct.
The model interprets the request; the approved execution then follows the same hotel workflow as Path A. Missing or unsupported requirements require a corrected submission—not automatic execution.

Path C: Capture from your normal Chrome or Edge
Use this when you want to browse and sign in normally.
Install the extension once:
1. Open chrome://extensions or edge://extensions.
2. Enable Developer mode.
3. Select Load unpacked.
4. Choose:
   D:\Projects\AgenticAI_Web_demo\extensions\page-capture
5. Pin Agentic Studio Page Capture.
For each extraction:
1. In Website Studio choose **Use my browser**, enter an HTTPS address, and select
   **Open website in this browser**. Or open the page yourself in the same Chrome/Edge.
2. Sign in yourself if needed and navigate to the actual content.
3. Click the extension → Capture visible content.
4. Review the captured text and links for sensitive information.
5. Confirm authorization → Keep this capture for transfer.
6. Switch to your signed-in dashboard tab in the same browser.
7. Open the extension again.
8. Confirm the displayed destination account → Send to displayed dashboard account.
9. In Custom Website, review the received capture.
10. Choose a framework, add optional instructions and confirm paid extraction.
Example:
Extract the visible article headlines and their link URLs. Include authors and publication dates only when present. Do not summarize or invent missing information.

This captures the current page—not the whole website. It does not automatically navigate, paginate or log in.


Path D: Open the website through Chromium
1. Select Custom Website → Chromium browser.
2. Choose a framework.
3. Enter one public HTTPS URL.
4. Choose the login method:
   - No login needed (default): open the page without a sign-in attempt.
   - Manual: sign in yourself in the Chromium window.
   - Automatic: provide website credentials for one supported login attempt. The HTTPS login URL is optional if a single visible sign-in link can be found.
5. Enter optional extraction instructions.
6. Confirm permissions and start inspection.
7. In Chromium, navigate to the desired content.
8. Select Capture current page & extract in the dashboard.
Trusted resource/verification origins are advanced settings, not a guarantee of access. If the site denies access, stop that session. This browser does not reuse your normal Chrome cookies.


Path E: Static public HTML
Use this for accessible public pages that don’t require JavaScript rendering or login.
1. Select Custom Website → Static public HTML pages.
2. Supply up to three explicit URLs from the same origin.
3. Choose a framework and enter optional instructions.
4. Confirm permissions → Inspect & preview extraction.
This reader does not open Chromium, sign in or crawl additional links.


Path F: Paste authorized page text
1. Select Custom Website → Paste authorized page text.
2. Enter the original source URL.
3. Paste the relevant text—without credentials, cookies or secrets.
4. Choose a framework and enter optional instructions.
5. Confirm permissions → Inspect & preview extraction.
This is useful for a controlled demonstration or content the other capture methods cannot retrieve. The source is user-supplied, not independently fetched.



4. Review and save Custom Website results

All four Custom Website paths converge here:
1. Review the proposed fields, interpretation, filters and evidence.
2. Check warnings about truncation or incomplete coverage.
3. Inspect any rejected records.
4. If partial results are acceptable, explicitly check the additional partial-results approval.
5. Select Approve & save snapshot.
Only accepted records proceed to saved results, business rules and events. If no source-verified records remain after validation and filtering, there is no approvable result.
Approval saves the reviewed snapshot. It does not fetch the page or call the model again.
Leaving extraction instructions blank means “infer the main available content without extra filters”—not “download the entire website.”
5. Optionally apply rules and publish events
For Custom Website, configure this before creating the preview:
1. Expand Optional business rule & event.
2. Enter a field expected in the extracted schema, an operator and a value.
3. Enable event publication if wanted.
Example: price → at most → 200.
Search filters determine which records remain in the results. Business rules then mark qualifying saved records without removing the others.
Custom Website publishes one summary event for qualifying records, with IDs/counts rather than article bodies. Its current delivery evidence is a broker acknowledgement, not a verified consumer receipt. The Hotel demo has the fuller receipt-verification workflow.
6. Retrieve your data
After an approved run saves successfully:
1. Open its results.
2. Select a format:
   - Excel: business review.
   - CSV: spreadsheets and downstream processing.
   - JSON: structured data and metadata.
   - JSON Lines: record-by-record processing.
3. Select Download results.
Hotel downloads support all saved records or the current filtered subset. Custom Website downloads contain the accepted saved snapshot.
Use Run history to reopen previous dashboard jobs and downloads without rerunning extraction. Local artifacts are under:
D:\Projects\AgenticAI_Web_demo\data\users\<account-uuid>\
7. Stop cleanly
Wait for active jobs to finish, then press Ctrl+C in the launcher terminal. Closing a browser tab does not stop the servers.
NATS stays running. Stop it separately if desired:
docker compose stop nats
Recommended first walkthrough: guided Hotel demo → extension capture of one permitted external page → review → approve → download CSV/Excel. Then repeat the external capture with the other framework.
