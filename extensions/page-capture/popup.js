"use strict";
const el = id => document.getElementById(id);
let tab, preview, destination;
const dashboard = url => ['http://127.0.0.1:8120', 'http://localhost:8120'].includes(new URL(url).origin);
const show = capture => { el('preview').textContent = JSON.stringify(capture, null, 2); };
const injected = async (func, args = []) => {
  const [result] = await chrome.scripting.executeScript({target: {tabId: tab.id}, func, args});
  if (result.error) throw new Error(result.error.message || 'Page capture failed.');
  return result.result;
};
const safe = fn => async () => {
  try { await fn(); } catch (e) { el('status').textContent = e.message || 'Operation failed.'; }
};
async function sessionInfo() {
  const response = await fetch('/api/session', {cache: 'no-store'});
  if (!response.ok) throw new Error('Open the local dashboard and sign in.');
  const s = await response.json();
  return {authenticated: s.authenticated, username: s.username, instance_id: s.instance_id, csrf: s.csrf};
}
el('capture').onclick = safe(async () => {
  preview = await injected(captureDocument); show(preview);
  el('keep').hidden = false; el('consent-label').hidden = false; el('consent').checked = false;
  el('status').textContent = 'Review all text and links below. Forms and hidden content are excluded, but visible secrets may remain.';
});
el('keep').onclick = safe(async () => {
  if (!preview || !el('consent').checked) throw new Error('Review and confirm the capture first.');
  await chrome.storage.session.set({capture: preview, expires: Date.now() + 600000});
  el('status').textContent = 'Capture kept temporarily. Switch to the signed-in dashboard tab (port 8120) and open this extension again.';
});
el('clear').onclick = safe(async () => {
  await chrome.storage.session.clear(); preview = null; show(null);
  el('keep').hidden = true; el('send').hidden = true; el('consent').checked = false;
  el('status').textContent = 'Capture discarded.';
});
el('send').onclick = safe(async () => {
  if (!el('consent').checked) throw new Error('Confirm transfer to the displayed account.');
  el('send').disabled = true;
  try {
    const saved = await chrome.storage.session.get(['capture', 'expires']);
    if (!saved.capture || saved.expires <= Date.now()) throw new Error('Capture expired. Capture again.');
    const result = await injected(async (capture, expected) => {
      if (!['http://127.0.0.1:8120', 'http://localhost:8120'].includes(location.origin))
        return {error: 'Dashboard address changed. Nothing transferred.'};
      const s = await (await fetch('/api/session', {cache: 'no-store'})).json();
      if (!s.authenticated || s.csrf !== expected.csrf || s.instance_id !== expected.instance_id)
        return {error: 'Dashboard session changed. Reopen the extension and review the account.'};
      if (!document.getElementById('web-create') || document.getElementById('web-create').disabled)
        return {error: 'Dashboard is busy or outdated. Wait or refresh before sending.'};
      const response = await fetch('/api/custom/captures', {
        method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': s.csrf},
        body: JSON.stringify(capture),
      });
      if (!response.ok) return {error: 'Dashboard rejected the capture. Check content size and session.'};
      const body = await response.json();
      window.postMessage({type: 'agentic-capture-ready-v1', capture_id: body.capture_id}, location.origin);
      return {ok: true};
    }, [saved.capture, destination]);
    if (result.error) throw new Error(result.error);
    el('status').textContent = 'Sent. Review the capture in Custom Website, then approve extraction separately. No model call was made.';
    el('send').hidden = true; show(null);
  } finally { el('send').disabled = false; }
});
safe(async () => {
  [tab] = await chrome.tabs.query({active: true, currentWindow: true});
  if (!tab?.url || !/^https?:/.test(tab.url)) throw new Error('Open an HTTP/HTTPS website or your local dashboard.');
  const saved = await chrome.storage.session.get(['capture', 'expires']);
  if (saved.expires <= Date.now()) await chrome.storage.session.clear();
  if (dashboard(tab.url)) {
    destination = await injected(sessionInfo);
    if (!destination?.authenticated) throw new Error('Sign in to your dashboard first.');
    el('status').textContent = `Destination: ${destination.username} at ${new URL(tab.url).origin}.`;
    if (saved.capture && saved.expires > Date.now()) {
      show(saved.capture); el('send').hidden = false; el('consent-label').hidden = false;
    } else el('status').textContent += ' No pending capture. Open a content page first.';
  } else {
    el('capture').hidden = false;
    el('status').textContent = 'Only this tab is captured. No cookies, history or API keys are read.';
  }
})();
