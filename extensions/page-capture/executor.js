/* Packaged, isolated-world executor. No model-provided JavaScript or selectors. */
(() => {
  'use strict';
  const version = '0.5.2';
  if (globalThis.__agenticTabExecutor?.version === version) return;
  const token = crypto.randomUUID();
  let observedUrl = null;
  let nativeTransaction = null;
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
      observed:null,steps:0,attempts:0,dispatched:false,counter_outcome:'blocked_before_input',counter_preflight:preflight,
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
  const activeElement = () => {
    let element = document.activeElement;
    while (element?.shadowRoot?.activeElement) element = element.shadowRoot.activeElement;
    return element;
  };
  const selectSignature = e => JSON.stringify([...e.options].map(option => [option.value,clean(option.textContent),option.disabled,option.closest('optgroup')?.disabled === true]));
  const actionLabel = e => clean([e.getAttribute('aria-label'),e.getAttribute('title'),e.name,e.innerText].join(' '));
  function nativeStep(step, requireFocus=false) {
    ensure(step.document_token);
    const e = step.element;
    if (!e.isConnected || !visible(e) || e.disabled || e.getAttribute('aria-disabled') === 'true' || e.closest('[inert]') || sensitive(e) || forbidden.test(actionLabel(e))) throw new Error('control_changed');
    if (step.kind === 'fill' && (e.readOnly || e.getAttribute('aria-readonly') === 'true')) throw new Error('unsupported');
    const current = identity(e);
    if (Object.keys(current).some(key => !(step.kind === 'select' && key === 'value') && current[key] !== step.identity[key]) ||
        step.kind === 'select' && selectSignature(e) !== step.options_signature ||
        step.counter && !sameCounter(counter(e),step.counter)) throw new Error('control_changed');
    // CDP routes keys to the bound page, not the side panel. Require the exact
    // page-local field, without making a side-panel document-focus flag a gate.
    if (requireFocus && activeElement() !== e) throw new Error('control_changed');
    const box = e.getBoundingClientRect();
    const left = Math.max(0,box.left), right = Math.min(innerWidth,box.right);
    const top = Math.max(0,box.top), bottom = Math.min(innerHeight,box.bottom);
    if (right <= left || bottom <= top) throw new Error('control_changed');
    const point = {x:(left+right)/2,y:(top+bottom)/2};
    let hit = document.elementFromPoint(point.x,point.y);
    while (hit?.shadowRoot) {
      const inner = hit.shadowRoot.elementFromPoint(point.x,point.y);
      if (!inner || inner === hit) break;
      hit = inner;
    }
    if (!hit || hit !== e && !e.contains(hit)) throw new Error('control_changed');
    return {id:step.id,kind:step.kind,point,value:step.value,selection_steps:step.selection_steps};
  }
  async function input(kind,e,value='') {
    const tx = nativeTransaction;
    if (!tx) {
      // Kept for isolated DOM fixtures; the extension worker always uses native_begin.
      if (kind === 'click') e.click();
      else if (kind === 'fill' || kind === 'select') setValue(e,value);
      else if (kind === 'key' && ['ArrowUp','ArrowDown'].includes(value) && e.matches('input[type="number"]')) {
        if (value === 'ArrowUp') e.stepUp(); else e.stepDown();
        e.dispatchEvent(new Event('input',{bubbles:true,composed:true}));
        e.dispatchEvent(new Event('change',{bubbles:true,composed:true}));
      } else if (kind === 'key' && value === 'Enter' && e.form) e.form.requestSubmit();
      else if (kind === 'key' && value === 'Escape') {
        e.focus();
        e.dispatchEvent(new KeyboardEvent('keydown',{key:value,code:value,bubbles:true}));
        e.dispatchEvent(new KeyboardEvent('keyup',{key:value,code:value,bubbles:true}));
      } else throw new Error('unsupported');
      return;
    }
    if (tx.aborted || tx.pending || ++tx.steps > 30) throw new Error('delivery_unknown');
    const original = identity(e), originalCounter = counter(e);
    e.scrollIntoView({block:'nearest',inline:'nearest',behavior:'instant'});
    if (kind === 'key') e.focus({preventScroll:true});
    if (!e.isConnected || Object.keys(original).some(key => identity(e)[key] !== original[key]) ||
        originalCounter && !sameCounter(counter(e),originalCounter)) throw new Error('control_changed');
    const selectionSteps = kind === 'select' ? [...e.options].filter(option => !option.disabled && !option.closest('optgroup')?.disabled).findIndex(option => option.value === value) : 0;
    if (kind === 'select' && (e.multiple || selectionSteps < 0 || selectionSteps > 40)) throw new Error('unsupported');
    const step = {id:crypto.randomUUID(),kind,element:e,identity:original,counter:originalCounter,
      options_signature:kind === 'select' ? selectSignature(e):null,
      document_token:tx.document_token,value,selection_steps:selectionSteps};
    const prepared = nativeStep(step);
    return new Promise((resolve,reject) => {
      step.resolve = resolve; step.reject = reject;
      step.timer = setTimeout(() => {
        tx.aborted = true; tx.pending = null;
        if (nativeTransaction === tx) nativeTransaction = null;
        reject(new Error('delivery_unknown'));
      },15000);
      tx.pending = step;
      tx.offer({transaction_id:tx.id,native_step:prepared});
    });
  }
  function nativeOutput(tx) {
    if (tx.output) {
      const output = tx.output; tx.output = null;
      if (tx.finished && nativeTransaction === tx) nativeTransaction = null;
      if (output.error) throw new Error(output.error);
      return Promise.resolve(output);
    }
    return new Promise((resolve,reject) => { tx.waiter = {resolve,reject}; });
  }
  function nativeBegin(payload) {
    ensure(payload.document_token);
    if (nativeTransaction) throw new Error('control_changed');
    const tx = {id:crypto.randomUUID(),document_token:payload.document_token,steps:0,pending:null,finished:false,aborted:false,output:null,waiter:null};
    tx.offer = output => {
      if (tx.waiter) {
        const waiter = tx.waiter; tx.waiter = null;
        if (tx.finished && nativeTransaction === tx) nativeTransaction = null;
        if (output.error) waiter.reject(new Error(output.error)); else waiter.resolve(output);
      } else tx.output = output;
    };
    nativeTransaction = tx;
    execute(payload).then(result => {
      tx.finished = true; tx.offer({transaction_id:tx.id,result});
    },error => {
      tx.finished = true; tx.offer({transaction_id:tx.id,error:error?.message || 'execution_failed'});
    });
    return nativeOutput(tx);
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
    const inputName = nativeTransaction ? 'browser-level':'DOM';
    ensure(payload.document_token);
    await input('click',actionable);
    let changed = false;
    for (let n=0;n<8;n++) {
      await pause(100); ensure(payload.document_token);
      const selected = selection(true);
      if (selected && selected !== '[]' && selected !== previousSelection) return {status:'action_performed',calendar:{...metadata,status:'selected',dispatched:true},note:'One '+inputName+' date click was sent and its same-day selection changed. Verify the final stay dates in the form summary.'};
      changed = changed || snapshot() !== before;
    }
    return {status:changed ? 'action_performed':'value_mismatch',expected,observed:null,calendar:{...metadata,status:changed ? 'changed':'unconfirmed',dispatched:true},note:changed ? 'The calendar changed after one '+inputName+' click, but the requested day is not independently confirmed; inspect a fresh observation.' : 'No same-day selection or local calendar change was confirmed after one '+inputName+' click. It was not repeated; inspect the calendar before continuing.'};
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
      await input('fill',e,d.value); await pause(200);
      if (!e.isConnected) throw new Error('control_changed');
      const observed = e.isContentEditable ? clean(e.innerText) : e.value;
      return {status:observed === d.value ? 'value_verified':'value_mismatch',expected:d.value,observed};
    }
    if (action === 'select') {
      if (e.tagName !== 'SELECT') throw new Error('unsupported');
      const choices = [...e.options].filter(o => !o.disabled && [o.value,clean(o.textContent)].includes(d.value));
      if (choices.length !== 1) throw new Error('control_changed');
      const expected = choices[0].value;
      await input('select',e,expected); await pause(150);
      if (!e.isConnected) throw new Error('control_changed');
      return {status:e.value === expected ? 'value_verified':'value_mismatch',expected,observed:e.value};
    }
    if (action === 'check') {
      if (!['true','false'].includes(d.value)) throw new Error('unsupported');
      const native = e.tagName === 'INPUT' && ['checkbox','radio'].includes(e.type);
      if (!native && !['checkbox','radio'].includes(e.getAttribute('role'))) throw new Error('unsupported');
      const before = native ? String(e.checked) : e.getAttribute('aria-checked');
      if (!['true','false'].includes(before)) throw new Error('unsupported');
      if (before !== d.value) await input('click',e); await pause(150);
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
        // Focus only the verified actuator, then reject any focus-time change
        // before sending input; never edit a detached or replaced button.
        if (typeof e.focus !== 'function') return counterRejected(d,{counterPreflight:{reason:'focus_unavailable',mismatched_fields:[]}});
        e.focus({preventScroll:true}); ensure(payload.document_token);
        if (!e.isConnected) return counterRejected(d,{counterPreflight:{reason:'focus_changed',mismatched_fields:[]}});
        try { e = target(d,facts); }
        catch(error) {
          if (error?.message === 'control_changed') return counterRejected(d,error);
          throw error;
        }
      }
      // Keep only already-observed ancestor scopes. Replaced controls may be
      // rebound uniquely inside them, never by a page-wide label guess.
      const scopes = [];
      for (let parent=e.parentElement,depth=0;parent && depth<7;parent=parent.parentElement,depth++) {
        if (parent.matches('body,html,main')) break;
        scopes.push(parent);
        if (parent.matches('[role="dialog"],form')) break;
      }
      const actuatorIdentity = identity(e);
      const readCounter = () => {
        if (e.isConnected) return counter(e);
        for (const scope of scopes) {
          if (!scope.isConnected || !visible(scope)) continue;
          const candidates = [...scope.querySelectorAll('button,[role="button"],input[type="number"],[role="spinbutton"]')].filter(node => {
            if (!visible(node) || sensitive(node)) return false;
            const facts = identity(node), quantity = counter(node);
            return ['tag','role','name','type','text'].every(key => facts[key] === actuatorIdentity[key]) &&
              quantity?.label === before.label && quantity.method === before.method &&
              [direction,'unknown','both'].includes(quantity.direction);
          });
          if (candidates.length > 1) return null;
          if (candidates.length === 1) { e = candidates[0]; return counter(e); }
        }
        return null;
      };
      let observed = before.value, steps = 0, attempts = 0, reason = 'target_reached';
      while (observed !== expected && steps < 10) {
        ensure(payload.document_token);
        const fresh = readCounter();
        if (!e.isConnected || !visible(e) || e.disabled || e.getAttribute('aria-disabled') === 'true' || e.getAttribute('aria-readonly') === 'true' || e.closest('[inert]') || !fresh || fresh.label !== before.label || fresh.value !== observed || ![direction,'unknown','both'].includes(fresh.direction) || (fresh.minimum != null && expected < fresh.minimum) || (fresh.maximum != null && expected > fresh.maximum)) { reason = 'control_changed_before_input'; break; }
        const previous = observed;
        if (['number_input','spinbutton'].includes(before.method)) {
          // Native mode steps a real numeric input with browser keyboard events.
          // Read-only/custom ARIA wrappers still need a visible button actuator.
          if (e.tagName !== 'INPUT' || e.type !== 'number') throw new Error('unsupported');
          await input('key',e,direction === 'increase' ? 'ArrowUp':'ArrowDown');
        } else await input('click',e);
        attempts++;
        for (let n=0;n<5;n++) {
          await pause(100); ensure(payload.document_token);
          const next=readCounter(); observed=next && next.label === before.label ? next.value : null;
          if (observed !== null && observed !== previous) break;
        }
        if (observed !== previous + (direction === 'increase' ? 1:-1)) { reason = observed === previous ? 'unchanged_after_input':'readback_unconfirmed'; break; }
        steps++;
      }
      return {status:observed === expected ? 'counter_verified':'counter_unconfirmed',counter:before.label,before:before.value,expected,observed,steps,attempts,dispatched:attempts>0,counter_outcome:observed === expected ? 'target_reached':reason,input_method:nativeTransaction ? 'native_cdp':'dom',note:observed === expected ? 'The requested counter value was read back. Confirm the closed form summary before Search.' : attempts ? 'Input was sent, but the requested count was not confirmed. Inspect the actual count; no unchanged step was repeated.' : 'The counter changed or became unavailable before input. No counter click was sent.'};
    }
    if ((action === 'click' && facts.submits_form) || (action === 'press' && d.value === 'Enter')) {
      const form = e.form || e.closest('form');
      if (form && !form.noValidate && !e.formNoValidate) {
        const invalid = [...form.elements].filter(field => visible(field) && !sensitive(field) &&
          field.willValidate === true && field.validity?.valid === false);
        if (invalid.length) return {status:'validation_blocked',submitted:false,
          dispatch_status:'not_dispatched',validation:{form_scope:facts.form_scope,
            fields:invalid.slice(0,12).map(field=>({
              control_id:field.hasAttribute('data-agentic-loop-id') ? '0:'+field.getAttribute('data-agentic-loop-id'):null,
              label:clean(field.getAttribute('aria-label') ||
                [...(field.labels || [])].map(label=>label.textContent).join(' ') || field.name || 'Required field').slice(0,180)
            }))},note:'Required form fields are incomplete. No Search input was sent.'};
      }
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
        // Search widgets may expose their options on focus. Recheck the target
        // before native dispatch (or the isolated fixture's DOM fallback).
        if (e.matches('input,textarea,select') || e.isContentEditable) {
          e.focus();
          if (!e.isConnected) throw new Error('control_changed');
        }
        await input('click',e);
      }
      return {status:'action_performed',note:'Action dispatched once. Inspect a fresh observation to verify its effect.'};
    }
    if (action === 'press') {
      if (d.value === 'Escape') { await input('key',e,'Escape'); return {status:'action_performed'}; }
      // Enter is limited to an observed same-origin form. Production uses
      // browser input; isolated DOM fixtures retain requestSubmit behavior.
      if (d.value === 'Enter' && e.form) {
        if (new URL(e.form.action || location.href,location.href).origin !== location.origin) throw new Error('origin_changed');
        await input('key',e,'Enter'); return {status:'action_performed'};
      }
      throw new Error('unsupported');
    }
    throw new Error('unsupported');
  }
  globalThis.__agenticTabExecutor = {
    version,
    input_protocol:1,
    async dispatch(operation,payload = {}) {
      if (operation === 'capabilities') return {executor_version:version,input_protocol:1};
      if (operation === 'native_begin') return nativeBegin(payload);
      if (operation === 'native_validate' || operation === 'native_continue' || operation === 'native_abort') {
        const tx = nativeTransaction;
        if (!tx || payload.transaction_id !== tx.id || payload.document_token !== tx.document_token) throw new Error('stale_document');
        if (operation === 'native_abort') {
          tx.aborted = true;
          if (tx.pending) { clearTimeout(tx.pending.timer); tx.pending.reject(new Error('delivery_unknown')); tx.pending = null; }
          if (nativeTransaction === tx) nativeTransaction = null;
          return {aborted:true};
        }
        if (!tx.pending || payload.step_id !== tx.pending.id) throw new Error('control_changed');
        if (operation === 'native_validate') return nativeStep(tx.pending,payload.require_focus === true);
        const pending = tx.pending; tx.pending = null; clearTimeout(pending.timer);
        pending.resolve();
        return nativeOutput(tx);
      }
      if (operation === 'validate') {
        ensure(payload.document_token);
        if (location.href !== payload.url) throw new Error('stale_document');
        return {valid:true};
      }
      if (operation === 'observe') {
        observedUrl = location.href;
        const tabState = {visibility:document.visibilityState,has_focus:document.hasFocus()};
        const metadata = {url:safeUrl(location.href),document_token:token,executor_version:version,
          input_driver:payload.input_driver === 'native_cdp' ? 'native_cdp':'dom',tab_state:tabState};
        if (restricted()) return {...metadata,frame:{controls:[],text:'Access restriction or manual sign-in/verification is visible.',access_restriction:true,manual_verification_required:true}};
        if (typeof globalThis.agenticObserve !== 'function') throw new Error('unsupported');
        const frame = globalThis.agenticObserve(payload.focus || 'all');
        return {...metadata,frame};
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
