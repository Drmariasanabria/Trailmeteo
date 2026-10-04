'use strict';
/* Presentación: arranque, sonido sintetizado, vibración y fotografía de fondo con atribución. */
const FX={ctx:null,muted:false,themes:{},current:null,layer:0,photoSeq:0};
try{FX.muted=localStorage.getItem('tm.sound')==='off'}catch{}
const TAB_IDS=['route','now','radar','mountain','canales','models'];

/* ---------- Sonido: Web Audio, sin archivos ---------- */
function audio(){if(FX.muted)return null;const AC=globalThis.AudioContext||globalThis.webkitAudioContext;if(!AC)return null;try{if(!FX.ctx)FX.ctx=new AC();if(FX.ctx.state==='suspended')FX.ctx.resume();return FX.ctx}catch{return null}}
function tone(ctx,{f=440,to=null,d=.12,type='sine',g=.06,at=0,attack=.006}){const t=ctx.currentTime+at,o=ctx.createOscillator(),v=ctx.createGain();o.type=type;o.frequency.setValueAtTime(f,t);if(to)o.frequency.exponentialRampToValueAtTime(to,t+d);v.gain.setValueAtTime(0,t);v.gain.linearRampToValueAtTime(g,t+attack);v.gain.exponentialRampToValueAtTime(.0001,t+d);o.connect(v).connect(ctx.destination);o.start(t);o.stop(t+d+.05)}
function whoosh(ctx,{d=.35,g=.05,from=400,to=2400,at=0}){const t=ctx.currentTime+at,len=Math.ceil(ctx.sampleRate*d),buf=ctx.createBuffer(1,len,ctx.sampleRate),data=buf.getChannelData(0);for(let i=0;i<len;i++)data[i]=Math.random()*2-1;const src=ctx.createBufferSource(),bp=ctx.createBiquadFilter(),v=ctx.createGain();src.buffer=buf;bp.type='bandpass';bp.Q.value=1.4;bp.frequency.setValueAtTime(from,t);bp.frequency.exponentialRampToValueAtTime(to,t+d);v.gain.setValueAtTime(0,t);v.gain.linearRampToValueAtTime(g,t+d*.35);v.gain.exponentialRampToValueAtTime(.0001,t+d);src.connect(bp).connect(v).connect(ctx.destination);src.start(t);src.stop(t+d)}
const SOUNDS={
 boot(c){tone(c,{f:55,to:40,d:.9,type:'sine',g:.22});whoosh(c,{d:.9,g:.07,from:200,to:5200});[261.6,329.6,392,523.3,659.3,784].forEach((f,i)=>tone(c,{f,d:.9-i*.06,type:i%2?'triangle':'sine',g:.05,at:.12+i*.085}));tone(c,{f:1568,d:1.2,type:'sine',g:.03,at:.7})},
 tap(c){tone(c,{f:1900,to:1500,d:.045,type:'sine',g:.035})},
 tab(c){whoosh(c,{d:.22,g:.035,from:900,to:3600});tone(c,{f:740,to:990,d:.09,type:'triangle',g:.04,at:.03})},
 ok(c){tone(c,{f:880,d:.18,type:'triangle',g:.06});tone(c,{f:1318.5,d:.32,type:'sine',g:.05,at:.09})},
 warn(c){tone(c,{f:330,to:220,d:.28,type:'square',g:.03})},
 open(c){tone(c,{f:420,to:880,d:.2,type:'sine',g:.05});whoosh(c,{d:.25,g:.03,from:600,to:3000})},
 close(c){tone(c,{f:760,to:380,d:.18,type:'sine',g:.04})},
 msg(c){tone(c,{f:1046.5,d:.35,type:'sine',g:.045});tone(c,{f:1568,d:.4,type:'sine',g:.025,at:.06})},
 scan(c){[0,.12,.24].forEach(at=>tone(c,{f:1200,to:1800,d:.07,type:'sine',g:.03,at}))}
};
function sfx(name){const c=audio();if(!c||!SOUNDS[name])return;try{SOUNDS[name](c)}catch{}}
function buzz(p=12){try{if(!FX.muted&&navigator.vibrate)navigator.vibrate(p)}catch{}}
function setMuted(m){FX.muted=m;try{localStorage.setItem('tm.sound',m?'off':'on')}catch{}const t=$('#soundToggle');if(t){t.textContent=m?'🔇':'🔊';t.setAttribute('aria-pressed',String(!m));t.setAttribute('aria-label',m?'Activar sonidos':'Silenciar sonidos')}const s=$('#splashMute');if(s){s.textContent=m?'Sonido desactivado':'Sonido activado';s.setAttribute('aria-pressed',String(m))}if(!m)sfx('ok')}
setMuted(FX.muted);
$('#soundToggle')?.addEventListener('click',e=>{e.stopPropagation();setMuted(!FX.muted)});
document.addEventListener('click',e=>{const b=e.target.closest('button,.dropzone,.file-button');if(!b||b.id==='soundToggle'||b.id==='splashMute'||b.id==='splashEnter')return;if(b.dataset.tab||b.dataset.go){sfx('tab');buzz(8)}else if(b.classList.contains('primary')){sfx('ok');buzz(14)}else sfx('tap')},true);

