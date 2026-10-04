const assert=require('node:assert/strict');const F=require('../field-core.js');
const hm=t=>new Date(t).toISOString().slice(11,16);
// Madrid, solsticio de verano: orto 04:45 UTC y ocaso 19:49 UTC (06:45 / 21:49 CEST).
let t=F.sunTimes(Date.UTC(2026,5,21,12),40.4168,-3.7038);assert.equal(hm(t.sunrise),'04:45');assert.equal(hm(t.sunset),'19:49');assert.ok(t.dusk>t.sunset&&t.dawn<t.sunrise);
// Noche polar: sin orto ni ocaso.
t=F.sunTimes(Date.UTC(2026,11,21,12),78.2,15.6);assert.equal(t.sunrise,null);assert.equal(t.sunset,null);
// UTM de referencia: (0,0) → 31N 166021,44 E; Puerta del Sol → 30T 440290 4474257.
let u=F.toUTM(0,0);assert.equal(u.zone,31);assert.ok(Math.abs(u.easting-166021.44)<.05);assert.ok(Math.abs(u.northing)<.01);
u=F.toUTM(40.4168,-3.7038);assert.equal(u.text,'30T 440290 E 4474257 N');assert.equal(F.toUTM(-33.9,18.4).northing>5e6,true);
assert.equal(F.toDMS(43.2312,-4.9617),'43°13′52.3″N 4°57′42.1″O');
assert.ok(Math.abs(F.bearing({lat:43,lon:-5},{lat:44,lon:-5}))<1e-9);assert.ok(Math.abs(F.bearing({lat:0,lon:0},{lat:0,lon:1})-90)<1e-9);assert.equal(F.cardinal(359),'N');assert.equal(F.cardinal(225),'SO');
assert.equal(F.stormDistance(30).toFixed(2),'10.29');assert.equal(F.stormDistance(0),null);
const r=F.turnaround({start:0,now:3,deadline:10});assert.equal(r.turn,5);assert.equal(r.late,false);assert.equal(F.turnaround({start:0,now:6,deadline:10}).late,true);assert.equal(F.turnaround({start:NaN,now:1,deadline:2}),null);
const m=F.moonIllumination(Date.UTC(2026,8,26,16,49));assert.ok(m.fraction>.97,'luna llena 26-sep-2026');assert.equal(m.name,'Luna llena');
const pts=[0,1,2,3].map(i=>({lat:43+i*.001,lon:-5,ele:1000+i*10,t:i*60000}));const s=F.trackStats(pts);assert.ok(Math.abs(s.km-.3336)<.002);assert.equal(s.up,30);assert.ok(s.pace>8.5&&s.pace<9.5,"9 min/km");
assert.match(F.toGPX('A & B',pts),/<name>A &amp; B<\/name>.*<time>1970-01-01T00:00:00.000Z<\/time>/s);
console.log('Field core passed: sun times (incl. polar night), UTM, DMS, bearings, storm distance, turnaround, moon phase, track stats, GPX.');
