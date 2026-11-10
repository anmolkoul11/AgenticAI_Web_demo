# Agentic Web Assistant — Project Overview

**Draft for review · 9 November 2026**

## 1. Purpose and objective

The project helps people collect useful information from websites by describing
what they need in everyday language. It aims to reduce repetitive searching,
form filling and copying information into spreadsheets.

For example, a user can ask for hotels in a city with specific dates and guest
counts, or ask for sports articles from a news website. The assistant uses the
website, gathers relevant information and presents it for review before saving.

## 2. Current scope

The current version can:

- Work in a newly opened browser or an existing Chrome/Edge tab through the
  Browser Companion extension.
- Read a request, navigate website controls and fill supported search fields.
- Collect relevant information from the current page, result lists and linked
  pages when the task calls for them.
- Organize information into useful fields, such as hotel names, prices,
  amenities and links, or article headlines, summaries and source links.
- Apply requested selection criteria when the captured evidence supports them.
- Let users preview, approve, save and download results as Excel, CSV, JSON or
  JSON Lines files.

The Companion offers a record limit from **0 to 500**, with **50** selected by
default. Zero disables Start. This is a maximum collection setting; the number
of usable saved records may be lower.

Reservations and payments are outside the current scope. Users complete website
sign-in, MFA and CAPTCHA themselves. If a required value was not supplied—for
example, a child's age—the assistant should pause for the user to provide it.

## 3. How the user gets results

**Request → Website actions → Collection → Review → Approval → Saved results**

### Step 1 — Choose a website and describe the task

The user selects a new browser or connects their current tab, enters a request
and chooses the maximum number of records.

Example: “Find hotels in New York from December 24–30, 2026, for 4 adults and
2 rooms. Include prices, ratings and listing links.”

**[Insert screenshot 1: Task setup]**
Show the request, connected website and record-limit slider.

### Step 2 — Let the assistant work on the website

The assistant observes the page, chooses an action and checks what changed.
It adjusts its approach to the website: Booking.com requires Search after
entering stay details, while Tripadvisor can update listings on the same page.
For a news request, it can collect relevant articles already visible on the page.

**[Insert screenshot 2: Website actions]**
Show the website with the requested dates and guest counts applied.

### Step 3 — Follow progress and provide missing information

The progress view shows the current activity. If information or user interaction
is needed, the user completes it on the website and presses Resume. The user
can also stop the task.

**[Insert screenshot 3: Progress or a user-input pause]**
Show one clear status message and the Resume control, without expanded logs.

### Step 4 — Review the collected information

The dashboard presents records in cards or a table, with source links and
supporting evidence. Missing or unconfirmed details are identified so users can
check them. A captured price is not automatically a confirmed match for the
requested dates, room count or price basis.

The website remains open so the user can compare the preview with the source.

**[Insert screenshot 4: Results preview]**
Show a few organized records, including a source link and any missing-field label.

### Step 5 — Approve, save and download

The user approves the reviewed results before saving. The Companion and
dashboard follow the same save status. Reopening results leads to the existing
save attempt instead of starting another one. Saved results can be downloaded
or revisited through run history.

**[Insert screenshot 5: Saved results and downloads]**
Show the saved confirmation and export options.

## 4. Results demonstrated so far

The user has reported successful live workflows on:

| Website | Demonstrated use |
| --- | --- |
| Booking.com | Enter stay details, submit a search and collect hotel listings. |
| Tripadvisor | Navigate to hotels, adjust stay details and collect dynamically updated listings. |
| BBC and The New York Times | Collect relevant articles from news pages. |

Recent improvements include the record-limit slider, clearer progress states
and a shared review/save state between the extension and dashboard.

These are user-reported demonstrations. They do not establish compatibility
with every page or website, complete coverage, or a measured accuracy or speed
improvement. The project remains a working prototype under refinement.

**[Optional screenshot 6: News results]**
Show a news preview alongside the hotel example to demonstrate both use cases.

## 5. How it works behind the scenes

The dashboard, workflow controller and saved data run locally. The browser is
controlled either through the Companion extension or through Playwright, a
browser automation tool. An OpenAI model interprets requests and helps choose
actions and extract information; relevant website content is sent to that
external API. The current autonomous browser workflow uses LangGraph to
coordinate the steps.

The model does not automatically retrain itself after each run. Improvements
currently come from reviewing outcomes and refining the application, prompts
and verification logic.

## 6. Remaining improvements

- Reduce unnecessary pauses when a valid action appears to make no change.
- Recognize already-applied values and visible results more reliably, avoiding
  repeated edits and false loops.
- Improve consistency across changing website layouts and data formats.
- Continue checking field completeness, price context and collection coverage.

For screenshots, use one consistent example and short captions. Crop out API
keys, credentials, account details and unrelated browser content.
