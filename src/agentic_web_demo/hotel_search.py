"""Goal-reviewed hotel search. No model calls, reservations, or payment actions."""

import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from playwright.sync_api import Error as PlaywrightError

from agentic_web_demo.browser_dates import resolve_stay_dates
from agentic_web_demo.browser_navigation import (
    SearchRequirement,
    guest_counts,
    requested_destination,
)
from agentic_web_demo.custom_fetch import WebsiteError, origin
from agentic_web_demo.search_form_dom import HOTEL_DESTINATION_FACTS

MAX_ACTIONS = 64
MAX_SECONDS = 120
MAX_MONTH_HOPS = 12


@dataclass(frozen=True)
class HotelSearchRequest:
    destination: str
    check_in: str
    check_out: str
    adults: int
    rooms: int
    children: int | None = None
    price_min: str | None = None
    price_max: str | None = None
    currency: str | None = None
    date_resolution: dict | None = None

    def requirements(self):
        counts = f"{self.adults} adults, {self.rooms} rooms"
        if self.children is not None:
            counts += f", {self.children} children"
        rows = [
            SearchRequirement(field=key, value=value, application="site").model_dump()
            for key, value in (
                ("destination", self.destination),
                ("check_in", self.check_in),
                ("check_out", self.check_out),
                ("guests", counts),
            )
        ]
        for key, value in (("min_price", self.price_min), ("max_price", self.price_max)):
            if value is not None:
                rows.append(
                    SearchRequirement(
                        field=key,
                        value=f"{value} {self.currency}",
                        application="extraction",
                    ).model_dump()
                )
        return rows

    def model_dump(self):
        return {
            "destination": self.destination,
            "check_in": self.check_in,
            "check_out": self.check_out,
            "adults": self.adults,
            "rooms": self.rooms,
            "children": self.children,
            "requirements": self.requirements(),
            "max_actions": MAX_ACTIONS,
            "max_seconds": MAX_SECONDS,
            "planning_api_calls": 0,
            "date_resolution": self.date_resolution,
        }


def prepare_hotel_search(instructions, reference_date=None):
    destination = requested_destination(instructions)
    dates, resolution = resolve_stay_dates(instructions, reference_date)
    counts = guest_counts(instructions)
    if not destination or len(dates) != 2 or not counts or not {"adults", "rooms"} <= counts.keys():
        raise WebsiteError(
            "Complete hotel search requires a destination, two resolvable dates, "
            "and explicit adult and room counts. No website actions or model calls ran."
        )
    if dates[0] >= dates[1]:
        raise WebsiteError("Check-out must follow check-in. No website actions ran.")
    if not (1 <= counts["adults"] <= 30 and 1 <= counts["rooms"] <= 30):
        raise WebsiteError("Use 1–30 adults and rooms for this bounded demo search.")
    if counts.get("children", 0) > 0:
        raise WebsiteError(
            "Child-age selection is not supported by Complete hotel search. "
            "Prepare that form manually or use the individual reviewed actions."
        )
    price = re.search(
        r"(?<![\d-])(\d+(?:\.\d+)?)\s*(?:-|–|to|and)\s*"
        r"(\d+(?:\.\d+)?)\s*(USD|EUR|GBP)\b",
        instructions,
        re.I,
    )
    return HotelSearchRequest(
        destination,
        dates[0],
        dates[1],
        counts["adults"],
        counts["rooms"],
        counts.get("children"),
        *(price.groups() if price else (None, None, None)),
        date_resolution=resolution,
    )


