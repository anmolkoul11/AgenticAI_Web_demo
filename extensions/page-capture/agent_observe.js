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
    if(countParts.length>1 || (!countParts.length && tokens.length!==1)) continue;
    const count=countParts[0];
    if(leanQuantityRegion===null && count) {
      const otherParts=parts.filter((_,index)=>index!==count.index);
      leanQuantityRegion=otherParts.length<=1 && clean(otherParts.join(' ')).length<=40 &&
        !row.querySelector('a[href],[role="link"],img,picture,video,iframe,article,h1,h2,h3,h4');
    }
    const quantity=count ? Number(count.value) : Number(tokens[0][1]);
    let rowLabel=count ? clean(parts.filter((_,i)=>i!==count.index).join(' ')) :
      clean(text.replace(/(?:^|\s)\d{1,3}(?=\s|$)/,' '));
    // Some steppers name their quantity using an external accessible label.
    // Read that declared relationship rather than relying on nearby page text.
    if(!rowLabel || !/\p{L}/u.test(rowLabel)) rowLabel=clean(
      row.getAttribute('aria-label') || (row.getAttribute('aria-labelledby')||'')
        .split(/\s+/).map(id=>document.getElementById(id)?.textContent||'').join(' '));
    if(!rowLabel || !/\p{L}/u.test(rowLabel)) continue;
    if(/password|passcode|verification|\botp\b|credit card|security token/i.test(rowLabel))
      continue;
    const directions=buttons.map(direction);
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
  const candidates=query('input,textarea,select,button,a[href],'+
    '[role="button"],[role="option"],[role="combobox"],[role="gridcell"],'+
    '[role="spinbutton"],[role="checkbox"],[role="radio"],[contenteditable="true"]')
    .filter(e=>visible(e)&&!sensitive(e)&&!e.closest('[inert]'));
  const counters=new Map(candidates.map(e=>[e,inspectCounter(e)]));
  // aria-hidden is an accessibility annotation, not CSS invisibility. Keep
  // physically rendered, recognized quantity actuators without exposing other
  // accessibility-hidden controls/text or inert/credential controls.
  const raw=candidates.filter(e=>!e.closest('[aria-hidden="true"]')||counters.get(e));
  // Give search-form widgets priority even when background links exhaust the
  // inventory. An open calendar/counter popup still has the highest priority.
  const formScopes=query('form,[role="search"]').filter(visible);
  const popupScopes=query('[role="dialog"],[role="listbox"],[role="grid"],[role="menu"]')
    .filter(visible);
  const counterButtons=raw.filter(e=>counters.get(e)),counterGroups=[];
  for(const button of counterButtons) {
    for(let group=button.parentElement,depth=0;group && depth<8;group=group.parentElement,depth++) {
      if(group.matches('body,html,main')) break;
      if(counterButtons.filter(e=>group.contains(e)).length<4) continue;
      if(group.querySelectorAll('button,[role="button"]').length<=12 &&
        clean(group.innerText).length<1800) {counterGroups.push(group);break;}
    }
  }
  // Foreground popups/calendar/options take priority over background navigation.
  const priority=e=>popupScopes.some(scope=>scope.contains(e)) ? 0 :
    counters.get(e)||counterGroups.some(group=>group.contains(e)) ? 0 :
    e.getAttribute('role')==='option' ? 1 :
    formScopes.some(scope=>scope.contains(e)) ? (focus==='form'?0:2) :
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
      const selected=e.getAttribute('aria-selected')||e.getAttribute('aria-checked')||
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
        value:['INPUT','TEXTAREA','SELECT'].includes(e.tagName)?(e.value||'').slice(0,300):
          e.isContentEditable?clean(e.innerText).slice(0,300):e.getAttribute('aria-valuenow')||'',
         selected,expanded:e.getAttribute('aria-expanded')||
           (editable(e)?comboOwner(e).getAttribute('aria-expanded'):'')||'',
         haspopup:e.getAttribute('aria-haspopup')||
           (editable(e)?comboOwner(e).getAttribute('aria-haspopup'):'')||'',
         ...(combos.includes(e)?{selection_required:true,
           option_ids:(optionsFor.get(e)||[]).map(n=>n.getAttribute('data-agentic-loop-id'))}:{}),
         ...(optionOwners.has(e)?{option_primary:optionPrimary(e)}:{}),
        editable:!!e.isContentEditable,required:!!e.required||e.getAttribute('aria-required')==='true',
        rect:{x:Math.round(rect.x),y:Math.round(rect.y),width:Math.round(rect.width),height:Math.round(rect.height)},
        href:e.tagName==='A'?e.href:'',enabled:!e.disabled&&
          e.getAttribute('aria-disabled')!=='true',readonly:!!e.readOnly,
        options:e.tagName==='SELECT'?[...e.options].slice(0,50).map(o=>({value:o.value,
          label:clean(o.textContent),disabled:o.disabled})):[],
        date:e.getAttribute('data-date')||e.getAttribute('datetime')||'',
        date_owner_id:elements.includes(e.closest('[role="gridcell"]'))?
          e.closest('[role="gridcell"]').getAttribute('data-agentic-loop-id'):null};
    });
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
  const records=[...root.querySelectorAll('article,li,[role="listitem"],'+
    '[itemscope],[data-testid*="card"]')].filter(e=>visible(e)&&!e.closest(excluded)&&
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
      !e.closest('article,li,[role="listitem"],[data-testid*="card"],'+
        '[itemtype$="/Hotel"],[itemtype$="/Product"],[itemtype$="/Article"]'))
    .map(e=>({text:clean(e.innerText),level:Number(e.getAttribute('aria-level')||
      (/^H[12]$/.test(e.tagName)?e.tagName.slice(1):0))}))
    .filter(e=>[1,2].includes(e.level)&&e.text.length>0&&e.text.length<=240).slice(0,8);
  const results={record_count:records.filter(e=>!records.some(n=>n!==e&&e.contains(n))).length,
    busy:[...root.querySelectorAll('[aria-busy="true"],[role="progressbar"],[role="status"]')]
      .some(e=>visible(e)&&!e.closest(excluded)&&
        (e.getAttribute('aria-busy')==='true'||e.getAttribute('role')==='progressbar'||
          /\bloading\b/i.test(clean(e.innerText)+' '+label(e)))),
    no_results:emptyResults.test(resultText),price_contexts:priceContexts,headings:resultHeadings};
  return {title:document.title,text:chunks.join(' ').slice(0,12000),controls,
    autocomplete_diagnostics:autocompleteDiagnostics,
    results,
    focus,widgets:popupScopes.slice(0,8).map(e=>({role:e.getAttribute('role'),label:label(e),
      text:clean(e.innerText).slice(0,800)})),
    controls_truncated:raw.length>140,visible_control_count:raw.length,
    viewport:{width:innerWidth,height:innerHeight,scroll_y:scrollY},
    password_or_code_visible:query('input').some(e=>visible(e)&&
      (e.type==='password'||e.autocomplete==='one-time-code'||/otp|verification|^code$/i.test(e.name)))};
};

