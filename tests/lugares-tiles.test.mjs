/* Nomenclátor desde teselas vectoriales: lector MVT propio, tipos, nombres alternativos, márgenes y repetidos. Sin red. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
/* Los generadores viven en scripts/; en la prueba de la versión minificada (public/tests) están un nivel más arriba. */
const dir=fs.existsSync(new URL('../scripts/mvt.mjs',import.meta.url))?'../scripts/':'../../scripts/';
const {decodeTile,tileToLonLat,lonLatToTile}=await import(dir+'mvt.mjs');
const {placesFromTile,dedupe,kindOf,altNames,tilesFor}=await import(dir+'update-lugares.mjs');

/* Codificador mínimo (solo para la prueba): capas con puntos y valores de texto o enteros. */
const vint=n=>{const o=[];do{let b=n%128;n=Math.floor(n/128);if(n)b|=128;o.push(b)}while(n);return o};
const zz=n=>n<0?-2*n-1:2*n;const fld=(f,t)=>vint(f*8+t);const lenD=(f,bytes)=>[...fld(f,2),...vint(bytes.length),...bytes];const str=s=>[...new TextEncoder().encode(s)];
function layer(name,feats,extent=4096){const keys=[],vals=[],kid=k=>{let i=keys.indexOf(k);if(i<0){keys.push(k);i=keys.length-1}return i},vid=v=>{let i=vals.findIndex(x=>x===v);if(i<0){vals.push(v);i=vals.length-1}return i};
 const fb=feats.map(({props,x,y})=>{const tags=Object.entries(props).flatMap(([k,v])=>[kid(k),vid(v)]);const geom=[9,zz(x),zz(y)];return lenD(2,[...lenD(2,tags.flatMap(vint)),...fld(3,0),...vint(1),...lenD(4,geom.flatMap(vint))])});
 const vb=vals.map(v=>lenD(4,typeof v==='string'?lenD(1,str(v)):[...fld(4,0),...vint(v)]));
 return lenD(3,[...fld(15,0),...vint(2),...lenD(1,str(name)),...fb.flat(),...keys.flatMap(k=>lenD(3,str(k))),...vb.flat(),...fld(5,0),...vint(extent)])}

const [tx,ty]=lonLatToTile(14,-4.8177,43.2008);
/* Posición dentro de la tesela del Picu Urriellu real (43.20084, -4.81770). */
const n=2**14,fx=((-4.8177+180)/360*n-tx),r=43.20084*Math.PI/180,fy=((1-Math.log(Math.tan(r)+1/Math.cos(r))/Math.PI)/2*n-ty);
const tile=new Uint8Array([
 ...layer('mountain_peak',[{props:{name:'Picu Urriellu','name:es':'Pico Urriellu','name:en':'Naranjo de Bulnes  / Picu Urriellu','name:ja':'ナランホ',class:'peak',ele:2518},x:Math.round(fx*4096),y:Math.round(fy*4096)},
  {props:{name:'Collada Bonita',class:'saddle',ele:2382},x:1000,y:1200},{props:{name:'Pico del margen',class:'peak',ele:2000},x:-60,y:500},{props:{name:'Roca',class:'cliff'},x:10,y:10}]),
 ...layer('poi',[{props:{name:'Refugio de Urriellu',class:'lodging',subclass:'alpine_hut'},x:2000,y:2000},{props:{name:'Bar',class:'bar',subclass:'bar'},x:5,y:5}]),
 ...layer('water_name',[{props:{name:'Lago de la Ercina','name:es':'Categoría:Lago Ercina',class:'lake'},x:3000,y:100}])]);

const feats=decodeTile(tile);
assert.equal(feats.length,7);
const peak=feats.find(f=>f.props.name==='Picu Urriellu');assert.equal(peak.layer,'mountain_peak');assert.equal(peak.props.ele,2518);
const [lon,lat]=tileToLonLat(14,tx,ty,peak.x,peak.y);assert.ok(Math.abs(lat-43.20084)<2e-5&&Math.abs(lon+4.8177)<2e-5,'coordenadas exactas de la tesela');

const places=placesFromTile(14,tx,ty,feats);
assert.deepEqual(places.map(p=>p[2]).sort(),['collado','lago','pico','refugio'],'solo lo útil en el monte; fuera acantilados, bares y lo que cae en el margen');
const pu=places.find(p=>p[0]==='Picu Urriellu');assert.deepEqual(pu[1],['Pico Urriellu','Naranjo de Bulnes']);assert.equal(pu[5],2518);
assert.deepEqual(places.find(p=>p[2]==='lago')[1],[],'sin «Categoría:» ni escrituras no latinas');
assert.equal(kindOf('place',{class:'hamlet'}),'pueblo');assert.equal(kindOf('poi',{class:'aerialway',subclass:'station'}),'teleférico');assert.equal(kindOf('poi',{class:'railway',subclass:'station'}),null);
assert.deepEqual(altNames({name:'A','name:es':'A'}),[]);

const d=dedupe([['Lago Enol',[],'lago',43.2719,-4.9916,null,'omt'],['Lago Enol',[],'lago',43.2722,-4.9905,null,'omt'],['Lago Enol',[],'lago',43.30,-4.99,null,'omt'],['Torre Cerredo',[],'pico',43.1978,-4.8529,2649,'omt']]);
assert.equal(d.length,3,'el mismo lago repetido a 100 m se queda una vez');assert.equal(d[0][0],'Torre Cerredo','los picos van primero');
assert.ok(tilesFor().length>4000&&tilesFor().length<5000);
console.log('Nomenclátor por teselas: lector MVT, coordenadas exactas, tipos, otros nombres, márgenes y repetidos.');
