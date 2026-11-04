/* Lector mínimo de teselas vectoriales (Mapbox Vector Tile 2.x) sin dependencias: solo puntos y centros de líneas/áreas.
   Devuelve [{layer, props, x, y}] con x/y en coordenadas de tesela (0…extent). Lo usa scripts/update-lugares.mjs. */
export function decodeTile(buf){
 const u8=buf instanceof Uint8Array?buf:new Uint8Array(buf);let pos=0;
 const varint=()=>{let r=0,s=0,b;do{b=u8[pos++];r+=(b&127)*2**s;s+=7}while(b&128);return r};
 const skip=t=>{if(t===0)varint();else if(t===1)pos+=8;else if(t===2){const l=varint();pos+=l}else if(t===5)pos+=4;else throw new Error('wire '+t)};
 const td=new TextDecoder();const out=[];
 function value(end){let v=null;while(pos<end){const k=varint(),f=k>>3,t=k&7;
  if(f===1){const l=varint();v=td.decode(u8.subarray(pos,pos+l));pos+=l}
  else if(f===2){v=new DataView(u8.buffer,u8.byteOffset+pos,4).getFloat32(0,true);pos+=4}
  else if(f===3){v=new DataView(u8.buffer,u8.byteOffset+pos,8).getFloat64(0,true);pos+=8}
  else if(f===4||f===5){v=varint()}else if(f===6){const n=varint();v=(n>>>1)^-(n&1)}else if(f===7){v=!!varint()}else skip(t)}return v}
 function packed(){const l=varint(),end=pos+l,a=[];while(pos<end)a.push(varint());return a}
 function geomCenter(cmds,type){let x=0,y=0,pts=[];for(let i=0;i<cmds.length;){const c=cmds[i++],id=c&7,n=c>>3;if(id===7)continue;for(let k=0;k<n;k++){const dx=cmds[i++],dy=cmds[i++];x+=(dx>>>1)^-(dx&1);y+=(dy>>>1)^-(dy&1);pts.push([x,y])}}
  if(!pts.length)return null;if(type===1)return pts[0];let sx=0,sy=0;for(const p of pts){sx+=p[0];sy+=p[1]}return[sx/pts.length,sy/pts.length]}
 while(pos<u8.length){const k=varint();if((k>>3)!==3||(k&7)!==2){skip(k&7);continue}const lend=pos+varint();let name='',extent=4096;const keys=[],vals=[],feats=[];
  while(pos<lend){const kk=varint(),f=kk>>3,t=kk&7;
   if(f===1){const l=varint();name=td.decode(u8.subarray(pos,pos+l));pos+=l}
   else if(f===3){const l=varint();keys.push(td.decode(u8.subarray(pos,pos+l)));pos+=l}
   else if(f===4){const l=varint();vals.push(value(pos+l))}
   else if(f===5)extent=varint();
   else if(f===2){const fend=pos+varint();let tags=[],type=0,geom=[];while(pos<fend){const fk=varint(),ff=fk>>3,ft=fk&7;if(ff===2)tags=packed();else if(ff===3)type=varint();else if(ff===4)geom=packed();else skip(ft)}feats.push({tags,type,geom})}
   else skip(t)}
  for(const f of feats){const props={};for(let i=0;i<f.tags.length;i+=2)props[keys[f.tags[i]]]=vals[f.tags[i+1]];const c=geomCenter(f.geom,f.type);if(c)out.push({layer:name,props,x:c[0]/extent,y:c[1]/extent,type:f.type})}}
 return out}
export function tileToLonLat(z,x,y,fx,fy){const n=2**z,lon=(x+fx)/n*360-180,lat=Math.atan(Math.sinh(Math.PI*(1-2*(y+fy)/n)))*180/Math.PI;return[lon,lat]}
export function lonLatToTile(z,lon,lat){const n=2**z,r=lat*Math.PI/180;return[Math.floor((lon+180)/360*n),Math.floor((1-Math.log(Math.tan(r)+1/Math.cos(r))/Math.PI)/2*n)]}
