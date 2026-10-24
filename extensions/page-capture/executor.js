/* Packaged, isolated-world executor. No model-provided JavaScript or selectors. */
(() => {
  'use strict';
  const version = '0.4.4';
  if (globalThis.__agenticTabExecutor?.version === version) return;
  const token = crypto.randomUUID();
  let observedUrl = null;
  const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
  const visible = e => !!e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden';
  const sensitive = e => e.matches('input[type="password"],input[type="email"],input[type="tel"],input[autocomplete="username"],input[autocomplete="one-time-code"],input[autocomplete^="cc-"],input[name*="password" i],input[name*="otp" i],input[name*="token" i],input[name*="email" i],input[name="code" i]') || /password|passcode|verification code|credit card|security token/i.test([e.name, e.getAttribute('aria-label'), e.autocomplete].join(' '));
  const forbidden = /\b(pay(?:ment)?|purchase|reserve|book now|confirm booking|delete|send message|sign in|log in|register|sign up|subscribe)\b/i;
  const safeUrl = value => {
    const u = new URL(value, location.href);
    if (!['https:', 'http:'].includes(u.protocol) || u.username || u.password) throw new Error('unsupported');
    const allowed = /^(?:id|item|product|article|story|hotel|listing|slug|variant|page|p|(?:item|product|article|story|hotel|listing|variant)_id|checkin|checkout|check_in|check_out|group_adults|group_children|no_rooms|adults|children|rooms|dest_id|dest_type|ss)$/i;
    const query = [...u.searchParams].filter(([k,v]) => allowed.test(k) && v.length <= 128 && !/https?:|@|[\u0000-\u001f]/i.test(v)).slice(0, 12);
    u.search = new URLSearchParams(query).toString(); u.hash = ''; return u.href;
  };
  const roots = () => {
    const found = [document];
    for (let i = 0; i < found.length; i++) for (const e of found[i].querySelectorAll('*')) if (e.shadowRoot) found.push(e.shadowRoot);
    return found;
  };
  const restricted = () => {
    const text = clean((document.querySelector('main,[role="main"]') || document.body)?.innerText).slice(0, 30000);
    const denied = /access is temporarily restricted|we detected unusual activity|verify (?:that )?you are (?:a )?human|complete (?:the |this )?(?:captcha|security check)|slide (?:to|the).*verif/i.test(text) ||
      (text.length < 6000 && /^access denied\b/i.test(text)) || /^access denied\b/i.test(document.title);
    const challenge = [...document.querySelectorAll('iframe')].some(e => {
      const box = e.getBoundingClientRect();
      return visible(e) && box.width > 25 && box.height > 25 && box.bottom > 0 && box.top < innerHeight && box.right > 0 && box.left < innerWidth && /captcha|challenge|turnstile/i.test([e.src,e.title].join(' '));
    });
    if (denied || challenge) return true;
    // A newsletter input below the results is not an authentication challenge.
    // Pause only for a visible credential/OTP form or an active auth dialog.
    return [...document.querySelectorAll('input')].some(e => {
      if (!visible(e) || !sensitive(e)) return false;
      const box = e.getBoundingClientRect();
      if (box.width <= 0 || box.height <= 0 || box.bottom <= 0 || box.top >= innerHeight || box.right <= 0 || box.left >= innerWidth) return false;
      if (e.type === 'password' || e.autocomplete === 'one-time-code' || /otp|password|passcode|verification code/i.test([e.name,e.getAttribute('aria-label')].join(' '))) return true;
      const scope = e.closest('[role="dialog"],form');
      return !!scope && /\b(sign in|log in|verify|verification|security code)\b/i.test(clean(scope.innerText));
    });
  };
  const ensure = expected => { if (expected !== token || observedUrl !== location.href) throw new Error('stale_document'); if (restricted()) throw new Error('access_restriction'); };
  const pause = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
  const identity = e => ({tag:e.tagName,role:e.getAttribute('role')||'',name:e.name||'',type:e.type||'',href:e.tagName==='A'?e.href:'',submits_form:!!e.form&&['BUTTON','INPUT'].includes(e.tagName)&&['submit','image'].includes(e.type),text:clean(e.innerText).slice(0,400),value:['INPUT','TEXTAREA','SELECT'].includes(e.tagName)?String(e.value||'').slice(0,300):e.isContentEditable?clean(e.innerText).slice(0,300):e.getAttribute('aria-valuenow')||''});
  const counter = e => typeof globalThis.agenticInspectCounter === 'function' ? globalThis.agenticInspectCounter(e) : null;
  // Transported JSON objects have no semantic property order. Compare every
  // counter fact exactly, as the managed adapter's dictionary comparison does.
  const sameCounter = (actual, expected) => !!actual && !!expected &&
    Object.keys(actual).length === Object.keys(expected).length &&
    Object.keys(expected).every(key => Object.prototype.hasOwnProperty.call(actual,key) && actual[key] === expected[key]);
  const stale = (reason, fields=[]) => {
    const error = new Error('control_changed');
    error.counterPreflight = {reason,mismatched_fields:fields}; throw error;
  };
  const counterFields = ['label','value','direction','method','minimum','maximum','owner_readonly','evidence'];
  const counterMismatch = (actual, expected) => {
    if (!actual || !expected) return ['counter'];
    const fields = counterFields.filter(key => Object.prototype.hasOwnProperty.call(actual,key) !== Object.prototype.hasOwnProperty.call(expected,key) || actual[key] !== expected[key]);
    if ([...Object.keys(actual),...Object.keys(expected)].some(key => !counterFields.includes(key))) fields.push('keys');
    return fields;
  };
  const counterRejected = (decision, error) => {
    const preflight = error.counterPreflight || {reason:'control_changed',mismatched_fields:[]};
    const guidance = 'Counter preflight: '+preflight.reason+(preflight.mismatched_fields.length ? ' ('+preflight.mismatched_fields.join(', ')+')':'')+'. No click sent; inspect fresh controls before continuing.';
    return {status:'counter_unconfirmed',
      expected:/^\d{1,2}$/.test(decision.value) ? Number(decision.value) : null,
      observed:null,steps:0,dispatched:false,counter_preflight:preflight,
      note:guidance,guidance};
  };
  function target(decision, facts) {
    const id = String(decision.control_id || '').replace(/^0:/, '');
    if (!/^\d{1,3}$/.test(id) || !facts || typeof facts !== 'object') stale('invalid_reference');
    const matches = roots().flatMap(root => [...root.querySelectorAll('[data-agentic-loop-id="' + id + '"]')]);
    if (matches.length !== 1) stale('reference_ambiguous');
    const e = matches[0];
    if (!visible(e) || e.disabled || e.getAttribute('aria-disabled') === 'true' || e.closest('[inert]')) stale('not_actionable');
    if (sensitive(e) || forbidden.test([facts.label, facts.name, facts.text].join(' '))) throw new Error('unsupported');
    const current = identity(e);
    const changed = Object.keys(current).filter(key => current[key] !== (key === 'href' ? facts.raw_href ?? facts.href : facts[key]));
    if (changed.length) stale('identity_changed',changed);
    const fresh = facts.counter ? counter(e) : null;
    if (facts.counter && !sameCounter(fresh,facts.counter)) stale('counter_changed',counterMismatch(fresh,facts.counter));
    return e;
  }
  function setValue(e, value) {
    if (e.readOnly || e.getAttribute('aria-readonly') === 'true') throw new Error('unsupported');
    e.focus();
    // Focus handlers may replace a controlled field. Do not edit or verify a
    // detached copy while the live form remains unchanged.
    if (!e.isConnected) throw new Error('control_changed');
    if (e.isContentEditable) e.textContent = value;
    else {
      const prototype = e.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : e.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(prototype, 'value').set.call(e, value);
    }
    // Use the native value setter plus DOM events for controlled inputs. These
    // events are synthetic (isTrusted=false); composed lets an open-shadow-root
    // field notify the owning app outside its root, as normal input does.
    const input = e.tagName === 'SELECT' ? new Event('input', {bubbles:true,composed:true}) :
      new InputEvent('input', {bubbles:true,composed:true,inputType:'insertReplacementText',data:value});
    e.dispatchEvent(input); e.dispatchEvent(new Event('change', {bubbles:true,composed:true}));
  }
  const fullDates = text => {
    const dates = new Set(), months = 'january february march april may june july august september october november december'.split(' ');
    const add = (year,month,day) => {
      const value = new Date(Date.UTC(Number(year),Number(month)-1,Number(day)));
      if (value.getUTCFullYear() === Number(year) && value.getUTCMonth()+1 === Number(month) && value.getUTCDate() === Number(day)) dates.add(value.toISOString().slice(0,10));
    };
    for (const m of String(text).matchAll(/\b(\d{4})-(\d{2})-(\d{2})\b/g)) add(m[1],m[2],m[3]);
    const names = months.concat(months.map(name => name.slice(0,3)),['sept']).join('|'), month = name => months.findIndex(value => value.startsWith(name.slice(0,3)))+1;
    for (const m of String(text).toLowerCase().matchAll(new RegExp('\\b('+names+')\\.?\\s+(\\d{1,2})(?:st|nd|rd|th)?(?:,\\s*|\\s+)(\\d{4})\\b','g'))) add(m[3],month(m[1]),m[2]);
    for (const m of String(text).toLowerCase().matchAll(new RegExp('\\b(\\d{1,2})(?:st|nd|rd|th)?\\s+('+names+')\\.?(?:,\\s*|\\s+)(\\d{4})\\b','g'))) add(m[3],month(m[2]),m[1]);
    return [...dates];
  };
  const dateText = e => [e.getAttribute('data-date'),e.getAttribute('datetime'),e.getAttribute('aria-label'),(e.getAttribute('aria-labelledby') || '').split(/\s+/).map(id => (e.getRootNode().getElementById?.(id) || document.getElementById(id))?.textContent || '').join(' '),e.getAttribute('title'),e.innerText].join(' ');
  const selectedDay = (e,allowHidden=false) => e.isConnected && (allowHidden || visible(e)) && (e.matches('input[type="checkbox"],input[type="radio"]') && e.checked || e.getAttribute('aria-selected') === 'true' || e.getAttribute('aria-checked') === 'true' || /^(?:selected|checked)$/.test(e.getAttribute('data-state') || ''));
  async function clickDate(e,facts,payload) {
    if (e.tagName === 'A' || facts.submits_form) return null;
    const text = [facts.date,facts.label,facts.text].join(' '), dates = fullDates(text);
    const semantic = e.matches('[role="gridcell"]') || !!e.closest('[role="gridcell"],[role="grid"]') || !!facts.date || dates.length === 1 && e.matches('button,[role="button"],[role="checkbox"],[role="radio"]');
    if (!semantic) return null;
    if (dates.length !== 1) {
      if (dates.length > 1) throw new Error('control_changed');
      if (/\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}\s+[a-z\u00c0-\u024f]{3,12}\.?,?\s+\d{4}|[a-z\u00c0-\u024f]{3,12}\.?\s+\d{1,2}(?:,\s*|\s+)\d{4})\b/i.test(text)) return {status:'value_mismatch',expected:null,observed:null,calendar:{date:null,status:'unconfirmed',dispatched:false,target:'observed_control'},note:'This calendar date could not be interpreted unambiguously. No click was sent; inspect its full date label.'};
      return null;
    }
    const expected = dates[0], own = fullDates(dateText(e));
    if (own.length !== 1 || own[0] !== expected) throw new Error('control_changed');
    let owner = e;
    if (facts.date_owner_id != null) {
      const id = String(facts.date_owner_id).replace(/^0:/,'');
      if (!/^\d{1,3}$/.test(id)) throw new Error('control_changed');
      const owners = roots().flatMap(root => [...root.querySelectorAll('[data-agentic-loop-id="'+id+'"]')]);
      if (owners.length !== 1 || !owners[0].matches('[role="gridcell"]') || !(owners[0] === e || owners[0].contains(e))) throw new Error('control_changed');
      owner = owners[0];
      const ownerDates = fullDates(dateText(owner));
      if (ownerDates.length !== 1 || ownerDates[0] !== expected) throw new Error('control_changed');
    }
    const available = n => visible(n) && n.getBoundingClientRect().width > 0 && n.getBoundingClientRect().height > 0 && !n.disabled && n.getAttribute('aria-disabled') !== 'true' && !n.closest('[inert]') && !sensitive(n);
    const sameDay = (n,dayOwner=owner) => {
      const values = fullDates(dateText(n));
      const day = clean(n.innerText || n.getAttribute('aria-label') || (n.matches('input') ? n.value : ''));
      return values.length === 1 ? values[0] === expected : !values.length && dayOwner.contains(n) && /^\d{1,2}$/.test(day) && Number(day) === Number(expected.slice(-2));
    };
    // Only descend inside the observed target. Never jump to a sibling date or
    // another calendar. A day-only inner label needs the observed full-date owner.
    const rendered = facts.date_owner_id == null ? [] : [...e.querySelectorAll('button,[role="button"],[role="checkbox"],[role="radio"],input[type="checkbox"],input[type="radio"]')].filter(available);
    if (rendered.some(n => fullDates(dateText(n)).length && !sameDay(n))) throw new Error('control_changed');
    const nested = rendered.filter(n => sameDay(n));
    const leaves = nested.filter(n => !nested.some(other => other !== n && n.contains(other)));
    if (leaves.length > 1) throw new Error('control_changed');
    const actionable = leaves[0] || e;
    if (!available(actionable)) throw new Error('control_changed');
    const scope = owner.closest('[role="grid"],[role="dialog"]') || owner;
    const selection = (allowHidden=false) => {
      let dayOwner = owner;
      if (!owner.isConnected && scope.isConnected && scope !== owner) {
        const replacements = [...scope.querySelectorAll('[role="gridcell"]')].filter(n => {
          const values = fullDates(dateText(n)); return values.length === 1 && values[0] === expected;
        });
        if (replacements.length !== 1) return '';
        dayOwner = replacements[0];
      }
      return JSON.stringify([dayOwner,...dayOwner.querySelectorAll('[aria-selected],[aria-checked],[data-state],input[type="checkbox"],input[type="radio"]')].filter(n => sameDay(n,dayOwner) && selectedDay(n,allowHidden)).map(n => [n.getAttribute('aria-label'),n.getAttribute('aria-selected'),n.getAttribute('aria-checked'),n.getAttribute('data-state'),n.checked]));
    };
    const snapshot = () => JSON.stringify([scope.isConnected,visible(scope),clean(scope.innerText).slice(0,2000),...scope.querySelectorAll('[aria-selected],[aria-checked],[data-state]')].map(n => n instanceof Element ? [n.getAttribute('aria-label'),n.getAttribute('aria-selected'),n.getAttribute('aria-checked'),n.getAttribute('data-state')] : n));
    const metadata = {date:expected,target:actionable === e ? 'observed_control':'inner_action',dispatched:false};
    // aria-selected may mark every interior day in a previous range. Only a
    // native checked choice is idempotent without knowing the requested endpoint.
    if (actionable.matches('input[type="checkbox"],input[type="radio"]') && actionable.checked) return {status:'action_performed',calendar:{...metadata,status:'already_selected'},note:'This native day choice is already checked; no click was sent. Stay dates still require a fresh form-summary check.'};
    const before = snapshot(), previousSelection = selection(true);
    ensure(payload.document_token);
    actionable.click(); // One synthetic DOM click; never a trusted pointer claim.
    let changed = false;
    for (let n=0;n<8;n++) {
      await pause(100); ensure(payload.document_token);
      const selected = selection(true);
      if (selected && selected !== '[]' && selected !== previousSelection) return {status:'action_performed',calendar:{...metadata,status:'selected',dispatched:true},note:'One DOM date click was sent and its same-day selection changed. Verify the final stay dates in the form summary.'};
      changed = changed || snapshot() !== before;
    }
    return {status:changed ? 'action_performed':'value_mismatch',expected,observed:null,calendar:{...metadata,status:changed ? 'changed':'unconfirmed',dispatched:true},note:changed ? 'The calendar changed after one DOM click, but the requested day is not independently confirmed; inspect a fresh observation.' : 'No same-day selection or local calendar change was confirmed after one DOM click. It was not repeated; inspect the calendar before continuing.'};
  }
  async function execute(payload) {
    ensure(payload.document_token);
    const d = payload.decision || {}, facts = payload.facts || {}, action = d.action;
    if (action === 'wait') { await pause(700); return {status:'waited'}; }
    if (action === 'scroll') {
      if (!['up','down'].includes(d.value)) throw new Error('unsupported');
      window.scrollBy({top:d.value === 'down' ? 650 : -650,behavior:'instant'}); await pause(250); return {status:'scrolled',direction:d.value};
    }
    if (action === 'back') {
      const previous = new URL(facts.previous_url || '');
      if (previous.origin !== location.origin) throw new Error('origin_changed');
      return {status:'returned_to_observed_page',url:safeUrl(previous.href),_navigation_url:previous.href,_navigation_from_url:location.href};
    }
    let e;
    try { e = target(d, facts); }
    catch(error) {
      if (action === 'set_counter' && error?.message === 'control_changed') return counterRejected(d,error);
      throw error;
    }
    if (action === 'fill') {
      if ((!['INPUT','TEXTAREA'].includes(e.tagName) && !e.isContentEditable) || typeof d.value !== 'string' || d.value.length > 1000) throw new Error('unsupported');
      setValue(e, d.value); await pause(200);
      if (!e.isConnected) throw new Error('control_changed');
      const observed = e.isContentEditable ? clean(e.innerText) : e.value;
      return {status:observed === d.value ? 'value_verified':'value_mismatch',expected:d.value,observed};
    }
    if (action === 'select') {
      if (e.tagName !== 'SELECT') throw new Error('unsupported');
      const choices = [...e.options].filter(o => !o.disabled && [o.value,clean(o.textContent)].includes(d.value));
      if (choices.length !== 1) throw new Error('control_changed');
      const expected = choices[0].value;
      setValue(e,expected); await pause(150);
      if (!e.isConnected) throw new Error('control_changed');
      return {status:e.value === expected ? 'value_verified':'value_mismatch',expected,observed:e.value};
    }
    if (action === 'check') {
      if (!['true','false'].includes(d.value)) throw new Error('unsupported');
      const native = e.tagName === 'INPUT' && ['checkbox','radio'].includes(e.type);
      if (!native && !['checkbox','radio'].includes(e.getAttribute('role'))) throw new Error('unsupported');
      const before = native ? String(e.checked) : e.getAttribute('aria-checked');
      if (!['true','false'].includes(before)) throw new Error('unsupported');
      if (before !== d.value) e.click(); await pause(150);
      const observed = native ? String(e.checked) : e.getAttribute('aria-checked');
      return {status:observed === d.value ? 'value_verified':'value_mismatch',expected:d.value,observed};
    }
    if (action === 'set_counter') {
      const before = counter(e);
      if (!before || !/^\d{1,2}$/.test(d.value)) throw new Error('unsupported');
      const expected = Number(d.value), delta = expected - before.value;
      if (expected > 30 || Math.abs(delta) > 10 || (before.minimum != null && expected < before.minimum) || (before.maximum != null && expected > before.maximum) || e.readOnly || before.owner_readonly) throw new Error('unsupported');
      const direction = delta > 0 ? 'increase':'decrease';
      if (delta && ![direction,'unknown','both'].includes(before.direction)) throw new Error('unsupported');
      if (delta) {
        // DOM click does not focus its target like a pointer action does. Focus
        // only the already verified actuator, then reject any focus-time change
        // before sending a click/step; never edit a detached or replaced button.
        if (typeof e.focus !== 'function') return counterRejected(d,{counterPreflight:{reason:'focus_unavailable',mismatched_fields:[]}});
        e.focus({preventScroll:true}); ensure(payload.document_token);
        if (!e.isConnected) return counterRejected(d,{counterPreflight:{reason:'focus_changed',mismatched_fields:[]}});
        try { e = target(d,facts); }
        catch(error) {
          if (error?.message === 'control_changed') return counterRejected(d,error);
          throw error;
        }
      }
      let observed = before.value, steps = 0;
      while (observed !== expected && steps < 10) {
        ensure(payload.document_token);
        const fresh = counter(e);
        if (!e.isConnected || !visible(e) || e.disabled || e.getAttribute('aria-disabled') === 'true' || e.getAttribute('aria-readonly') === 'true' || e.closest('[inert]') || !fresh || fresh.label !== before.label || fresh.value !== observed || ![direction,'unknown','both'].includes(fresh.direction) || (fresh.minimum != null && expected < fresh.minimum) || (fresh.maximum != null && expected > fresh.maximum)) break;
        const previous = observed;
        if (['number_input','spinbutton'].includes(before.method)) {
          // Native DOM stepping dispatches synthetic input/change events; custom ARIA
          // spinbuttons cannot receive trusted keyboard input in this adapter.
          if (e.tagName !== 'INPUT' || e.type !== 'number') throw new Error('unsupported');
          if (direction === 'increase') e.stepUp(); else e.stepDown();
          e.dispatchEvent(new Event('input',{bubbles:true,composed:true})); e.dispatchEvent(new Event('change',{bubbles:true,composed:true}));
        } else e.click();
        for (let n=0;n<5;n++) { await pause(100); const next=counter(e); observed=next && next.label === before.label ? next.value : null; if (observed !== previous) break; }
        if (observed !== previous + (direction === 'increase' ? 1:-1)) break;
        steps++;
      }
      return {status:observed === expected ? 'counter_verified':'counter_unconfirmed',counter:before.label,before:before.value,expected,observed,steps,input_method:'dom',note:'Each step was read back; inspect the final closed form summary before Search.'};
    }
    if (action === 'click') {
      const calendar = await clickDate(e,facts,payload);
      if (calendar) return calendar;
      if (e.tagName === 'A' && e.href) {
        const destination = new URL(e.href);
        if (destination.origin !== location.origin) throw new Error('origin_changed');
        return {status:'action_performed',note:'Observed link dispatched once; inspect the next document to verify navigation.',_navigation_url:destination.href,_navigation_from_url:location.href};
      } else {
        const form = e.form || e.closest('form');
        if (facts.submits_form && form?.action && new URL(form.action,location.href).origin !== location.origin) throw new Error('origin_changed');
        // HTMLElement.click() does not perform the focus step of a browser
        // pointer click. Search widgets commonly expose their options on focus.
        if (e.matches('input,textarea,select') || e.isContentEditable) {
          e.focus();
          if (!e.isConnected) throw new Error('control_changed');
        }
        e.click();
      }
      return {status:'action_performed',note:'Action dispatched once. Inspect a fresh observation to verify its effect.'};
    }
    if (action === 'press') {
      if (d.value === 'Escape') { e.focus(); e.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true})); e.dispatchEvent(new KeyboardEvent('keyup',{key:'Escape',code:'Escape',bubbles:true})); return {status:'action_performed'}; }
      // Synthetic Enter does not have browser default submission behavior.
      // A native form requestSubmit is explicit and grounded in the observed form.
      if (d.value === 'Enter' && e.form) {
        if (new URL(e.form.action || location.href,location.href).origin !== location.origin) throw new Error('origin_changed');
        e.form.requestSubmit(); return {status:'action_performed'};
      }
      throw new Error('unsupported');
    }
    throw new Error('unsupported');
  }
  globalThis.__agenticTabExecutor = {
    version,
    async dispatch(operation,payload = {}) {
      if (operation === 'validate') {
        ensure(payload.document_token);
        if (location.href !== payload.url) throw new Error('stale_document');
        return {valid:true};
      }
      if (operation === 'observe') {
        observedUrl = location.href;
        const tabState = {visibility:document.visibilityState,has_focus:document.hasFocus()};
        if (restricted()) return {url:safeUrl(location.href),document_token:token,tab_state:tabState,frame:{controls:[],text:'Access restriction or manual sign-in/verification is visible.',access_restriction:true,manual_verification_required:true}};
        if (typeof globalThis.agenticObserve !== 'function') throw new Error('unsupported');
        const frame = globalThis.agenticObserve(payload.focus || 'all');
        return {url:safeUrl(location.href),document_token:token,executor_version:version,tab_state:tabState,frame};
      }
      if (operation === 'execute') return execute(payload);
      if (operation === 'capture') {
        ensure(payload.document_token); const original = location.href;
        if (typeof captureDocument !== 'function') throw new Error('unsupported');
        const steps = Math.max(0,Math.min(8,Number(payload.scroll_steps)||0));
        for(let n=0;n<steps;n++) { ensure(payload.document_token); window.scrollBy({top:650,behavior:'instant'}); await pause(250); }
        ensure(payload.document_token); const capture = captureDocument();
        capture.coverage = {...capture.coverage,scroll_steps:steps,at_page_end:Math.ceil(scrollY + innerHeight) >= document.documentElement.scrollHeight,preparation:'bounded_browser',content_settled:false};
        if (original !== location.href) throw new Error('stale_document');
        return {capture,document_token:token,url:safeUrl(location.href)};
      }
      if (operation === 'viewport_image') throw new Error('unsupported');
      throw new Error('unsupported');
    }
  };
})();
