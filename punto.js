'use strict';
/* TrailMeteo 17 · Tiempo en el punto: ficha de montaña para cualquier sitio (pico, refugio, collado, pueblo o punto
   del mapa), con o sin ruta cargada. Se calcula a la altitud del punto (Open-Meteo corrige por altitud) e incluye
   viento y dirección, niebla probable, isoterma y cota de nieve, tormenta, los tres próximos días con su mejor
   ventana, y la nieve explicada en frases: cuánta ha caído y caerá, si rehiela, cuándo se ablanda y si el viento la
   transporta. Cada dato indica si es MODELO u ESTIMADO. */
(function(){
const H=3600000,PT={seq:0,data:null,key:''};
const pv=(k,t='')=>`<span class="pv pv-${k}" title="${esc(t)}">${{off:'Oficial',obs:'Observado',mod:'Modelo',est:'Estimado',none:'Sin dato'}[k]}</span>`;
const ASP=['N','NE','E','SE','S','SO','O','NO'],asp=a=>finite(a)?ASP[Math.round(((a%360)+360)%360/45)%8]:'—';
const r50=v=>finite(v)?Math.max(0,Math.round(v/50)*50):null;
const cotaOf=f=>finite(f)?(typeof snowLine==='function'?snowLine(f):r50(f-300)):null;
const day=t=>new Date(t).toLocaleDateString('es-ES',{weekday:'long',day:'numeric'});
const hm=t=>new Date(t).toLocaleTimeString('es-ES',{hour:'2-digit',minute:'2-digit'});
const one=v=>finite(v)?(Math.round(v*10)/10).toLocaleString('es-ES'):'—';
const range=v=>{if(!finite(v)||v<.5)return'0';const lo=Math.max(1,Math.floor(v*.7)),hi=Math.max(lo+1,Math.ceil(v*1.3));return lo+'–'+hi};
const WORD={high:'STOP',medium:'OJO',low:'GO',unknown:'?'};

function pointURL(loc){const p={latitude:loc.lat,longitude:loc.lon,hourly:'temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,precipitation_probability,snowfall,snow_depth,weather_code,cloud_cover,cloud_cover_low,visibility,wind_speed_10m,wind_direction_10m,wind_gusts_10m,freezing_level_height,cape',daily:'sunrise,sunset,sunshine_duration,temperature_2m_max,temperature_2m_min,precipitation_sum,snowfall_sum,wind_gusts_10m_max,wind_direction_10m_dominant',timeformat:'unixtime',timezone:'auto',forecast_days:'7',past_days:'3'};if(finite(loc.ele))p.elevation=String(loc.ele);return'https://api.open-meteo.com/v1/forecast?'+new URLSearchParams(p)}

/* ---------- Lectura de la nieve en el punto (pura: tests/v17.mjs) ---------- */
function sum(rows,a,b,k='snowfall'){return rows.filter(r=>r.time>a&&r.time<=b&&finite(r[k])).reduce((s,r)=>s+r[k],0)}
function snowBrief(rows,ele,now=Date.now()){if(!rows?.length)return null;const past=sum(rows,now-72*H,now),n24=sum(rows,now,now+24*H),n48=sum(rows,now,now+48*H),n72=sum(rows,now,now+72*H),cur=nearest(rows,now,3*H)||rows[0];
 const depth=finite(cur.snow_depth)?Math.round(cur.snow_depth*100):null,future=rows.filter(r=>r.time>=now&&r.time<now+72*H);
 const lines=[],cot=future.map(r=>cotaOf(r.freezing_level_height)).filter(finite),cmin=cot.length?Math.min(...cot):null,cmax=cot.length?Math.max(...cot):null;
 const precip=future.filter(r=>r.precipitation>=.3),wetAbove=precip.filter(r=>finite(r.freezing_level_height)&&cotaOf(r.freezing_level_height)>ele);
 let headline;
 const days=[0,1,2].map(i=>{const start=new Date(now);start.setHours(0,0,0,0);const a=start.getTime()+i*24*H,b=a+24*H;return{a,b,snow:sum(rows,Math.max(a,now),b),label:i===0?'Hoy':i===1?'Mañana':day(a)}});
 const firstSnow=days.find(d=>d.snow>=1);
 if(firstSnow){const c=rows.filter(r=>r.time>firstSnow.a&&r.time<=firstSnow.b).map(r=>cotaOf(r.freezing_level_height)).filter(finite);headline=`${firstSnow.label} nevará en el punto: ${range(firstSnow.snow)} cm nuevos${c.length?`, con la cota bajando hasta ${fmt(Math.min(...c))} m`:''}.`}
 else if(precip.length&&wetAbove.length>=precip.length/2)headline=`La precipitación prevista será de lluvia o aguanieve aquí: la cota de nieve (${fmt(cmin)}–${fmt(cmax)} m) queda por encima de los ${fmt(ele)} m del punto.`;
 else if(depth>=5)headline=`Sin nieve nueva en 3 días. Manto modelado en el punto: unos ${depth} cm.`;
 else if(finite(cmin)&&cmin<=ele+200)headline=`Sin precipitación relevante, pero la cota de nieve (${fmt(cmin)} m) ronda la altitud del punto: posibles neveros viejos y hielo.`;
 else headline='No se espera nieve en el punto en los próximos 3 días.';
 if(past>=.5)lines.push(['Han caído',`${one(past)} cm en los últimos 3 días`,'mod']);
 lines.push(['Nieve nueva',`${one(n24)} cm en 24 h · ${one(n48)} cm en 48 h · ${one(n72)} cm en 72 h`,'mod']);
 if(finite(depth))lines.push(['En el suelo',depth>=1?`unos ${depth} cm (modelo, no ve neveros ni ventisqueros)`:'sin manto en el modelo','mod']);
 if(finite(cmin))lines.push(['Cota de nieve',cmin===cmax?`${fmt(cmin)} m`:`entre ${fmt(cmin)} y ${fmt(cmax)} m (3 días)`,'est']);
 const relevant=(depth||0)>=5||past>=2||n72>=2||(finite(cmin)&&cmin<=ele+300);
 let refreeze=null,windload=null;
 if(relevant){const night=rows.filter(r=>{const h=new Date(r.time).getHours();return r.time>now&&r.time<now+30*H&&(h>=22||h<=7)});const tmin=night.length?Math.min(...night.map(r=>r.temperature_2m).filter(finite)):null;
  if(finite(tmin)){const morning=rows.find(r=>r.time>(night.at(-1)?.time||now)&&r.temperature_2m>1&&new Date(r.time).getHours()>=7);
   refreeze=tmin<=-1?{kind:'hard',text:`Rehiela de noche (mínima ${one(tmin)} °C): nieve dura y helada a primera hora; lleva crampones y cuchillas.${morning?` Se ablanda hacia las ${hm(morning.time)} en solanas.`:' Puede no ablandarse en todo el día.'}`}:tmin<1?{kind:'weak',text:`Rehielo débil (mínima ${one(tmin)} °C): costra fina que cede pronto.`}:{kind:'none',text:`No rehiela (mínima ${one(tmin)} °C): nieve húmeda y pesada desde el amanecer; más probables las purgas y aludes de fusión.`};lines.push(['Rehielo',refreeze.text,'est'])}
  const windy=rows.filter(r=>r.time>now&&r.time<now+48*H&&r.wind_gusts_10m>=45);if(windy.length&&((depth||0)>=10||past>=3||n48>=3)){const top=windy.reduce((a,b)=>b.wind_gusts_10m>a.wind_gusts_10m?b:a),lee=finite(top.wind_direction_10m)?asp(top.wind_direction_10m+180):null;windload={gust:Math.round(top.wind_gusts_10m),from:asp(top.wind_direction_10m),lee,time:top.time};lines.push(['Viento y nieve',`Rachas de hasta ${windload.gust} km/h del ${windload.from} (${day(top.time)}): el viento transporta nieve${lee?`; placas probables en laderas orientadas al ${lee}`:''}.`,'est'])}}
 return{headline,lines,past,n24,n48,n72,depth,cmin,cmax,relevant,refreeze,windload}}

/* ---------- Niebla y tormenta (estimaciones con su nombre) ---------- */
function fogAt(h){if(!h)return null;const rh=h.relative_humidity_2m,vis=h.visibility,low=h.cloud_cover_low;if(finite(vis)&&vis<1000||rh>=97&&(low??100)>=70)return['Probable','high'];if(rh>=92&&(low??0)>=50||finite(vis)&&vis<5000)return['Posible','medium'];return['Poco probable','low']}
function stormAt(h){if(!h)return null;if(h.weather_code>=95)return['Prevista','high'];if(finite(h.cape)&&h.cape>=800&&(h.precipitation_probability??0)>=30)return['Posible','medium'];if(finite(h.cape)&&h.cape>=400)return['Baja','low'];return['No','low']}
function windows(rows,a,b){const day=rows.filter(r=>r.time>=a&&r.time+H<=b);let best=null;for(let i=0;i+2<day.length;i++){const w=day.slice(i,i+3);if(w[2].time-w[0].time!==2*H)continue;const s=w.reduce((x,r)=>x+penalty(r),0);if(!best||s<best.s)best={s,from:w[0].time,to:w[2].time+H,a:assess(w.reduce((m,r)=>penalty(r)>penalty(m)?r:m))}}return best}

/* ---------- Render ---------- */
function mount(){if($('#ptCard'))return;$('#daySummary')?.insertAdjacentHTML('afterend','<section id="ptCard" class="pt card" aria-live="polite"></section>')}
function tile(label,value,sub,prov,cls=''){return`<div class="pt-tile ${cls}"><span class="pt-l">${label}</span><b>${value}</b><small>${sub||''}</small>${prov?pv(prov):''}</div>`}
function arrow(dir){return finite(dir)?`<svg class="pt-arrow" viewBox="0 0 24 24" style="transform:rotate(${Math.round(dir+180)}deg)" aria-hidden="true"><path d="M12 3v18M6 9l6-6 6 6"/></svg>`:''}
function render(){const el=$('#ptCard');if(!el)return;const d=PT.data,loc=S.location;if(!d){el.innerHTML=`<p class="muted">Consultando el tiempo en ${esc(loc?.name||'el punto')}…</p>`;return}
 const rows=hours(d),now=Date.now(),h=nearest(rows,now,2*H),ele=Math.round(d.elevation),kind=loc.kind&&loc.kind!=='lugar'?TMPlaces?.label?.(loc.kind)||'':'';
 const cota=cotaOf(h?.freezing_level_height),fog=fogAt(h),storm=stormAt(h),sb=snowBrief(rows,ele,now),fav=globalThis.TMPlaces?.isFav?.(loc);
 const daily=d.daily||{},dayCards=[0,1,2].map(i=>{const t=(daily.time?.[i+3]??null);if(t==null)return'';const a=t*1000,b=a+24*H,sr=daily.sunrise?.[i+3]*1000,ss=daily.sunset?.[i+3]*1000,w=windows(rows,Math.max(finite(sr)?sr:a+7*H,i===0?Math.floor(now/H)*H:0),finite(ss)?ss:a+19*H),tmax=daily.temperature_2m_max?.[i+3],tmin=daily.temperature_2m_min?.[i+3],g=daily.wind_gusts_10m_max?.[i+3],pr=daily.precipitation_sum?.[i+3],sn=daily.snowfall_sum?.[i+3],sun=daily.sunshine_duration?.[i+3];
  return`<article class="pt-day"><header><b>${i===0?'Hoy':i===1?'Mañana':esc(day(a))}</b>${w?`<span class="pill ${w.a.level}">${WORD[w.a.level]||'?'}</span>`:''}</header><p class="pt-temp">${finite(tmin)?Math.round(tmin):'—'}° <span>/</span> ${finite(tmax)?Math.round(tmax):'—'}°</p><ul><li>Rachas <b>${finite(g)?Math.round(g):'—'} km/h</b></li><li>Precipitación <b>${one(pr)} mm</b></li>${sn>=.5?`<li>Nieve <b>${one(sn)} cm</b></li>`:''}<li>Sol <b>${finite(sun)?one(sun/3600):'—'} h</b></li></ul>${w?`<p class="pt-win">Mejor ventana <b>${hm(w.from)}–${hm(w.to)}</b></p>`:''}</article>`}).join('');
 const near=globalThis.TMWebcams?.near?.(loc.lat,loc.lon,15)||[];
 el.innerHTML=`<div class="pt-head"><div><p class="eyebrow">TIEMPO EN EL PUNTO</p><h2>${esc(loc.name)}</h2><p class="pt-meta">${[kind,`${fmt(ele)} m${finite(loc.ele)?' (altitud del lugar)':' (terreno del modelo, MDT 90 m)'}`,`${loc.lat.toFixed(4)}, ${loc.lon.toFixed(4)}`].filter(Boolean).map(esc).join(' · ')}</p></div>
  <div class="pt-actions">${(()=>{const rf=globalThis.TMRefugios?.near?.(loc.lat,loc.lon,.5);return rf?`<button type="button" class="primary" data-pt="refu" data-id="${rf.id}">Ficha del refugio</button>`:''})()}<button type="button" class="quiet" data-pt="fav" aria-pressed="${!!fav}">${fav?'★ Favorito':'☆ Guardar'}</button><button type="button" class="quiet" data-pt="map">Ver en el mapa</button><button type="button" class="quiet" data-pt="snow">Nieve aquí</button><button type="button" class="quiet" data-pt="cams">Webcams${near.length?` (${near.length})`:''}</button></div></div>
 <div class="pt-tiles">${tile('Temperatura',`${finite(h?.temperature_2m)?one(h.temperature_2m):'—'} °C`,`sensación ${finite(h?.apparent_temperature)?one(h.apparent_temperature):'—'} °C`,'mod')}${tile('Viento',`${arrow(h?.wind_direction_10m)}${finite(h?.wind_speed_10m)?Math.round(h.wind_speed_10m):'—'} km/h`,`del ${asp(h?.wind_direction_10m)} · rachas ${finite(h?.wind_gusts_10m)?Math.round(h.wind_gusts_10m):'—'}`,'mod',h?.wind_gusts_10m>=60?'bad':h?.wind_gusts_10m>=35?'warn':'')}${tile('Niebla en el punto',fog?fog[0]:'—',`humedad ${finite(h?.relative_humidity_2m)?Math.round(h.relative_humidity_2m):'—'} % · nubes bajas ${finite(h?.cloud_cover_low)?Math.round(h.cloud_cover_low):'—'} %`,'est',fog?.[1]==='high'?'warn':'')}${tile('Visibilidad',finite(h?.visibility)?(h.visibility>=10000?'>10 km':one(h.visibility/1000)+' km'):'—','','mod')}${tile('Isoterma 0 °C',finite(h?.freezing_level_height)?fmt(r50(h.freezing_level_height))+' m':'—',finite(h?.freezing_level_height)?(h.freezing_level_height<ele?'el punto está por encima: hiela':'por encima del punto'):'','mod')}${tile('Cota de nieve',finite(cota)?fmt(cota)+' m':'—',typeof calibration==='function'&&calibration()?'calibrada con satélite':'isoterma − 300 m','est')}${tile('Tormenta',storm?storm[0]:'—',finite(h?.cape)?`energía convectiva ${Math.round(h.cape)} J/kg`:'','est',storm?.[1]==='high'?'bad':storm?.[1]==='medium'?'warn':'')}${tile('Nieve en el suelo',finite(sb?.depth)?(sb.depth>=1?sb.depth+' cm':'sin manto'):'—','según el modelo','mod')}</div>
 <div class="pt-days">${dayCards}</div>
 ${sb?`<div class="pt-snow"><p class="pt-snow-h"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2v20M3.3 7l17.4 10M20.7 7 3.3 17"/></svg><span>${esc(sb.headline)}</span></p><dl>${sb.lines.map(([k,v,p])=>`<div><dt>${esc(k)} ${pv(p)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl><p id="ptAv" class="pt-av"></p></div>`:''}
 ${near.length?`<div class="pt-cams" id="ptCams">${near.slice(0,4).map(c=>globalThis.TMWebcams.thumb(c)).join('')}</div>`:''}
 <p class="footnote">Modelo Open-Meteo a ${fmt(ele)} m. El modelo no ve neveros, ventisqueros ni efectos locales del relieve (vientos canalizados, nieblas de valle). Orientativo: contrasta con AEMET y en el refugio.</p>`;
 el.onclick=e=>{const b=e.target.closest('[data-pt]');if(!b)return;const k=b.dataset.pt;if(k==='refu'){enterApp('refugios');TMRefugios.show(b.dataset.id);return}if(k==='fav'){const on=TMPlaces.toggleFav(loc);b.textContent=on?'★ Favorito':'☆ Guardar';b.setAttribute('aria-pressed',String(on))}else if(k==='map'){enterApp('mapa');globalThis.TMMap?.focus?.(loc)}else if(k==='snow')showTab('nieve');else if(k==='cams'){enterApp('webcams');globalThis.TMWebcams?.focusNear?.(loc)}};
 renderAv(loc)}
async function renderAv(loc){const out=$('#ptAv');if(!out||typeof loadAludes!=='function')return;await loadAludes();const z=avZone(loc.lat,loc.lon);if(!$('#ptAv'))return;
 out.innerHTML=!z?`${pv('none')} AEMET no publica boletín de aludes para esta zona.`:z.status==='valid'&&z.level_max?`${pv('off')} Aludes en ${esc(z.name)}: <b>nivel ${z.level_max} (${['','débil','limitado','notable','fuerte','muy fuerte'][z.level_max]})</b>${z.issued?` · emitido ${esc(z.issued)}`:''}. <a href="${esc(z.pdf)}" target="_blank" rel="noopener">Boletín ↗</a>`:`${pv('off')} ${esc(z.name)}: ${z.status==='off'?'campaña de aludes finalizada o sin comenzar':'sin boletín vigente'}. <a href="${esc(z.page||z.pdf)}" target="_blank" rel="noopener">AEMET ↗</a>`}
async function load(){const loc=S.location;if(!loc||!$('#ptCard'))return;const key=pointURL(loc);if(key===PT.key&&PT.data){render();return}const my=++PT.seq;PT.data=null;PT.key=key;render();try{const d=await json(key,900000);if(my!==PT.seq)return;PT.data=d;render()}catch(e){if(my!==PT.seq)return;$('#ptCard').innerHTML=`<p class="load-fail">No se pudo cargar el tiempo en el punto: ${esc(e.message)}</p>`}}
mount();
const prevSet=setLocation;setLocation=async function(){const r=await prevSet.apply(this,arguments);load();return r};
const prevShow=showTab;showTab=function(t){prevShow.apply(this,arguments);if(t==='now'){mount();load()}};
if(S.tab==='now')setTimeout(load,0);
document.addEventListener('tm:webcams',()=>{if(PT.data&&$('#ptCard'))render()});document.addEventListener('tm:refugios',()=>{if(PT.data&&$('#ptCard'))render()});
globalThis.TMPoint={snowBrief,fogAt,stormAt,windows,pointURL,load,get data(){return PT.data}};
})();
