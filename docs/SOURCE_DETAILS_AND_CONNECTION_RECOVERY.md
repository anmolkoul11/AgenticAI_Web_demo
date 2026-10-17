# Connection recovery and additional source details

Checkpoint: UI/backend `2026-10-17.1`. Manual verification pending.

## OpenAI connection failures

Authentication/access guidance now asks the user to check whether their OpenAI
API key is active, re-paste the complete key in API connection, and replace it if
expired, revoked or invalid. An authentication rejection alone does not establish
that a key expired. Active-key failures can also need account/project access or
IP restrictions reviewed. See the official OpenAI error-code guidance:
https://developers.openai.com/api/docs/guides/error-codes

Saving the connection does not call OpenAI to verify it. Existing browser agents
keep their original settings/client; cancel the old browser and start a fresh
workflow after replacing the key. Both failure and connection-save messages now
explain this. No secret is displayed, no extra paid call is introduced, and no
automatic retry or key rotation occurs. CLI planning guidance also mentions
local configuration where applicable.

## Why the source drawer contained these quotes

In user1's latest Element by Marriott New York Times Square West record, all six
reported blocks belonged to that hotel's captured group, not a neighboring
record. The model's amenities field joined Breakfast included and Recommended
for your group into a single quote across separate blocks. Source validation
cleared that unsupported combined quote. The individual source blocks survived.

The completeness helper also retained expanded title and review representations
because their entire wording did not fit inside a returned field/evidence quote.
The literal source drawer was therefore useful, but its flat unmapped label was
confusing.

The drawer is now called Additional source details. A small local classifier
reuses generic field families and adds offers/recommendations. Examples:

| Captured quote | Display category |
| --- | --- |
| Breakfast included | Terms & inclusions |
| 2 nights, 4 adults | Options & configuration |
| Location 9.3 | Ratings & feedback |
| Recommended for your group | Offers & recommendations |
| Scored 8.1 ... Very Good ... reviews | Ratings & feedback |
| Unfamiliar source wording | Other source details |

An exact mapped title with only Opens in new window/tab appended is not repeated
in this supplemental drawer. Its original evidence remains untouched. Expanded
review wording remains when it contains additional descriptors; a location
subscore is not converted into the overall guest rating or assigned a scale.

Categories are organizational hints, not additional approved output fields or
proof that a filter matches. Quotes keep their full wording, negation, source URL
and block IDs; evidence links are collapsed under View source to reduce clutter.
Unknown wording and older flat supplemental lists remain visible via a fallback.
Record ownership, snippet/count limits, source validation, null fields and price
rules are unchanged. No additional model call or website action is introduced.
Saved historical results use the existing read-only preview projection when
their original source blocks remain available; old exports are not rewritten.

## Manual checks

1. Restart the dashboard and hard-refresh to load matching `2026-10-17.1` assets.
2. If an actual authentication/access failure occurs, check that the error
   directs you to API connection, active-key/re-paste/replace guidance and a fresh
   workflow. A quota failure must still use its separate quota guidance.
3. Save the active key. Confirm the save notice explains that existing agents
   retain the previous connection. Cancel the old browser and start a new run.
   Do not share any key in logs or screenshots.
4. Open the previous Element record from Run history, in cards and full preview.
   Breakfast, stay counts, location subscore and recommendation should be grouped
   as above. The duplicate title plus new-window suffix should not repeat there.
5. Expand View source. The quote URL and original block IDs must remain available;
   Location 9.3 must not replace the overall 8.1 rating. Missing amenities remain
   missing rather than silently becoming approved values.
6. Try a news or product result. Unrecognized wording must stay visible in Other
   source details, without empty hotel-specific groups or changed output fields.
   Historical downloads must retain the original saved data.

Regression fixtures were authored but not executed at the user's request.
No tests, validators, application imports/startup, browsers or model API calls ran.
