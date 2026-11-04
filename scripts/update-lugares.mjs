/* Nomenclátor de montaña para el buscador, leído de las teselas vectoriales de OpenFreeMap (OpenMapTiles, datos de OpenStreetMap).
   Son las mismas teselas que pinta el mapa: un CDN rápido y estable, sin depender de Overpass (que se satura a menudo).
   Recorre a zoom 14 (donde están todos los picos, collados, refugios, lagos y pueblos) la zona de Picos de Europa y la
   Cordillera Cantábrica central y oriental, y escribe data/lugares.json con el mismo formato que scripts/update-lugares.py:
   [nombre, otros nombres, tipo, lat, lon, altitud, origen]. Las coordenadas son las del elemento de OpenStreetMap.
   Uso: node scripts/update-lugares.mjs [--bbox sur,oeste,norte,este] */
import fs from 'node:fs';import path from 'node:path';import {fileURLToPath} from 'node:url';
import {decodeTile,tileToLonLat,lonLatToTile} from './mvt.mjs';

export const BBOX=[42.80,-6.10,43.45,-3.70];
const Z=14,TILEJSON='https://tiles.openfreemap.org/planet',UA='TrailMeteo/18 (https://github.com/wilderwests/Trailmeteo)',BUDGET=360e3;

/* Tipo de lugar en TrailMeteo a partir de la capa y la clase de OpenMapTiles. Lo que no sirve para orientarse en el monte se descarta. */
export function kindOf(layer,p){
 if(layer==='mountain_peak')return{peak:'pico',volcano:'pico',saddle:'collado',ridge:'cresta',arete:'cresta'}[p.class]||null;
 if(layer==='water_name')return['lake','pond','reservoir'].includes(p.class)?'lago':null;
 if(layer==='place')return{town:'pueblo',village:'pueblo',hamlet:'pueblo',isolated_dwelling:'paraje',locality:'paraje'}[p.class]||null;
 if(layer==='poi'){const s=p.subclass;if(s==='alpine_hut')return'refugio';if(s==='wilderness_hut'||s==='shelter')return'cabaña';if(s==='viewpoint')return'mirador';
  if(s==='spring'||s==='drinking_water')return'fuente';if(s==='cave_entrance')return'cueva';if(p.class==='aerialway'&&s==='station')return'teleférico';return null}
 return null}