# Collect just search-form controls. Never inspect password fields or browser storage.
HOTEL_INVENTORY = (
    r"""() => {
  const hotelDestination = ("""
    + HOTEL_DESTINATION_FACTS
    + r""");
  const clean = s => (s || '').replace(/\s+/g,' ').trim();
  const visible = e => !!e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden';
  const label = e => {
    const labelled=(e.getAttribute('aria-labelledby')||'').split(/\s+/)
      .map(id=>e.getRootNode().getElementById?.(id)?.textContent||'').join(' ');
    return clean(e.getAttribute('aria-label') || labelled || e.getAttribute('placeholder') ||
      (e.labels && [...e.labels].map(x=>x.textContent).join(' ')) ||
      e.getAttribute('title') || e.innerText || e.name);
  };
  const component = s => {
    const keys = [['adults',/\badults?\b|group_adults/i],
      ['children',/\bchildren\b|\bchild\b|group_children/i], ['rooms',/\brooms?\b|no_rooms/i]];
    const found = keys.filter(([,r])=>r.test(s)); return found.length===1 ? found[0][0] : null;
  };
  document.querySelectorAll('[data-agentic-hotel-id]')
    .forEach(e=>e.removeAttribute('data-agentic-hotel-id'));
  let seq=0;
  const handle = e => {
    if (!e.hasAttribute('data-agentic-hotel-id'))
      e.setAttribute('data-agentic-hotel-id',String(seq++));
    return {id:e.getAttribute('data-agentic-hotel-id'),label:label(e).slice(0,200),
      tag:e.tagName,name:e.getAttribute('name')||'',role:e.getAttribute('role')||'',
      enabled:!e.disabled && e.getAttribute('aria-disabled')!=='true'};
  };
  const inputFacts=[...document.querySelectorAll('input')]
    .filter(e=>visible(e) && ['text','search'].includes(e.type))
    .map(e=>({el:e,facts:hotelDestination(e)}))
    .filter(item=>item.facts.reason!=='not_destination_input');
  const matches=inputFacts.filter(item=>item.facts.recognized);
  const structuredMatches=matches.filter(item=>item.facts.structured);
  const destinations=(structuredMatches.length?structuredMatches:matches).map(item=>item.el);
  const destination = destinations.length===1 ? destinations[0] : null;
  const form=destination?inputFacts.find(item=>item.el===destination).facts.form:null;
  const destinationDiagnostics={matching_fields:destinations.length,
    structured_matching_fields:structuredMatches.length,visible_text_fields:inputFacts.length,
    reason:destination?'recognized':destinations.length?'multiple_matches':'no_match',
    candidates:inputFacts.slice(0,8).map(({el,facts})=>({
      label:label(el).slice(0,100),name:(el.name||'').slice(0,80),type:el.type,
      recognized:facts.recognized,structured:facts.structured,canonical:facts.canonical,
      reason:structuredMatches.length && facts.recognized && !facts.structured ?
        'outside_selected_hotel_form':facts.reason}))};
  const fields = [];
  if (form) for (const e of form.querySelectorAll('input')) {
    const hint = `${label(e)} ${e.name}`;
    const key = /^(check[_-]?in|arrival)([_-]?date)?$/i.test(e.name) ||
      /check.?in|arrival/i.test(label(e)) ? 'check_in' :
      /^(check[_-]?out|departure)([_-]?date)?$/i.test(e.name) ||
      /check.?out|departure/i.test(label(e)) ? 'check_out' : '';
    if (key && ['date','hidden','text'].includes(e.type)) fields.push({key,value:e.value||'',
      ...(visible(e) && !e.readOnly && e.type!=='hidden' ? handle(e) : {}),
      writable:visible(e)&&!e.readOnly&&e.type!=='hidden'});
    const c = component(hint);
    if (c && e.type==='number' && visible(e))
      fields.push({key:c,value:e.value||'',...handle(e),writable:!e.readOnly});
  }
  const popupIds=(destination?.getAttribute('aria-controls')||'')+' '+
    (destination?.getAttribute('aria-owns')||'');
  const popups=popupIds.split(/\s+/).filter(Boolean).map(id=>document.getElementById(id))
    .filter(e=>e&&visible(e));
  const rawSuggestions=[...document.querySelectorAll(
    '[role="option"],[data-testid="autocomplete-result"],li[data-testid^="autocomplete-result-"]')]
    .filter(e=>visible(e)&&!e.closest('[aria-hidden="true"],[inert]'));
  const insideForm=rawSuggestions.filter(e=>form?.contains(e));
  const scopedSuggestions=popups.length ? rawSuggestions.filter(e=>
    popups.some(p=>p===e||p.contains(e))) : insideForm.length ? insideForm : rawSuggestions;
  // A row wrapper and its nested role=option are one DOM result, not two places.
  // Distinct sibling rows stay distinct even if they have identical text.
  const rows=scopedSuggestions.filter(e=>!scopedSuggestions.some(other=>
    other!==e&&other.contains(e)));
  const suggestions = rows.slice(0,12).map(e=>{
    const firstLine=s=>(s||'').split('\n').map(clean).find(Boolean)||'';
    const title=e.querySelector('[data-testid="autocomplete-result-label"],'+
      '[data-testid="autocomplete-result-title"],[data-testid="autocomplete-result-name"],'+
      'h3,h4,[role="heading"]');
    const names=[title?.innerText,firstLine(e.innerText),firstLine(label(e))];
    if(title && ![...title.childNodes].some(n=>
      n.nodeType===Node.TEXT_NODE&&clean(n.textContent))) {
      const first=[...title.children].find(n=>clean(n.innerText));
      if(first) names.push(firstLine(first.innerText));
    }
    for(const strong of e.querySelectorAll('strong,b,mark')) {
      // Highlighted "New" alone is not the title "New York". Read its whole parent too.
      names.push(firstLine(strong.parentElement?.innerText));
      if(!title && strong.parentElement===e && e.firstElementChild===strong &&
        ![...e.childNodes].some(n=>n.nodeType===Node.TEXT_NODE&&clean(n.textContent)))
        names.push(strong.innerText);
    }
    const nameCandidates=[...new Set(names.map(clean).filter(Boolean))].slice(0,8);
    let kind='unknown';
    const metadata=[e,...e.querySelectorAll('[data-dest-type],[data-destination-type]')];
    for(const node of metadata) {
      const raw=node.getAttribute('data-dest-type')||node.getAttribute('data-destination-type');
      if(['city','district','airport','region','country','hotel','landmark'].includes(raw)) {
        kind=raw;break;
      }
    }
    if(kind==='unknown') {
      const testid=e.getAttribute('data-testid')||'';
      const match=testid.match(/autocomplete-result-(city|district|airport|region|country|hotel)/);
      if(match) kind=match[1];
    }
    return {...handle(e),primary:clean(title?.innerText||nameCandidates[0]),
      name_candidates:nameCandidates,kind,text:clean(e.innerText||label(e)).slice(0,240)};
  });
  const buttons = [...document.querySelectorAll('button,[role="button"]')].filter(visible);
  const picker = e=>e.closest('[role="dialog"],[role="grid"],[class*="calendar"],'+
    '[class*="datepicker"],[data-testid*="datepicker"],[data-testid*="calendar"]');
  const fullDate = e => {
    const raw=e.getAttribute('data-date')||e.getAttribute('aria-label')||'';
    if(/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;
    const months='January February March April May June July August September '+
      'October November December';
    const names=months.split(' '), pattern=names.concat(names.map(s=>s.slice(0,3))).join('|');
    let match=raw.match(new RegExp(
      `\\b(${pattern})\\s+(\\d{1,2})(?:st|nd|rd|th)?[,]?\\s+(\\d{4})\\b`,'i'));
    let month,day,year;
    if(match) [,month,day,year]=match;
    else {
      match=raw.match(new RegExp(
        `\\b(\\d{1,2})(?:st|nd|rd|th)?\\s+(${pattern})\\s+(\\d{4})\\b`,'i'));
      if(!match) return '';
      [,day,month,year]=match;
    }
    const index=names.findIndex(s=>s.slice(0,3).toLowerCase()===month.slice(0,3).toLowerCase());
    return `${year}-${String(index+1).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
  };
  const openers = buttons.filter(e=>!picker(e) && (!form||form.contains(e)) &&
    /check.?in|check.?out|select dates|calendar|number of travelers|guests|adults.*rooms/i
      .test(label(e)))
    .slice(0,10).map(e=>({...handle(e),
      purpose:/date|check.?in|check.?out|calendar/i.test(label(e))?'dates':'guests',
      field:/check.?in/i.test(label(e))&&!/check.?out/i.test(label(e))?'check_in':
        /check.?out/i.test(label(e))&&!/check.?in/i.test(label(e))?'check_out':'date_range',
      text:clean(e.innerText||label(e))}));
  const days = [...document.querySelectorAll(
    '[data-date],button[aria-label],[role="gridcell"][aria-label]')]
    .filter(e=>visible(e) && (picker(e)||e.getAttribute('data-testid')==='date-cell'))
    .map(e=>{
      return {...handle(e),date:fullDate(e),selected:e.getAttribute('aria-selected')==='true'||
        e.getAttribute('aria-checked')==='true'||e.getAttribute('data-selected')==='true'||
        ['selected','range-start','range-end'].includes(e.getAttribute('data-state'))};
    }).filter(x=>x.date).slice(0,80);
  const months = buttons.filter(e=>picker(e)&&
    /^(next|previous|prev)(\s+month)?$|next month|previous month/i.test(label(e)))
    .slice(0,4).map(e=>({...handle(e),direction:/next/i.test(label(e))?'next':'previous'}));
  const counters=[], seen=new Set();
  for(const e of buttons) {
    if(!(form?.contains(e)||e.closest(
      '[role="dialog"],[data-testid*="occupancy"],[data-testid*="guest"]'))) continue;
    for(let box=e.parentElement,depth=0;box&&depth<4;box=box.parentElement,depth++) {
      const c=component(clean(box.innerText)); if(!c) continue;
      const numbers=[...box.querySelectorAll('span,input,[role="spinbutton"]')]
        .map(n=>n.getAttribute('aria-valuenow')||n.value||clean(n.textContent))
        .filter(s=>/^\d{1,2}$/.test(s));
      const unique=[...new Set(numbers)]; if(unique.length!==1) continue;
      const controls=[...box.querySelectorAll('button,[role="button"]')].filter(visible);
      if(controls.length!==2) continue;
      const direction=n=>{
        const hint=clean(label(n)+' '+(n.getAttribute('data-testid')||''));
        if(/increase|increment|add|plus|^\+$|\+$/i.test(hint)) return 'increase';
        if(/decrease|decrement|subtract|minus|^[−-]$|[−-]$/i.test(hint)) return 'decrease';
        return null;
      };
      const plus=controls.filter(n=>direction(n)==='increase');
      const minus=controls.filter(n=>direction(n)==='decrease');
      if(plus.length!==1||minus.length!==1||seen.has(box)) break;
      seen.add(box); counters.push({component:c,count:Number(unique[0]),
        popup:!!box.closest('[role="dialog"],[data-testid*="occupancy"],[data-testid*="guest"]'),
        increase:handle(plus[0]),decrease:handle(minus[0])}); break;
    }
  }
  const submits = buttons.filter(e=>
    /^(search|find hotels|show results|see results)$/i.test(label(e)) &&
    (!form||form.contains(e))).slice(0,4).map(handle);
  const records=[...document.querySelectorAll(
    '[data-testid="property-card"],[data-testid="hotel-card"],[data-listing-id]')]
    .filter(visible);
  const cards=records.length;
  const destinationSelected=!!form?.querySelector('input[name="dest_id"]')?.value;
  return {destination:destination?{...handle(destination),value:destination.value}:null,
    destination_diagnostics:destinationDiagnostics,
    fields,suggestions,openers,days,months,counters,submits,record_count:cards,
    suggestion_scope:popups.length?'input_popup':insideForm.length?'hotel_form':'visible_options',
    destination_selected:destinationSelected,
    record_signature:records.slice(0,5).map(e=>clean(e.innerText).slice(0,200)).join('|'),
    ready_state:document.readyState};
}"""
)


