import {Window} from 'happy-dom';import fs from 'node:fs';import assert from 'node:assert/strict';import {indexedDB} from 'fake-indexeddb';import xmldom from '@xmldom/xmldom';
const w=new Window({url:'http://localhost:8765/',settings:{disableJavaScriptFileLoading:true,disableCSSFileLoading:true}});w.DOMParser=xmldom.DOMParser;w.indexedDB=indexedDB;w.structuredClone=structuredClone;w.IntersectionObserver=class{observe(){}unobserve(){}};w.scrollTo=()=>{};w.HTMLElement.prototype.scrollIntoView=()=>{};
w.document.write(fs.readFileSync('index.html','utf8'));w.eval(fs.readFileSync('core.js','utf8'));
const start=Math.floor(Date.now()/3600000)*3600;let aiCalls=[],commons=0;
function forecast(u){const time=Array.from({length:168},(_,i)=>start+i*3600),hourly={time};for(const k of (u.searchParams.get('hourly')||'temperature_2m').split(','))for(const id of u.searchParams.get('models')?.split(',')||[''])hourly[k+(id?'_'+id:'')]=time.map(()=>k==='temperature_2m'?4:k==='apparent_temperature'?-1:k==='wind_gusts_10m'?40:k==='visibility'?10000:k==='freezing_level_height'?900:k==='precipitation'?.5:0);const daily={sunrise:[start-3600],sunset:[start+12*3600]};const d={timezone:'Europe/Madrid',elevation:1000,current:{temperature_2m:4,weather_code:61},hourly,daily};return u.searchParams.get('latitude').split(',').length>1?u.searchParams.get('latitude').split(',').map(()=>structuredClone(d)):d}
w.fetch=async(url,opts={})=>{const u=new URL(url,'http://localhost:8765');let d;
 if(u.hostname==='text.pollinations.ai'){const body=JSON.parse(opts.body);aiCalls.push(body);d={choices:[{message:{content:'**Sal a las 9:00**\n- Lleva chaqueta\n- Vigila el km 1'}}]}}
 else if(u.hostname==='commons.wikimedia.org'){commons++;d={query:{pages:{1:{title:'File:Picos.jpg',imageinfo:[{thumburl:'https://upload.wikimedia.org/x/Picos.jpg',url:'https://upload.wikimedia.org/x/Picos.jpg',descriptionurl:'https://commons.wikimedia.org/wiki/File:Picos.jpg',width:3000,height:2000,mime:'image/jpeg',extmetadata:{Artist:{value:'<a>Autora</a>'},LicenseShortName:{value:'CC BY-SA 4.0'},LicenseUrl:{value:'https://creativecommons.org/licenses/by-sa/4.0'}}}]},2:{title:'File:Vertical.jpg',imageinfo:[{thumburl:'https://upload.wikimedia.org/x/V.jpg',width:1000,height:3000,mime:'image/jpeg',extmetadata:{LicenseShortName:{value:'CC0'}}}]}}}}}
 else if(u.pathname.includes('mountain.json'))d=JSON.parse(fs.readFileSync('data/mountain.json'));
 else if(u.pathname.includes('alerts.json'))d={complete:true,fetched:new Date().toISOString(),alerts:[]};
 else if(u.hostname==='overpass-api.de')d={elements:[],osm3s:{}};
 else if(u.hostname==='api.met.no')d={properties:{timeseries:[]}};
 else if(u.hostname==='r.jina.ai')return{ok:true,text:async()=>String(url).includes('duckduckgo')?'## [Canal de Trea - Wikiloc | Ruta Senderismo](https://es.wikiloc.com/rutas-senderismo/canal-de-trea-12345678)\nDistancia 8,5 km · Desnivel positivo 1.250 m · Difícil\n## [Otra](https://blog.example/x)':'<html><title>Canal de Trea | Wikiloc</title><script>var d={"geometry":{"coordinates":['+Array.from({length:40},(_,i)=>`[${(-4.87+i*.001).toFixed(5)},${(43.22+i*.0008).toFixed(5)}]`).join(',')+']}}</script></html>'};
 else if(u.hostname==='api.open-meteo.com'&&u.pathname.includes('elevation'))d={elevation:u.searchParams.get('latitude').split(',').map((_,i)=>500+i*20)};
 else d=forecast(u);return{ok:true,status:200,json:async()=>d,text:async()=>JSON.stringify(d)}};
