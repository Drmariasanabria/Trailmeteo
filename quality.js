'use strict';
/* Veredicto único para toda la app (decisión, tarjeta, parte y copiloto).
   STOP / OJO / GO solo valoran la meteorología a tu hora de paso; INFO aparece cuando falta información
   para decidir (previsión incompleta, o posible nieve en la ruta sin boletín de aludes vigente).
   Un GO no certifica que la ruta sea segura: lo dice siempre. */
(function(){
const WORD={high:'STOP',medium:'OJO',low:'GO',info:'INFO',unknown:'?'},COLOR={high:'#e14545',medium:'#d4861a',low:'#1d9b72',info:'#5d6f7a',unknown:'#6a767c'};
const TITLE={high:'Replantea la salida',medium:'Sal con precauciones',low:'Meteo favorable',info:'Información insuficiente',unknown:'Datos incompletos'};
function verdict(p,snow=globalThis.TMSnow?.state?.()){
 if(!p?.rows?.length)return{level:'unknown',word:'?',title:TITLE.unknown,text:'Carga una ruta y analízala.',gaps:[],risks:[],color:COLOR.unknown};
 const rows=p.rows,medium=rows.filter(q=>q.assessment?.level==='medium').length,coverage=p.known/rows.length,risks=[...new Set(rows.flatMap(q=>q.assessment?.risks||[]))],gaps=[];
 let level=p.high?'high':medium?'medium':p.complete?'low':'unknown';
 if(coverage<.75)gaps.push(`Previsión en solo ${p.known} de ${rows.length} puntos`);
 if(snow){const av=snow.av||{};
  if(snow.relevant){
   if(av.status==='valid'&&av.level){risks.push(`Peligro de aludes ${av.level} (${['','débil','limitado','notable','fuerte','muy fuerte'][av.level]})`);if(av.level>=3&&level==='low')level='medium';if(av.level>=4&&snow.steep)level='high'}
   else gaps.push(`Posible nieve en ${snow.probable+snow.possible} sectores y ${av.status==='off'?'sin boletín de aludes (fuera de temporada)':av.status==='nozone'?'sin boletín de aludes para la zona':'sin boletín de aludes vigente'}`);
   if(snow.steep){risks.push(`${snow.steep} sectores con nieve posible junto a laderas ≥30°`);if(level==='low')level='medium'}
  }else if(snow.relevant===null)gaps.push('Nieve aún sin evaluar en tu ruta (temporada invernal y cota alta)');
 }
 if(level!=='high'&&gaps.length)level='info';
 const known=p.known+'/'+rows.length,text=level==='high'?`${p.high} puntos con condiciones exigentes a tu hora de paso. Prueba otra hora en «Comparar horas de salida».`
  :level==='medium'?`${risks.slice(0,3).join(' · ')||medium+' puntos con alguna señal'}.`
  :level==='low'?'Sin señales adversas en la meteorología consultada. No valora el estado del terreno ni certifica que la ruta sea segura.'
  :level==='info'?`Falta información para decidir: ${gaps.join(' · ')}.${risks.length?' Además: '+risks.slice(0,2).join(' · ')+'.':''}`
  :`${known} puntos con previsión. Actualiza o elige una salida más próxima.`;
 return{level,word:WORD[level],title:TITLE[level],text,gaps,risks,color:COLOR[level],coverage}}
function knowHTML(p,v){const s=globalThis.TMSnow?.state?.(),av=s?.av||{},row=(ok,k,t)=>`<li class="${ok}"><b>${k}</b><span>${t}</span></li>`;
 return `<details class="know-panel"${v.level==='info'?' open':''}><summary>Qué sabemos y qué no</summary><ul class="know-list">${
  row(v.coverage>=.75?'ok':'gap','Meteorología',`${p.known}/${p.rows.length} puntos con previsión a tu hora · previsto (modelos)`)+
  row(!s?'gap':s.relevant===false?'ok':s.relevant?'warn':'gap','Nieve en la ruta',!s?'Sin evaluar':s.relevant===false?'Sin indicios en el modelo a tu hora (no ve neveros)':s.relevant?`${s.probable} sectores probable · ${s.possible} posible · modelo y estimación`:'Pendiente de cálculo')+
  row(av.status==='valid'?'ok':'gap','Boletín de aludes',av.status==='valid'?`Nivel ${av.level} · ${av.zone} · ${av.issued}`:av.status==='off'?'Fuera de temporada: sin boletín vigente':av.status==='nozone'?'AEMET no cubre esta zona':'No disponible')+
  row(s?.steep?'warn':s?.known?'ok':'gap','Terreno',s?.known?`${s.steep} sectores con nieve posible junto a laderas ≥30° (MDT)`:'Pendientes sin calcular')+
  row(s?.obs?'ok':'gap','Observaciones de campo',s?.obs?`${s.obs} propias en 10 días`:'Ninguna reciente')
 }</ul><button type="button" class="quiet" data-go-nieve>❄ Ver nieve y aludes</button></details>`}
function apply(p=typeof currentPlan==='function'?currentPlan():null){const el=document.getElementById('goMeter');if(!el||!p)return null;const v=verdict(p);el.className='go-meter '+v.level;el.innerHTML=`<div class="dial">${v.word}</div><div><h3>${esc(v.title)}</h3><p>${esc(v.text)}</p>${knowHTML(p,v)}</div>`;try{globalThis.TMResults?.summary?.()}catch{}return v}
let t=0;function refresh(){clearTimeout(t);t=setTimeout(()=>{if(S.route?.data)apply()},150)}
globalThis.TMVerdict=Object.assign(verdict,{apply,refresh,WORD,COLOR,TITLE});
})();
