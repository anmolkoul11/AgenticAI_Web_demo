"""Shared DOM evidence for hotel destination inputs, without reading input values."""

HOTEL_DESTINATION_FACTS = r"""el => {
  const clean = value => (value || '').replace(/\s+/g,' ').trim();
  const label = node => {
    const by=(node.getAttribute('aria-labelledby')||'').split(/\s+/)
      .map(id=>node.getRootNode().getElementById?.(id)?.textContent||'').join(' ');
    return clean(node.getAttribute('aria-label') || by || node.getAttribute('placeholder') ||
      (node.labels && [...node.labels].map(x=>x.textContent).join(' ')) ||
      node.getAttribute('title') || node.innerText || node.getAttribute('name'));
  };
  const visible = node => !!node.getClientRects().length &&
    getComputedStyle(node).visibility!=='hidden' && !node.closest('[aria-hidden="true"],[inert]');
  const type=(el.type||'').toLowerCase(), name=el.getAttribute('name')||'';
  const textInput=el.tagName==='INPUT' && ['text','search'].includes(type);
  const inputLabel=label(el), testid=el.getAttribute('data-testid') ||
    el.closest('[data-testid]')?.getAttribute('data-testid') || '';
  const credential=/password|passcode|email|phone|card|payment|account|login|sign.?in|user.?name/i
    .test(`${inputLabel} ${name} ${el.getAttribute('autocomplete')||''}`);
  if(!textInput || credential) return {recognized:false, form:null, eligible:false,
    structured:false, canonical:false, natural:false, reason:'not_destination_input'};
  const natural=/own words|natural language|describe your/i.test(inputLabel);
  const canonical=/^(ss|destination|destination_name|city|city_name|location)$/i.test(name) ||
    /destination[-_](?:input|search|field|container)|searchbox[-_]destination/i.test(testid);
  const destination=/destination|where.*going|where.*stay|location|\bcity\b/i.test(inputLabel);
  const peers = box => [...box.querySelectorAll('input,button,[role="button"]')];
  const hasDate = nodes => nodes.some(n=>
    /check.?in|check.?out|arrival|departure|select dates|calendar/i
      .test(`${label(n)} ${n.name||''}`)
    && (visible(n) || n.tagName==='INPUT' && n.type==='hidden'));
  const hasGuests = nodes => nodes.some(n=>
    /guests|adults|rooms|travelers|travellers|group_adults|no_rooms/i
      .test(`${label(n)} ${n.name||''}`) && visible(n));
  const hasSearch = nodes => nodes.some(n=>visible(n) &&
    (n.tagName==='BUTTON'||n.getAttribute('role')==='button'||n.type==='submit') &&
    /^(search|find hotels|show results|see results)$/i.test(label(n)));
  let form=el.closest('form,[role="search"]');
  if(!form) for(let box=el.parentElement,depth=0;box&&depth<8;box=box.parentElement,depth++) {
    if(['BODY','HTML'].includes(box.tagName)) break;
    const nodes=peers(box);
    if(hasDate(nodes) && (hasSearch(nodes)||hasGuests(nodes))) { form=box;break; }
  }
  const nodes=form?peers(form):[];
  const structured=hasDate(nodes) && (hasSearch(nodes)||hasGuests(nodes));
  const textFields=nodes.filter(n=>n.tagName==='INPUT' && visible(n) &&
    ['text','search'].includes(n.type) && !n.disabled && !n.readOnly &&
    !/password|passcode|email|phone|card|payment|account|login|sign.?in|user.?name/i
      .test(`${label(n)} ${n.name} ${n.autocomplete}`));
  const eligible=visible(el) && !el.disabled && !el.readOnly &&
    el.getAttribute('aria-disabled')!=='true';
  const recognized=eligible && ((!natural && destination) ||
    canonical && structured || !natural && structured && textFields.length===1 &&
      !/query|keyword/i.test(inputLabel));
  return {recognized,form,eligible,structured,canonical,natural,
    reason:!eligible?'disabled_or_readonly':recognized?'recognized':
      natural?'natural_language_without_destination_context':'unrecognized_metadata'};
}"""
