"use strict";
// Packaged existing browser observations, not remotely downloaded/evaluated code.
// Source of truth: browser_agent.py COUNTER_OBSERVATION + AGENT_OBSERVATION.
// Keep in sync when those observation expressions change; no model calls here.
globalThis.agenticInspectCounter = e => {
  const clean=s=>(s||'').replace(/\s+/g,' ').trim();
  const visible=n=>!!n.getClientRects().length &&
    getComputedStyle(n).visibility!=='hidden' &&
    !n.closest('[inert]');
  const accessibleName=n=>clean(n.getAttribute('aria-label')||
    (n.getAttribute('aria-labelledby')||'').split(/\s+/).map(id=>
      (n.getRootNode().getElementById?.(id)||document.getElementById(id))?.textContent||'')
      .join(' ')||(n.labels&&[...n.labels].map(label=>label.textContent).join(' '))||
      n.getAttribute('placeholder')||n.getAttribute('title')||n.name);
  const numeric=n=>{
    const method=n.matches('input[type="number"]')?'number_input':
      n.matches('[role="spinbutton"]')?'spinbutton':'';
    if(!method || !visible(n)) return null;
    const value=clean(method==='number_input'?n.value:n.getAttribute('aria-valuenow'));
    const label=accessibleName(n);
    if(!/^\d{1,3}$/.test(value) || !label || !/\p{L}/u.test(label)) return null;
    if(/password|passcode|verification|\botp\b|credit card|security token/i.test(label))
      return null;
    const bound=name=>{
      const raw=n.getAttribute(method==='number_input'?name:'aria-value'+name);
      return raw!==null&&raw!==''&&Number.isFinite(Number(raw))?Number(raw):null;
    };
    return {label,value:Number(value),direction:'both',method,
      minimum:bound('min'),maximum:bound('max'),
      owner_readonly:method==='spinbutton'&&n.getAttribute('aria-readonly')==='true',
      evidence:label+' '+value};
  };
  const ownNumeric=numeric(e); if(ownNumeric) return ownNumeric;
  const actuator=n=>n.matches('button') ? !n.querySelector('button') :
    n.matches('[role="button"]') && !n.parentElement?.closest('button') &&
    !n.querySelector('button,[role="button"]');
  if(!actuator(e)) return null;
  const direction=button=>{
    const localReferences=[...button.querySelectorAll('svg use')].flatMap(use=>{
      const href=use.getAttribute('href')||use.getAttribute('xlink:href')||'';
      // Read only an explicit same-document icon reference; never fetch a sprite.
      if(!href.startsWith('#')) return [];
      const node=use.getRootNode().getElementById?.(href.slice(1))||
        document.getElementById(href.slice(1));
      return [href.slice(1),node?.getAttribute('aria-label')||'',
        ...[...(node?.querySelectorAll('title')||[])].map(n=>n.textContent)];
    });
    const text=clean([button.getAttribute('aria-label'),button.getAttribute('title'),
      button.getAttribute('data-testid'),button.innerText,
      ...[...button.querySelectorAll('svg title')].map(n=>n.textContent),
      ...localReferences].join(' '));
    const plus=/\b(increase|increment|plus)\b/i.test(text) || /^[+ï¼‹]$/.test(text);
    const minus=/\b(decrease|decrement|minus)\b/i.test(text) || /^[-âˆ’â€“]$/.test(text);
    if(plus!==minus) return plus?'increase':'decrease';
    // Recognize a rendered cross/bar rather than guessing from button order.
    // Unknown/compound artwork remains unknown; it is never assigned a direction.
    const svg=button.querySelector('svg'); if(!svg) return '';
    const shapes=[...svg.querySelectorAll('path,rect,line,polyline,polygon')]
      .filter(n=>!n.closest('defs,clipPath,mask') && !!n.getClientRects().length &&
        getComputedStyle(n).visibility!=='hidden');
    if(!shapes.length) return '';
    const boxes=shapes.map(n=>n.getBoundingClientRect());
    const left=Math.min(...boxes.map(b=>b.left)),top=Math.min(...boxes.map(b=>b.top));
    const width=Math.max(...boxes.map(b=>b.right))-left;
    const height=Math.max(...boxes.map(b=>b.bottom))-top;
    if(width<=0) return '';
    const hit=(x,y)=>shapes.some(n=>{
      try {
        const matrix=n.getScreenCTM(); if(!matrix) return false;
        const point=new DOMPoint(left+x*width,top+y*height).matrixTransform(matrix.inverse());
        const style=getComputedStyle(n);
        return (style.fill!=='none' && n.isPointInFill(point)) ||
          (style.stroke!=='none' && n.isPointInStroke(point));
      } catch {return false;}
    });
    if(width>3*Math.max(height,1) && [0.2,0.5,0.8].every(x=>hit(x,0.5))) return 'decrease';
    if(height>0 && width/height>0.7 && width/height<1.4 &&
      [0.2,0.5,0.8].every(v=>hit(v,0.5)&&hit(0.5,v)) &&
      [[0.2,0.2],[0.2,0.8],[0.8,0.2],[0.8,0.8]].every(([x,y])=>!hit(x,y)))
      return 'increase';
    return '';
  };
  // The focusable spinbutton may own visually rendered +/- buttons that are
  // hidden only from accessibility APIs, not from the user or the browser.
  const owner=e.closest('[role="spinbutton"]');
  const ownedNumeric=owner&&numeric(owner);
  if(ownedNumeric) return {...ownedNumeric,method:'button',direction:direction(e)||'unknown'};
  const namedQuantity=button=>{
    // An actuator's "by 1" describes its effect, never the current quantity.
    const match=accessibleName(button).match(
      /^(?:increase|decrease|increment|decrement)\s+(.+?)(?:\s+by\s+\d+)?[.!]?$/i);
    if(!match) return null;
    const label=clean(match[1].replace(/^(?:the\s+)?(?:number\s+of\s+)?/i,'')
      .replace(/\s+(?:count|quantity)$/i,''));
    if(!label || label.length>80 || !/\p{L}/u.test(label) || /\d/.test(label)) return null;
    return {label,key:label.toLocaleLowerCase()};
  };
  let leanQuantityRegion=null;
  for(let row=e.parentElement,depth=0;row && depth<7;row=row.parentElement,depth++) {
    if(row.matches('body,html,main')) break;
    const buttons=[...row.querySelectorAll('button,[role="button"]')]
      .filter(n=>visible(n)&&actuator(n));
    if(buttons.length!==2 || !buttons.includes(e)) continue;
    const numberFields=[...row.querySelectorAll('input[type="number"],[role="spinbutton"]')]
      .map(numeric).filter(Boolean);
    if(numberFields.length===1) return {...numberFields[0],method:'button',
      direction:direction(e)||'unknown'};
    const directions=buttons.map(direction),named=buttons.map(namedQuantity);
    if(named.every(Boolean) && named[0].key!==named[1].key) return null;
    const namedPair=named.every(Boolean) && named[0].key===named[1].key &&
      directions.includes('increase') && directions.includes('decrease');
    const walker=document.createTreeWalker(row,NodeFilter.SHOW_TEXT),parts=[],partNodes=[];
    let node;
    while((node=walker.nextNode())) {
      const p=node.parentElement;
      if(!p || !visible(p) || p.closest('svg,script,style') ||
        buttons.some(button=>button.contains(p))) continue;
      const text=clean(node.textContent); if(text) {parts.push(text);partNodes.push(node);}
    }
    const text=clean(parts.join(' '));
    if(text.length>180) continue;
    // Age/help text can contain numbers (e.g. "Ages 18 or above").
    // The rendered quantity is a standalone numeric text node, not that metadata.
    const follows=(first,second)=>!!(first.compareDocumentPosition(second) &
      Node.DOCUMENT_POSITION_FOLLOWING);
    const countParts=parts.map((value,index)=>({value,index}))
      .filter(item=>/^\d{1,3}$/.test(item.value) &&
        follows(buttons[0],partNodes[item.index]) && follows(partNodes[item.index],buttons[1]));
    const tokens=[...text.matchAll(/(?:^|\s)(\d{1,3})(?=\s|$)/g)];
    const allNumbers=[...text.matchAll(/\d+/g)];
    if(countParts.length>1) return null;
    // A semantically named pair may render its count before/after both buttons.
    // Prefer an isolated quantity over numbers embedded in age/help text. Never
    // use numbers from the actuator names, including their explicit click delta.
    const isolated=namedPair ? parts.map((value,index)=>({value,index}))
      .filter(item=>/^\d{1,3}$/.test(item.value)) : [];
    const noun=namedPair ? named[0].label.match(/\p{L}+/gu).join('\\s+').replace(/s$/i,'')+'s?' : '';
    const labelled=namedPair ? [
      '(?:^|\\s)'+noun+'(?:\\s+(?:count|quantity))?\\s*[:=]?\\s*(\\d{1,3})(?=\\s|$)',
      '(?:^|\\s)(\\d{1,3})\\s+'+noun+'(?=\\s|$)',
    ].flatMap(pattern=>[...text.matchAll(new RegExp(pattern,'ig'))]) : [];
    if(labelled.length>1 || countParts.length && labelled.length &&
      Number(countParts[0].value)!==Number(labelled[0][1])) return null;
    const count=countParts[0] || (!labelled.length && isolated.length===1 &&
      allNumbers.length===1 ? isolated[0] : null);
    if(!count && !labelled.length &&
      (tokens.length!==1 || namedPair && allNumbers.length!==1)) continue;
    if(leanQuantityRegion===null && count) {
      const otherParts=parts.filter((_,index)=>index!==count.index);
      leanQuantityRegion=otherParts.length<=1 && clean(otherParts.join(' ')).length<=40 &&
        !row.querySelector('a[href],[role="link"],img,picture,video,iframe,article,h1,h2,h3,h4');
    }
    const quantity=count ? Number(count.value) : Number(labelled[0]?.[1]||tokens[0][1]);
    let rowLabel=count ? clean(parts.filter((_,i)=>i!==count.index).join(' ')) :
      clean(text.replace(/(?:^|\s)\d{1,3}(?=\s|$)/,' '));
    if(namedPair) rowLabel=named[0].label;
    // Some steppers name their quantity using an external accessible label.
    // Read that declared relationship rather than relying on nearby page text.
    if(!rowLabel || !/\p{L}/u.test(rowLabel)) rowLabel=clean(
      row.getAttribute('aria-label') || (row.getAttribute('aria-labelledby')||'')
        .split(/\s+/).map(id=>document.getElementById(id)?.textContent||'').join(' '));
    if(!rowLabel || !/\p{L}/u.test(rowLabel)) continue;
    if(/password|passcode|verification|\botp\b|credit card|security token/i.test(rowLabel))
      continue;
    // A clear rendered quantity row can expose its buttons without asserting
    // what an unfamiliar icon does. Only an explicitly selected fresh button
    // can then be used; numeric read-back, not button order, verifies the effect.
    if(directions.filter(d=>d==='increase').length>1 ||
      directions.filter(d=>d==='decrease').length>1) continue;
    // A review count/rating between carousel buttons is not a quantity widget.
    // Unknown icons require a compact, isolated numeric region, not an arbitrary
    // integer found in surrounding listing/article content.
    if(directions.includes('') && !leanQuantityRegion) continue;
    return {label:rowLabel,value:quantity,
      direction:directions[buttons.indexOf(e)]||'unknown',method:'button',evidence:text};
  }
  return null;
};
globalThis.agenticObserve = focus => {
  const inspectCounter=globalThis.agenticInspectCounter;
  const clean=s=>(s||'').replace(/\s+/g,' ').trim();
  const roots=[document];
  for(let i=0;i<roots.length;i++) for(const node of roots[i].querySelectorAll('*'))
    if(node.shadowRoot) roots.push(node.shadowRoot);
  const query=selector=>roots.flatMap(root=>[...root.querySelectorAll(selector)]);
  query('[data-agentic-loop-id]').forEach(e=>e.removeAttribute('data-agentic-loop-id'));
  const visible=e=>!!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
  const sensitive=e=>e.matches('input[type="password"],input[type="email"],input[type="tel"],'+
    'input[autocomplete="username"],input[autocomplete="one-time-code"],input[autocomplete^="cc-"],'+
    'input[name*="password" i],input[name*="otp" i],input[name*="token" i],'+
    'input[name*="email" i],input[name="code" i]') ||
    /password|passcode|verification code|credit card|security token/i.test(
      (e.name||'')+' '+(e.getAttribute('aria-label')||'')+' '+(e.autocomplete||''));
  const label=e=>clean(e.getAttribute('aria-label')||
    (e.getAttribute('aria-labelledby')||'').split(/\s+/).map(id=>
      (e.getRootNode().getElementById?.(id)||document.getElementById(id))?.textContent||'')
      .join(' ')||
    (e.labels&&[...e.labels].map(n=>n.textContent).join(' '))||
    e.getAttribute('placeholder')||e.innerText||e.getAttribute('title')||e.name).slice(0,240);
  // Calendar choices and date-field openers can both name a full date. Keep
  // that distinction grounded in the actual control, shared with the executor.
  const inspectDate=globalThis.agenticInspectDate=e=>{
    const iso=(year,month,day)=>{
      const y=Number(year),m=Number(month),d=Number(day);
      if(y<1000||y>9999||m<1||m>12||d<1||d>31) return '';
      const value=new Date(Date.UTC(y,m-1,d));
      return value.getUTCFullYear()===y&&value.getUTCMonth()===m-1&&value.getUTCDate()===d?
        String(y)+'-'+String(m).padStart(2,'0')+'-'+String(d).padStart(2,'0'):'';
    };
    const parse=value=>{
      const text=clean(value).replace(/[.;:!?]\s*$/,'')
        .replace(/^(?:enter|choose|select|change|edit|open)\s+(?:the\s+)?(?:(?:check[ -]?in|check[ -]?out|arrival|departure|start|end)(?:\s+date)?|dates?)\s*[:.,;\u2013\u2014-]?\s*/i,'')
        .replace(/^(?:the\s+)?selected\s+date\s+is\s*[:.,;\u2013\u2014-]?\s*/i,'')
        .replace(/^(?:selected|chosen)\s+/i,'')
        .replace(/\s*[,;]?\s*(?:selected|chosen)$/i,'')
        .replace(/^(?:check[ -]?in|arrival|start(?:\s+date)?|range\s+start|check[ -]?out|departure|end(?:\s+date)?|range\s+end)(?:\s+date)?\s*[:,-]?\s*/i,'')
        .replace(/\s*[,;:-]?\s*(?:check[ -]?in|arrival|start\s+date|range\s+start|check[ -]?out|departure|end\s+date|range\s+end)$/i,'')
        .replace(/^(?:mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\s*,?\s*/i,'');
      let match=text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
      if(match) return iso(match[1],match[2],match[3]);
      const months='jan feb mar apr may jun jul aug sep oct nov dec'.split(' ');
      match=text.match(/^(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s*(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(\d{4})$/i);
      if(match) return iso(match[3],months.indexOf(match[1].slice(0,3).toLowerCase())+1,match[2]);
      match=text.match(/^(\d{1,2})(?:st|nd|rd|th)?\s*(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s*,?\s*(\d{4})$/i);
      return match?iso(match[3],months.indexOf(match[2].slice(0,3).toLowerCase())+1,match[1]):'';
    };
    const name=label(e),text=clean(e.innerText);
    const fullDate=n=>parse(n.getAttribute('data-date')||n.getAttribute('datetime'))||
      parse(label(n))||parse(n.innerText);
    const ownDate=fullDate(e),cell=e.closest('[role="gridcell"]');
    const cellDate=cell&&fullDate(cell)||'';
    const input=e.matches('input:not([type="checkbox"]):not([type="radio"]),textarea,select,[role="combobox"]')||e.isContentEditable;
    const dateWords=/\b(?:dates?|calendar|check[ -]?in|check[ -]?out|arrival|departure)\b/i;
    const opening=/^(?:enter|choose|select|change|open|edit)\s+(?:the\s+)?(?:(?:check[ -]?in|check[ -]?out|arrival|departure|start|end)\s+)?(?:dates?|calendar)\b/i.test(name);
    const popup=e.getAttribute('aria-haspopup'),expanded=e.hasAttribute('aria-expanded');
    const checkable=e.matches('input[type="checkbox"],input[type="radio"],[role="checkbox"],[role="radio"]');
    const opener=input&&(e.matches('input[type="date"],input[type="datetime-local"],input[type="month"],input[type="week"]')||dateWords.test(name))||
      !cell&&!checkable&&(opening||(popup&&popup!=='false'||expanded)&&(dateWords.test(name)||!!ownDate));
    if(opener) {
      const endpointName=name+' '+clean(e.name).slice(0,120)+' '+text.slice(0,240);
      const start=/\b(?:check[ -]?in|arrival|start\s+date|range\s+start)\b/i.test(endpointName);
      const end=/\b(?:check[ -]?out|departure|end\s+date|range\s+end)\b/i.test(endpointName);
      return {date_kind:'opener',date:ownDate,selected:'',
        date_endpoint:start!==end?(start?'check_in':'check_out'):'',owner:null};
    }
    const dayToken=/^\d{1,2}$/.test(name)||/^\d{1,2}$/.test(text);
    const dateAttribute=clean(e.getAttribute('data-date')||e.getAttribute('datetime'));
    const structuralDate=!!cell&&(dayToken||e===cell&&/\b\d{4}\b/.test(label(cell))||
      !!cellDate&&checkable);
    const choice=!input&&(!!ownDate||!!dateAttribute||structuralDate);
    if(!choice) return {date_kind:'',date:'',selected:'',date_endpoint:'',owner:null};
    const date=ownDate||cellDate;
    const owner=cell&&date&&cellDate===date?cell:null;
    const state=n=>{
      if(n.matches('input[type="checkbox"],input[type="radio"]')) return String(n.checked);
      const values=[n.getAttribute('aria-selected'),n.getAttribute('aria-checked'),
        n.getAttribute('data-state')].map(value=>(value||'').toLowerCase());
      if(values.some(value=>['false','unselected','unchecked','off'].includes(value))) return 'false';
      return values.some(value=>['true','selected','checked','on'].includes(value))?'true':'';
    };
    const declaredState=state(e)||(owner&&owner!==e?state(owner):'');
    const namedSelection=n=>parse(label(n))===date&&
      /^(?:selected|chosen)\s+|\s+(?:selected|chosen)$/i.test(label(n));
    const selectedLabel=declaredState!=='false'&&!!date&&
      !!(namedSelection(e)||owner&&namedSelection(owner));
    const selected=declaredState||(selectedLabel?'true':'');
    const endpointName=name+' '+(owner&&owner!==e?label(owner):'');
    const start=/\b(?:check[ -]?in|arrival|start\s+date|range\s+start)\b/i.test(endpointName);
    const end=/\b(?:check[ -]?out|departure|end\s+date|range\s+end)\b/i.test(endpointName);
    return {date_kind:'day_choice',date,selected,selected_label:selectedLabel,
      date_endpoint:start!==end?(start?'check_in':'check_out'):'',owner};
  };
  // A custom age combobox has no native .value. Observe only its declared
  // value, one explicitly owned selected option, or its compact rendered age.
  // Popup prose and an active/highlighted option never establish selection.
  const customAgeValue=globalThis.agenticInspectCustomAgeValue=e=>{
    if(['INPUT','TEXTAREA','SELECT'].includes(e.tagName)||
      e.getAttribute('role')!=='combobox'||
      !/\bages?\b|\bage\d+\b|\baged\b|\byears?\s+old\b|\bhow\s+old\b/i
        .test((e.name||'')+' '+label(e))) return null;
    const compactAge=/^(?:age\s*:?\s*)?\d{1,3}(?:\s*(?:years?(?:\s+old)?|yrs?))?$/i;
    const displayed=n=>{
      const walker=document.createTreeWalker(n,NodeFilter.SHOW_TEXT),parts=[];
      let node,length=0;
      while((node=walker.nextNode())&&length<=120) {
        const parent=node.parentElement;
        if(!parent||!visible(parent)) continue;
        let excluded=false;
        for(let p=parent;p&&(p===n||n.contains(p));p=p.parentElement)
          if(sensitive(p)||p.matches('input,textarea,select,script,style,noscript,'+
            '[contenteditable="true"],[inert],[aria-hidden="true"]')||
            p!==n&&p.matches('[role="option"],[role="listbox"]')) {excluded=true;break;}
        if(!excluded) {parts.push(node.textContent);length+=node.textContent.length;}
      }
      const text=clean(parts.join(' '));
      return compactAge.test(text)?text:'';
    };
    let value=clean(e.getAttribute('aria-valuetext')),
      source=value?'aria-valuetext':'';
    if(!value) {value=clean(e.getAttribute('aria-valuenow'));source=value?'aria-valuenow':'';}
    if(!value) {
      const ids=clean((e.getAttribute('aria-controls')||'')+' '+
        (e.getAttribute('aria-owns')||'')).split(' ').filter(Boolean);
      const scopes=[e,...ids.map(id=>e.getRootNode().getElementById?.(id)||
        document.getElementById(id)).filter(Boolean)];
      const selected=[...new Set(scopes.flatMap(scope=>[
        ...(scope.matches('[role="option"][aria-selected="true"]')?[scope]:[]),
        ...scope.querySelectorAll('[role="option"][aria-selected="true"]')]))]
        .filter(option=>!sensitive(option)&&!option.closest('[inert],[aria-hidden="true"]'));
      if(selected.length===1) {
        const named=clean(selected[0].getAttribute('aria-label'));
        value=compactAge.test(named)?named:displayed(selected[0]);
        source=value?'selected_option':'';
      }
    }
    if(!value) {value=displayed(e);source=value?'rendered_text':'';}
    return {value:value.slice(0,300),value_source:source,selected_label:value.slice(0,240)};
  };
  const validation=e=>{
    const required=!!e.required||e.getAttribute('aria-required')==='true';
    const option=e.tagName==='SELECT'&&!e.multiple?e.selectedOptions?.[0]:null;
    const optionLabel=clean(option?.textContent);
    const customAge=customAgeValues.get(e);
    const selectionPlaceholder=customAge?(!customAge.value||
      /^(?:please\s+)?(?:select|choose)\b|^(?:unknown|unset|not\s+(?:set|selected))$|\b(?:age|value)\s+(?:needed|required)\b/i
        .test(customAge.value)):e.tagName==='SELECT'&&!e.multiple&&(!option||
      option.disabled||option.hidden||
      (!clean(option.value)&&! /^(?:any|all|none|no preference)\b/i.test(optionLabel))||
      /^(?:please\s+)?(?:select|choose)(?:\s+(?:an?\s+)?(?:option|value|age|one))?[\s.…:]*$|\b(?:age|value)\s+(?:needed|required)\b/i.test(optionLabel));
    const nativeInvalid=e.willValidate===true&&e.validity?.valid===false;
    const valueMissing=e.validity?.valueMissing===true||(required&&customAge&&selectionPlaceholder)||(required&&
      e.matches('input:not([type="checkbox"]):not([type="radio"]),textarea,select')&&
      !clean(e.value));
    const errorIds=clean(e.getAttribute('aria-errormessage')).split(' ').filter(Boolean);
    const errorText=errorIds.map(id=>e.getRootNode().getElementById?.(id)||
      document.getElementById(id)).filter(n=>n&&visible(n)&&!n.closest('[inert]'))
      .map(n=>clean(n.textContent)).join(' ');
    const valueControl=e.matches('input,textarea,select,[role="combobox"],[role="spinbutton"],'+
      '[role="checkbox"],[role="radio"]')||e.isContentEditable||required||e.hasAttribute('aria-invalid');
    return {required,...(valueControl?{invalid:nativeInvalid||e.getAttribute('aria-invalid')==='true',
      value_missing:valueMissing,selection_placeholder:selectionPlaceholder,
      ...(e.tagName==='SELECT'?{selected_label:optionLabel.slice(0,240)}:{}),
      ...(customAge?{selected_label:customAge.selected_label}:{}),
      ...(nativeInvalid||errorText?{validation_message:clean([nativeInvalid?e.validationMessage:'',errorText]
        .join(' ')).slice(0,240)}:{})}:{})};
  };
  const candidates=query('input,textarea,select,button,a[href],'+
    '[role="button"],[role="option"],[role="combobox"],[role="gridcell"],[role="tab"],'+
    '[role="spinbutton"],[role="checkbox"],[role="radio"],[contenteditable="true"]')
    .filter(e=>visible(e)&&!sensitive(e)&&!e.closest('[inert]'));
  const counters=new Map(candidates.map(e=>[e,inspectCounter(e)]));
  // aria-hidden is an accessibility annotation, not CSS invisibility. Keep
  // physically rendered quantity actuators and stay summaries without exposing
  // unrelated accessibility-hidden controls/text or inert/credential controls.
  const dates=new Map(candidates.map(e=>[e,inspectDate(e)]));
  const staySummary=e=>dates.get(e).date_kind==='opener'||
    !counters.get(e)&&e.matches('button,[role="button"]')&&
    /\brooms?\b/i.test(label(e))&&/\b(?:adults?|guests?|travell?ers?)\b/i.test(label(e))&&
    (e.hasAttribute('aria-expanded')||e.hasAttribute('aria-haspopup')||
     /number of rooms|rooms\s*\/\s*guests|rooms.*selected.*guests/i.test(label(e)));
  const raw=candidates.filter(e=>!e.closest('[aria-hidden="true"]')||counters.get(e)||staySummary(e));
  const customAgeValues=new Map(raw.map(e=>[e,customAgeValue(e)]));
  const validations=new Map(raw.map(e=>[e,validation(e)]));
  // Give search-form widgets priority even when background links exhaust the
  // inventory. Unresolved value fields precede foreground widget choices.
  const formScopes=query('form,[role="search"]').filter(visible);
  const popupScopes=query('[role="dialog"],[role="listbox"],[role="grid"],[role="menu"]')
    .filter(visible);
  // Scope selected endpoints and confirmation controls to the actual rendered
  // calendar. A multi-month dialog is one widget; unrelated popups stay separate.
  const calendarScopes=popupScopes.filter(scope=>scope.matches('[role="dialog"],[role="grid"]')&&
    raw.some(e=>dates.get(e).date_kind==='day_choice'&&scope.contains(e)));
  // Some calendars omit dialog/grid roles. A compact date collection plus both
  // explicitly named month actuators establishes its actual common container.
  const calendarDays=raw.filter(e=>dates.get(e).date_kind==='day_choice');
  const monthDirection=e=>{
    if(!e.matches('button,[role="button"],a[href]')) return '';
    const text=clean([label(e),e.getAttribute('title'),e.getAttribute('data-testid'),
      ...[...e.querySelectorAll('svg title,svg [aria-label]')].map(n=>n.getAttribute('aria-label')||n.textContent),
      ...[...e.querySelectorAll('svg use')].map(n=>n.getAttribute('href')||n.getAttribute('xlink:href'))
    ].join(' ')).replace(/([a-z])([A-Z])/g,'$1 $2').replace(/[_-]/g,' ');
    if(/\b(?:years?|decades?|weeks?|today)\b/i.test(text)&&!/\bmonth\b/i.test(text)) return '';
    const next=/\b(?:next|forward|chevron right|arrow right)\b/i.test(text)||/^[›»→]$/.test(text);
    const previous=/\b(?:previous|prev|back|chevron left|arrow left)\b/i.test(text)||/^[‹«←]$/.test(text);
    if(next!==previous) return next?'next':'previous';
    // Only a single open, symmetric rendered chevron establishes icon direction.
    // DOM order and the position of an unlabelled button never do.
    try {
    const shapes=[...e.querySelectorAll('svg path,svg polyline')].filter(n=>
      !!n.getClientRects().length&&getComputedStyle(n).visibility!=='hidden');
    if(shapes.length!==1||/[zZ]/.test(shapes[0].getAttribute('d')||'')) return '';
    const shape=shapes[0],matrix=shape.getScreenCTM();
    if(!matrix||!shape.getTotalLength) return '';
    const length=shape.getTotalLength();
    if(!length) return '';
    const point=t=>{const p=shape.getPointAtLength(length*t);return new DOMPoint(p.x,p.y).matrixTransform(matrix);};
    const a=point(0),b=point(0.5),c=point(1),height=Math.abs(a.y-c.y);
    if(height<3||Math.abs(a.x-c.x)>height*0.15||Math.abs(b.y-(a.y+c.y)/2)>height*0.15||
      Math.abs(b.x-(a.x+c.x)/2)<height*0.25) return '';
    return b.x>(a.x+c.x)/2?'next':'previous';
    } catch {return '';}
  };
  const monthDirections=new Map(raw.map(e=>[e,monthDirection(e)]));
  const previousMonths=raw.filter(e=>monthDirections.get(e)==='previous');
  const nextMonths=raw.filter(e=>monthDirections.get(e)==='next');
  const rolelessCalendars=new Set(),calendarRegions=new Map();
  for(const day of calendarDays.filter(e=>dates.get(e).date)) {
    for(let scope=day.parentElement;scope;scope=scope.parentElement) {
      if(scope.matches('body,html,main,form,nav,header,footer,aside')) break;
      let region=calendarRegions.get(scope);
      if(!region) {
        const days=calendarDays.filter(e=>scope.contains(e));
        const controlCount=raw.filter(e=>scope.contains(e)).length;
        region={oversized:days.length>180||controlCount>300,
          calendar:new Set(days.map(e=>dates.get(e).date).filter(Boolean)).size>=7&&
            previousMonths.some(e=>scope.contains(e))&&nextMonths.some(e=>scope.contains(e))};
        calendarRegions.set(scope,region);
      }
      if(region.oversized) break;
      if(region.calendar) {rolelessCalendars.add(scope);break;}
    }
  }
  for(const scope of rolelessCalendars) if(!calendarScopes.includes(scope)) calendarScopes.push(scope);
  const calendarScope=e=>{
    for(let scope=e;scope;scope=scope.parentElement)
      if(rolelessCalendars.has(scope)) return scope;
    const dialog=e.closest('[role="dialog"]');
    if(calendarScopes.includes(dialog)) return dialog;
    const grid=e.closest('[role="grid"]');
    if(calendarScopes.includes(grid)) return grid;
    if(dates.get(e)?.date_kind==='opener') {
      const ids=clean((e.getAttribute('aria-controls')||'')+' '+(e.getAttribute('aria-owns')||''))
        .split(' ').filter(Boolean);
      const scopes=ids.map(id=>e.getRootNode().getElementById?.(id)||document.getElementById(id))
        .filter(scope=>calendarScopes.includes(scope));
      if(scopes.length===1) return scopes[0];
    }
    return null;
  };
  const counterButtons=raw.filter(e=>counters.get(e)),counterGroups=[];
  for(const button of counterButtons) {
    for(let group=button.parentElement,depth=0;group && depth<8;group=group.parentElement,depth++) {
      if(group.matches('body,html,main')) break;
      if(counterButtons.filter(e=>group.contains(e)).length<4) continue;
      if(group.querySelectorAll('button,[role="button"]').length<=12 &&
        clean(group.innerText).length<1800) {counterGroups.push(group);break;}
    }
  }
  // Keep a few visible category entry points when result links exhaust the
  // inventory. These are observed labels, not inferred routes or click plans.
  const categoryNavigation=new Set(raw.filter(e=>
    e.matches('a[href],button,[role="button"],[role="tab"]') &&
    e.getAttribute('role')!=='option' &&
    /^(?:hotels?|stays|accommodations?|restaurants?|dining|things to do|attractions?|essentials|flights|shopping|news|sports|business|travel|technology|science)(?:\s+(?:in|near)\s+.{1,40})?$/i
      .test(label(e))).slice(0,8));
  const pagination=new Map();
  for(const e of focus==='collection'?raw:[]) {
    if(!e.matches('a[href],button,[role="button"]')) continue;
    if(e.closest('[role="dialog"],[role="menu"],[role="listbox"]')) continue;
    const text=label(e),nav=e.closest('nav,[role="navigation"]');
    const numbered=nav&&[...nav.querySelectorAll('a,button')].filter(n=>/^\d{1,3}$/.test(label(n))).length>=2;
    if(e.matches('a[rel~="next"]')||/^(?:next page|next results|go to (?:the )?next page)$/i.test(text)||
      /^next$/i.test(text)&&numbered) pagination.set(e,'next');
    else if(/^(?:load|show|see) more (?:results|hotels|properties|listings|articles)$/i.test(text)&&
      e.closest('main,[role="main"]')&&!e.closest('article,[itemtype*="Product"]')) pagination.set(e,'more');
  }
  // Keep current stay values beside a large calendar; day cells alone must
  // not consume the entire inventory and hide the summaries needed to commit.
  const stayAnchors=new Set([
    ...raw.filter(e=>dates.get(e).date_kind==='opener').slice(0,4),
    ...raw.filter(e=>e.matches('input,textarea,select')&&!sensitive(e)&&
      /destination|location|\bcity\b|where .*going|^(?:search|query)\b/i.test(label(e))).slice(0,2),
    ...raw.filter(e=>staySummary(e)&&dates.get(e).date_kind!=='opener').slice(0,2)
  ]);
  // Foreground popups/calendar/options take priority over category navigation.
  const priority=e=>validations.get(e).invalid||validations.get(e).value_missing||
    validations.get(e).selection_placeholder ? -1 :
    stayAnchors.has(e) ? -0.5 :
    focus==='collection' && pagination.has(e) ? -0.4 :
    monthDirections.get(e)&&calendarScope(e) ? -0.3 :
    dates.get(e).date_kind==='day_choice'&&dates.get(e).selected==='true' ? -0.25 :
    dates.get(e).date_kind==='day_choice' ? -0.1 :
    popupScopes.some(scope=>scope.contains(e)) ? 0 :
    counters.get(e)||counterGroups.some(group=>group.contains(e)) ? 0 :
    e.getAttribute('role')==='option' ? 1 :
    categoryNavigation.has(e) ? 1.5 :
    formScopes.some(scope=>scope.contains(e)) ? (focus==='form'&&!e.matches('a[href]')?0:2) :
    e.matches('input,select,textarea') ? 3 : 4;
  raw.sort((a,b)=>priority(a)-priority(b));
   const elements=raw.filter(e=>
    (e.matches('[role="spinbutton"],input[type="number"]')||
      !raw.some(child=>child!==e&&e.contains(child)&&counters.get(child))) &&
    (counters.get(e)||!raw.some(other=>other!==e&&other.contains(e)&&
       other.matches('button,a[href],[role="button"],[role="option"]')))).slice(0,140);
   elements.forEach((e,i)=>e.setAttribute('data-agentic-loop-id',String(i)));
   const editable=e=>e.matches('input,textarea')&&!sensitive(e);
   const comboOwner=e=>{
     const owner=e.closest('[role="combobox"]');
     return owner && [...owner.querySelectorAll('input,textarea')]
       .filter(n=>visible(n)&&editable(n)).length===1?owner:e;
   };
   const controlled=e=>clean((e.getAttribute('aria-controls')||'')+' '+
     (e.getAttribute('aria-owns')||'')+' '+(comboOwner(e).getAttribute('aria-controls')||'')+' '+
     (comboOwner(e).getAttribute('aria-owns')||'')).split(' ').filter(Boolean).map(id=>
       e.getRootNode().getElementById?.(id)||document.getElementById(id)).filter(Boolean);
   const combos=elements.filter(e=>editable(e)&&(
     e.closest('[role="combobox"]')||/^(list|both)$/.test(
       e.getAttribute('aria-autocomplete')||comboOwner(e).getAttribute('aria-autocomplete')||'')||
     (e.getAttribute('aria-haspopup')||comboOwner(e).getAttribute('aria-haspopup'))==='listbox'||
     controlled(e).some(n=>n.matches('[role="listbox"]')||n.querySelector('[role="option"]'))));
   const listboxes=popupScopes.filter(e=>e.matches('[role="listbox"]'));
   const optionOwners=new Map(),optionsFor=new Map(),optionAssociations=new Map();
   for(const field of combos) {
     let boxes=controlled(field);
     let association=boxes.length?'explicit_aria':'unresolved';
     if(!boxes.length && combos.length===1 && listboxes.length===1 &&
       (field.getAttribute('aria-expanded')||comboOwner(field).getAttribute('aria-expanded'))==='true') {
       boxes=listboxes;
       association='single_expanded_listbox';
     }
     const options=elements.filter(e=>e!==field&&boxes.some(box=>box.contains(e))&&
       e.matches('[role="option"],button,a[href],[role="button"]'));
     optionsFor.set(field,options);
     optionAssociations.set(field,association);
     for(const option of options) optionOwners.set(option,field);
   }
   // Value-free diagnostics distinguish missing/hidden choices from an input
   // event or association failure. They stay out of compact model context.
   let activeElement=document.activeElement;
   while(activeElement?.shadowRoot?.activeElement)
     activeElement=activeElement.shadowRoot.activeElement;
   const autocompleteDiagnostics={field_count:combos.length,
     visible_listbox_count:listboxes.length,
     visible_option_count:raw.filter(e=>e.getAttribute('role')==='option').length,
     owned_option_count:optionOwners.size,
     fields:combos.slice(0,8).map(field=>{
       const declared=controlled(field);
       const expanded=field.getAttribute('aria-expanded')||
         comboOwner(field).getAttribute('aria-expanded')||'';
       return {control_id:field.getAttribute('data-agentic-loop-id'),
         focused:field===activeElement,
         expanded:['true','false'].includes(expanded)?expanded:'',
         controlled_popup_count:declared.length,
         visible_controlled_popup_count:declared.filter(visible).length,
         owned_option_count:(optionsFor.get(field)||[]).length,
         association:optionAssociations.get(field)};
     })};
   const optionPrimary=e=>{
     // Accessible names often concatenate a primary label and its subtitle.
     // A rendered row boundary is useful; an arbitrary inline span/bold split
     // is not. Keep an unstructured name whole rather than inventing a city.
     const lines=(e.innerText||'').split(/\n/).map(clean).filter(Boolean);
     return clean((lines.length>1?lines[0]:'')||e.getAttribute('aria-label')||e.innerText||label(e));
   };
   // Association comes from the actual native form, not a label/model guess.
   const nativeForm=e=>e.form||e.closest('form');
   const nativeForms=query('form');
   const controls=elements.map((e,i)=>{
      const box=e.closest('label,[role="group"],li,[data-testid],fieldset');
      const dateInfo=dates.get(e),dateScope=calendarScope(e);
      const selected=dateInfo.date_kind==='day_choice'?dateInfo.selected:
        e.getAttribute('aria-selected')||e.getAttribute('aria-checked')||
        e.getAttribute('data-state')||(e.matches('input[type="checkbox"],input[type="radio"]')?
          String(e.checked):'');
      const counter=counters.get(e);
      const rect=e.getBoundingClientRect();
      return {id:String(i),tag:e.tagName,role:e.getAttribute('role')||'',type:e.type||'',
        form_scope:nativeForm(e)?String(nativeForms.indexOf(nativeForm(e))):null,
        widget_scope:counterGroups.some(group=>group.contains(e))?'counter':
          popupScopes.some(scope=>scope.contains(e)&&
            scope.matches('[role="listbox"],[role="grid"],[role="menu"]'))?'choice':'',
        submits_form:!!e.form && ['BUTTON','INPUT'].includes(e.tagName) &&
          ['submit','image'].includes(e.type),
        name:e.name||'',label:label(e)||(counter?counter.direction+' '+counter.label:''),
        text:clean(e.innerText).slice(0,400),counter,
        numeric_probe:{role:e.getAttribute('role')||'',type:e.type||'',
          aria_value:e.getAttribute('aria-valuenow')||'',
          child_buttons:[...e.querySelectorAll('button,[role="button"]')].filter(visible).length,
          accessibility_hidden_buttons:[...e.querySelectorAll('button,[role="button"]')]
            .filter(n=>visible(n)&&n.closest('[aria-hidden="true"]')).length},
        context:clean([counter?.evidence,box?.innerText,e.parentElement?.innerText,
          e.parentElement?.parentElement?.innerText].join(' ')).slice(0,500),
        ...(customAgeValues.get(e)?{value_source:customAgeValues.get(e).value_source}:{}),
        value:customAgeValues.get(e)?customAgeValues.get(e).value:
          ['INPUT','TEXTAREA','SELECT'].includes(e.tagName)?(e.value||'').slice(0,300):
          e.isContentEditable?clean(e.innerText).slice(0,300):e.getAttribute('aria-valuenow')||'',
         selected,expanded:e.getAttribute('aria-expanded')||
           (editable(e)?comboOwner(e).getAttribute('aria-expanded'):'')||'',
         haspopup:e.getAttribute('aria-haspopup')||
           (editable(e)?comboOwner(e).getAttribute('aria-haspopup'):'')||'',
         ...(combos.includes(e)?{selection_required:true,
           option_ids:(optionsFor.get(e)||[]).map(n=>n.getAttribute('data-agentic-loop-id'))}:{}),
         ...(e.tagName==='SELECT'&&validations.get(e).selection_placeholder?{selection_required:true}:{}),
         ...(optionOwners.has(e)?{option_primary:optionPrimary(e)}:{}),
        editable:!!e.isContentEditable,...validations.get(e),
        rect:{x:Math.round(rect.x),y:Math.round(rect.y),width:Math.round(rect.width),height:Math.round(rect.height)},
        href:e.tagName==='A'?e.href:'',enabled:!e.disabled&&
          e.getAttribute('aria-disabled')!=='true',readonly:!!e.readOnly,
        options:e.tagName==='SELECT'?[...e.options].slice(0,50).map(o=>({value:o.value,
          label:clean(o.textContent),disabled:o.disabled||o.closest('optgroup')?.disabled===true,
          selected:o.selected,hidden:o.hidden})):[],
        ...(focus==='collection'&&pagination.has(e)?{pagination:pagination.get(e)}:{}),
        date_kind:dateInfo.date_kind,date:dateInfo.date,
        ...(dateInfo.date_endpoint?{date_endpoint:dateInfo.date_endpoint}:{}),
        ...(dateScope?{date_widget_id:'calendar:'+calendarScopes.indexOf(dateScope)}:{}),
        ...(dateScope&&monthDirections.get(e)?{date_navigation:monthDirections.get(e)}:{}),
        date_owner_id:elements.includes(dateInfo.owner)?
          dateInfo.owner.getAttribute('data-agentic-loop-id'):null};
    });
  const unresolved=controls.filter(e=>e.enabled&&(e.invalid||e.value_missing||e.selection_placeholder));
  const validationAlerts=query('[role="alert"],[aria-live="assertive"]')
    .filter(e=>visible(e)&&!e.closest('[inert],[aria-hidden="true"]')&&
      (nativeForm(e)||popupScopes.some(scope=>scope.contains(e))||counterGroups.some(scope=>scope.contains(e))))
    .slice(0,4).map(e=>({text:clean(e.innerText).slice(0,240),
      form_scope:nativeForm(e)?String(nativeForms.indexOf(nativeForm(e))):null,
      control_ids:elements.filter(field=>e.id&&
        clean(field.getAttribute('aria-errormessage')).split(' ').includes(e.id))
        .map(field=>field.getAttribute('data-agentic-loop-id'))})).filter(e=>e.text);
  const formValidation={unresolved_count:unresolved.length,fields:unresolved.slice(0,12)
    .map(e=>({control_id:e.id,label:e.label,form_scope:e.form_scope,required:e.required,
      invalid:e.invalid,value_missing:e.value_missing,selection_placeholder:e.selection_placeholder,
      validation_message:e.validation_message})),alerts:validationAlerts};
  const root=document.querySelector('main,[role="main"]')||document.body;
  if(!root) throw new Error('AGENT_DOM_NOT_READY');
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT),chunks=[];
  let node,length=0;
  while((node=walker.nextNode()) && length<12000) {
    const p=node.parentElement;
    if(!p||!visible(p)||p.closest('script,style,noscript,input,textarea,select,'+
      '[contenteditable="true"],[inert],[aria-hidden="true"]')) continue;
    const text=clean(node.textContent); if(text){chunks.push(text);length+=text.length;}
  }
  // Readiness hints only: these do not verify availability, price or coverage.
  const excluded='form,nav,header,footer,aside,[role="dialog"],[inert]';
  const recordMarkers='[data-testid*="card" i],[data-test-target*="card" i],[data-automation*="card" i],'+
    '[data-testid*="hotel-listing" i],[data-test-target*="hotel-listing" i],[data-automation*="hotel-listing" i],'+
    '[data-testid*="hotel-list-item" i],[data-test-target*="hotel-list-item" i],[data-automation*="hotel-list-item" i]';
  const records=[...root.querySelectorAll('article,li,[role="listitem"],[itemscope],'+recordMarkers)].filter(e=>visible(e)&&!e.closest(excluded)&&
      e.querySelector('a[href]')&&clean(e.innerText).length>=40);
  const resultText=chunks.join(' ');
  const priceContexts=[];
  for(const e of records.filter(e=>!records.some(n=>n!==e&&e.contains(n)))) {
    const text=clean(e.innerText);
    const matches=[...text.matchAll(/\b(?:price\s+from|starting\s+(?:at|from)|\d{1,3}\s+nights?|\d{1,3}\s+adults?|\d{1,3}\s+rooms?)\b/gi)];
    if(matches.length) {
      const first=matches[0].index,last=matches[matches.length-1].index;
      priceContexts.push(text.slice(Math.max(0,first-25),Math.min(text.length,last+120)).slice(0,500));
    }
    if(priceContexts.length>=12) break;
  }
  const emptyResults=new RegExp('\\b(?:no search results|no (?:properties|hotels|results|stays) '+
    '(?:found|available|match)|we (?:couldn.t|could not) find any '+
    '(?:properties|hotels|results))\\b','i');
  // Fresh page headings can establish the returned destination when a SPA no
  // longer renders its destination input. Card headlines and form echoes cannot.
  const resultHeadings=[...root.querySelectorAll('h1,h2,[role="heading"]')]
    .filter(e=>visible(e)&&!e.closest(excluded+', [aria-hidden="true"]')&&
      !e.closest('article,li,[role="listitem"],'+recordMarkers+','+
        '[itemtype$="/Hotel"],[itemtype$="/Product"],[itemtype$="/Article"]'))
    .map(e=>({text:clean(e.innerText),level:Number(e.getAttribute('aria-level')||
      (/^H[12]$/.test(e.tagName)?e.tagName.slice(1):0))}))
    .filter(e=>[1,2].includes(e.level)&&e.text.length>0&&e.text.length<=240).slice(0,8);
  const recordLeaves=records.filter(e=>!records.some(n=>n!==e&&e.contains(n)));
  // A bounded content-change hint for SPA refreshes, never price/availability proof.
  // Form fields and page chrome are excluded; only actual rendered record text
  // and link paths contribute. The signature stays out of model context.
  let recordHash=2166136261;
  for(const record of recordLeaves.slice(0,8)) {
    const paths=[...record.querySelectorAll('a[href]')].slice(0,2).map(link=>{
      try {return new URL(link.href,location.href).pathname;} catch (_) {return '';}
    }).join('|');
    const text=clean(record.innerText).slice(0,800)+'|'+paths;
    for(let i=0;i<text.length;i++) recordHash=Math.imul(recordHash^text.charCodeAt(i),16777619)>>>0;
  }
  const resultSignature=recordLeaves.length ?
    recordHash.toString(16).padStart(8,'0') : emptyResults.test(resultText)?'empty':null;
  const identities=(focus==='collection'?recordLeaves:[]).map(record=>{
    const heading=record.querySelector('h1,h2,h3,[role="heading"]');
    const link=heading?.closest('a[href]')||heading?.querySelector('a[href]')||record.querySelector('a[href]');
    let path='';try{path=link?new URL(link.href).pathname:'';}catch{}
    return path+'|'+clean(heading?.innerText||link?.innerText).replace(/^\d+[.)]\s*/,'');
  }).sort();
  let identityHash=2166136261;
  for(const text of identities) for(let i=0;i<text.length;i++) identityHash=Math.imul(identityHash^text.charCodeAt(i),16777619)>>>0;
  const results={record_count:recordLeaves.length,result_signature:resultSignature,
    ...(focus==='collection'?{record_set_signature:recordLeaves.length?identityHash.toString(16).padStart(8,'0'):emptyResults.test(resultText)?'empty':null}:{}),
    busy:[...root.querySelectorAll('[aria-busy="true"],[role="progressbar"],[role="status"]')]
      .some(e=>visible(e)&&!e.closest(excluded)&&
        (e.getAttribute('aria-busy')==='true'||e.getAttribute('role')==='progressbar'||
          /\bloading\b/i.test(clean(e.innerText)+' '+label(e)))),
    no_results:emptyResults.test(resultText),price_contexts:priceContexts,headings:resultHeadings};
  return {title:document.title,text:chunks.join(' ').slice(0,12000),controls,
    autocomplete_diagnostics:autocompleteDiagnostics,
    form_validation:formValidation,
    results,
    focus,widgets:popupScopes.slice(0,8).map(e=>({role:e.getAttribute('role'),label:label(e),
      text:clean(e.innerText).slice(0,800)})),
    controls_truncated:raw.length>140,visible_control_count:raw.length,
    viewport:{width:innerWidth,height:innerHeight,scroll_y:scrollY,
      document_height:document.documentElement.scrollHeight,
      at_page_end:Math.ceil(scrollY+innerHeight)>=document.documentElement.scrollHeight-4},
    password_or_code_visible:query('input').some(e=>visible(e)&&
      (e.type==='password'||e.autocomplete==='one-time-code'||/otp|verification|^code$/i.test(e.name)))};
};

