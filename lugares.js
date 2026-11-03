'use strict';
/* TrailMeteo 17 · Buscador de lugares de montaña.
   Encuentra picos, refugios, collados, majadas, canales, lagos, fuentes y pueblos («pico urriellu», «casetón de ándara»,
   «refugio de cabrones») y da el tiempo en ese punto exacto y a su altitud real.
   Fuentes, por orden: nomenclátor propio precalculado desde OpenStreetMap (data/lugares.json, sin red), canales de Picos
   (data/canales.json), Photon (búsqueda mientras escribes), Open-Meteo Geocoding (localidades) y, al pulsar Buscar,
   Nominatim. La altitud del punto (OSM) se pasa a Open-Meteo, que corrige temperatura y nieve por altitud; sin ella,
   Open-Meteo usa su modelo digital del terreno de 90 m en esa coordenada. */
(function(){
const PL={index:null,loading:null,seq:0,timer:0,last:[]};
const KINDS={pico:['Pico','<path d="M3 20 10 6l4 7 2-3 5 10Z"/>'],refugio:['Refugio','<path d="M4 20V11l8-6 8 6v9Z"/><path d="M10 20v-5h4v5"/>'],cabaña:['Cabaña o abrigo','<path d="M3 20 12 5l9 15Z"/><path d="M10 20v-4h4v4"/>'],collado:['Collado','<path d="M2 18c4 0 5-9 10-9s6 9 10 9"/>'],canal:['Canal','<path d="M7 3c2 5 1 9 3 12s1 4 0 6M17 3c-2 5-1 9-3 12s-1 4 0 6"/>'],lago:['Lago','<path d="M3 14c3-2 6 2 9 0s6 2 9 0M3 18c3-2 6 2 9 0s6 2 9 0"/>'],fuente:['Fuente','<path d="M12 3c3 5 5 8 5 11a5 5 0 0 1-10 0c0-3 2-6 5-11Z"/>'],paraje:['Paraje o majada','<circle cx="12" cy="10" r="3"/><path d="M12 21s-7-6.5-7-11a7 7 0 0 1 14 0c0 4.5-7 11-7 11Z"/>'],mirador:['Mirador','<circle cx="12" cy="12" r="3"/><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/>'],cueva:['Cueva','<path d="M3 20c0-9 4-15 9-15s9 6 9 15Z"/><path d="M9 20c0-4 1.5-6 3-6s3 2 3 6"/>'],teleférico:['Teleférico','<path d="M3 4l18 5M8 6v5M16 8v5"/><rect x="5" y="11" width="6" height="5" rx="1"/><rect x="13" y="13" width="6" height="5" rx="1"/>'],cresta:['Cresta','<path d="M2 18 7 9l3 4 3-7 3 6 2-3 4 9Z"/>'],valle:['Valle','<path d="M2 6c4 0 6 12 10 12S18 6 22 6"/>'],pueblo:['Localidad','<path d="M3 20V10l5-4 5 4v10M13 20v-6h8v6"/>'],lugar:['Lugar','<circle cx="12" cy="10" r="3"/><path d="M12 21s-7-6.5-7-11a7 7 0 0 1 14 0c0 4.5-7 11-7 11Z"/>']};
const PRIORITY={pico:9,refugio:9,collado:7,canal:7,cabaña:6,lago:6,paraje:5,mirador:4,fuente:4,teleférico:4,cresta:4,cueva:3,valle:3,pueblo:5,lugar:1};
/* Palabras que se escriben de muchas formas o en asturiano/cántabro */
const SYN={picu:'pico',pica:'pico',penya:'pena',peña:'pena',penes:'pena',collau:'collado',colladu:'collado',col:'collado',horcada:'collado',horcadina:'collado',refu:'refugio',ref:'refugio',albergue:'refugio',caseton:'caseton',casetón:'caseton',canalon:'canal',canalona:'canal',canalu:'canal',llagu:'lago',lagu:'lago',llago:'lago',xou:'jou',hoyo:'jou',torrezuela:'torre',torres:'torre',majadas:'majada',brana:'majada',braña:'majada',vegas:'vega',fte:'fuente',fuentona:'fuente',naranjo:'naranjo'};
const STOP=new Set(['de','del','la','el','los','las','y','d','l','en','a','al','les','lu','los']);
const KIND_WORDS={pico:['pico','cumbre','pena','torre','cima'],refugio:['refugio'],cabaña:['refugio','cabana','abrigo','chozo'],collado:['collado','paso','puerto'],canal:['canal'],lago:['lago','laguna'],fuente:['fuente'],paraje:['majada','vega','paraje'],mirador:['mirador'],teleférico:['teleferico','cable'],pueblo:[]};
const kindOf=k=>KINDS[k]?k:'lugar';
const icon=k=>`<svg viewBox="0 0 24 24" aria-hidden="true">${KINDS[kindOf(k)][1]}</svg>`;
const label=k=>KINDS[kindOf(k)][0];

function norm(s){return String(s||'').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'').replace(/[^a-z0-9]+/g,' ').trim()}
function tokens(s){return norm(s).split(' ').filter(t=>t&&!STOP.has(t)).map(t=>SYN[t]||t)}
function lev1(a,b){if(a===b)return true;if(Math.abs(a.length-b.length)>1)return false;let i=0,j=0,d=0;while(i<a.length&&j<b.length){if(a[i]===b[j]){i++;j++;continue}if(++d>1)return false;if(a.length>b.length)i++;else if(b.length>a.length)j++;else{i++;j++}}return d+(a.length-i)+(b.length-j)<=1}
function tokenScore(q,toks){let best=0;for(const t of toks){if(t===q)return 3;if(q.length>=2&&t.startsWith(q))best=Math.max(best,2.2);else if(q.length>=5&&lev1(q,t))best=Math.max(best,1.4);else if(q.length>=6&&t.length>=6&&lev1(q.slice(0,t.length),t))best=Math.max(best,1)}return best}
/* Puntuación de un lugar para una consulta; null si no encaja. Pura y probada en tests/v17.mjs */
function score(place,query){const q=tokens(query);if(!q.length)return null;const nameToks=place.toks||(place.toks=[...new Set([place.name,...(place.alts||[])].flatMap(tokens))]),kindToks=KIND_WORDS[place.kind]||[];let s=0,matched=0;
 for(const t of q){const n=tokenScore(t,nameToks);if(n){s+=n;matched++;continue}if(kindToks.includes(t)){s+=.6;matched++;continue}if(Object.values(KIND_WORDS).some(w=>w.includes(t))){s-=.4;continue}return null}
 if(!matched)return null;const nq=norm(query),nn=norm(place.name);if(nn===nq)s+=3;else if(nn.startsWith(nq))s+=1.5;else if((place.alts||[]).some(a=>norm(a)===nq))s+=2.5;
 s+=(PRIORITY[place.kind]||1)*.12;if(finite(place.ele))s+=.15;const c=S.location||{lat:43.18,lon:-4.82};if(finite(place.lat)){const km=TM.distance(c,place);s+=Math.max(0,1-km/80)*.6}return s}
function rank(list,query,limit=8){const out=[];for(const p of list){const s=score(p,query);if(s!=null)out.push([s,p])}return out.sort((a,b)=>b[0]-a[0]).slice(0,limit).map(x=>x[1])}

/* ---------- Índice local ---------- */
function centerOf(e){if(finite(e.lat))return{lat:e.lat,lon:e.lon};if(e.center)return e.center;const g=e.geometry||(e.members||[]).flatMap(m=>m.geometry||[]);const v=(g||[]).filter(p=>p&&finite(p.lat));if(!v.length)return e.bounds?{lat:(e.bounds.minlat+e.bounds.maxlat)/2,lon:(e.bounds.minlon+e.bounds.maxlon)/2}:null;return v[Math.floor(v.length/2)]}
async function loadIndex(){if(PL.index)return PL.index;if(PL.loading)return PL.loading;PL.loading=(async()=>{const list=[];
 try{const d=await json('data/lugares.json',86400000);for(const [name,alts,kind,lat,lon,ele,id] of d.places||[])list.push({name,alts:alts||[],kind,lat,lon,ele:finite(ele)?ele:null,id,src:'Nomenclátor OSM'});PL.meta={fetched:d.fetched,n:list.length}}catch{PL.meta={error:true}}
 try{const d=await json('data/canales.json',86400000),seen=new Set();for(const e of d.elements||[]){const n=e.tags?.name,c=n&&centerOf(e);if(!c)continue;const k=norm(n)+Math.round(c.lat*100);if(seen.has(k))continue;seen.add(k);list.push({name:n,alts:[],kind:'canal',lat:+c.lat,lon:+c.lon,ele:null,id:'canal'+e.id,src:'Canales OSM'})}}catch{}
 PL.index=list;return list})();try{return await PL.loading}finally{PL.loading=null}}

/* ---------- Fuentes en directo ---------- */
const OSM_KIND={peak:'pico',volcano:'pico',saddle:'collado',mountain_pass:'collado',alpine_hut:'refugio',wilderness_hut:'cabaña',shelter:'cabaña',spring:'fuente',water:'lago',lake:'lago',viewpoint:'mirador',cave_entrance:'cueva',ridge:'cresta',arete:'cresta',valley:'valle',station:'teleférico',locality:'paraje',isolated_dwelling:'paraje',hamlet:'pueblo',village:'pueblo',town:'pueblo',city:'pueblo',municipality:'pueblo'};
function bias(){const c=S.route?.points?.[0]||S.location||{lat:43.18,lon:-4.82};return c}
async function photon(q,signal){const c=bias(),r=await fetch('https://photon.komoot.io/api/?'+new URLSearchParams({q,limit:'10',lat:c.lat.toFixed(3),lon:c.lon.toFixed(3),bbox:'-9.5,41.5,-1.5,43.9'}),{signal,credentials:'omit'});if(!r.ok)throw Error('Photon '+r.status);const d=await r.json();
 return(d.features||[]).map(f=>{const p=f.properties||{},[lon,lat]=f.geometry?.coordinates||[];return{name:p.name||q,alts:[],kind:OSM_KIND[p.osm_value]||OSM_KIND[p.type]||'lugar',lat,lon,ele:finite(+p.ele)?+p.ele:null,area:[p.city||p.county,p.state].filter(Boolean).join(', '),src:'Photon · OSM'}}).filter(p=>finite(p.lat))}
async function nominatim(q,signal){const c=bias(),vb=[c.lon-1.6,c.lat+1,c.lon+1.6,c.lat-1].map(v=>v.toFixed(3)).join(',');const r=await fetch('https://nominatim.openstreetmap.org/search?'+new URLSearchParams({q,format:'jsonv2',limit:'10',viewbox:vb,bounded:'0',countrycodes:'es,fr,ad,pt','accept-language':'es',extratags:'1'}),{signal,credentials:'omit'});if(!r.ok)throw Error('Nominatim '+r.status);const d=await r.json();
 return(d||[]).map(x=>({name:x.name||String(x.display_name||q).split(',')[0],alts:[],kind:OSM_KIND[x.type]||OSM_KIND[x.category]||'lugar',lat:+x.lat,lon:+x.lon,ele:finite(parseFloat(x.extratags?.ele))?Math.round(parseFloat(x.extratags.ele)):null,area:String(x.display_name||'').split(',').slice(1,3).join(',').trim(),src:'Nominatim · OSM'})).filter(p=>finite(p.lat))}
async function openMeteo(q){const d=await json('https://geocoding-api.open-meteo.com/v1/search?'+new URLSearchParams({name:q,count:'6',language:'es',format:'json'}),86400000);return(d.results||[]).map(r=>({name:r.name,alts:[],kind:'pueblo',lat:r.latitude,lon:r.longitude,ele:null,demEle:r.elevation,area:[r.admin2||r.admin1,r.country].filter(Boolean).join(', '),src:'Open-Meteo'}))}
function merge(lists){const out=[];for(const p of lists.flat()){if(!p||!finite(p.lat))continue;const dup=out.find(o=>norm(o.name)===norm(p.name)&&TM.distance(o,p)<.6||TM.distance(o,p)<.06&&o.kind===p.kind);if(dup){if(!finite(dup.ele)&&finite(p.ele))dup.ele=p.ele;if(!dup.area&&p.area)dup.area=p.area;continue}out.push(p)}return out}

/* ---------- Interfaz ---------- */
const box=()=>$('#searchResults');
function row(p,i){const meta=[label(p.kind),finite(p.ele)?fmt(p.ele)+' m':'',p.area||''].filter(Boolean).join(' · ');return `<button type="button" data-pl="${i}" class="pl-row pl-${kindOf(p.kind)}">${icon(p.kind)}<span><b>${esc(p.name)}</b><small>${esc(meta)}</small></span><em>${esc(p.src||'')}</em></button>`}
function show(rows,{note='',more=true}={}){const b=box();if(!b)return;PL.last=rows;b.hidden=false;b.classList.add('pl-results');
 b.innerHTML=(rows.length?rows.map(row).join(''):`<p class="pl-empty">${note||'Sin coincidencias en el nomenclátor de montaña.'}</p>`)+(more?`<button type="button" class="pl-more" data-pl-more>Buscar también en OpenStreetMap ↵</button>`:'')+(rows.length&&note?`<p class="pl-note">${note}</p>`:'');
 b.querySelectorAll('[data-pl]').forEach(x=>x.onclick=()=>pick(PL.last[+x.dataset.pl]));b.querySelector('[data-pl-more]')?.addEventListener('click',()=>full($('#placeSearch').value))}
async function pick(p,opts={}){if(!p)return;box()&&(box().hidden=true);const input=$('#placeSearch');if(input&&!opts.keep)input.value='';const loc={name:p.name,lat:+(+p.lat).toFixed(5),lon:+(+p.lon).toFixed(5),kind:kindOf(p.kind),src:p.src||''};if(finite(p.ele)&&p.kind!=='pueblo')loc.ele=Math.round(p.ele);remember(loc);if(opts.noFetch)return loc;
 if(typeof enterApp==='function'&&!['now','nieve','models','mountain','radar'].includes(S.tab)&&!opts.stay)enterApp('now');await setLocation(loc);return loc}
function coords(q){const m=String(q).match(/^\s*(-?\d+(?:[.,]\d+)?)\s*[,; ]\s*(-?\d+(?:[.,]\d+)?)\s*$/);if(!m)return null;const lat=+m[1].replace(',','.'),lon=+m[2].replace(',','.');return Math.abs(lat)<=90&&Math.abs(lon)<=180?{lat,lon}:null}
async function quick(q){const my=++PL.seq;q=q.trim();if(q.length<2){box()&&(box().hidden=true);return}const idx=await loadIndex();if(my!==PL.seq)return;let rows=rank(idx,q,8);show(rows,{note:idx.length?'':'Cargando el nomenclátor…'});
 if(q.length<3)return;clearTimeout(PL.timer);PL.timer=setTimeout(async()=>{if(my!==PL.seq)return;const ctrl=new AbortController(),t=setTimeout(()=>ctrl.abort(),7000);try{const [ph,om]=await Promise.allSettled([photon(q,ctrl.signal),openMeteo(q)]);if(my!==PL.seq)return;const live=[ph,om].flatMap(r=>r.status==='fulfilled'?r.value:[]);const all=merge([rows,rank(live,q,10)]);rows=all.slice(0,9);show(rows)}catch{}finally{clearTimeout(t)}},420)}
async function full(q){const my=++PL.seq;q=String(q||'').trim();if(q.length<2){notice('Escribe al menos dos letras o coordenadas.');return}const c=coords(q);if(c){box()&&(box().hidden=true);$('#placeSearch').value='';setLocation({name:'Punto '+c.lat.toFixed(4)+', '+c.lon.toFixed(4),lat:c.lat,lon:c.lon,kind:'lugar'});return}
 show(PL.last.length?PL.last:[],{note:'Buscando en OpenStreetMap…',more:false});const idx=await loadIndex(),ctrl=new AbortController(),t=setTimeout(()=>ctrl.abort(),9000);
 const res=await Promise.allSettled([nominatim(q,ctrl.signal),photon(q,ctrl.signal),openMeteo(q)]);clearTimeout(t);if(my!==PL.seq)return;const live=res.flatMap(r=>r.status==='fulfilled'?r.value:[]);const fails=res.filter(r=>r.status==='rejected').length;
 const all=merge([rank(idx,q,8),rank(live,q,12),live.slice(0,4)]).slice(0,10);show(all,{note:all.length?(fails===3?'Sin conexión con los buscadores: resultados del nomenclátor guardado.':''):'Sin resultados. Prueba otro nombre, el pueblo más cercano o coordenadas (43.24, -4.82).',more:false});if(all.length===1)pick(all[0])}

/* ---------- Favoritos y recientes ---------- */
const FKEY='tm.places.v17';
function store(){try{return JSON.parse(localStorage.getItem(FKEY))||{fav:[],recent:[]}}catch{return{fav:[],recent:[]}}}
function save(s){try{localStorage.setItem(FKEY,JSON.stringify(s))}catch{}renderChips()}
const same=(a,b)=>a&&b&&Math.abs(a.lat-b.lat)<1e-4&&Math.abs(a.lon-b.lon)<1e-4;
function remember(loc){const s=store();s.recent=[loc,...s.recent.filter(x=>!same(x,loc))].slice(0,6);save(s)}
function isFav(loc=S.location){return store().fav.some(x=>same(x,loc))}
function toggleFav(loc=S.location){const s=store();if(s.fav.some(x=>same(x,loc)))s.fav=s.fav.filter(x=>!same(x,loc));else s.fav=[{name:loc.name,lat:loc.lat,lon:loc.lon,ele:loc.ele??null,kind:loc.kind||'lugar'},...s.fav].slice(0,12);save(s);return isFav(loc)}
function renderChips(){const el=$('#plChips');if(!el)return;const s=store(),rec=s.recent.filter(r=>!s.fav.some(f=>same(f,r))).slice(0,4);const chip=(p,cls)=>`<button type="button" class="pl-chip ${cls}" data-chip="${esc(JSON.stringify({name:p.name,lat:p.lat,lon:p.lon,ele:p.ele??null,kind:p.kind||'lugar'}))}">${cls==='fav'?'★ ':''}${esc(p.name)}${finite(p.ele)?` <small>${fmt(p.ele)} m</small>`:''}</button>`;el.innerHTML=[...s.fav.map(p=>chip(p,'fav')),...rec.map(p=>chip(p,'rec'))].join('');el.hidden=!el.innerHTML}

/* ---------- Integración con la app ---------- */
/* El tiempo del punto se pide a SU altitud (no a la del pueblo ni a la de la celda del modelo). */
const prevURL=forecastURL;forecastURL=function(lat,lon,extra={}){const l=S.location;if(l&&finite(l.ele)&&!('elevation' in extra)&&String(lat)===String(l.lat)&&String(lon)===String(l.lon))extra={...extra,elevation:String(l.ele)};return prevURL(lat,lon,extra)};
const prevRender=renderNow;renderNow=function(){prevRender.apply(this,arguments);const l=S.location,m=$('#placeMeta');if(!m||!S.forecast)return;const k=l?.kind&&l.kind!=='lugar'?label(l.kind)+' · ':'';if(finite(l?.ele))m.textContent=m.textContent.replace(/^[^·]*\(terreno del modelo\)/,`${k}${fmt(S.forecast.elevation)} m (altitud del punto)`);else if(k)m.textContent=k+m.textContent;const n=$('#placeName');if(n&&!n.querySelector('.pl-star')){n.insertAdjacentHTML('beforeend',`<button type="button" class="pl-star" aria-pressed="${isFav()}" title="Guardar en favoritos">${isFav()?'★':'☆'}</button>`);n.querySelector('.pl-star').onclick=e=>{e.stopPropagation();const on=toggleFav();e.currentTarget.textContent=on?'★':'☆';e.currentTarget.setAttribute('aria-pressed',String(on))}}};
search=function(){return full($('#placeSearch').value)};
function mount(){const input=$('#placeSearch');if(!input||input.dataset.pl)return;input.dataset.pl='1';input.placeholder='Pico, refugio, collado, canal, pueblo o coordenadas';input.setAttribute('aria-label','Buscar un lugar de montaña o una localidad');input.setAttribute('enterkeyhint','search');
 input.addEventListener('input',()=>quick(input.value));input.addEventListener('focus',()=>{loadIndex();if(input.value.trim().length>=2)quick(input.value)});
 input.addEventListener('keydown',e=>{const rows=[...(box()?.querySelectorAll('[data-pl]')||[])];if(!rows.length)return;const i=rows.indexOf(document.activeElement);if(e.key==='ArrowDown'){e.preventDefault();rows[Math.min(rows.length-1,i+1)]?.focus()}});
 box()?.addEventListener('keydown',e=>{const rows=[...box().querySelectorAll('[data-pl]')],i=rows.indexOf(document.activeElement);if(e.key==='ArrowDown'){e.preventDefault();rows[Math.min(rows.length-1,i+1)]?.focus()}if(e.key==='ArrowUp'){e.preventDefault();(i<=0?input:rows[i-1]).focus()}if(e.key==='Escape'){box().hidden=true;input.focus()}});
 $('#searchForm')?.insertAdjacentHTML('afterend','<div id="plChips" class="pl-chips" hidden></div>');$('#plChips')?.addEventListener('click',e=>{const b=e.target.closest('[data-chip]');if(!b)return;try{const p=JSON.parse(b.dataset.chip);pick({...p,src:'Favorito'},{stay:true})}catch{}});renderChips()}
mount();
globalThis.TMPlaces={norm,tokens,score,rank,merge,loadIndex,pick,full,quick,icon,label,kinds:KINDS,isFav,toggleFav,store,photon,openMeteo,coords,get meta(){return PL.meta}};
})();