def _place(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().strip().rstrip(",.").split())


def place_matches(actual, wanted):
    """Literal names plus one explicit common city alias; never substring/fuzzy matching."""
    observed, expected = _place(actual.split(",")[0]), _place(wanted.split(",")[0])
    new_york = {"new york", "new york city", "nyc"}
    return observed == expected or observed in new_york and expected in new_york


def match_destination_suggestions(suggestions, wanted):
    matching = [
        row
        for row in suggestions
        if row.get("enabled", True)
        and any(
            place_matches(name, wanted)
            for name in row.get("name_candidates", [row.get("primary", "")])
        )
    ]
    # A city result is a closer match for a city-named hotel search than its state,
    # district or airport. Multiple cities (or untyped matches) remain ambiguous.
    cities = [row for row in matching if row.get("kind") == "city"]
    preferred = cities or matching
    diagnostics = {
        "requested": wanted,
        "visible_count": len(suggestions),
        "matching_count": len(matching),
        "preferred_count": len(preferred),
        "reason": "unique_match"
        if len(preferred) == 1
        else ("ambiguous_matches" if preferred else "no_matching_suggestion"),
        "candidates": [
            {
                "primary": row.get("primary", ""),
                "text": row.get("text", ""),
                "names": row.get("name_candidates", [row.get("primary", "")]),
                "kind": row.get("kind", "unknown"),
                "matched": row in matching,
            }
            for row in suggestions
        ],
    }
    return (preferred[0] if len(preferred) == 1 else None), diagnostics


