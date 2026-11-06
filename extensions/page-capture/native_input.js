/* Worker-owned native input for one explicitly connected tab. No raw CDP API. */
(() => {
  'use strict';
  if (globalThis.AgenticNativeInput) return;
  const allowed = new Set(['Page.bringToFront','Input.dispatchMouseEvent','Input.dispatchKeyEvent','Input.insertText']);
  const keys = {
    Control:{key:'Control',code:'ControlLeft',windowsVirtualKeyCode:17},
    a:{key:'a',code:'KeyA',windowsVirtualKeyCode:65},
    Home:{key:'Home',code:'Home',windowsVirtualKeyCode:36},
    Backspace:{key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8},
    Enter:{key:'Enter',code:'Enter',windowsVirtualKeyCode:13},
    Escape:{key:'Escape',code:'Escape',windowsVirtualKeyCode:27},
    ArrowUp:{key:'ArrowUp',code:'ArrowUp',windowsVirtualKeyCode:38},
    ArrowDown:{key:'ArrowDown',code:'ArrowDown',windowsVirtualKeyCode:40},
  };
  let attached = null, pendingAttach = null, generation = 0, active = null, detaching = null;
  const failure = code => new Error(code);
  const owns = (tabId, revision) => attached === tabId && generation === revision;
  const requireOwner = (tabId, revision) => {
    if (!owns(tabId,revision)) throw failure('native_input_detached');
  };
  async function send(tabId, revision, method, params = {}) {
    requireOwner(tabId,revision);
    if (!allowed.has(method)) throw failure('unsupported');
    let result;
    try { result = await chrome.debugger.sendCommand({tabId},method,params); }
    catch (error) {
      if (/not attached|debugger.*detached|session.*(?:closed|not found)|target.*closed/i.test(error?.message || '')) {
        if (owns(tabId,revision)) { attached = null; generation += 1; }
        throw failure('native_input_detached');
      }
      throw error;
    }
    requireOwner(tabId,revision);
    return result;
  }
  function descriptor(step) {
    if (!step || !['click','fill','select','key'].includes(step.kind) ||
        !['string','number'].includes(typeof step.id) || typeof step.id === 'number' && !Number.isSafeInteger(step.id) ||
        !String(step.id).length || String(step.id).length > 128) throw failure('unsupported');
    const point = step.point;
    if (step.kind !== 'key' && (!point || !Number.isFinite(point.x) || !Number.isFinite(point.y) ||
        point.x < 0 || point.y < 0 || point.x > 32768 || point.y > 32768)) throw failure('unsupported');
    const value = step.value ?? '';
    if (typeof value !== 'string' || value.length > 1000 || value.includes('\0')) throw failure('unsupported');
    if (step.kind === 'key' && !['Enter','Escape','ArrowUp','ArrowDown'].includes(value)) throw failure('unsupported');
    const steps = step.selection_steps ?? 0;
    if (!Number.isInteger(steps) || steps < 0 || steps > 40) throw failure('unsupported');
    return {id:String(step.id),kind:step.kind,point:point ? {x:point.x,y:point.y}:null,value,selection_steps:steps};
  }
  async function attach(tabId) {
    if (!Number.isSafeInteger(tabId) || tabId < 0 || !chrome.debugger?.attach) throw failure('native_input_unavailable');
    if (detaching) await detaching;
    if (attached === tabId) return;
    if (attached !== null || pendingAttach !== null || active) throw failure('native_input_unavailable');
    const revision = generation;
    pendingAttach = tabId;
    try {
      await chrome.debugger.attach({tabId},'1.3');
      if (pendingAttach !== tabId || revision !== generation) throw failure('native_input_detached');
      attached = tabId;
    } catch (_) { throw failure('native_input_unavailable'); }
    finally { if (pendingAttach === tabId) pendingAttach = null; }
  }
  async function focus(tabId) {
    if (attached !== tabId) throw failure('native_input_unavailable');
    const revision = generation;
    try { await send(tabId,revision,'Page.bringToFront'); }
    catch (_) { throw failure(owns(tabId,revision) ? 'native_input_unavailable':'native_input_detached'); }
  }
  async function perform(tabId, step, validate) {
    if (attached !== tabId) throw failure('native_input_unavailable');
    const original = descriptor(step), revision = generation;
    requireOwner(tabId,revision);
    if (typeof validate !== 'function' || active) throw failure('native_input_unavailable');
    let finish;
    const operation = {tabId,done:new Promise(resolve => { finish = resolve; })};
    active = operation;
    let dispatched = false, mousePoint = null;
    const held = new Map();
    async function check(requireFocus, cleanup = false) {
      requireOwner(tabId,revision);
      const fresh = await validate({require_focus:requireFocus,cleanup});
      requireOwner(tabId,revision);
      if (cleanup) return original;
      const current = descriptor(fresh);
      if (current.id !== original.id || current.kind !== original.kind ||
          current.value !== original.value || current.selection_steps !== original.selection_steps) throw failure('control_changed');
      return current;
    }
    async function input(method, params) {
      requireOwner(tabId,revision);
      // Mark before dispatch: a rejected/lost reply cannot prove no event ran.
      dispatched = true;
      return send(tabId,revision,method,params);
    }
    async function releaseMouse() {
      if (!mousePoint) return;
      await check(false,true);
      const point = mousePoint;
      mousePoint = null; // An uncertain release must not be sent a second time.
      await input('Input.dispatchMouseEvent',{type:'mouseReleased',...point,button:'left',buttons:0,clickCount:1});
    }
    async function click() {
      let fresh = await check(false);
      await input('Input.dispatchMouseEvent',{type:'mouseMoved',...fresh.point,button:'none',buttons:0});
      fresh = await check(false);
      mousePoint = {x:fresh.point.x,y:fresh.point.y};
      await input('Input.dispatchMouseEvent',{type:'mousePressed',...mousePoint,button:'left',buttons:1,clickCount:1});
      await releaseMouse();
    }
    async function releaseKey(name) {
      if (!held.has(name)) return;
      await check(false,true);
      const spec = held.get(name);
      held.delete(name); // Never replay a keyUp whose delivery is uncertain.
      await input('Input.dispatchKeyEvent',{type:'keyUp',...spec,modifiers:held.has('Control') ? 2:0});
    }
    async function down(name) {
      await check(true);
      const spec = keys[name];
      held.set(name,spec);
      const enter = name === 'Enter';
      await input('Input.dispatchKeyEvent',{type:enter ? 'keyDown':'rawKeyDown',...spec,
        modifiers:held.has('Control') ? 2:0,
        ...(enter ? {text:'\r',unmodifiedText:'\r'}:{})});
    }
    async function press(name) { await down(name); await releaseKey(name); }
    try {
      if (original.kind === 'click') await click();
      else if (original.kind === 'fill') {
        await click();
        await down('Control');
        await press('a');
        await releaseKey('Control');
        await check(true);
        if (original.value) await input('Input.insertText',{text:original.value});
        else await press('Backspace');
      } else if (original.kind === 'select') {
        await click();
        await press('Home');
        for (let n=0;n<original.selection_steps;n++) await press('ArrowDown');
        await press('Enter');
      } else await press(original.value);
      return {dispatched:true};
    } catch (error) {
      if (dispatched) throw failure('delivery_unknown');
      if (!owns(tabId,revision)) throw failure('native_input_detached');
      if (['unsupported','control_changed','stale_document','origin_changed','tab_closed','cancelled',
        'access_restriction','permission_required','website_focus_required','session_changed',
        'run_expired','run_unavailable','operation_conflict'].includes(error?.message)) throw error;
      throw failure('native_input_unavailable');
    } finally {
      // Releases may finish an in-flight input after Pause/Cancel, but only
      // while the caller still proves the same bound tab/window/origin.
      try { await releaseMouse(); } catch (_) { /* No blind release retries. */ }
      for (const name of [...held.keys()].reverse()) {
        try { await releaseKey(name); } catch (_) { /* Detach/origin changes stop cleanup. */ }
      }
      if (active === operation) active = null;
      finish();
    }
  }
  async function detach(tabId) {
    if (detaching) { await detaching; return; }
    if (active?.tabId === tabId) await active.done;
    if (attached !== tabId) return;
    attached = null; generation += 1;
    const closing = (async () => { try { await chrome.debugger.detach({tabId}); } catch (_) { /* Already detached. */ } })();
    detaching = closing;
    try { await closing; } finally { if (detaching === closing) detaching = null; }
  }
  chrome.debugger?.onDetach?.addListener(source => {
    if (source.tabId === attached || source.tabId === pendingAttach) {
      attached = null; pendingAttach = null; generation += 1;
    }
  });
  globalThis.AgenticNativeInput = Object.freeze({attach,focus,perform,detach,get attachedTabId() { return attached; }});
})();
