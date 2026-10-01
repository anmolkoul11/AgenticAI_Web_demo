function captureDocument() {
  // Runs only in the selected top frame, on an explicit user action.
  const clean = value => {
    try {
      const u = new URL(value, location.href);
      if (!['http:', 'https:'].includes(u.protocol) || u.username || u.password) return null;
      u.search = ''; u.hash = ''; return u.href;
    } catch (_) { return null; }
  };
  const excluded = 'script,style,noscript,template,form,input,textarea,select,button,' +
    '[contenteditable],[hidden],[aria-hidden="true"],iframe';
  const visible = element => {
    if (!element || element.closest(excluded) || !element.getClientRects().length) return false;
    for (let e = element; e; e = e.parentElement) {
      const s = getComputedStyle(e);
      if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
    }
    return true;
  };
  if (!clean(location.href)) throw new Error('Use a normal HTTP/HTTPS content page.');
  if ([...document.querySelectorAll('input[type=password]')].some(e => e.getClientRects().length))
    throw new Error('Finish login and close password forms before capture.');
  if (!document.body) throw new Error('No page body available.');
  // Prefer the page's primary content. Fall back to the full body only when
  // that region is too sparse; otherwise menus and footers consume the budget.
  const primary = document.querySelector('main,[role="main"]');
  const roots = primary ? [primary, document.body] : [document.body];
  const seenNodes = new WeakSet();
  const groups = new Map(); let node, visited = 0, truncated = false, budget = 0;
  for (const root of roots) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while ((node = walker.nextNode())) {
      if (seenNodes.has(node)) continue;
      seenNodes.add(node);
      if (++visited > 50000) { truncated = true; break; }
      const parent = node.parentElement;
      if (!visible(parent)) continue;
      const text = node.textContent.replace(/\s+/g, ' ').trim();
      if (!text) continue;
      // Prefer the actual anchor over a nested heading/list container so its
      // destination survives as structured evidence for an index headline.
      const owner = parent.closest('a[href]') ||
        parent.closest('h1,h2,h3,h4,h5,h6,tr,p,li') || parent;
      if (!groups.has(owner)) {
        if (groups.size >= 200) { truncated = true; break; }
        groups.set(owner, '');
      }
      const prior = groups.get(owner), available = Math.min(6000 - prior.length, 23000 - budget);
      const added = (prior ? ' ' : '') + text;
      if (available < added.length) truncated = true;
      const part = added.slice(0, Math.max(0, available));
      groups.set(owner, prior + part); budget += part.length;
      if (budget >= 23000) { truncated = true; break; }
    }
    if (truncated && (groups.size >= 200 || budget >= 23000 || visited > 50000)) break;
    if (root === primary && budget >= 500) break;
  }
  const blocks = [];
  const recordGroups = new Map();
  for (const [e, text] of groups) {
    if (!text.trim()) continue;
    let href = e.tagName === 'A' ? clean(e.href) : null;
    if (href && (href.length > 2048 || budget + href.length > 24000)) {
      href = null; truncated = true;
    }
    budget += href?.length || 0;
    const kind = /^H[1-6]$/.test(e.tagName) ? 'heading' : e.tagName === 'TR' ? 'table_row' :
      e.tagName === 'A' ? 'link' : ['P', 'LI'].includes(e.tagName) ? 'paragraph' : 'text';
    const recordOwner = e.closest('[data-testid="property-card"],article,tr');
    if (recordOwner && !recordGroups.has(recordOwner))
      recordGroups.set(recordOwner, `g${recordGroups.size + 1}`);
    const group_id = recordOwner ? recordGroups.get(recordOwner) : null;
    blocks.push({id: `b${blocks.length + 1}`, kind, text, href, group_id});
  }
  if (budget < 80) throw new Error('Too little visible content. Open the article or listings first.');
  return {version: 1, url: clean(location.href), captured_at: new Date().toISOString(), truncated, blocks};
}