class HotelSearchDriver:
    """DOM-driven actions confined to the reviewed website and typed search controls."""

    def __init__(self, page, approved_origin, *, permitted=lambda: True, restricted=lambda: False):
        self.page, self.approved_origin = page, approved_origin
        self.permitted, self.restricted = permitted, restricted
        self.deadline = time.monotonic() + MAX_SECONDS
        self.actions = 0
        self.date_cache = None
        self.destination_diagnostics = None
        self.destination_suggestions = None
        self.destination_input_observation = None
        self.booking = urlsplit(approved_origin).hostname in {"booking.com", "www.booking.com"}

    def guard(self):
        if not self.permitted():
            raise WebsiteError("Hotel search cancelled or dashboard session expired.")
        if time.monotonic() >= self.deadline or self.actions > MAX_ACTIONS:
            raise WebsiteError("Hotel search reached its time/action limit. Inspect the browser.")
        if origin(self.page.url) != self.approved_origin:
            raise WebsiteError("Hotel search left the reviewed website. No further actions ran.")
        if self.restricted():
            raise WebsiteError(
                "Website verification or access restriction detected. Complete it manually."
            )

    def inventory(self):
        self.guard()
        return self.page.evaluate(HOTEL_INVENTORY)

    def locate(self, control):
        self.guard()
        locator = self.page.locator(f'[data-agentic-hotel-id="{control["id"]}"]')
        if (
            locator.count() != 1
            or not locator.is_visible()
            or not locator.is_enabled()
            or not control["enabled"]
        ):
            raise WebsiteError(
                "A hotel search control changed or is disabled. No further actions ran."
            )
        identity = locator.evaluate(
            "e=>({tag:e.tagName,name:e.getAttribute('name')||'',role:e.getAttribute('role')||''})"
        )
        if any(identity[key] != control[key] for key in ("tag", "name", "role")):
            raise WebsiteError("A hotel search control changed identity. Review the browser.")
        return locator

    def act(self, control, value=None):
        if self.actions >= MAX_ACTIONS:
            raise WebsiteError("Hotel search reached its action limit. No further actions ran.")
        self.actions += 1
        target = self.locate(control)
        if value is None:
            target.click(timeout=5000)
        else:
            target.fill(value, timeout=5000)
            if target.input_value() != value:
                raise WebsiteError("A hotel field did not retain its requested value.")

    def wait(self, predicate, *, seconds=4):
        limit = min(self.deadline, time.monotonic() + seconds)
        while time.monotonic() < limit:
            try:
                state = self.inventory()
                if predicate(state):
                    return state
            except PlaywrightError as exc:
                # A submitted navigation can replace the document between observations.
                # Retry observation only; never repeat a fill, click or submission.
                if not any(
                    marker in str(exc).casefold()
                    for marker in ("execution context was destroyed", "cannot find context")
                ):
                    raise
            self.page.wait_for_timeout(150)
        raise WebsiteError(
            "The expected hotel form state did not appear. "
            "Inspect the browser; no action is retried."
        )

    def destination(self, wanted):
        state = self.inventory()
        limit = min(self.deadline, time.monotonic() + 4)
        while state["destination"] is None and time.monotonic() < limit:
            if state.get("destination_diagnostics", {}).get("matching_fields", 0) > 1:
                break
            # Observation only while a dynamic form renders; never repeat input actions.
            self.page.wait_for_timeout(200)
            state = self.inventory()
        self.destination_diagnostics = state.get("destination_diagnostics")
        control = state["destination"]
        if control is None:
            if (self.destination_diagnostics or {}).get("matching_fields", 0) > 1:
                raise WebsiteError(
                    "Multiple destination fields match the hotel form. "
                    "Close the duplicate search panel or select one form, then review again. "
                    "No fields were entered. See destination-field diagnostics."
                )
            raise WebsiteError(
                "No recognized standard destination field appeared in the rendered form. "
                "Review destination-field diagnostics and page loading; no fields were entered. "
                "A standalone free-text box needs destination/form metadata before automation."
            )
        changed = not place_matches(control["value"], wanted)
        if changed:
            self.act(control, wanted)
        self.destination_input_observation = {
            "expected": wanted,
            "observed": wanted if changed else control["value"],
            "selection_confirmed": False,
            "entered_by_workflow": changed,
        }
        if (self.booking and (changed or not state.get("destination_selected"))) or state[
            "suggestions"
        ]:
            # Debounced/async suggestions can initially contain old or partial rows.
            # Observe a stable candidate set; never repeat the fill or click automatically.
            selection_limit = min(self.deadline, time.monotonic() + 8)
            signature, stable_since, choice = None, None, None
            while time.monotonic() < selection_limit:
                state = self.inventory()
                current_input = (state["destination"] or {}).get("value", "")
                if not place_matches(current_input, wanted):
                    raise WebsiteError(
                        "Destination text changed while suggestions were loading. "
                        "No option was clicked; review the browser before trying again."
                    )
                choice, diagnostic = match_destination_suggestions(state["suggestions"], wanted)
                diagnostic["scope"] = state.get("suggestion_scope", "unknown")
                self.destination_suggestions = diagnostic
                current = repr(
                    [
                        (
                            row.get("primary"),
                            row.get("text"),
                            row.get("name_candidates"),
                            row.get("kind"),
                        )
                        for row in state["suggestions"]
                    ]
                )
                if current != signature:
                    signature, stable_since = current, time.monotonic()
                if choice is not None and time.monotonic() - stable_since >= 0.6:
                    break
                self.page.wait_for_timeout(150)
            else:
                choice = None
            if choice is None:
                raise WebsiteError(
                    "Destination suggestions are ambiguous, do not match, or did not settle. "
                    "See Destination suggestion matching for the actual choices. "
                    "Choose the intended place manually in this browser, then prepare a new review."
                )
            self.destination_suggestions["attempted"] = {
                "primary": choice["primary"],
                "kind": choice.get("kind", "unknown"),
            }
            self.act(choice)
            state = self.wait(lambda s: not s["suggestions"])
        else:
            state = self.inventory()
        actual = (state["destination"] or {}).get("value", "")
        if not place_matches(actual, wanted):
            raise WebsiteError("The selected destination differs from the reviewed destination.")
        self.destination_input_observation.update(observed=actual, selection_confirmed=True)
        if self.destination_suggestions and self.destination_suggestions.get("attempted"):
            self.destination_suggestions["selected"] = self.destination_suggestions["attempted"]
        return actual

    @staticmethod
    def read_dates(state):
        answer = {}
        for key in ("check_in", "check_out"):
            values = {
                item["value"] for item in state["fields"] if item["key"] == key and item["value"]
            }
            if len(values) > 1:
                raise WebsiteError(
                    "Conflicting canonical date fields are visible. Review the form."
                )
            if len(values) == 1:
                value = next(iter(values))
                try:
                    date.fromisoformat(value)
                    answer[key] = value
                except ValueError:
                    pass
        selected = sorted({item["date"] for item in state["days"] if item["selected"]})
        if selected:
            observed = {"check_in": selected[0]}
            if len(selected) > 1:
                observed["check_out"] = selected[-1]
            for key, value in observed.items():
                if key in answer and answer[key] != value:
                    raise WebsiteError(
                        "Date widget and canonical form dates conflict. Review the calendar."
                    )
                answer[key] = value
        return answer

    def dates(self, check_in, check_out):
        wanted_dates = {"check_in": check_in, "check_out": check_out}
        state = self.inventory()
        if self.cached_dates(state) == wanted_dates:
            return wanted_dates
        for key, wanted in (("check_in", check_in), ("check_out", check_out)):
            state = self.inventory()
            if self.read_dates(state).get(key) == wanted:
                continue
            fields = [item for item in state["fields"] if item["key"] == key and item["writable"]]
            if len(fields) == 1:
                self.act(fields[0], wanted)
                self.wait(lambda s, key=key, wanted=wanted: self.read_dates(s).get(key) == wanted)
                continue
            if not state["days"]:
                openers = [
                    item
                    for item in state["openers"]
                    if item["purpose"] == "dates"
                    and item.get("field", "date_range") in {key, "date_range"}
                ]
                if len(openers) != 1:
                    raise WebsiteError(
                        "No unique calendar opener is visible. Open the date picker manually."
                    )
                self.act(openers[0])
                state = self.wait(lambda s: bool(s["days"]))
            for hop in range(MAX_MONTH_HOPS + 1):
                choices = [
                    item for item in state["days"] if item["date"] == wanted and item["enabled"]
                ]
                if len(choices) == 1:
                    self.act(choices[0])
                    state = self.wait(
                        lambda s, key=key, wanted=wanted: (
                            self.read_dates(s).get(key) == wanted or not s["days"]
                        )
                    )
                    break
                visible_months = sorted({item["date"][:7] for item in state["days"]})
                if not visible_months or visible_months[0] <= wanted[:7] <= visible_months[-1]:
                    raise WebsiteError(
                        "The requested date is disabled, ambiguous or lacks full-date evidence."
                    )
                if hop == MAX_MONTH_HOPS:
                    raise WebsiteError(
                        "Calendar month-navigation limit reached. No search submitted."
                    )
                direction = "next" if wanted[:7] > visible_months[-1] else "previous"
                controls = [
                    item
                    for item in state["months"]
                    if item["direction"] == direction and item["enabled"]
                ]
                if len(controls) != 1:
                    raise WebsiteError("No unique calendar month-navigation control is visible.")
                old_months = visible_months
                self.act(controls[0])
                state = self.wait(
                    lambda s, old_months=old_months: (
                        sorted({item["date"][:7] for item in s["days"]}) != old_months
                    )
                )
            else:
                raise WebsiteError("Calendar month-navigation limit reached. No search submitted.")
        state = self.inventory()
        wanted = {"check_in": check_in, "check_out": check_out}
        if self.read_dates(state) != wanted and not state["days"]:
            openers = [item for item in state["openers"] if item["purpose"] == "dates"]
            if len(openers) == 1:
                self.act(openers[0])
                state = self.wait(lambda s: bool(s["days"]))
        if self.read_dates(state) != wanted:
            raise WebsiteError(
                "Both full dates could not be independently read back. Search was not submitted."
            )
        summary = self.date_summary(state)
        if all(self.summary_has_date(summary, value) for value in wanted.values()):
            self.date_cache = (wanted, summary)
        if state["days"]:
            self.dismiss(lambda s: not s["days"])
        return wanted

    @staticmethod
    def date_summary(state):
        return " | ".join(item["text"] for item in state["openers"] if item["purpose"] == "dates")

    @staticmethod
    def summary_has_date(summary, value):
        parsed = date.fromisoformat(value)
        month = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()[parsed.month - 1]
        return value in summary or bool(
            re.search(
                rf"\b(?:{month}\w*\s+0?{parsed.day}(?:st|nd|rd|th)?|0?{parsed.day}(?:st|nd|rd|th)?\s+{month}\w*)\b",
                summary,
                re.I,
            )
        )

    def cached_dates(self, state):
        observed = self.read_dates(state)
        if (
            self.date_cache
            and self.date_summary(state) == self.date_cache[1]
            and all(self.date_cache[0].get(key) == value for key, value in observed.items())
        ):
            return self.date_cache[0]
        return observed

    def dismiss(self, predicate):
        self.guard()
        if self.actions >= MAX_ACTIONS:
            raise WebsiteError("Hotel search reached its action limit. No further actions ran.")
        self.actions += 1
        self.page.keyboard.press("Escape")
        self.wait(predicate)

    @staticmethod
    def read_counts(state):
        answer = {}
        for item in state["counters"]:
            component, count = item["component"], item["count"]
            if component in answer and answer[component] != count:
                raise WebsiteError("Conflicting occupancy counters are visible.")
            answer[component] = count
        for item in state["fields"]:
            if item["key"] in {"adults", "rooms", "children"} and item["value"].isdigit():
                component, count = item["key"], int(item["value"])
                if component in answer and answer[component] != count:
                    raise WebsiteError("Occupancy input and counter disagree.")
                answer[component] = count
        if not answer:
            for item in state["openers"]:
                if item["purpose"] == "guests":
                    counts = guest_counts(item["text"])
                    if counts:
                        for component, count in counts.items():
                            if component in answer and answer[component] != count:
                                raise WebsiteError("Conflicting occupancy summaries are visible.")
                            answer[component] = count
        return answer

    def occupancy(self, adults, rooms, children=None):
        wanted = {"adults": adults, "rooms": rooms}
        if children is not None:
            wanted["children"] = children
        state = self.inventory()
        if any(self.read_counts(state).get(key) != value for key, value in wanted.items()):
            if not state["counters"] and not any(item["key"] in wanted for item in state["fields"]):
                controls = [item for item in state["openers"] if item["purpose"] == "guests"]
                if len(controls) != 1:
                    raise WebsiteError("No unique adults/rooms widget is visible.")
                self.act(controls[0])
                state = self.wait(
                    lambda s: (
                        bool(s["counters"]) or any(item["key"] in wanted for item in s["fields"])
                    )
                )
        for key, value in wanted.items():
            while self.read_counts(state).get(key) != value:
                fields = [
                    item for item in state["fields"] if item["key"] == key and item["writable"]
                ]
                if len(fields) == 1:
                    self.act(fields[0], str(value))
                    state = self.wait(
                        lambda s, key=key, value=value: self.read_counts(s).get(key) == value
                    )
                    continue
                groups = [item for item in state["counters"] if item["component"] == key]
                if len(groups) != 1:
                    raise WebsiteError(
                        "A unique labelled occupancy counter could not be identified."
                    )
                old = groups[0]["count"]
                expected = old + (1 if value > old else -1)
                self.act(groups[0]["increase" if value > old else "decrease"])
                state = self.wait(lambda s, key=key, old=old: self.read_counts(s).get(key) != old)
                if self.read_counts(state).get(key) != expected:
                    raise WebsiteError(
                        "An occupancy counter changed unexpectedly. No further clicks ran."
                    )
        actual = self.read_counts(state)
        if any(actual.get(key) != value for key, value in wanted.items()):
            raise WebsiteError("Requested adult/room counts are unconfirmed. No search submitted.")
        if any(item.get("popup") for item in state["counters"]):
            self.dismiss(lambda s: not any(item.get("popup") for item in s["counters"]))
            actual = self.read_counts(self.inventory())
            if any(actual.get(key) != value for key, value in wanted.items()):
                raise WebsiteError("Occupancy summary did not retain the requested counts.")
        return {key: actual[key] for key in wanted}

    def submit(self, request, *, on_submission=lambda _: None):
        state = self.inventory()
        actual = (state["destination"] or {}).get("value", "")
        if not place_matches(actual, request.destination):
            raise WebsiteError("Destination changed before search submission.")
        dates, counts = self.cached_dates(state), self.read_counts(state)
        if dates != {"check_in": request.check_in, "check_out": request.check_out}:
            # Reopen a closed widget to verify its DOM-selected full dates again.
            dates = self.dates(request.check_in, request.check_out)
            state = self.inventory()
            counts = self.read_counts(state)
        wanted = {"adults": request.adults, "rooms": request.rooms}
        if request.children is not None:
            wanted["children"] = request.children
        if any(counts.get(key) != value for key, value in wanted.items()):
            raise WebsiteError("Occupancy changed before submission. No search clicked.")
        if len(state["submits"]) != 1:
            raise WebsiteError("No unique hotel Search button is visible.")
        previous_url, previous_signature = self.page.url, state["record_signature"]
        on_submission("attempted")
        self.act(state["submits"][0])
        on_submission("submitted")
        state = self.wait(
            lambda s: (
                s["record_count"] > 0
                and (
                    not previous_signature
                    or s["record_signature"] != previous_signature
                    or self.page.url != previous_url
                )
            ),
            seconds=12,
        )
        return {"record_elements": state["record_count"], "criteria_verified_in_results": False}


