"use strict";
const el = id => document.getElementById(id);
let tab, preview, destination, selectedDashboard;
let dashboards = [], transferLocked = false;
const dashboard = url => {
  try { return ['http://127.0.0.1:8120', 'http://localhost:8120'].includes(new URL(url).origin); }
  catch (_) { return false; }
};
const show = capture => { el('preview').textContent = capture ? JSON.stringify(capture, null, 2) : ''; };
const messages = {
  selected_tab: 'Select an HTTP/HTTPS website tab first.',
  page_access: 'The selected tab could not be read. Refresh it, reopen Browser Companion, and try again.',
  storage: 'The snapshot could not be kept in extension memory. Reopen Browser Companion and capture again.',
  dashboards: 'Dashboard tabs could not be checked. Open your local dashboard, sign in, and try Check dashboard tabs again.',
  dashboard_open: 'The dashboard tab could not be opened. Switch to it manually, then reopen Browser Companion.',
  consent: 'Review the snapshot and confirm it first.',
  transfer_consent: 'Choose a dashboard account and confirm transfer to that displayed account.',
  expired: 'This snapshot expired. Capture the website again; nothing was sent.',
  uncertain: 'A transfer was already attempted. Check the dashboard before capturing again; no request was repeated.',
  send_unknown: 'Transfer acknowledgement was interrupted. Check the dashboard before capturing again; the send request will not be repeated.',
};
const fail = code => { throw new Error(code); };
const safe = (stage, fn) => async () => {
  try { await fn(); }
  catch (error) { el('status').textContent = messages[error.message] || messages[stage] || 'This step could not complete. Reopen Browser Companion and try again.'; }
};
async function injectedAt(tabId, func, args = []) {
  const results = await chrome.scripting.executeScript({target: {tabId}, func, args});
  if (!results?.[0] || results[0].error) fail('page_access');
  return results[0].result;
}
// Runs only in a permitted loopback dashboard tab. Session secrets never appear
// in account labels, captured content, persistent transfer state, or diagnostics.
async function sessionInfo() {
  if (!['http://127.0.0.1:8120', 'http://localhost:8120'].includes(location.origin)) return null;
  try {
    const response = await fetch('/api/session', {cache: 'no-store'});
    if (!response.ok) return null;
    const s = await response.json();
    return {authenticated: s.authenticated, username: s.username, instance_id: s.instance_id,
      csrf: s.csrf, ui_version: s.ui_version,
      page_ready: document.documentElement.dataset.agenticConnection === 'ready'
        && document.documentElement.dataset.agenticUiVersion === s.ui_version};
  } catch (_) { return null; }
}
async function clearCapture() {
  // Never clear the extension's separate agent binding/run/command state.
  await chrome.storage.session.remove(['capture', 'expires']);
  await chrome.storage.session.remove(['snapshotTransfer']);
}
async function retainedCapture() {
  const saved = await chrome.storage.session.get(['capture', 'expires', 'snapshotTransfer']);
  if (saved.capture && saved.expires > Date.now()) return saved;
  if (saved.capture || saved.expires || saved.snapshotTransfer) await clearCapture();
  return null;
}
function reviewAccount() {
  el('consent').checked = false;
  destination = selectedDashboard?.session;
  const account = destination?.authenticated && destination?.username;
  el('dashboard-account').textContent = account
    ? `Send to ${destination.username} at ${new URL(selectedDashboard.url).origin}.${destination.page_ready ? '' : ' Refresh this dashboard and wait for sign-in to finish, then check tabs again.'}`
    : selectedDashboard ? 'Sign in on this dashboard, then check dashboard tabs again.'
      : dashboards.length > 1 ? 'Choose the dashboard account that should receive this snapshot.'
        : 'No local dashboard is open. Open it and sign in first.';
  el('send').hidden = !account || !destination.page_ready || transferLocked;
  el('consent-label').hidden = !account || !destination.page_ready || transferLocked;
  el('consent-label').lastChild.textContent = 'I reviewed this snapshot and authorize sending it to the dashboard account displayed above. It contains no secrets.';
  el('open-dashboard').hidden = false;
  el('open-dashboard').textContent = selectedDashboard ? 'Open this dashboard' : 'Open dashboard to send';
}
async function findDashboards() {
  const allTabs = await chrome.tabs.query({});
  const matches = allTabs.filter(candidate => candidate.id && dashboard(candidate.url));
  dashboards = await Promise.all(matches.map(async candidate => {
    let session = null;
    try { session = await injectedAt(candidate.id, sessionInfo); } catch (_) { /* Show refresh guidance, not raw errors. */ }
    return {id: candidate.id, windowId: candidate.windowId, url: candidate.url, session};
  }));
  const choice = el('dashboard-choice');
  choice.replaceChildren();
  selectedDashboard = null;
  if (dashboards.length > 1) {
    const empty = document.createElement('option'); empty.value = ''; empty.textContent = 'Choose a dashboard account'; choice.append(empty);
  }
  for (const candidate of dashboards) {
    const option = document.createElement('option'); option.value = String(candidate.id);
    option.textContent = `${candidate.session?.authenticated ? candidate.session.username : 'Sign-in or refresh required'} · ${new URL(candidate.url).origin} · tab ${candidate.id}`;
    choice.append(option);
  }
  // Multiple open dashboards are never silently assigned to an account.
  if (dashboards.length === 1) selectedDashboard = dashboards[0];
  el('dashboard-choice-label').hidden = dashboards.length < 2;
  el('find-dashboard').hidden = false;
  reviewAccount();
}
async function showPending(saved) {
  preview = saved.capture; show(preview);
  el('handoff').hidden = false; el('keep').hidden = true;
  transferLocked = saved.snapshotTransfer?.expires === saved.expires;
  el('pending-status').textContent = transferLocked
    ? 'A send was already attempted. Check the dashboard; it will not be sent twice.'
    : 'Snapshot kept — not sent yet. Review the receiving account, confirm transfer, then click Send.';
  await findDashboards();
}
el('dashboard-choice').onchange = () => {
  selectedDashboard = dashboards.find(candidate => String(candidate.id) === el('dashboard-choice').value) || null;
  reviewAccount();
};
el('find-dashboard').onclick = safe('dashboards', async () => {
  const saved = await retainedCapture();
  if (!saved) fail('expired');
  await showPending(saved);
});
el('open-dashboard').onclick = safe('dashboard_open', async () => {
  if (dashboards.length > 1 && !selectedDashboard) fail('transfer_consent');
  if (selectedDashboard) {
    const latest = await chrome.tabs.get(selectedDashboard.id);
    if (!dashboard(latest.url)) fail('dashboard_open');
    await chrome.tabs.update(selectedDashboard.id, {active: true});
    await chrome.windows.update(latest.windowId, {focused: true});
  } else await chrome.tabs.create({url: 'http://127.0.0.1:8120/'});
  window.close();
});
el('open-agent').onclick = safe('selected_tab', async () => {
  const [selected] = await chrome.tabs.query({active: true, currentWindow: true});
  if (!selected?.id) fail('selected_tab');
  await chrome.sidePanel.open({windowId: selected.windowId});
  const result = await chrome.runtime.sendMessage({type: 'agentic-panel-v1', operation: 'connect', tab_id: selected.id});
  if (!result?.ok) { el('status').textContent = 'The agent panel opened. Follow its dashboard connection guidance; snapshot transfer is separate.'; return; }
  window.close();
});
el('capture').onclick = safe('page_access', async () => {
  preview = await injectedAt(tab.id, captureDocument); show(preview);
  await clearCapture(); transferLocked = false;
  el('handoff').hidden = true; el('send').hidden = true;
  el('keep').hidden = false; el('consent-label').hidden = false; el('consent').checked = false;
  el('consent-label').lastChild.textContent = 'I reviewed this content and am authorized to transfer it. It contains no secrets.';
  el('status').textContent = 'Review all text and links below. Forms and hidden content are excluded, but visible secrets may remain.';
});
el('keep').onclick = safe('storage', async () => {
  if (!preview || !el('consent').checked) fail('consent');
  const saved = {capture: preview, expires: Date.now() + 600000};
  await chrome.storage.session.set(saved);
  await chrome.storage.session.remove(['snapshotTransfer']);
  el('status').textContent = 'Snapshot kept successfully. Complete the Send your snapshot step below; keeping does not send it.';
  // Local account discovery is read-only. No capture POST or model call here.
  await showPending(saved);
});
el('clear').onclick = safe('storage', async () => {
  await clearCapture(); preview = null; show(null); transferLocked = false;
  el('handoff').hidden = true; el('keep').hidden = true; el('send').hidden = true;
  el('consent-label').hidden = true; el('consent').checked = false;
  el('status').textContent = 'Snapshot discarded. Agent workflow state was not changed.';
});
// Wait for actual Source UI receipt, not just the storage endpoint's response.
async function sendCapture(capture, expected, transferId) {
  if (!['http://127.0.0.1:8120', 'http://localhost:8120'].includes(location.origin)) return {ok: false, stage: 'dashboard_changed', submitted: false};
  let s;
  try {
    const response = await fetch('/api/session', {cache: 'no-store'});
    if (!response.ok) return {ok: false, stage: 'session_changed', submitted: false};
    s = await response.json();
  } catch (_) { return {ok: false, stage: 'session_unavailable', submitted: false}; }
  if (!s.authenticated || s.csrf !== expected.csrf || s.instance_id !== expected.instance_id || s.username !== expected.username || s.ui_version !== expected.ui_version)
    return {ok: false, stage: 'session_changed', submitted: false};
  if (document.documentElement.dataset.agenticUiVersion !== s.ui_version)
    return {ok: false, stage: 'refresh_dashboard', submitted: false};
  if (document.documentElement.dataset.agenticConnection !== 'ready'
      || !document.getElementById('web-create') || !document.getElementById('web-form'))
    return {ok: false, stage: 'dashboard_not_ready', submitted: false};
  if (document.getElementById('web-form').dataset.busy === 'true') return {ok: false, stage: 'dashboard_busy', submitted: false};
  let response, body;
  try {
    response = await fetch('/api/custom/captures', {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': s.csrf,
        'X-Dashboard-Instance': s.instance_id, 'X-Dashboard-Version': s.ui_version},
      body: JSON.stringify(capture),
    });
    if (!response.ok) return {ok: false, stage: 'capture_rejected', submitted: true, http_status: response.status};
    body = await response.json();
  } catch (_) { return {ok: false, stage: 'delivery_unknown', submitted: true}; }
  if (!/^[0-9a-f-]{36}$/i.test(body.capture_id || '')) return {ok: false, stage: 'delivery_unknown', submitted: true};
  return await new Promise(resolve => {
    const finish = value => { clearTimeout(timer); window.removeEventListener('message', received); resolve(value); };
    const received = event => {
      const data = event.data;
      if (event.source !== window || event.origin !== location.origin || data?.type !== 'agentic-capture-received-v1'
          || data.transfer_id !== transferId || data.capture_id !== body.capture_id) return;
      const rejected = ['dashboard_not_ready', 'dashboard_busy', 'capture_claim_failed'].includes(data.reason)
        ? data.reason : 'dashboard_not_ready';
      finish({ok: data.ok === true, stage: data.ok === true ? 'received' : rejected,
        submitted: true, capture_id: body.capture_id});
    };
    const timer = setTimeout(() => finish({ok: false, stage: 'receipt_unknown', submitted: true, capture_id: body.capture_id}), 8000);
    window.addEventListener('message', received);
    window.postMessage({type: 'agentic-capture-ready-v1', capture_id: body.capture_id, transfer_id: transferId}, location.origin);
  });
}
el('send').onclick = safe('send_unknown', async () => {
  if (!destination?.authenticated || !selectedDashboard || !el('consent').checked) fail('transfer_consent');
  el('send').disabled = true;
  try {
    const saved = await retainedCapture();
    if (!saved) fail('expired');
    if (saved.snapshotTransfer?.expires === saved.expires) fail('uncertain');
    const target = await chrome.tabs.get(selectedDashboard.id);
    if (!dashboard(target.url)) fail('dashboard_open');
    // Persist before dispatch: reopening must not repeat an uncertain POST.
    const attempt = {expires: saved.expires, state: 'sending'};
    await chrome.storage.session.set({snapshotTransfer: attempt}); transferLocked = true;
    let result;
    try { result = await injectedAt(target.id, sendCapture, [saved.capture, destination, crypto.randomUUID()]); }
    catch (_) {
      await chrome.storage.session.set({snapshotTransfer: {...attempt, state: 'unknown'}});
      el('send').hidden = true; el('consent-label').hidden = true; fail('send_unknown');
    }
    if (result?.ok) {
      await clearCapture(); show(null); preview = null; transferLocked = false;
      el('send').hidden = true; el('consent-label').hidden = true;
      el('pending-status').textContent = 'Received in the dashboard Source preview. Transfer complete; extraction has not started.';
      el('status').textContent = 'Snapshot received. Open the dashboard, enter your request, and approve extraction separately. No model call was made.';
      // Receipt has already succeeded; a focus error must not report transfer failure.
      try { await chrome.tabs.update(target.id, {active: true}); await chrome.windows.update(target.windowId, {focused: true}); }
      catch (_) { el('status').textContent += ' Switch to the dashboard tab manually.'; }
    } else if (result?.submitted === false) {
      await chrome.storage.session.remove(['snapshotTransfer']); transferLocked = false;
      el('consent').checked = false;
      el('status').textContent = result.stage === 'dashboard_busy'
        ? 'The dashboard is busy. Wait for it to finish, then check dashboard tabs and confirm transfer again. Nothing was sent.'
        : 'The dashboard account, session, or page changed. Sign in or refresh it, then check dashboard tabs and confirm the account again. Nothing was sent.';
      el('send').hidden = true;
    } else {
      await chrome.storage.session.set({snapshotTransfer: {...attempt, state: 'unknown', capture_id: result?.capture_id || null}});
      el('send').hidden = true; el('consent-label').hidden = true;
      const rejected = {
        dashboard_busy: 'The snapshot reached local storage, but the dashboard became busy before showing its preview.',
        dashboard_not_ready: 'The snapshot reached local storage, but the dashboard was not ready to show its preview.',
        capture_claim_failed: 'The snapshot reached local storage, but the dashboard could not claim it for preview.',
      };
      el('status').textContent = result?.stage === 'capture_rejected'
        ? `Dashboard rejected the snapshot (HTTP ${Number(result.http_status) || 'unknown'}). Nothing was automatically retried. Review the dashboard and capture again after correcting the issue.`
        : `${rejected[result?.stage] || 'The send was attempted, but the dashboard did not confirm its Source preview.'} Open the dashboard and check it before capturing again. No request will be repeated.`;
    }
  } finally { el('send').disabled = false; }
});
safe('selected_tab', async () => {
  [tab] = await chrome.tabs.query({active: true, currentWindow: true});
  if (!tab?.url || !/^https?:/.test(tab.url)) fail('selected_tab');
  const saved = await retainedCapture();
  if (!dashboard(tab.url)) el('capture').hidden = false;
  if (saved) {
    el('status').textContent = 'A kept snapshot is waiting for transfer. Keeping alone does not send it.';
    await showPending(saved);
  } else el('status').textContent = dashboard(tab.url)
    ? 'No pending snapshot. Open a website tab and capture its content first.'
    : 'Only this tab is captured. No cookies, history or API keys are read.';
})();