const scripts=['app.js','mountain.js','expedition-core.js','expedition.js','terrain.js','route-library.js','home.js','public-sources.js','route-knowledge.js','cares-archive.js','fx.js','firebase-config.js','ai.js','wikiloc.js','canales.js','gear.js','field-core.js','field.js','pois.js'];
w.eval(scripts.map(s=>fs.readFileSync(s,'utf8')).join('\n')+'\nglobalThis.T={get route(){return S.route},importRoute,enterApp,showTab,get S(){return S}};');
await new Promise(r=>setTimeout(r,150));
const $=s=>w.document.querySelector(s),$$=s=>[...w.document.querySelectorAll(s)];
// Arranque y navegación
assert.ok($('#splash'),'splash visible al cargar');assert.equal($('#main').hidden,true);
$('#splashEnter').click();await new Promise(r=>setTimeout(r,800));assert.equal($('#splash'),null,'splash retirado');assert.equal($('#main').hidden,false);assert.equal($('#pane-route').hidden,false,'el arranque lleva al planificador');
assert.equal($$('.tabs [data-tab]')[0].dataset.tab,'route');assert.ok($('[data-tab="canales"]'));
w.T.showTab('canales');assert.equal($('#pane-canales').hidden,false);
// Fotos con atribución
assert.ok(commons>0);const photos=await w.TMPhotos.commonsPhotos('Picos de Europa');assert.equal(photos.length,1,'filtra verticales y sin licencia');assert.equal(photos[0].artist,'Autora');assert.match(w.TMPhotos.creditHTML(photos[0]),/CC BY-SA 4\.0/);
// Canales
assert.equal($$('#cnGrid .cn-card').length,15);assert.equal($$('#caresArchive .cares-route').length,15);
$('[data-cn-filter="water"]').click();assert.ok($$('#cnGrid .cn-card').length<15&&$$('#cnGrid .cn-card').length>0);$('[data-cn-filter="all"]').click();
$('#cnSearch').value='Cuarroble';$('#cnSearch').dispatchEvent(new w.Event('input'));assert.ok($$('#cnGrid .cn-card').some(c=>/Trea/.test(c.textContent)));$('#cnSearch').value='';$('#cnSearch').dispatchEvent(new w.Event('input'));
w.TMCanales.open(7);assert.match($('#cnDetail').textContent,/Vega de Ario/);assert.match($('#cnDetail').textContent,/2025/);assert.equal($$('#cnDetail .cn-steps li').length>=3,true);assert.ok($('#cnDetail svg.cn-profile'));
const ctx=JSON.parse(w.Copilot.context());assert.equal(ctx.canal_del_cares.canal,'Trea');$('#cnClose').click();assert.equal($('#cnDetail'),null);
// Wikiloc
const md='1. [Canal de Trea - Wikiloc](https://duckduckgo.com/l/?uddg=https%3A%2F%2Fes.wikiloc.com%2Frutas-senderismo%2Fcanal-de-trea-12345678)\nDistancia 8,5 km · Desnivel 1.250 m · Moderado\n2. [Blog](https://blog.example/x)';
const parsed=w.TMWikiloc.parse(md);assert.equal(parsed.length,1);assert.equal(parsed[0].id,'12345678');assert.equal(parsed[0].km,'8,5');assert.equal(parsed[0].level,'Moderado');
assert.equal(JSON.stringify(w.TMWikiloc.decodePolyline('_p~iF~ps|U_ulLnnqC_mqNvxq`@').map(p=>[p.lat,p.lon])),'[[38.5,-120.2],[40.7,-120.95],[43.252,-126.453]]');
assert.equal(w.TMWikiloc.extractGeometry('<p>sin datos</p>'),null);
w.T.showTab('route');const found=await w.TMWikiloc.search('Canal de Trea');assert.equal(found.length,1);assert.equal($$('#wlResults .wl-card').length,1);
await w.TMWikiloc.loadTrail(found[0]);assert.equal(w.T.route.name,'Canal de Trea');assert.equal(w.T.route.points.length,40);assert.equal(w.T.route.summary.elevationComplete,true,'altitudes añadidas');assert.match($('#wlStatus').textContent,/cargada desde Wikiloc/);
await new Promise(r=>setTimeout(r,100));
// Semáforo, mochila y compartir
assert.equal($('#expeditionPanel').hidden,false);assert.match($('#goMeter').textContent,/OJO|STOP|GO|\?/);const gear=$$('#gearList .gear-item').map(x=>x.textContent).join(' ');assert.match(gear,/Agua/);assert.match(gear,/impermeable/);assert.match(gear,/microcrampones/,'isoterma bajo la cota máxima');assert.match(gear,/Cortavientos/);assert.ok($('#shareExpedition'));
// Copiloto: proveedor gratuito sin Firebase, contexto real y adaptador de botones existentes
assert.equal(w.Copilot.provider(),'free');assert.equal(w.Copilot.parseFirebaseConfig('const firebaseConfig = {\n apiKey: "AIzaX",\n authDomain: "p.firebaseapp.com",\n projectId: "p",\n appId: "1:2:web:3", // app\n};').projectId,'p');assert.equal(w.Copilot.parseFirebaseConfig('{apiKey:"x"}'),null);
const before=aiCalls.length;const out=await w.Copilot.ask('¿A qué hora salgo?');assert.match(out.text,/9:00/);const last=aiCalls.at(-1);assert.ok(aiCalls.length>before);assert.match(last.messages.at(-1).content,/Canal de Trea/,'el contexto incluye la ruta');assert.match(last.messages.at(-1).content,/sectores/);assert.match($('#cpLog').textContent,/Lleva chaqueta/);assert.equal($$('#cpLog li').length>=2,true,'markdown en listas');
assert.equal(w.Copilot.md('<img src=x onerror=alert(1)> [x](javascript:alert(1))').includes('<img'),false);assert.equal(w.Copilot.md('[x](javascript:alert(1))').includes('href'),false);
const ai=w.T.S.qwen;const r=await ai.chat.completions.create({messages:[{role:'system',content:'S'},{role:'user',content:'U'}]});assert.match(r.choices[0].message.content,/9:00/);
// v9 · En ruta, temas, menú Más, fuentes y refugios
w.T.showTab('field');assert.equal($('#pane-field').hidden,false);assert.equal(w.document.body.dataset.tab,'field');
const F=w.Field;F.state.watch=1;const rp=w.T.route.points;const pos=(lat,lon,acc=8)=>({coords:{latitude:lat,longitude:lon,altitude:1200,accuracy:acc,speed:1.2,heading:90},timestamp:Date.now()});
F.onPosition(pos(rp[10].lat,rp[10].lon));assert.match($('#fieldReadouts').textContent,/Fuera de ruta/);assert.equal($('#fa-off'),null);assert.equal(F.state.track.length,1);
F.onPosition(pos(rp[10].lat+.006,rp[10].lon));F.onPosition(pos(rp[10].lat+.0062,rp[10].lon));assert.match($('#fa-off').textContent,/Fuera del track/);
F.onPosition(pos(rp[12].lat,rp[12].lon));assert.match($('#fa-off').textContent,/De nuevo sobre el track/);
const strike=F.recordStrike(20);assert.ok(strike.km<10);assert.match($('#fa-storm').textContent,/Rayos a 6,9 km/);assert.equal(F.recordStrike(10).trend,'se acerca');
const msg=F.sosMessage();assert.match(msg,/UTM 30T \d+ E \d+ N/);assert.match(msg,/Canal de Trea/);assert.match($('#sosCoords').textContent,/UTM/);
const ti=F.turnInfo();assert.ok(['outback','none'].includes(ti.mode));assert.match($('#sunRows').textContent,/Amanecer/);
assert.ok($('#compassTarget').options.length>=2);F.state.watch=null;
const rows=w.TMPois.rows(w.T.route,[{type:'node',id:1,lat:rp[30].lat+.0005,lon:rp[30].lon,tags:{natural:'spring',name:'Fuente Cuarroble'}},{type:'node',id:2,lat:rp[5].lat,lon:rp[5].lon+.0003,tags:{tourism:'alpine_hut',name:'Refugio'}},{type:'node',id:3,lat:44,lon:-4,tags:{amenity:'drinking_water'}},{type:'node',id:4,lat:rp[8].lat,lon:rp[8].lon,tags:{amenity:'bench'}}]);assert.equal(rows.length,2);assert.equal(rows[0].kind,'alpine_hut');assert.ok(rows[0].km<rows[1].km);
w.TMTheme.apply('night');assert.equal(w.document.documentElement.dataset.theme,'night');w.TMTheme.apply('day');assert.equal(w.document.documentElement.dataset.theme,undefined);
w.TMTheme.openMore();assert.ok($('#moreSheet'));$('#moreSheet [data-more="canales"]').click();assert.equal($('#moreSheet'),null);assert.equal($('#pane-canales').hidden,false);
console.log('v8/v9 checks passed: field mode (off-route alarm, storm, SOS/UTM, turnaround, compass targets), POIs near track, themes, Más sheet, splash→planner, dock order, Commons attribution, 15 visual canales + filters/search/detail, Wikiloc parse/search/load with elevation, go-meter + gear, copilot context/markdown safety/adapter.');await w.happyDOM.close();