def run_hotel_search(driver, request, *, on_progress=lambda _: None):
    """One explicitly approved goal, finite local steps, no replanning API loop."""
    parts = urlsplit(driver.approved_origin)
    report = {
        "execution_id": uuid4().hex,
        "workflow": "complete_hotel_search",
        "source_url": urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")),
        "coverage": "site_filters",
        "status": "running",
        "stage": "destination",
        "submitted": False,
        "submission_attempted": False,
        "actions": [],
        "requirements": [
            {
                **row,
                "status": "deferred_to_extraction"
                if row["application"] == "extraction"
                else "unconfirmed",
            }
            for row in request.requirements()
        ],
        "pending_fields": ["destination", "check_in", "check_out", "guests"],
        "missing_fields": [],
        "planning_api_calls": 0,
        "results_verified": False,
    }

    def completed(field, value):
        expected = next(row["value"] for row in report["requirements"] if row["field"] == field)
        for row in report["requirements"]:
            if row["field"] == field:
                row.update(status="verified_in_form", observed=[value])
        report["pending_fields"] = [
            row["field"] for row in report["requirements"] if row["status"] == "unconfirmed"
        ]
        report["actions"].append(
            {
                "control": field.replace("_", " "),
                "action": "prepare",
                "status": "value_verified",
                "expected": expected,
                "observed": value,
            }
        )
        report["browser_actions"] = getattr(driver, "actions", 0)
        on_progress(report)

    try:
        on_progress(report)
        destination = driver.destination(request.destination)
        if getattr(driver, "destination_diagnostics", None):
            report["destination_diagnostics"] = driver.destination_diagnostics
        if getattr(driver, "destination_suggestions", None):
            report["destination_suggestions"] = driver.destination_suggestions
        if not place_matches(destination, request.destination):
            raise WebsiteError("Destination read-back differs from the reviewed target.")
        completed("destination", destination)
        report["stage"] = "dates"
        on_progress(report)
        dates = driver.dates(request.check_in, request.check_out)
        if dates != {"check_in": request.check_in, "check_out": request.check_out}:
            raise WebsiteError("Date read-back differs from the reviewed targets.")
        for field, value in dates.items():
            completed(field, value)
        report["stage"] = "occupancy"
        on_progress(report)
        counts = driver.occupancy(request.adults, request.rooms, request.children)
        wanted = {"adults": request.adults, "rooms": request.rooms}
        if request.children is not None:
            wanted["children"] = request.children
        if any(counts.get(key) != value for key, value in wanted.items()):
            raise WebsiteError("Occupancy read-back differs from the reviewed targets.")
        completed("guests", ", ".join(f"{value} {key}" for key, value in counts.items()))
        report["stage"] = "submit"
        on_progress(report)

        def submission(state):
            report["submission_attempted"] = True
            report["browser_actions"] = getattr(driver, "actions", 0)
            if state == "submitted":
                report["submitted"] = True
            on_progress(report)

        report["result_observation"] = driver.submit(request, on_submission=submission)
        if report["result_observation"].get("record_elements", 0) <= 0 or not report["submitted"]:
            raise WebsiteError(
                "No completed search with listing elements was observed. No automatic extraction."
            )
        report.update(submitted=True, status="search_completed", stage="results", pending_fields=[])
        report["browser_actions"] = getattr(driver, "actions", 0)
        on_progress(report)
        return report
    except (WebsiteError, PlaywrightError) as exc:
        if getattr(driver, "destination_diagnostics", None):
            report["destination_diagnostics"] = driver.destination_diagnostics
        if getattr(driver, "destination_suggestions", None):
            report["destination_suggestions"] = driver.destination_suggestions
        if getattr(driver, "destination_input_observation", None):
            report["destination_input_observation"] = driver.destination_input_observation
            if not any(action["control"] == "destination" for action in report["actions"]):
                report["actions"].append(
                    {
                        "control": "destination text (location not yet confirmed)",
                        "action": "fill"
                        if driver.destination_input_observation["entered_by_workflow"]
                        else "read_back",
                        "status": "input_verified",
                        "expected": driver.destination_input_observation["expected"],
                        "observed": driver.destination_input_observation["observed"],
                    }
                )
        report["browser_actions"] = getattr(driver, "actions", 0)
        report.update(
            status="needs_review",
            guidance=str(exc)
            if isinstance(exc, WebsiteError)
            else "A hotel browser action failed or timed out. "
            "It may have taken effect; inspect the tab. No automatic retry.",
        )
        on_progress(report)
        error = WebsiteError(report["guidance"])
        error.navigation_result = report
        raise error from None