const latin=s=>/^[\p{Script=Latin}\p{N}\s'’·.,()\-/]+$/u.test(s);
/* Otros nombres: castellano, asturiano y los que usan otras lenguas («Naranjo de Bulnes» para el Picu Urriellu). */
export function altNames(p){const main=String(p.name||'').trim(),out=[];
 for(const [k,v] of Object.entries(p)){if(!(k==='name:es'||k==='name:ast'||k==='alt_name'||k==='old_name'||k==='loc_name'||/^name:[a-z]{2,3}$/.test(k)||k==='name_int'))continue;
  for(let s of String(v).split(/\s*[\/;]\s*/)){s=s.trim();if(!s||s===main||/^categor[ií]a:/i.test(s)||!latin(s)||out.includes(s))continue;out.push(s)}}
 return out.slice(0,6)}

/* Convierte los objetos de una tesela en lugares. Ignora los que caen en el margen de la tesela vecina (se cuentan allí). */
export function placesFromTile(z,x,y,features){const out=[];
 for(const f of features){const p=f.props||{};if(!p.name||f.x<0||f.x>=1||f.y<0||f.y>=1)continue;const kind=kindOf(f.layer,p);if(!kind)continue;
  const [lon,lat]=tileToLonLat(z,x,y,f.x,f.y),ele=Number.isFinite(+p.ele)&&+p.ele>-100&&+p.ele<5000?Math.round(+p.ele):null;
  out.push([String(p.name).trim(),altNames(p),kind,+lat.toFixed(5),+lon.toFixed(5),ele,'omt'])}
 return out}

const ORDER={pico:0,refugio:1,collado:2,cabaña:3,lago:4,paraje:5,mirador:6,fuente:7,pueblo:8};
const km=(a,b)=>{const r=Math.PI/180,dl=(b[3]-a[3])*r,dn=(b[4]-a[4])*r,h=Math.sin(dl/2)**2+Math.cos(a[3]*r)*Math.cos(b[3]*r)*Math.sin(dn/2)**2;return 12742*Math.asin(Math.sqrt(h))};
/* Quita repetidos (un lago grande tiene etiqueta en varias teselas): mismo nombre y tipo a menos de 400 m. */
export function dedupe(list){const seen=new Map(),out=[];
 for(const p of list){const k=p[0].toLowerCase()+'|'+p[2],prev=seen.get(k)||[];if(prev.some(q=>km(p,q)<.4))continue;prev.push(p);seen.set(k,prev);out.push(p)}
 return out.sort((a,b)=>(ORDER[a[2]]??9)-(ORDER[b[2]]??9)||a[0].localeCompare(b[0],'es'))}

export function tilesFor(b=BBOX,z=Z){const [x0,y0]=lonLatToTile(z,b[1],b[2]),[x1,y1]=lonLatToTile(z,b[3],b[0]),out=[];for(let x=x0;x<=x1;x++)for(let y=y0;y<=y1;y++)out.push([x,y]);return out}

async function get(url,ms=25e3){const c=new AbortController(),t=setTimeout(()=>c.abort(),ms);try{const r=await fetch(url,{headers:{'User-Agent':UA},signal:c.signal});if(r.status===204||r.status===404)return null;if(!r.ok)throw new Error('HTTP '+r.status);return new Uint8Array(await r.arrayBuffer())}finally{clearTimeout(t)}}

export async function build(b=BBOX,{budget=BUDGET,workers=12,log=console.error}={}){const t0=Date.now();
 const tj=JSON.parse(new TextDecoder().decode(await get(TILEJSON))),tpl=tj.tiles[0],jobs=tilesFor(b);let i=0,failed=0;const all=[];
 await Promise.all(Array.from({length:workers},async()=>{while(i<jobs.length){if(Date.now()-t0>budget){failed+=jobs.length-i;i=jobs.length;break}const [x,y]=jobs[i++];
  let buf=null,ok=false;for(let a=0;a<3&&!ok;a++){try{buf=await get(tpl.replace('{z}',Z).replace('{x}',x).replace('{y}',y));ok=true}catch(e){if(a===2)log('Tesela',Z,x,y,'falló:',e.message);else await new Promise(r=>setTimeout(r,800*(a+1)))}}
  if(!ok){failed++;continue}if(buf)try{all.push(...placesFromTile(Z,x,y,decodeTile(buf)))}catch(e){failed++;log('Tesela',Z,x,y,'ilegible:',e.message)}}}));
 return{places:dedupe(all),tiles:jobs.length,failed,version:tpl.split('/').slice(-4,-3)[0]}}

async function main(){const dest=path.join(path.dirname(fileURLToPath(import.meta.url)),'..','data','lugares.json');const ai=process.argv.indexOf('--bbox'),b=ai>0?process.argv[ai+1].split(',').map(Number):BBOX;
 const {places,tiles,failed,version}=await build(b);
 if(places.length<500||failed>tiles*.2){console.error(`Nomenclátor incompleto (${places.length} lugares, ${failed}/${tiles} teselas fallidas): se conserva el anterior`);process.exit(1)}
 fs.writeFileSync(dest,JSON.stringify({fetched:new Date().toISOString(),source:'OpenStreetMap contributors (ODbL) · teselas OpenFreeMap '+(version||''),bbox:b,partial:failed>0,
  fields:['nombre','otros nombres','tipo','lat','lon','altitud','origen'],places}));
 console.log('Lugares (teselas):',places.length,'·',tiles,'teselas ·',failed,'fallidas')}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))main().catch(e=>{console.error(e);process.exit(1)});
