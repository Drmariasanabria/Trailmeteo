// Prepara la carpeta que se publica en GitHub Pages: copia la web y minifica el JS/CSS propio
// (el código fuente del repositorio no se toca). Uso: node scripts/build-public.mjs [carpeta] [--test]
// Con --test vuelve a pasar `npm test` contra los archivos minificados antes de dar la carpeta por buena.
import fs from 'node:fs';import path from 'node:path';import {execSync} from 'node:child_process';import {transform} from 'esbuild';
const root=path.resolve(path.dirname(new URL(import.meta.url).pathname),'..');
const args=process.argv.slice(2),out=path.resolve(root,args.find(a=>!a.startsWith('--'))||'public'),test=args.includes('--test');
const BANNER='/*! TrailMeteo · © 2026 María Sanabria (wilderwests). Todos los derechos reservados. Prohibida su copia, modificación o redistribución sin permiso. Ver LICENSE. */';
const THIRD_PARTY=new Set(['leaflet.js','leaflet.css']);
fs.rmSync(out,{recursive:true,force:true});fs.mkdirSync(path.join(out,'data'),{recursive:true});
const files=fs.readdirSync(root).filter(f=>/\.(html|css|js|png)$/.test(f)||f==='manifest.webmanifest'||f==='LICENSE');
let before=0,after=0;
for(const f of files){
  const src=path.join(root,f),dst=path.join(out,f),ext=path.extname(f);
  if(THIRD_PARTY.has(f)||(ext!=='.js'&&ext!=='.css')){fs.copyFileSync(src,dst);continue}
  const code=fs.readFileSync(src,'utf8');
  // Sin `format`: esbuild conserva los nombres globales, que los scripts clásicos comparten entre sí.
  const r=await transform(code,{loader:ext.slice(1),minify:true,charset:'utf8',legalComments:'inline',banner:BANNER});
  fs.writeFileSync(dst,r.code);before+=code.length;after+=r.code.length;
}
fs.cpSync(path.join(root,'img'),path.join(out,'img'),{recursive:true});
for(const f of fs.readdirSync(path.join(root,'data')).filter(f=>/\.(json|png)$/.test(f)))fs.copyFileSync(path.join(root,'data',f),path.join(out,'data',f));
console.log(`Web preparada en ${path.relative(root,out)||'.'}: ${files.length} archivos, JS/CSS propio ${Math.round(before/1024)} KB → ${Math.round(after/1024)} KB.`);
if(test){
  const t=path.join(out,'tests');fs.cpSync(path.join(root,'tests'),t,{recursive:true});
  try{execSync(JSON.parse(fs.readFileSync(path.join(root,'package.json'),'utf8')).scripts.test,{cwd:out,stdio:'inherit'})}
  finally{fs.rmSync(t,{recursive:true,force:true})}
  console.log('Pruebas superadas con la versión minificada.');
}
