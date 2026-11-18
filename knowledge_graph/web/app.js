
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=v=>v===''||v==null?'미확인':Number.isFinite(Number(v))?Number(v).toLocaleString('ko-KR',{maximumFractionDigits:2}):String(v);
const pct=v=>v===''||v==null?'미확인':(Number(v)*100).toFixed(1)+'%';
const kv=(l,v)=>v===''||v==null?'':`<div class="kv"><span>${esc(l)}</span><span>${esc(v)}</span></div>`;
const section=(t,v)=>v?`<h3>${esc(t)}</h3><p>${esc(v)}</p>`:'';
const safeURL=v=>{try{const u=new URL(v);return ['https:','http:'].includes(u.protocol)?u.href:'';}catch{return '';}};
const colors={program:'#367d64',domain:'#93a975',complex:'#456578',case:'#b68c4c',card:'#d29c59',obstacle:'#bd776c',news:'#7e88a7',record:'#92aca6',recommendation:'#b99b55',partner:'#7591a1',resource:'#9d92ad',target:'#9aa67f'};
const icons={program:'◉',complex:'▥',case:'▤',card:'▤',news:'◷',record:'≡',obstacle:'!',domain:'◈'};
const statuses='observed,defined,derived,estimated,similarity';
const nodeColor=n=>colors[n.kind]||'#9ba99a';
const api=async(route,params={})=>{const r=await fetch('/api/'+route+'?'+new URLSearchParams(params));const d=await r.json();if(!r.ok)throw Error(d.error||'자료를 불러오지 못했습니다.');return d;};
let stats,cy,root='',view='overview',selected=null,currentGraph={nodes:[],edges:[]},currentEvidence={items:[],total:0},tab='content',evKind='',evOffset=0,searchKind='',loadToken=0,selectToken=0,evidenceToken=0,searchToken=0,trail=[],labelFrame=0,dragState=null,springFrame=0,layoutToken=0,hovered=null;
const labelMap=new Map(),reduceMotion=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
function toast(t){$('#toast').textContent=t;$('#toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('#toast').hidden=true,3200);}
function typeName(n){return stats?.type_labels[n.kind]||n.kind;}
function shortName(n){return n.kind==='obstacle'?(n.attrs?.obstacle||n.label):n.label;}
function scheduleLabels(){if(!labelFrame)labelFrame=requestAnimationFrame(()=>{labelFrame=0;renderLabels();});}
function renderLabels(){
 if(!cy)return;$('#zoomLevel').textContent=Math.round(cy.zoom()*100)+'%';
 const z=cy.zoom(),bounds=$('#cy').getBoundingClientRect(),w=cy.width(),h=cy.height(),occupied=[];
 const rectOf=e=>{const b=e.getBoundingClientRect();return {x:b.left-bounds.left-8,y:b.top-bounds.top-8,w:b.width+16,h:b.height+16};};
 for(const selector of ['.map-heading','.zoom-controls','.map-legend','.map-status','#startCards']){const el=$(selector);if(!el.hidden&&el.offsetWidth)occupied.push(rectOf(el));}
 const overlaps=(a,b)=>a.x<b.x+b.w&&a.x+a.w>b.x&&a.y<b.y+b.h&&a.y+a.h>b.y;
 const priority=n=>(n.id()===hovered?20000:0)+(n.selected()?10000:0)+(n.id()===root?5000:0)+(n.data('kind')==='domain'?500:0)+n.degree();
 const nodes=cy.nodes().toArray().sort((a,b)=>priority(b)-priority(a));
 const budget=Math.min(nodes.length,w<500?12:w<850?19:30);let count=0;
 for(const n of nodes){const el=labelMap.get(n.id());if(!el)continue;const p=n.renderedPosition(),r=n.renderedWidth()/2,active=n.selected()||n.id()===hovered;
  el.classList.toggle('is-selected',n.selected());el.classList.toggle('is-muted',n.hasClass('muted'));el.classList.toggle('is-root',n.id()===root);el.hidden=false;
  const lw=el.offsetWidth,lh=el.offsetHeight,gap=8;
  const candidates=[{x:p.x-lw/2,y:p.y+r+gap},{x:p.x+r+gap,y:p.y-lh/2},{x:p.x-r-gap-lw,y:p.y-lh/2},{x:p.x-lw/2,y:p.y-r-gap-lh}];
  let pos=candidates.find(q=>q.x>10&&q.x+lw<w-10&&q.y>8&&q.y+lh<h-12&&!occupied.some(b=>overlaps({x:q.x-5,y:q.y-5,w:lw+10,h:lh+10},b)));
  const visible=pos&&(count<budget||active)&&(!n.hasClass('muted')||nodes.length<15);
  if(!visible){el.hidden=true;continue;}
  el.style.transform=`translate(${Math.round(pos.x)}px,${Math.round(pos.y)}px)`;el.style.zIndex=active?11:5;
  occupied.push({x:pos.x-5,y:pos.y-5,w:lw+10,h:lh+10});count++;
 }
}
function scaleNodes(){if(!cy)return;const z=cy.zoom();cy.batch(()=>{cy.nodes().forEach(n=>n.style({width:n.data('radius')/z,height:n.data('radius')/z,'border-width':(n.selected()?2.5:1.8)/z}));cy.edges().forEach(e=>e.style({width:(e.hasClass('highlight')?1.8:1.05)/z,'arrow-scale':.55/Math.sqrt(z)}));});scheduleLabels();}
function createLabels(){
 $('#labels').replaceChildren();labelMap.clear();
 for(const n of cy.nodes()){const el=document.createElement('button');el.className='node-label';el.dataset.node=n.id();el.innerHTML=`<span>${esc(shortName(n.data()))}</span>`;el.title=n.data('label');el.setAttribute('aria-label',typeName(n.data())+' · '+n.data('label'));el.hidden=true;labelMap.set(n.id(),el);$('#labels').appendChild(el);
  let down=null,moved=false;
  el.onpointerdown=e=>{if(e.button!==0)return;e.preventDefault();e.stopPropagation();el.setPointerCapture(e.pointerId);down={x:e.clientX,y:e.clientY,p:{...n.position()}};moved=false;beginDrag(n);el.classList.add('is-dragging');};
  el.onpointermove=e=>{if(!down)return;const dx=e.clientX-down.x,dy=e.clientY-down.y;if(Math.hypot(dx,dy)>4)moved=true;if(moved){n.position({x:down.p.x+dx/cy.zoom(),y:down.p.y+dy/cy.zoom()});scheduleLabels();}};
  el.onpointerup=e=>{if(!down)return;down=null;endDrag();el.classList.remove('is-dragging');if(el.hasPointerCapture(e.pointerId))el.releasePointerCapture(e.pointerId);if(!moved)inspect(n.id(),true);};
  el.onpointercancel=()=>{down=null;endDrag();el.classList.remove('is-dragging');};
  el.onclick=e=>{if(e.detail===0)inspect(n.id(),true);};
  el.onmouseenter=()=>{if(!dragState)showHover(n);};el.onmouseleave=()=>{$('#hoverName').hidden=true;};
 }
}
function showHover(n){if(dragState)return;const p=n.renderedPosition(),el=$('#hoverName');el.textContent=n.data('label');el.hidden=false;el.style.left=Math.max(10,Math.min(cy.width()-el.offsetWidth-10,p.x+18))+'px';el.style.top=Math.max(10,Math.min(cy.height()-el.offsetHeight-100,p.y-el.offsetHeight-20))+'px';}
function beginDrag(n){
 cy.stop();cy.nodes().stop();layoutToken++;$('#hoverName').hidden=true;cancelAnimationFrame(springFrame);
 const neighbors=n.neighborhood('node').filter(x=>!x.locked()).toArray().slice(0,24);
 dragState={node:n,origin:{...n.position()},released:false,items:neighbors.map(x=>({node:x,base:{...x.position()},vx:0,vy:0,tx:x.position('x'),ty:x.position('y')}))};
 if(!reduceMotion())springFrame=requestAnimationFrame(springStep);
}
function springStep(){
 const s=dragState;if(!s)return;const z=cy.zoom(),p=s.node.position();let dx=(p.x-s.origin.x)*.16,dy=(p.y-s.origin.y)*.16;const cap=36/z,len=Math.hypot(dx,dy);if(len>cap){dx*=cap/len;dy*=cap/len;}
 let energy=0;cy.batch(()=>{for(const item of s.items){if(!s.released){item.tx=item.base.x+dx;item.ty=item.base.y+dy;}const pos=item.node.position();item.vx=(item.vx+(item.tx-pos.x)*.11)*.72;item.vy=(item.vy+(item.ty-pos.y)*.11)*.72;item.node.position({x:pos.x+item.vx,y:pos.y+item.vy});energy+=Math.abs(item.vx)+Math.abs(item.vy)+Math.abs(item.tx-pos.x)+Math.abs(item.ty-pos.y);}});scheduleLabels();
 if(s.released&&energy*z<.4){dragState=null;springFrame=0;return;}springFrame=requestAnimationFrame(springStep);
}
function endDrag(){if(dragState){dragState.released=true;if(reduceMotion())dragState=null;}scheduleLabels();}
function initializeGraph(){
 cy=cytoscape({container:$('#cy'),elements:[],minZoom:.12,maxZoom:3.5,userZoomingEnabled:false,boxSelectionEnabled:false,selectionType:'single',style:[
 {selector:'node',style:{label:'','background-color':'data(color)',width:22,height:22,'border-width':2,'border-color':'#ffffff','overlay-opacity':0}},
 {selector:'node[kind="record"]',style:{shape:'round-rectangle'}},{selector:'node[kind="recommendation"]',style:{shape:'diamond'}},
 {selector:'node:selected',style:{'border-color':'#244a34','border-width':3}},
 {selector:'edge',style:{width:1.15,'line-color':'#a6b9ae','target-arrow-color':'#a6b9ae','target-arrow-shape':'triangle','arrow-scale':.55,'curve-style':'bezier',opacity:.65}},
 {selector:'edge[status="estimated"],edge[status="similarity"],edge[status="tentative"]',style:{'line-style':'dashed','line-color':'#bca878','target-arrow-color':'#bca878'}},
 {selector:'node.muted',style:{opacity:.38}},{selector:'edge.muted',style:{opacity:.14}},
 {selector:'edge.highlight',style:{'line-color':'#5c9271','target-arrow-color':'#5c9271',width:2,opacity:.9}}
 ]});
 cy.on('tap','node',e=>inspect(e.target.id(),true));cy.on('tap','edge',e=>inspectEdge(e.target.data()));cy.on('tap',e=>{if(e.target===cy){highlight(null);$('#hoverName').hidden=true;}});
 cy.on('zoom',scaleNodes);cy.on('pan position',scheduleLabels);cy.on('grab','node',e=>beginDrag(e.target));cy.on('free','node',endDrag);
 cy.on('mouseover','node',e=>{hovered=e.target.id();showHover(e.target);scheduleLabels();});cy.on('mouseout','node',()=>{hovered=null;$('#hoverName').hidden=true;scheduleLabels();});
 setupWheel();
}
function setupWheel(){
 let frame=0,target=1,anchor,world;const el=$('#cy');
 function handle(e){if(e.target.closest('button')&&!e.target.closest('.node-label'))return;e.preventDefault();e.stopImmediatePropagation();cy.stop();$('#hoverName').hidden=true;const rect=el.getBoundingClientRect(),p={x:e.clientX-rect.left,y:e.clientY-rect.top},z=cy.zoom(),pan=cy.pan();const delta=Math.max(-100,Math.min(100,e.deltaY*(e.deltaMode===1?16:e.deltaMode===2?rect.height:1)));target=Math.max(cy.minZoom(),Math.min(cy.maxZoom(),(frame?target:z)*Math.exp(-delta*.0055)));anchor=p;world={x:(p.x-pan.x)/z,y:(p.y-pan.y)/z};if(!frame){const tick=()=>{const next=cy.zoom()+(target-cy.zoom())*.45;cy.viewport({zoom:next,pan:{x:anchor.x-world.x*next,y:anchor.y-world.y*next}});if(Math.abs(next-target)>.0005)frame=requestAnimationFrame(tick);else{frame=0;cy.viewport({zoom:target,pan:{x:anchor.x-world.x*target,y:anchor.y-world.y*target}});}};frame=requestAnimationFrame(tick);}}
 $('.graph-stage').addEventListener('wheel',handle,{capture:true,passive:false});$('.graph-stage').addEventListener('pointerdown',()=>{cancelAnimationFrame(frame);frame=0;});
}
function fitMap(animate=true){
 if(!cy?.nodes().length)return;cy.stop();const bb=cy.nodes().boundingBox({includeLabels:false}),w=cy.width(),h=cy.height(),top=$('.map-heading').offsetHeight+65,bottom=view==='overview'?210:125;
 const z=Math.max(.12,Math.min(1.65,(w-260)/Math.max(1,bb.w),(h-top-bottom)/Math.max(1,bb.h))),pan={x:w/2-(bb.x1+bb.w/2)*z,y:top+(h-top-bottom)/2-(bb.y1+bb.h/2)*z};
 if(animate&&!reduceMotion())cy.animate({zoom:z,pan},{duration:320,easing:'ease-out-cubic',complete:scheduleLabels});else cy.viewport({zoom:z,pan});
}
function arrange(){
 const token=++layoutToken;cy.stop();cy.nodes().stop();cancelAnimationFrame(springFrame);dragState=null;
 cy.layout({name:'cose',animate:false,randomize:false,nodeDimensionsIncludeLabels:false,fit:false,nodeRepulsion:()=>13500,idealEdgeLength:()=>145,edgeElasticity:()=>75,gravity:.45,numIter:600,componentSpacing:110}).run();
 const points=cy.nodes().map(n=>({n,x:n.position('x')*1.25,y:n.position('y')}));
 for(let iteration=0;iteration<45;iteration++){for(let i=0;i<points.length;i++)for(let j=i+1;j<points.length;j++){const a=points[i],b=points[j],dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||1;if(d<115){const force=(115-d)*.24,ux=d===1?.7:dx/d,uy=d===1?.7:dy/d;a.x-=ux*force;a.y-=uy*force;b.x+=ux*force;b.y+=uy*force;}}}
 cy.batch(()=>points.forEach(p=>p.n.position({x:p.x,y:p.y})));fitMap(false);scaleNodes();
 const targets=cy.nodes().map(n=>({n,p:{...n.position()}}));if(!reduceMotion())for(const {n,p} of targets){n.position({x:p.x*.94,y:p.y*.94});n.animate({position:p},{duration:400,easing:'ease-out-cubic',complete:()=>{if(token===layoutToken)scheduleLabels();}});}scheduleLabels();
}
function draw(data,merge=false){
 const previous=currentGraph,ids=new Set(cy.nodes().map(n=>n.id()));
 if(merge){const ns=new Map(previous.nodes.map(n=>[n.id,n])),es=new Map(previous.edges.map(e=>[e.id,e]));data.nodes.forEach(n=>ns.set(n.id,n));data.edges.forEach(e=>es.set(e.id,e));if(ns.size>130){toast('연결이 많습니다. 이 대상의 지도로 이동해 살펴보세요.');return;}data={...data,center:root,nodes:[...ns.values()],edges:[...es.values()]};}
 currentGraph=data;let k=0;const origin=merge&&cy.getElementById(selected?.id||root).length?cy.getElementById(selected?.id||root).position():{x:0,y:0};
 if(!merge)cy.elements().remove();
 for(const n of data.nodes){if(merge&&ids.has(n.id))continue;let hash=0;for(const c of n.id)hash=(Math.imul(hash,31)+c.charCodeAt(0))|0;const angle=merge?k*2.39996:(hash>>>0)/4294967296*Math.PI*2,r=merge?140+Math.sqrt(k)*45:180+((hash>>>6)%350);cy.add({data:{...n,color:nodeColor(n),radius:n.id===root?32:n.kind==='domain'?26:19},position:{x:origin.x+Math.cos(angle)*r,y:origin.y+Math.sin(angle)*r}});k++;}
 for(const e of data.edges){if(cy.getElementById(e.id).length)continue;cy.add({data:e});}
 createLabels();if(!merge)arrange();else{scaleNodes();highlight(selected?.id);toast(`${k}개의 연결을 더 펼쳤습니다.`);}
 $('#graphCount').textContent=`${data.nodes.length}개 대상 · ${data.edges.length}개 연결`;
 const kinds=[...new Set(data.nodes.map(n=>n.kind))];$('#legend').innerHTML=kinds.slice(0,7).map(kind=>`<span><i class="dot" style="background:${nodeColor({kind})}"></i>${esc(typeName({kind}))}</span>`).join('');scheduleLabels();
}
async function loadGraph(id='',mode='focus',merge=false,remember=true){
 const token=++loadToken;$('#loading').hidden=false;$('#hoverName').hidden=true;
 try{const data=await api('graph',{id,mode,limit:16,statuses});if(token!==loadToken)return;
  if(!merge){if(remember&&(root||view!=='overview'))trail.push({root,view});selectToken++;root=data.center||id;view=mode==='overview'?'overview':'focus';selected=null;$('#inspector').hidden=true;$('#startCards').hidden=view!=='overview';cy.resize();const center=data.nodes.find(n=>n.id===root);$('#mapCategory').textContent=view==='overview'?'프로그램 지도':typeName(center||{kind:'program'});$('#graphTitle').textContent=view==='overview'?'복지는 어떻게 연결될까요?':center?.label||id;$('#graphSubtitle').textContent=view==='overview'?'프로그램에서 사례로, 사례에서 새로운 가능성으로.':'이름을 눌러 내용을 읽고, 연결을 따라 탐색하세요.';window.history.replaceState(null,'',view==='overview'?location.pathname:'#focus='+encodeURIComponent(root));}
  draw(data,merge);$('#searchDialog').close();$$('.rail-item').forEach(b=>b.classList.toggle('active',b.dataset.nav===(view==='overview'||id.startsWith('program:')?'overview':id.startsWith('complex:')?'complex':id.startsWith('news:')?'news':'card')));
 }catch(e){toast(e.message);}finally{if(token===loadToken)$('#loading').hidden=true;}
}
function highlight(id){cy.elements().removeClass('muted highlight');cy.$(':selected').unselect();const n=id?cy.getElementById(id):null;if(n?.length){n.select();cy.elements().difference(n.closedNeighborhood()).addClass('muted');n.connectedEdges().addClass('highlight');}scaleNodes();scheduleLabels();}
function openDetail(){const previouslyHidden=$('#inspector').hidden;$('#inspector').hidden=false;$('#startCards').hidden=true;if(previouslyHidden){cy.resize();scheduleLabels();}$('#inspector').scrollTop=0;}
function closeDetail(){$('#inspector').hidden=true;$('#startCards').hidden=view!=='overview';cy.resize();highlight(null);}
async function inspect(id,move=false){
 const token=++selectToken;const n=cy.getElementById(id),wasSelected=n.selected();highlight(id);$('#hoverName').hidden=true;openDetail();
 if(move&&n.length&&!wasSelected){cy.stop();const z=Math.min(cy.maxZoom(),cy.zoom()*1.1),p=n.position();cy.animate({zoom:z,pan:{x:cy.width()/2-p.x*z,y:cy.height()*.52-p.y*z}},{duration:reduceMotion()?0:280,easing:'ease-out-cubic'});}
 $('#selectionType').textContent=n.length?typeName(n.data()):'상세 보기';$('#detail').innerHTML='<div class="detail-body empty">내용을 불러오고 있습니다.</div>';
 try{const [node,ev]=await Promise.all([api('node',{id}),api('evidence',{id,limit:8,statuses})]);if(token!==selectToken)return;selected=node;currentEvidence=ev;evOffset=0;evKind='';tab=['program','complex'].includes(node.kind)&&ev.total?'evidence':'content';renderDetail();}catch(e){if(token===selectToken)$('#detail').innerHTML='<div class="detail-body empty">내용을 불러오지 못했습니다.</div>';toast(e.message);}
}
function evidenceCard(n){const a=n.attrs;const text=n.kind==='card'?a.how_it_runs||a.need:n.kind==='case'?a.summary:n.kind==='record'?a.activity_content_masked:n.kind==='obstacle'?a.solution:'';const date=a.start_date||a.date||'';return `<article class="evidence-card"><div class="meta"><i class="dot" style="background:${nodeColor(n)}"></i>${esc(typeName(n))} ${esc(date)}</div><h4>${esc(n.label)}</h4>${text?`<p>${esc(String(text).slice(0,150))}${text.length>150?'…':''}</p>`:''}${n.kind==='record'?`<p>${esc(a.complex_name||'')} · ${fmt(a.activity_count)}회 · 참여기록 ${fmt(a.participants_total)}명</p>`:''}<button data-inspect="${esc(n.id)}">${n.kind==='card'?'사례 자세히 읽기':'내용 보기'} ↗</button>${n.kind==='news'&&safeURL(a.url)?`<a href="${esc(safeURL(a.url))}" target="_blank" rel="noopener noreferrer">기사 원문 ↗</a>`:''}</article>`;}
function renderDetail(){
 const n=selected;if(!n)return;$('#selectionType').innerHTML=`<i class="dot" style="background:${nodeColor(n)}"></i>${esc(typeName(n))}`;
 let html=`<div class="detail-head"><h2>${esc(n.label)}</h2><div class="detail-actions"><button class="primary" id="focusSelected">이 연결 따라가기 ↗</button>${cy.getElementById(n.id).length?'<button class="secondary" id="expandSelected">더 펼치기 +</button>':''}</div></div><div class="detail-tabs"><button data-tab="content" class="${tab==='content'?'active':''}">내용</button><button data-tab="evidence" class="${tab==='evidence'?'active':''}">관련 사례 <small>${fmt(currentEvidence.total)}</small></button><button data-tab="relations" class="${tab==='relations'?'active':''}">연결</button></div><div class="detail-body">`;
 if(tab==='content')html+=content(n);
 if(tab==='evidence'){html+='<div class="evidence-filters">'+[['','전체'],['card','실행 사례'],['record','운영 기록'],['news','소식']].map(([k,l])=>`<button data-evkind="${k}" class="${evKind===k?'active':''}">${l}</button>`).join('')+'</div>';html+=currentEvidence.items.length?currentEvidence.items.map(evidenceCard).join(''):'<div class="empty">이 조건에 연결된 사례가 없습니다.</div>';if(currentEvidence.total>8)html+=`<div class="pagination">${evOffset?'<button id="prevEvidence">← 이전</button>':'<span></span>'}<span>${Math.floor(evOffset/8)+1} / ${Math.ceil(currentEvidence.total/8)}</span>${evOffset+currentEvidence.items.length<currentEvidence.total?'<button id="nextEvidence">다음 →</button>':'<span></span>'}</div>`;}
 if(tab==='relations'){const related=currentGraph.edges.filter(e=>e.source===n.id||e.target===n.id);const seen=new Set();html+='<div class="relation-list">';for(const edge of related){const id=edge.source===n.id?edge.target:edge.source;if(seen.has(id))continue;seen.add(id);const other=currentGraph.nodes.find(x=>x.id===id);if(other)html+=`<button data-inspect="${esc(id)}"><small>${esc(edge.rel)}</small><b>${esc(other.label)}</b></button>`;}html+='</div>';if(!seen.size)html+='<div class="empty">‘이 연결 따라가기’에서 주변 대상을 확인하세요.</div>';}
 $('#detail').innerHTML=html+'</div>';
}
async function loadEvidence(){const token=++evidenceToken,id=selected.id,kind=evKind,offset=evOffset;try{const ev=await api('evidence',{id,kind,offset,limit:8,statuses});if(token!==evidenceToken||id!==selected?.id||kind!==evKind||offset!==evOffset)return;currentEvidence=ev;renderDetail();}catch(e){toast(e.message);}}
function inspectEdge(e){selectToken++;selected=null;openDetail();$('#selectionType').textContent=['estimated','similarity','tentative'].includes(e.status)?'추정된 연결':'연결';const a=currentGraph.nodes.find(n=>n.id===e.source),b=currentGraph.nodes.find(n=>n.id===e.target);$('#detail').innerHTML=`<div class="detail-head"><h2>${esc(e.rel)}</h2></div><div class="detail-body"><div class="relation-list"><button data-inspect="${esc(e.source)}"><small>출발 대상</small><b>${esc(a?.label||'')}</b></button><button data-inspect="${esc(e.target)}"><small>연결 대상</small><b>${esc(b?.label||'')}</b></button></div>${['estimated','similarity','tentative'].includes(e.status)?'<div class="notice">모델 또는 유사도에 따른 연결입니다.</div>':''}</div>`;}
async function search(){const token=++searchToken;try{const data=await api('search',{q:$('#search').value,kind:searchKind,limit:20});if(token!==searchToken)return;$('#searchResults').innerHTML=data.items.filter(n=>n.kind!=='office').map(n=>`<button data-focus="${esc(n.id)}"><span class="result-icon">${icons[n.kind]||'◈'}</span><span class="result-text"><b>${esc(n.label)}</b><small>${esc(typeName(n))}</small></span><span class="result-arrow">↗</span></button>`).join('')||'<div class="empty">검색 결과가 없습니다.</div>';}catch(e){toast(e.message);}}
function openSearch(kind=''){searchKind=kind;$('#search').value='';$$('[data-kind]').forEach(b=>b.classList.toggle('active',b.dataset.kind===kind));$('#searchDialog').showModal();search();$('#search').focus();}
function zoomBy(k){cy.stop();cy.zoom({level:Math.max(cy.minZoom(),Math.min(cy.maxZoom(),cy.zoom()*k)),renderedPosition:{x:cy.width()/2,y:cy.height()/2}});}
document.addEventListener('click',e=>{const inspectButton=e.target.closest('[data-inspect]');if(inspectButton){inspect(inspectButton.dataset.inspect);return;}const focus=e.target.closest('[data-focus]');if(focus){loadGraph(focus.dataset.focus);return;}const kind=e.target.closest('[data-kind]');if(kind){searchKind=kind.dataset.kind;$$('[data-kind]').forEach(b=>b.classList.toggle('active',b===kind));search();return;}const nav=e.target.closest('[data-nav]');if(nav){if(nav.dataset.nav==='overview')loadGraph('','overview');else openSearch(nav.dataset.nav);return;}const t=e.target.closest('[data-tab]');if(t){tab=t.dataset.tab;renderDetail();return;}const f=e.target.closest('[data-evkind]');if(f){evKind=f.dataset.evkind;evOffset=0;loadEvidence();return;}const id=e.target.closest('button')?.id;if(id==='focusSelected'&&selected)loadGraph(selected.id);if(id==='expandSelected'&&selected)loadGraph(selected.id,'focus',true,false);if(id==='nextEvidence'){evOffset+=8;loadEvidence();}if(id==='prevEvidence'){evOffset=Math.max(0,evOffset-8);loadEvidence();}});
$('#brand').onclick=e=>{e.preventDefault();loadGraph('','overview');};$('#home').onclick=()=>loadGraph('','overview');$('#back').onclick=()=>{const previous=trail.pop();loadGraph(previous?.root||'',previous?.view==='focus'?'focus':'overview',false,false);};$('#openSearch').onclick=()=>openSearch();$('#closeSearch').onclick=()=>$('#searchDialog').close();$('#closeDetail').onclick=closeDetail;$('#fit').onclick=()=>fitMap();$('#zoomIn').onclick=()=>zoomBy(1.5);$('#zoomOut').onclick=()=>zoomBy(1/1.5);
let searchTimer;$('#search').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(search,180);};$('#searchDialog').onclick=e=>{if(e.target===$('#searchDialog')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.target.close();}};
window.addEventListener('keydown',e=>{if(e.key==='/'&&!['INPUT','TEXTAREA'].includes(document.activeElement.tagName)){e.preventDefault();openSearch();}if(e.key==='Escape'&&!$('#searchDialog').open)closeDetail();});
new ResizeObserver(()=>{if(cy){cy.resize();scheduleLabels();}}).observe($('.graph-stage'));
(async()=>{try{stats=await api('stats');initializeGraph();const id=new URLSearchParams(location.hash.slice(1)).get('focus');await loadGraph(id||'',id?'focus':'overview',false,false);}catch(e){toast(e.message);}})();