/* ---------- Fotografía de fondo: Wikimedia Commons, con autor y licencia ---------- */
const PHOTO_QUERIES={splash:'Picos de Europa',home:'Picos de Europa macizo',route:'Ruta del Cares',now:'Picos de Europa nubes',radar:'Picos de Europa niebla',mountain:'Naranjo de Bulnes',canales:'Garganta del Cares',models:'Lagos de Covadonga'};
const stripHTML=s=>String(s||'').replace(/<[^>]*>/g,' ').replace(/\s+/g,' ').trim();
function photoCache(){try{return JSON.parse(localStorage.getItem('tm.photos.v1'))||{}}catch{return{}}}
function savePhotoCache(c){try{localStorage.setItem('tm.photos.v1',JSON.stringify(c))}catch{}}
async function commonsPhotos(query,limit=10){const key=query.toLowerCase(),cache=photoCache(),hit=cache[key];if(hit&&Date.now()-hit.at<7*86400000&&Array.isArray(hit.items))return hit.items;
 const url='https://commons.wikimedia.org/w/api.php?'+new URLSearchParams({action:'query',format:'json',origin:'*',generator:'search',gsrnamespace:'6',gsrsearch:query+' filetype:bitmap',gsrlimit:'24',prop:'imageinfo',iiprop:'url|size|mime|extmetadata',iiurlwidth:'1920'});
 const ctrl=new AbortController(),timer=setTimeout(()=>ctrl.abort(),12000);
 try{const r=await fetch(url,{signal:ctrl.signal,credentials:'omit',referrerPolicy:'no-referrer'});if(!r.ok)throw Error();const d=await r.json();const pages=Object.values(d?.query?.pages||{});
  const items=pages.map(p=>{const i=p.imageinfo?.[0],m=i?.extmetadata||{};return i&&{title:String(p.title||'').replace(/^File:|^Archivo:/,''),url:i.thumburl||i.url,page:i.descriptionurl,w:i.width,h:i.height,mime:i.mime,artist:stripHTML(m.Artist?.value).slice(0,80),license:stripHTML(m.LicenseShortName?.value),licenseUrl:m.LicenseUrl?.value||''}}).filter(x=>x&&/^https:\/\/upload\.wikimedia\.org\//.test(x.url)&&/jpe?g/i.test(x.mime||'')&&x.w>=1400&&x.w>x.h*1.15&&x.license&&!/fair use|non-free/i.test(x.license)).slice(0,limit);
  cache[key]={at:Date.now(),items};const keys=Object.keys(cache);if(keys.length>40)delete cache[keys[0]];savePhotoCache(cache);return items}catch{return hit?.items||[]}finally{clearTimeout(timer)}}
function creditHTML(p){if(!p)return'';const lic=p.licenseUrl&&/^https?:\/\//.test(p.licenseUrl)?`<a href="${esc(p.licenseUrl)}" target="_blank" rel="noopener">${esc(p.license)}</a>`:esc(p.license);return `📷 <a href="${esc(p.page)}" target="_blank" rel="noopener">${esc(p.title.replace(/\.[a-z]+$/i,''))}</a> · ${esc(p.artist||'Autor en Commons')} · ${lic}`}
function preload(src){return new Promise((res,rej)=>{const img=new Image();img.referrerPolicy='no-referrer';img.onload=()=>res(src);img.onerror=rej;img.src=src;setTimeout(()=>rej(Error('timeout')),15000)})}
async function pickPhoto(theme){const items=FX.themes[theme]||(FX.themes[theme]=await commonsPhotos(PHOTO_QUERIES[theme]||PHOTO_QUERIES.home));if(!items.length)return null;const day=Math.floor(Date.now()/86400000);return items[(day+(theme.length*7))%items.length]}
async function showBackdrop(theme){if(FX.current===theme)return;FX.current=theme;const seq=++FX.photoSeq;const p=await pickPhoto(theme);if(seq!==FX.photoSeq||!p)return;try{await preload(p.url)}catch{return}if(seq!==FX.photoSeq)return;const layers=$$('.bd-img');if(layers.length<2)return;const next=layers[FX.layer^1];next.style.backgroundImage=`url("${p.url.replace(/"/g,'%22')}")`;next.classList.add('on');layers[FX.layer].classList.remove('on');FX.layer^=1;const credit=$('#photoCredit');if(credit)credit.innerHTML=creditHTML(p);const home=$('.home-photo');if(theme==='home'&&home){home.style.backgroundImage=next.style.backgroundImage;home.classList.add('on');home.title=stripHTML(creditHTML(p))}}
globalThis.TMPhotos={commonsPhotos,creditHTML,preload,showBackdrop};

/* ---------- Integración con la navegación existente ---------- */
const fxShowTab=showTab;
showTab=function(tab){fxShowTab(tab);document.body.dataset.tab=tab;showBackdrop(tab);if(!$('#splash'))window.scrollTo?.({top:0,behavior:'smooth'})};
const fxGoHome=goHome;
goHome=function(){fxGoHome();document.body.dataset.tab='home';showBackdrop('home')};
$$('[data-home]').forEach(b=>b.onclick=goHome);$('#homeButton')&&($('#homeButton').onclick=goHome);$('.brand')&&($('.brand').onclick=e=>{e.preventDefault();goHome()});
$('.home-art')?.insertAdjacentHTML('afterbegin','<div class="home-photo"></div>');

/* ---------- Pantalla de arranque ---------- */
(function splash(){const el=$('#splash');if(!el)return;const lines=['Calibrando sensores…','Leyendo modelos ECMWF · ICON · GFS…','Sincronizando radar…','Trazando curvas de nivel…','Listo para tu ruta'];let i=0;const status=$('#splashStatus');const timer=setInterval(()=>{if(status&&i<lines.length)status.textContent=lines[i++];else clearInterval(timer)},430);
 commonsPhotos(PHOTO_QUERIES.splash).then(async items=>{const p=items[Math.floor(Math.random()*items.length)];if(!p||!$('#splash'))return;try{await preload(p.url);const ph=$('.splash-photo');if(ph){ph.style.backgroundImage=`url("${p.url.replace(/"/g,'%22')}")`;ph.classList.add('on')}}catch{}});
 let done=false;function enter(){if(done)return;done=true;clearInterval(timer);sfx('boot');buzz([10,40,18]);el.classList.add('leaving');const want=location.hash.slice(1),tab=TAB_IDS.includes(want)?want:'route';setTimeout(()=>{el.remove();document.body.classList.add('booted');enterApp(tab);showBackdrop(tab)},reduce()?10:720)}
 const reduce=()=>globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
 $('#splashEnter').addEventListener('click',enter);
 $('#splashMute').addEventListener('click',()=>setMuted(!FX.muted));
 document.addEventListener('keydown',function key(e){if(!$('#splash')){document.removeEventListener('keydown',key);return}if(e.key==='Enter'||e.key===' '){e.preventDefault();enter()}});
 setTimeout(()=>$('#splashEnter')?.focus?.({preventScroll:true}),2200);
})();
