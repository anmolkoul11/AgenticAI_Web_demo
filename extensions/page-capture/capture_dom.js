function captureDocument(options = {}) {
  // Python Playwright passes null when evaluate() has no explicit argument.
  options = options || {};
  // One collector for explicit capture, link discovery and extension handoff.
  // Never reads credentials or arbitrary form values. An explicit visible
  // currency selector may contribute its selected label, not other options.
  // Results describe this DOM, not the whole website.
  const tidy = value => (value || '').replace(/\s+/g, ' ').trim();
  // Python validates Unicode characters, whereas JS length measures UTF-16 units.
  // Budget conservatively in units, but report code points and never split a pair.
  const characterCount = value => [...value].length;
  const clipText = (value, limit) => {
    const clipped = value.slice(0, Math.max(0, limit));
    const finalUnit = clipped.charCodeAt(clipped.length - 1);
    return finalUnit >= 0xd800 && finalUnit <= 0xdbff ? clipped.slice(0, -1) : clipped;
  };
  const sensitive = /token|auth|session|key|code|sig|state|redirect|return|next|email/i;
  const unsafePath = /\/(?:login|logout|signout|signin|subscribe|unsubscribe|account|payment|pay|checkout|delete|book|reserve)(?:\/|$)/i;
  // Evidence URLs must be compact before grouping and charging the budget.
  // Keep bounded record-identifying query values, not attribution/session state.
  // Python capture.clean_url uses the same keys and limits. Live navigation links
  // below remain unchanged; a compact evidence URL is not a browser action.
  const identityQuery = /^(?:id|item|product|article|story|hotel|listing|slug|variant|page|p|(?:item|product|article|story|hotel|listing|variant)_id)$/i;
  const genericQueryPath = /(?:^|\/)(?:index|view|detail|details|item|product|article|story|hotel|listing)(?:\.(?:php|aspx?|html?))?\/?$/i;
  const nonIdentityQuery = /^utm_|^(?:aid|sid|label|lang|ref|source|campaign|affiliate|clickid|gclid|fbclid)$/i;
  const queryEncode = value => encodeURIComponent(value).replace(/[!'()*]/g,
    char => '%' + char.charCodeAt(0).toString(16).toUpperCase()).replace(/%20/g, '+');
  const clean = value => {
    try {
      const u = new URL(value, location.href);
      if (!['http:', 'https:'].includes(u.protocol) || u.username || u.password) return null;
      const query = [];
      let size = 0;
      for (const [key, content] of u.searchParams) {
        if (!identityQuery.test(key) || characterCount(content) > 128 ||
          /:\/\/|@|[\u0000-\u001f]/.test(content)) continue;
        const encoded = queryEncode(key) + '=' + queryEncode(content);
        if (query.length >= 8 || size + encoded.length + Number(query.length > 0) > 512) continue;
        size += encoded.length + Number(query.length > 0); query.push(encoded);
      }
      u.search = query.join('&'); u.hash = ''; return u.href;
    } catch (_) { return null; }
  };
  const queryIdentityOmitted = value => {
    try {
      const original = new URL(value, location.href);
      const compact = clean(value);
      if (!compact) return false;
      const retained = [...new URL(compact).searchParams];
      for (const [key, content] of original.searchParams) {
        if (!identityQuery.test(key)) continue;
        const match = retained.findIndex(pair => pair[0] === key && pair[1] === content);
        if (match < 0) return true;
        retained.splice(match, 1);
      }
      if (original.pathname !== '/' && !genericQueryPath.test(original.pathname)) return false;
      return [...original.searchParams.keys()]
        .some(key => !identityQuery.test(key) && !nonIdentityQuery.test(key));
    } catch (_) { return false; }
  };
  const evidenceURL = value => {
    if (queryIdentityOmitted(value)) { reasons.add('url_identity_omitted'); return null; }
    const url = clean(value);
    return url && !unsafePath.test(new URL(url).pathname) ? url : null;
  };
  const linkURL = value => {
    try {
      const u = new URL(value, location.href);
      if (u.protocol !== 'https:' || u.username || u.password || unsafePath.test(u.pathname))
        return null;
      if ([...u.searchParams.keys()].some(key => sensitive.test(key))) return null;
      u.hash = ''; return u.href;
    } catch (_) { return null; }
  };
  const excluded = 'script,style,noscript,template,form,input,textarea,select,button,' +
    '[contenteditable],[hidden],iframe';
  const navigation = 'nav,[role="navigation"],footer,[role="banner"],[role="contentinfo"]';
  const contentHeaders = 'article,main,[role="main"],[itemtype*="Article"],' +
    '[class*="article-header"],[class*="article-headline"],[class*="story-header"]';
  const inNavigation = element => {
    if (element.closest(navigation)) return true;
    const header = element.closest('header');
    return !!header && !header.closest(contentHeaders);
  };
  const headingSelector = 'h1,h2,h3,h4,h5,h6,[role="heading"],[itemprop="headline"],' +
    '[data-testid="title"],[itemprop="name"]';
  // Relationships share the existing 24k capture ceiling; reserve a small part
  // rather than growing model input to repeat whole listing cards as context.
  const blockLimit = 600, captureLimit = 24000, characterLimit = captureLimit - 2000;
  const bodySelector = '[itemprop="articleBody"],[data-testid="article-body"],' +
    '[class~="article-body"],[class~="article-content"],[class~="story-body"]';
  const hasExplicitBody = !!document.querySelector(bodySelector);
  const cards = '[data-testid="property-card"],[data-testid="product-card"],' +
    '[itemtype$="/Hotel"],[itemtype$="/Product"],article,li,tr,[class*="card"],[class*="story"],' +
    '[class~="article"],[class~="listing"],[class~="product"]';
  const semanticRecords = '[data-testid$="-card"],[itemtype$="/Hotel"],' +
    '[itemtype$="/Product"],article,[itemtype*="Article"]';
  const ancestor = e => e.parentElement || e.getRootNode()?.host || null;
  // aria-hidden is an accessibility instruction, not a CSS visibility rule.
  // Sites often mark a rendered amount this way and provide a separate spoken
  // label. Retain only short literal numeric/value text inside a headed public
  // record; other aria-hidden content, controls and CSS-hidden content stay out.
  const numericValue = text => /^(?:(?:[A-Z]{3}|US\$|CA\$|A\$|[$€£¥₹])\s*)?[+-]?(?:\d{1,3}(?:[,\u00a0\u202f ]\d{3})+(?:\.\d+)?|\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)(?:\s*(?:[A-Za-zµμ°]{1,5}|%|\/\s*\d+(?:[.,]\d+)?|(?:per|\/)\s*(?:night|room|item|unit|month|year|hour|day)))?$/.test(text);
  const scalarValue = text => numericValue(text.replace(/^(?:price|cost|rating|score)\s*:?\s*/i, ''));
  const renderedRecordValue = element => {
    const text = tidy(element.textContent);
    if (!text || text.length > 120 || !scalarValue(text) ||
      element.matches(semanticRecords + ',' + headingSelector) || element.querySelector(headingSelector)) return false;
    for (let card = element.closest(cards); card; card = ancestor(card)?.closest(cards)) {
      if (card !== element && !element.contains(card) &&
        card.querySelector(headingSelector + ',a[href]')) return true;
    }
    return false;
  };
  const renderedValueFragment = (element, hidden) => {
    // A visible accessibility-hidden wrapper can hold old/current amounts.
    // Permit its scalar descendants, not its headings, whole records or prose.
    if (tidy(hidden.textContent).length > 240 || hidden.matches(semanticRecords + ',' + headingSelector) ||
      hidden.querySelector(headingSelector + ',a[href]')) return false;
    for (let value = element, depth = 0; value && depth < 5 && hidden.contains(value);
      value = ancestor(value), depth++) {
      if (renderedRecordValue(value)) return true;
    }
    return false;
  };
  const visible = element => {
    if (!element || !element.getClientRects().length) return false;
    for (let e = element; e; e = ancestor(e)) {
      if (e.matches(excluded)) return false;
      if (e.getAttribute('aria-hidden') === 'true' &&
        !renderedRecordValue(e) && !renderedValueFragment(element, e)) return false;
      const s = getComputedStyle(e);
      if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
    }
    return true;
  };
  if (!clean(location.href)) throw new Error('Use a normal HTTP/HTTPS content page.');
  if (!document.body) throw new Error('No page body available.');
  const primary = document.querySelector('main,[role="main"]');
  // An article's header may sit outside <main>; preserve its headline before
  // the body budget is spent. Nodes are still de-duplicated and visibility checked.
  const primaryHeadings = [...document.querySelectorAll('h1,[itemprop="headline"],[role="heading"][aria-level="1"]')]
    .filter(element => !inNavigation(element));
  const roots = [...primaryHeadings, ...(primary ? [primary, document.body] : [document.body])];
  const reasons = new Set(), shadowRoots = new Set();
  const pageURLIdentityOmitted = queryIdentityOmitted(location.href);
  if (pageURLIdentityOmitted) reasons.add('url_identity_omitted');
  let inspectedElements = 0;
  // Open shadow roots share the collector; closed roots cannot be inspected.
  const visitShadows = root => {
    for (const el of root.querySelectorAll('*')) {
      if (++inspectedElements > 50000) { reasons.add('element_scan_limit'); return; }
      if (el.shadowRoot && !shadowRoots.has(el.shadowRoot)) {
        if (shadowRoots.size >= 20) { reasons.add('shadow_root_limit'); continue; }
        shadowRoots.add(el.shadowRoot); roots.push(el.shadowRoot); visitShadows(el.shadowRoot);
      }
    }
  };
  visitShadows(document.body);
  // innerText on a parent can include excluded text. Collect literal rendered
  // text through the same exclusion rules as the source blocks, not form values.
  const literalCache = new WeakMap();
  const boundaryCache = new WeakMap(), boundaryRange = document.createRange();
  const boundarySpace = (previous, current, left, right) => {
    if (!previous || !left || !right || /\s$/.test(left) || /^\s/.test(right)) return '';
    // Formatting a word or decimal across inline nodes must not change its value.
    if (/\d$/.test(left) && /^[.,]\d/.test(right) || /\d[.,]$/.test(left) && /^\d/.test(right)) return '';
    if (previous.parentElement?.closest('sup,sub') || current.parentElement?.closest('sup,sub')) return '';
    let next = boundaryCache.get(previous);
    if (!next) { next = new WeakMap(); boundaryCache.set(previous, next); }
    if (next.has(current)) return next.get(current);
    let separator = '';
    try {
      const lastSize = [...previous.textContent].at(-1)?.length || 1;
      boundaryRange.setStart(previous, Math.max(0, previous.length - lastSize));
      boundaryRange.setEnd(previous, previous.length);
      const before = boundaryRange.getBoundingClientRect();
      const firstSize = [...current.textContent][0]?.length || 1;
      boundaryRange.setStart(current, 0); boundaryRange.setEnd(current, firstSize);
      const after = boundaryRange.getBoundingClientRect();
      if (before.width && after.width) {
        const lineChanged = Math.abs(after.top - before.top) > Math.max(before.height, after.height) * 0.6;
        const rtl = getComputedStyle(current.parentElement).direction === 'rtl';
        const gap = rtl ? before.left - after.right : after.left - before.right;
        if (lineChanged || gap > 0.75) separator = ' ';
      }
    } catch (_) { /* An unmeasurable boundary is not permission to invent text. */ }
    next.set(current, separator); return separator;
  };
  let labelNodesVisited = 0;
  const literalLabel = element => {
    if (literalCache.has(element)) return literalCache.get(element);
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    let node, previous = null, text = '';
    while ((node = walker.nextNode())) {
      if (++labelNodesVisited > 50000) { reasons.add('text_scan_limit'); return ''; }
      if (visible(node.parentElement)) {
        text += boundarySpace(previous, node, text, node.textContent) + node.textContent;
        previous = node;
      }
      if (text.length > 6000) { reasons.add('cell_text_limit'); return ''; }
    }
    const result = tidy(text); literalCache.set(element, result); return result;
  };
  if (roots.some(root => [...root.querySelectorAll('input[type=password]')].some(visible)))
    throw new Error('Finish login and close password forms before capture.');
  const cardURLs = new WeakMap();
  const byURL = new Map(), seenAnchors = new WeakSet(), literalLinks = [];
  let anchorsVisited = 0;
  const detectedURLs = new Set();
  const urlsIn = card => {
    if (!card) return [];
    if (!cardURLs.has(card)) {
      const urls = new Set();
      for (const a of card.querySelectorAll('a[href]')) {
        if (!visible(a)) continue;
        const url = evidenceURL(a.href);
        if (url) urls.add(url);
        if (urls.size >= 100) break;
      }
      cardURLs.set(card, [...urls]);
    }
    return cardURLs.get(card);
  };
  const headingURL = heading => {
    const enclosing = heading.closest('a[href]');
    if (enclosing) return evidenceURL(enclosing.href);
    // <h3><a>Title</a></h3> is as common as <a><h3>Title</h3></a>.
    // Never choose the first of several different links inside a heading.
    const urls = new Set([...heading.querySelectorAll('a[href]')]
      .filter(visible).map(a => evidenceURL(a.href)).filter(Boolean));
    return urls.size === 1 ? [...urls][0] : null;
  };
  const recordInfoCache = new WeakMap(), recordOwnerCache = new WeakMap();
  const recordInfo = card => {
    if (recordInfoCache.has(card)) return recordInfoCache.get(card);
    const headings = [...card.querySelectorAll(headingSelector)].filter(visible).filter(heading => {
      const nested = heading.closest(semanticRecords);
      return !nested || nested === card || !card.contains(nested);
    });
    const rank = heading => heading.matches('[itemprop="headline"],[itemprop="name"],[data-testid="title"]') ? 0 :
      /^H[1-6]$/.test(heading.tagName) ? Number(heading.tagName[1]) : Number(heading.getAttribute('aria-level') || 7);
    const best = Math.min(...headings.map(rank));
    let identities = headings.filter(heading => rank(heading) === best);
    if (identities.length > 1) {
      const linked = identities.filter(heading => headingURL(heading));
      // One linked identity may share an H3 level with an unlinked "Rooms" or
      // "Features" subheading. Two independently linked updates remain distinct,
      // even if their links happen to use the same URL.
      if (linked.length === 1 && identities.every(heading => heading === linked[0] ||
        !heading.closest('a[href]') && !heading.querySelector('a[href]'))) identities = linked;
    }
    let info = null;
    // Count actual headings, not unique URLs: two live updates may intentionally
    // link to the same page and must not become one parent-wrapper record.
    if (identities.length === 1) {
      const text = literalLabel(identities[0]), href = headingURL(identities[0]);
      const headingLinks = new Set([...identities[0].querySelectorAll('a[href]')]
        .filter(visible).map(link => evidenceURL(link.href)).filter(Boolean));
      if (text && headingLinks.size <= 1) info = {key: (href || '') + '\u0000' + text, href,
        qualified: !!href || card.matches(semanticRecords)};
    } else if (!identities.length && card.matches(semanticRecords)) {
      const ownLinks = [...card.querySelectorAll('a[href]')].filter(visible).filter(link =>
        link.closest(semanticRecords) === card);
      const urls = new Set(ownLinks.map(link => evidenceURL(link.href)).filter(Boolean));
      if (urls.size === 1 && ownLinks.length) {
        const href = [...urls][0], text = literalLabel(ownLinks[0]);
        if (text) info = {key: href + '\u0000' + text, href, qualified: true};
      }
    }
    recordInfoCache.set(card, info); return info;
  };
  const recordOwner = element => {
    if (recordOwnerCache.has(element)) return recordOwnerCache.get(element);
    let selected = null, selectedInfo = null, fallback = null, fallbackInfo = null;
    for (let card = element.closest(cards); card; card = ancestor(card)?.closest(cards)) {
      const info = recordInfo(card);
      if (!info) continue;
      if (!selected) {
        if (info.qualified) { selected = card; selectedInfo = info; }
        else if (!fallback || info.key === fallbackInfo.key) { fallback = card; fallbackInfo = info; }
      } else if (info.key === selectedInfo.key) { selected = card; selectedInfo = info; }
      else break;
    }
    const owner = selected || fallback;
    recordOwnerCache.set(element, owner); return owner;
  };
  // Merge every representation before choosing a headline. A short kicker
  // encountered first must not hide a later heading for the same URL.
  for (const root of roots) {
    for (const a of root.querySelectorAll('a[href]')) {
      if (seenAnchors.has(a)) continue;
      seenAnchors.add(a);
      if (++anchorsVisited > 10000) { reasons.add('link_scan_limit'); break; }
      if (!visible(a)) continue;
      const url = linkURL(a.href);
      if (!url || url === linkURL(location.href)) continue;
      const heading = a.querySelector(headingSelector) || a.closest(headingSelector);
      const literal = literalLabel(a);
      const label = clipText(tidy(literal || a.getAttribute('aria-label') ||
        a.querySelector('img[alt]')?.alt), 180);
      const title = clipText(tidy(heading && literalLabel(heading) || label), 180);
      if (title.length < 4) continue;
      const card = recordOwner(a) || a.closest(cards);
      const nav = inNavigation(a);
      const score = (heading ? 1000 : 0) + (nav ? 0 : 200) + Math.min(title.length, 180);
      if (!nav && literal)
        literalLinks.push({element: a, href: evidenceURL(a.href), text: literal, score});
      const context = urlsIn(card).length === 1 ?
        clipText(tidy(card?.querySelector('p')?.innerText), 240) : '';
      let item = byURL.get(url);
      if (!item) {
        detectedURLs.add(url);
        if (byURL.size >= 1000) { reasons.add('inventory_link_limit'); continue; }
        item = {url, title, context, navigation: nav, score, labels: []};
        byURL.set(url, item);
      }
      if (label && !item.labels.includes(label) && item.labels.length < 6) item.labels.push(label);
      if (score > item.score) {
        item.title = title; item.score = score; item.context = context;
      }
      item.navigation = item.navigation && nav;
      if (!item.context && context) item.context = context;
    }
  }
  const links = [...byURL.values()].sort((a, b) =>
    Number(a.navigation) - Number(b.navigation) || b.score - a.score)
    .slice(0, 100).map((item, id) => ({
      id, title: item.title, context: item.context, url: item.url,
      navigation: item.navigation, labels: item.labels.filter(label => label !== item.title)
    }));
  if (options.mode === 'links') return links;

  const groupIDs = new Map();
  const group = key => {
    if (!groupIDs.has(key)) groupIDs.set(key, 'g' + (groupIDs.size + 1));
    return groupIDs.get(key);
  };
  const association = element => {
    if (inNavigation(element)) return {group_id: null, association: 'page'};
    const card = recordOwner(element);
    const a = element.closest('a[href]');
    if (a && queryIdentityOmitted(a.href))
      return {group_id: null, association: 'ambiguous'};
    if (element.matches(headingSelector) && [...element.querySelectorAll('a[href]')]
      .some(link => queryIdentityOmitted(link.href)))
      return {group_id: null, association: 'ambiguous'};
    // Container identity, not URL alone, owns a record. Nested metadata shares
    // that owner; independently headed child records retain a separate owner.
    if (card) return {group_id: group(card), association: 'record'};
    const url = element.matches(headingSelector) ? headingURL(element) : a && evidenceURL(a.href);
    if (url) return {group_id: group(url), association: 'record'};
    const nearest = element.closest(cards);
    const urls = urlsIn(nearest);
    if (urls.length === 1) return {group_id: group(nearest), association: 'record'};
    if (urls.length > 1) return {group_id: null, association: 'ambiguous'};
    if (nearest) {
      return {group_id: group(nearest), association: 'record'};
    }
    return {group_id: null, association: 'page'};
  };
  const seenNodes = new WeakSet(), grouped = new Map(), lastNodes = new WeakMap();
  const clippedOwners = new WeakSet();
  const labelBlocks = [];
  const labelURLs = new Set();
  let node, visited = 0, capturedChars = 0, eligibleChars = 0, omittedChars = 0;
  let navigationChars = 0;
  // Currency controls normally live in navigation, excluded from content.
  // Capture only one unambiguous selected currency setting, never an open
  // currency menu's alternatives or arbitrary occurrences of a currency code.
  const currencySettings = new Map();
  const currencyCodes = /\b(?:USD|EUR|GBP|CAD|AUD|JPY|INR|CHF)\b/g;
  const currencyVisible = element => {
    if (!element.getClientRects().length) return false;
    for (let parent = element; parent; parent = ancestor(parent)) {
      if (parent.matches('[hidden],[inert],[aria-hidden="true"],iframe')) return false;
      const style = getComputedStyle(parent);
      if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    }
    return true;
  };
  for (const element of document.querySelectorAll('button,[role="button"],select')) {
    if (!currencyVisible(element)) continue;
    const aria = tidy(element.getAttribute('aria-label'));
    let label = aria || tidy(element.innerText);
    if (element.tagName === 'SELECT' && /^currency$/i.test(aria)) {
      const selected = element.selectedOptions?.[0];
      label = selected ? 'Currency: ' + tidy(selected.textContent) : '';
    }
    if (!/^(?:prices?(?:\s+shown)?(?:\s+are)?\s+in\s+|(?:selected\s+)?currency\s*[: ]\s*)/i.test(label)) continue;
    const codes = [...new Set(label.toUpperCase().match(currencyCodes) || [])];
    if (codes.length !== 1 || label.length > 180) continue;
    if (!currencySettings.has(codes[0])) currencySettings.set(codes[0], label);
  }
  if (currencySettings.size === 1) {
    const text = [...currencySettings.values()][0];
    labelBlocks.push({id: '', kind: 'text', text, href: null, group_id: null,
      association: 'page', content_role: 'currency_setting'});
    capturedChars += text.length; eligibleChars += text.length;
  }
  // Coherent record bundles precede unrelated headings and secondary labels.
  // Reserving every heading/URL first used to leave no room for the prices and
  // ratings attached to those same records, especially with attribution URLs.
  const contentHeadings = [...new Set(roots.flatMap(root =>
    [...root.querySelectorAll(headingSelector)]))].filter(e => visible(e) && !inNavigation(e));
  const recordRoots = [...new Set([
    ...contentHeadings.map(recordOwner),
    ...literalLinks.map(item => recordOwner(item.element))
  ].filter(Boolean))].filter(card =>
    !(card.matches('article,[itemtype*="Article"]') &&
      card.querySelector('h1,[itemprop="headline"]')));
  const preserveLinkLabels = (items = literalLinks, quota = Infinity) => {
    const beforeChars = capturedChars;
    // Deduplicate by literal label AND URL, not URL alone: a paragraph can already
    // carry that href while still lacking the separate link-role evidence.
    const represented = new Set([...grouped.values()].filter(block =>
      ['heading', 'link'].includes(block.kind) && block.href && tidy(block.text))
      .map(block => clean(block.href) + '\u0000' + tidy(block.text)));
    for (const item of [...items].sort((a, b) => b.score - a.score)) {
      const key = item.href + '\u0000' + item.text;
      if (!item.href || item.href.length > 2048 || represented.has(key)) continue;
      if (capturedChars - beforeChars + item.href.length + item.text.length > quota) continue;
      if (grouped.size + labelBlocks.length >= blockLimit ||
        capturedChars + item.href.length + item.text.length > characterLimit) {
        reasons.add('link_evidence_limit'); continue;
      }
      represented.add(key); capturedChars += item.href.length + item.text.length;
      labelURLs.add(item.href);
      labelBlocks.push({id: '', kind: 'link', text: item.text, href: item.href,
        content_role: 'other', ...association(item.element)});
    }
  };
  const splitValueOwners = new WeakMap();
  const hasSeparateAmounts = owner => {
    if (!splitValueOwners.has(owner)) {
      const parts = [...owner.querySelectorAll('*')].slice(0, 120)
        .filter(element => visible(element) && scalarValue(literalLabel(element)));
      const values = parts.filter(element => !parts.some(other =>
        other !== element && other.contains(element)));
      const monetary = values.filter(element =>
        /[$€£¥₹]|\b(?:USD|EUR|GBP|CAD|AUD|JPY|INR)\b/i.test(literalLabel(element)));
      splitValueOwners.set(owner, values.length > 1 && (monetary.length > 1 ||
        getComputedStyle(owner).textDecorationLine.includes('line-through') ||
        values.some(element => element.closest('s,del') ||
          getComputedStyle(element).textDecorationLine.includes('line-through'))));
    }
    return splitValueOwners.get(owner);
  };
  const ownerOf = parent => {
    const owner = parent.closest(headingSelector + ',tr,p');
    if (owner && (!owner.matches('p,tr') || !hasSeparateAmounts(owner))) return owner;
    // A scalar can be split across styled spans (currency, integer, cents).
    // Keep the smallest bounded scalar cluster together, without lifting a
    // whole record or joining values from independently headed records.
    let valueOwner = null;
    for (let value = parent, depth = 0; value && depth < 5; value = ancestor(value), depth++) {
      if (value.matches(cards + ',a[href]')) break;
      const text = literalLabel(value);
      if (text.length > 120) break;
      // Old/current prices or separate counters are not a numeric fragment
      // cluster merely because their rendered digits happen to be adjacent.
      if (value !== parent && [...value.children].filter(child =>
        scalarValue(literalLabel(child))).length > 1) break;
      if (scalarValue(text)) valueOwner = value;
      else if (valueOwner) break;
    }
    if (valueOwner) return valueOwner;
    if (owner) return owner;
    const item = parent.closest('li');
    // A list can be a grid of complete records. Do not join all of its adjacent
    // price/rating spans into one giant paragraph or charge its description first.
    if (item && !item.querySelector(headingSelector)) return item;
    return parent.closest('a[href]') || parent;
  };
  const collectRoot = (root, quota = Infinity, ownOnly = false) => {
    const beforeChars = capturedChars;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while ((node = walker.nextNode())) {
      if (seenNodes.has(node)) continue;
      // Record-local prioritization must not reorder a paragraph's text nodes,
      // or consume its nested heading twice under an outer list/table owner.
      if (ownOnly && ownerOf(node.parentElement) !== root) continue;
      if (capturedChars - beforeChars >= quota) break;
      seenNodes.add(node);
      if (++visited > 50000) { reasons.add('text_scan_limit'); break; }
      const parent = node.parentElement;
      if (!visible(parent)) continue;
      const text = tidy(node.textContent);
      if (!text) continue;
      if (inNavigation(parent)) { navigationChars += text.length; continue; }
      eligibleChars += text.length;
      // Keep inline names in their paragraph and retain heading identity inside links.
      const owner = ownerOf(parent);
      if (clippedOwners.has(owner)) { omittedChars += text.length; continue; }
      const label = literalLabel(owner);
      const scalar = label.length <= 240 && scalarValue(label);
      // Do not turn a short scalar into a different value by clipping its final
      // digits. Leave it unseen for the shared-budget pass, or disclose omission.
      if (!grouped.has(owner) && scalar &&
        label.length > Math.min(characterLimit - capturedChars, quota - (capturedChars - beforeChars))) {
        seenNodes.delete(node);
        reasons.add(label.length > characterLimit - capturedChars ? 'text_budget' : 'record_bundle_limit');
        continue;
      }
      let block = grouped.get(owner);
      if (!block) {
        if (grouped.size + labelBlocks.length >= blockLimit) {
          omittedChars += text.length; reasons.add('block_limit'); continue;
        }
        const isHeading = owner.matches(headingSelector);
        const enclosingLink = owner.closest('a[href]');
        const href = isHeading ? headingURL(owner) : enclosingLink ?
          evidenceURL(enclosingLink.href) : null;
        const validHref = href && href.length <= 2048 ? href : null;
        const level = /^H[1-6]$/.test(owner.tagName) ? Number(owner.tagName[1]) :
          Number(owner.getAttribute('aria-level') || (owner.matches('[itemprop="headline"]') ? 1 : 0));
        const kind = isHeading ? 'heading' : owner.tagName === 'TR' ?
          'table_row' : owner.tagName === 'A' ? 'link' : ['P', 'LI'].includes(owner.tagName) ?
          'paragraph' : 'text';
        block = {id: 'b' + (grouped.size + 1), kind, text: '', href: null, ...association(owner)};
        if (isHeading && level >= 1 && level <= 6) block.heading_level = level;
        const article = owner.closest('article,[itemtype*="Article"]');
        block.content_role = isHeading && level === 1 &&
          (article || owner.matches('[itemprop="headline"]') ||
            owner.closest('[class*="article-header"],[class*="article-headline"]')) ? 'headline' :
          kind === 'paragraph' && (owner.closest(bodySelector) ||
            (!hasExplicitBody && article?.querySelector('h1'))) ? 'body' : 'other';
        // The separate label block already carries this URL and group. Do not
        // spend the URL budget twice on its paragraph/text representation.
        const hrefRepresented = validHref && labelURLs.has(clean(validHref)) && !isHeading;
        const reservedText = scalar ? label.length : text.length;
        if (validHref && !hrefRepresented &&
          capturedChars + validHref.length + reservedText <= characterLimit &&
          capturedChars - beforeChars + validHref.length + reservedText <= quota) {
          block.href = validHref; capturedChars += validHref.length;
        } else if (href && !hrefRepresented) reasons.add('link_evidence_limit');
        grouped.set(owner, block);
      }
      // Normalize after the whole block, preserving text-node boundaries around links.
      const separator = boundarySpace(lastNodes.get(owner), node, block.text, node.textContent);
      const rawText = separator + node.textContent;
      eligibleChars += separator.length;
      const available = Math.max(0, Math.min(6000 - block.text.length,
        characterLimit - capturedChars, quota - (capturedChars - beforeChars)));
      const limitedByCell = available === 6000 - block.text.length;
      const appended = clipText(rawText, available);
      block.text += appended; capturedChars += appended.length;
      lastNodes.set(owner, node);
      if (appended.length < rawText.length) {
        clippedOwners.add(owner);
        omittedChars += rawText.length - appended.length;
        reasons.add(limitedByCell ? 'cell_text_limit' :
          capturedChars >= characterLimit ? 'text_budget' : 'record_bundle_limit');
      }
    }
  };
  // Genuine article headlines remain first, even when their header is outside
  // <main>. An opened article's body precedes recommendation-card bundles.
  for (const heading of primaryHeadings) collectRoot(heading);
  const detailHeadings = primaryHeadings.filter(heading =>
    heading.closest('article,[itemtype*="Article"],[class*="article-header"],' +
      '[class*="article-headline"],[class*="story-header"]') ||
    heading.matches('[itemprop="headline"]'));
  if (detailHeadings.length) {
    const detailBodies = [...new Set(roots.flatMap(root =>
      [...root.querySelectorAll(bodySelector)]))].filter(visible);
    if (detailBodies.length) {
      for (const body of detailBodies) collectRoot(body);
    } else {
      // Native <article><h1> detail layouts need no site-specific body selector.
      for (const heading of detailHeadings) {
        const article = heading.closest('article,[itemtype*="Article"]');
        if (!article) continue;
        for (const paragraph of article.querySelectorAll('p')) {
          const nearestCard = recordOwner(paragraph);
          if (nearestCard === article) collectRoot(paragraph);
        }
      }
    }
  }
  const prioritizedOwners = card => {
    const owners = new Set();
    const walker = document.createTreeWalker(card, NodeFilter.SHOW_TEXT);
    let textNode;
    while ((textNode = walker.nextNode())) {
      if (owners.size > blockLimit || visited > 50000) break;
      if (!visible(textNode.parentElement) || !tidy(textNode.textContent)) continue;
      if (recordOwner(textNode.parentElement) !== card) continue;
      owners.add(ownerOf(textNode.parentElement));
    }
    const priority = owner => {
      if (owner.matches(headingSelector)) return 0;
      const text = literalLabel(owner);
      // Generic literal metadata, not site-specific CSS or inferred values.
      if (owner.closest('[itemprop="price"],[itemprop="priceCurrency"],' +
        '[itemprop="ratingValue"],[itemprop="reviewCount"]')) return 1;
      // Short literal amount/score fields precede descriptive paragraphs that
      // happen to mention a stay, night or review. No amount is derived here.
      if (text.length <= 240 && (/(?:[$€£¥]|\b(?:USD|EUR|GBP|CAD|AUD|JPY|INR)\b|\b(?:price|rating|score)\b)/i.test(text) ||
        scalarValue(text))) return 1;
      if (text.length <= 240 &&
        /\b(?:night|nights|stay|tax|taxes|fees?|adults?|children|rooms?|beds?|bedrooms?|bathrooms?|suite|balcony|breakfast|reviews?)\b/i.test(text)) return 2;
      if (owner.tagName === 'A') return 3;
      return text.length <= 180 ? 4 : 5;
    };
    return [...owners].sort((a, b) => priority(a) - priority(b));
  };
  // Give each early record a share before spending the rest on long descriptions.
  // A loaded page can exceed this bounded snapshot; omissions are disclosed.
  const bundleRoots = recordRoots.slice(0, 50);
  if (recordRoots.length > bundleRoots.length) reasons.add('record_bundle_limit');
  const bundleQuota = Math.max(400, Math.min(1600,
    Math.floor((characterLimit - capturedChars) / Math.max(bundleRoots.length, 1))));
  for (const card of bundleRoots) {
    const start = capturedChars;
    const localLinks = literalLinks.filter(item => recordOwner(item.element) === card);
    // Link-role labels are retained before tiny spans/cells; bounded compact URLs
    // keep this reservation proportional to the record rather than its trackers.
    preserveLinkLabels(localLinks, Math.max(200, Math.floor(bundleQuota * 0.35)));
    for (const owner of prioritizedOwners(card)) {
      const remaining = bundleQuota - (capturedChars - start);
      if (remaining <= 0 || visited > 50000) break;
      collectRoot(owner, remaining, true);
    }
  }
  // Non-card headlines and paragraph/span link titles still survive hundreds of
  // early secondary paragraphs. Literal labels remain separate link evidence.
  for (const heading of contentHeadings) collectRoot(heading);
  preserveLinkLabels();
  for (const root of [...recordRoots, ...roots]) {
    collectRoot(root);
    if (visited > 50000) break;
  }
  // Numeric blocks retain literal amount-specific relationships. A record-wide
  // "per night" must not become the basis of every amount in that record.
  const struckThrough = (element, record) => {
    for (let current = element; current; current = ancestor(current)) {
      if (current.matches('s,del') ||
        getComputedStyle(current).textDecorationLine.includes('line-through')) return true;
      if (current === record) break;
    }
    return false;
  };
  const scalars = [...grouped].map(([element, block]) => ({element, block,
    record: recordOwner(element), text: tidy(block.text)})).filter(item =>
      item.record && item.block.association === 'record' && item.text.length <= 120 && scalarValue(item.text));
  for (const item of scalars) item.struck = struckThrough(item.element, item.record);
  const valueLabels = /^(?:per\s+(?:night|room|item|unit|month|year|hour|day|person|adult|ticket)(?:\s+per\s+(?:night|room|item|unit|month|year|hour|day|person|adult|ticket))?|(?:order\s+|stay\s+|grand\s+)?total(?:\s+(?:price|cost|for\s+(?:your|the)\s+stay))?|subtotal|(?:original|current|discounted|sale)\s+(?:price|cost)|\d+\s+(?:nights?|days?|adults?|children|rooms?|items?|units?|tickets?)(?:\s*(?:[,·]|and)\s*\d+\s+(?:nights?|days?|adults?|children|rooms?|items?|units?|tickets?))*)$/i;
  const remainingLiteral = (container, ignored) => {
    if (!ignored.length) return literalLabel(container);
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    let textNode, previous = null, text = '';
    while ((textNode = walker.nextNode())) {
      if (!visible(textNode.parentElement) || ignored.some(element => element.contains(textNode))) continue;
      text += boundarySpace(previous, textNode, text, textNode.textContent) + textNode.textContent;
      previous = textNode;
    }
    return tidy(text);
  };
  const localContext = (item, known = []) => {
    if (item.struck) return {container: item.element, quote: item.text, label: ''};
    for (let container = item.element, depth = 0; container && depth < 7;
      container = ancestor(container), depth++) {
      if (!item.record.contains(container)) break;
      const quote = literalLabel(container);
      if (quote.length > 500) break;
      const ignored = known.filter(context => context.container !== container &&
        container.contains(context.container) && !context.container.contains(item.element))
        .map(context => context.container);
      const local = scalars.filter(other => other.record === item.record &&
        container.contains(other.element) && !ignored.some(element => element.contains(other.element)));
      const current = local.filter(other => !other.struck);
      if (current.length === 1 && current[0] === item) {
        let label = remainingLiteral(container, ignored);
        for (const other of [...local].sort((a, b) => b.text.length - a.text.length))
          label = label.replace(other.text, '');
        label = tidy(label).replace(/^[\s:;,·–—-]+|[\s:;,·–—-]+$/g, '');
        // Label is itself literal source text, not a joined paraphrase. Multiple
        // unlabelled current amounts remain ambiguous, regardless of magnitude.
        if (label.length <= 160 && valueLabels.test(label) && quote.includes(label)) {
          // A contiguous rendered span can exclude a separately labelled sibling
          // without synthesizing a label/value sentence or repeating the card.
          const valueAt = quote.indexOf(item.text), labelAt = quote.indexOf(label);
          const unique = valueAt >= 0 && quote.indexOf(item.text, valueAt + item.text.length) < 0 &&
            quote.indexOf(label, labelAt + label.length) < 0;
          const span = unique ? quote.slice(Math.min(valueAt, labelAt),
            Math.max(valueAt + item.text.length, labelAt + label.length)) : quote;
          return {container, quote: span, label};
        }
      }
      if (container === item.record) break;
    }
    return null;
  };
  const contexts = new Map(scalars.map(item => [item, localContext(item)]));
  const independent = [...contexts.values()].filter(context => context?.label);
  for (const item of scalars) {
    if (!contexts.get(item)) contexts.set(item, localContext(item, independent));
  }
  let contextChars = 0;
  const sourceSize = [...grouped.values(), ...labelBlocks].reduce((size, block) =>
    size + tidy(block.text).length + (block.href?.length || 0), 0);
  // Prefer useful labelled current values over decorative strike status when a
  // busy page exhausts the shared budget. Omission is explicit, never guessed.
  for (const [item, context] of [...contexts].sort((a, b) =>
    Number(!a[1]?.label) - Number(!b[1]?.label))) {
    if (!context) continue;
    const size = context.quote.length + context.label.length;
    if (contextChars + size > 6000 || sourceSize + contextChars + size > captureLimit) {
      reasons.add('value_context_limit'); continue;
    }
    item.block.value_context = {quote: context.quote, label: context.label,
      relation: 'local_container', struck_through: item.struck};
    contextChars += size;
  }
  const retainedLinkLabels = new Set();
  const blocks = [...grouped.values(), ...labelBlocks].map(block => ({...block, text: tidy(block.text)}))
    .filter(block => block.text).filter(block => {
      if (block.kind !== 'link' || !block.href) return true;
      const key = clean(block.href) + '\u0000' + block.text + '\u0000' + (block.group_id || '');
      if (retainedLinkLabels.has(key)) return false;
      retainedLinkLabels.add(key); return true;
    });
  // Re-number after empty/fully omitted blocks; never invent missing text.
  blocks.forEach((block, index) => { block.id = 'b' + (index + 1); });
  if (blocks.reduce((n, block) => n + characterCount(block.text) +
    (block.href?.length || 0), 0) < 80)
    throw new Error('CAPTURE_INSUFFICIENT_CONTENT: Too little visible content. ' +
      'Open the content or listings first.');
  const frames = document.querySelectorAll('iframe').length;
  return {
    version: 1, url: clean(location.href), captured_at: new Date().toISOString(),
    truncated: reasons.size > 0, blocks,
    coverage: {
      collector_version: 'source-inventory-v6', scope: 'loaded_dom',
      page_url_identity_omitted: pageURLIdentityOmitted,
      eligible_text_chars: Math.min(eligibleChars, 10000000),
      captured_text_chars: blocks.reduce((n, block) => n + characterCount(block.text), 0),
      omitted_text_chars: Math.min(omittedChars, 10000000),
      excluded_navigation_chars: Math.min(navigationChars, 10000000),
      unique_links_detected: detectedURLs.size,
      links_returned: links.length, candidate_limit_reached: byURL.size > 100,
      frames_excluded: Math.min(frames, 10000), open_shadow_roots: shadowRoots.size,
      record_groups: groupIDs.size, limit_reasons: [...reasons].slice(0, 10),
      scroll_steps: 0,
      at_page_end: scrollY + innerHeight >= document.documentElement.scrollHeight - 4,
      content_settled: false,
      preparation: 'manual_snapshot'
    }
  };
}
