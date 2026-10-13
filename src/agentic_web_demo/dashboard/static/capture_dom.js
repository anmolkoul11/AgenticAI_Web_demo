function captureDocument(options = {}) {
  // Python Playwright passes null when evaluate() has no explicit argument.
  options = options || {};
  // One collector for explicit capture, link discovery and extension handoff.
  // Never reads form values. Results describe this DOM, not the whole website.
  const tidy = value => (value || '').replace(/\s+/g, ' ').trim();
  const sensitive = /token|auth|session|key|code|sig|state|redirect|return|next|email/i;
  const unsafePath = /\/(?:login|logout|signout|signin|subscribe|unsubscribe|account|payment|pay|checkout|delete|book|reserve)(?:\/|$)/i;
  const clean = value => {
    try {
      const u = new URL(value, location.href);
      if (!['http:', 'https:'].includes(u.protocol) || u.username || u.password) return null;
      u.search = ''; u.hash = ''; return u.href;
    } catch (_) { return null; }
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
    '[contenteditable],[hidden],[aria-hidden="true"],iframe';
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
  const blockLimit = 600, characterLimit = 24000;
  const bodySelector = '[itemprop="articleBody"],[data-testid="article-body"],' +
    '[class~="article-body"],[class~="article-content"],[class~="story-body"]';
  const hasExplicitBody = !!document.querySelector(bodySelector);
  const cards = '[data-testid="property-card"],[data-testid="product-card"],' +
    '[itemtype$="/Hotel"],[itemtype$="/Product"],article,li,tr,[class*="card"],[class*="story"],' +
    '[class~="article"],[class~="listing"],[class~="product"]';
  const ancestor = e => e.parentElement || e.getRootNode()?.host || null;
  const visible = element => {
    if (!element || !element.getClientRects().length) return false;
    for (let e = element; e; e = ancestor(e)) {
      if (e.matches(excluded)) return false;
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
  // innerText on a parent can include aria-hidden text. Collect literal rendered
  // text through the same exclusion rules as the source blocks, not form values.
  const literalCache = new WeakMap();
  let labelNodesVisited = 0;
  const literalLabel = element => {
    if (literalCache.has(element)) return literalCache.get(element);
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    let node, text = '';
    while ((node = walker.nextNode())) {
      if (++labelNodesVisited > 50000) { reasons.add('text_scan_limit'); return ''; }
      if (visible(node.parentElement)) text += node.textContent;
      if (text.length > 6000) { reasons.add('cell_text_limit'); return ''; }
    }
    const result = tidy(text); literalCache.set(element, result); return result;
  };
  if (roots.some(root => [...root.querySelectorAll('input[type=password]')].some(visible)))
    throw new Error('Finish login and close password forms before capture.');
  const cardURLs = new WeakMap(), primaryURLs = new WeakMap();
  const byURL = new Map(), seenAnchors = new WeakSet(), literalLinks = [];
  let anchorsVisited = 0;
  const detectedURLs = new Set();
  const urlsIn = card => {
    if (!card) return [];
    if (!cardURLs.has(card)) {
      const urls = new Set();
      for (const a of card.querySelectorAll('a[href]')) {
        if (!visible(a)) continue;
        const url = linkURL(a.href);
        if (url) urls.add(url);
        if (urls.size >= 100) break;
      }
      cardURLs.set(card, [...urls]);
    }
    return cardURLs.get(card);
  };
  const primaryURL = card => {
    if (!card) return null;
    if (primaryURLs.has(card)) return primaryURLs.get(card);
    const headings = [...card.querySelectorAll('h1,h2,h3,h4,h5,h6,' +
      '[data-testid="title"],[itemprop="name"]')].filter(visible);
    const urls = new Set(headings.map(heading => headingURL(heading)).filter(Boolean));
    const result = urls.size === 1 ? [...urls][0] : null;
    primaryURLs.set(card, result);
    return result;
  };
  const headingURL = heading => {
    const enclosing = heading.closest('a[href]');
    if (enclosing) return linkURL(enclosing.href);
    // <h3><a>Title</a></h3> is as common as <a><h3>Title</h3></a>.
    // Never choose the first of several different links inside a heading.
    const urls = new Set([...heading.querySelectorAll('a[href]')]
      .filter(visible).map(a => linkURL(a.href)).filter(Boolean));
    return urls.size === 1 ? [...urls][0] : null;
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
      const label = tidy(literal || a.getAttribute('aria-label') ||
        a.querySelector('img[alt]')?.alt).slice(0, 180);
      const title = tidy(heading && literalLabel(heading) || label).slice(0, 180);
      if (title.length < 4) continue;
      const card = a.closest(cards);
      const nav = inNavigation(a);
      const score = (heading ? 1000 : 0) + (nav ? 0 : 200) + Math.min(title.length, 180);
      if (!nav && literal) literalLinks.push({element: a, href: clean(url), text: literal, score});
      const context = urlsIn(card).length === 1 ?
        tidy(card?.querySelector('p')?.innerText).slice(0, 240) : '';
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

  const groupIDs = new Map(), containerIDs = new WeakMap();
  let nextContainer = 0;
  const group = key => {
    if (!groupIDs.has(key)) groupIDs.set(key, 'g' + (groupIDs.size + 1));
    return groupIDs.get(key);
  };
  const association = element => {
    if (inNavigation(element)) return {group_id: null, association: 'page'};
    const card = element.closest(cards);
    // An opened detail article's body remains one record, including inline links.
    // Nested cards use their own nearest container instead.
    const article = element.closest('article,[itemtype*="Article"]');
    const nestedCard = card && card !== article &&
      card.matches('[data-testid="property-card"],[data-testid="product-card"],[class*="card"],li,tr');
    if (article?.querySelector('h1,[itemprop="headline"]') && !nestedCard)
      return {group_id: group(article), association: 'record'};
    const a = element.closest('a[href]');
    const url = element.matches(headingSelector) ? headingURL(element) : a && linkURL(a.href);
    if (url) return {group_id: group(url), association: 'record'};
    const urls = urlsIn(card);
    const primaryLink = primaryURL(card);
    if (primaryLink) return {group_id: group(primaryLink), association: 'record'};
    if (urls.length === 1) return {group_id: group(urls[0]), association: 'record'};
    if (urls.length > 1) return {group_id: null, association: 'ambiguous'};
    if (card) {
      if (!containerIDs.has(card)) containerIDs.set(card, ++nextContainer);
      return {group_id: group('container-' + containerIDs.get(card)), association: 'record'};
    }
    return {group_id: null, association: 'page'};
  };
  const seenNodes = new WeakSet(), grouped = new Map();
  const labelBlocks = [];
  const labelURLs = new Set();
  let node, visited = 0, capturedChars = 0, eligibleChars = 0, omittedChars = 0;
  let navigationChars = 0;
  // Reserve space for record identities/links throughout the loaded DOM before
  // secondary labels consume the block budget. Still bounded, never full-site proof.
  const contentHeadings = [...new Set(roots.flatMap(root =>
    [...root.querySelectorAll(headingSelector)]))].filter(e => visible(e) && !inNavigation(e));
  const recordRoots = [...new Set(contentHeadings.map(heading => heading.closest(cards)).filter(Boolean))];
  const headingRoots = new Set([...primaryHeadings, ...contentHeadings]);
  let labelsPreserved = false;
  const preserveLinkLabels = () => {
    if (labelsPreserved) return;
    labelsPreserved = true;
    // Deduplicate by literal label AND URL, not URL alone: a paragraph can already
    // carry that href while still lacking the separate link-role evidence.
    const represented = new Set([...grouped.values()].filter(block =>
      ['heading', 'link'].includes(block.kind) && block.href && tidy(block.text))
      .map(block => clean(block.href) + '\u0000' + tidy(block.text)));
    for (const item of literalLinks.sort((a, b) => b.score - a.score)) {
      const key = item.href + '\u0000' + item.text;
      if (!item.href || item.href.length > 2048 || represented.has(key)) continue;
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
  for (const root of [...primaryHeadings, ...contentHeadings, ...recordRoots, ...roots]) {
    // Keep native headings first, then reserve link identity evidence before body
    // text. This also covers <a><p>Title</p></a>, <p><a>Title</a></p> and spans.
    if (!headingRoots.has(root)) preserveLinkLabels();
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while ((node = walker.nextNode())) {
      if (seenNodes.has(node)) continue;
      seenNodes.add(node);
      if (++visited > 50000) { reasons.add('text_scan_limit'); break; }
      const parent = node.parentElement;
      if (!visible(parent)) continue;
      const text = tidy(node.textContent);
      if (!text) {
        const container = parent.closest(headingSelector + ',tr,p,li');
        if (container && grouped.has(container) && capturedChars < 24000) {
          grouped.get(container).text += ' '; capturedChars += 1;
        }
        continue;
      }
      if (inNavigation(parent)) { navigationChars += text.length; continue; }
      eligibleChars += text.length;
      // Keep inline names in their paragraph and retain heading identity inside links.
      const owner = parent.closest(headingSelector + ',tr,p,li') ||
        parent.closest('a[href]') || parent;
      let block = grouped.get(owner);
      if (!block) {
        if (grouped.size + labelBlocks.length >= blockLimit) {
          omittedChars += text.length; reasons.add('block_limit'); continue;
        }
        const isHeading = owner.matches(headingSelector);
        const enclosingLink = owner.closest('a[href]');
        const href = isHeading ? headingURL(owner) : enclosingLink ? clean(enclosingLink.href) : null;
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
        if (validHref && !hrefRepresented && capturedChars + validHref.length + text.length <= 24000) {
          block.href = validHref; capturedChars += validHref.length;
        } else if (href && !hrefRepresented) reasons.add('link_evidence_limit');
        grouped.set(owner, block);
      }
      // Normalize after the whole block, preserving text-node boundaries around links.
      const rawText = node.textContent;
      const available = Math.max(0, Math.min(6000 - block.text.length, 24000 - capturedChars));
      const appended = rawText.slice(0, available);
      block.text += appended; capturedChars += appended.length;
      if (appended.length < rawText.length) {
        omittedChars += rawText.length - appended.length;
        reasons.add(block.text.length >= 6000 ? 'cell_text_limit' : 'text_budget');
      }
    }
    if (visited > 50000) break;
  }
  preserveLinkLabels();
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
  if (blocks.reduce((n, block) => n + block.text.length + (block.href?.length || 0), 0) < 80)
    throw new Error('Too little visible content. Open the content or listings first.');
  const frames = document.querySelectorAll('iframe').length;
  return {
    version: 1, url: clean(location.href), captured_at: new Date().toISOString(),
    truncated: reasons.size > 0, blocks,
    coverage: {
      collector_version: 'source-inventory-v1', scope: 'loaded_dom',
      eligible_text_chars: Math.min(eligibleChars, 10000000),
      captured_text_chars: blocks.reduce((n, block) => n + block.text.length, 0),
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
