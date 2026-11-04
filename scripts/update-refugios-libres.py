"""Refugios libres (no guardados) de Picos de Europa y la Montaña Palentina, con su estado más reciente.

Una vez al día:
  1. OpenStreetMap (Overpass): cabañas y refugios libres (tourism=wilderness_hut, amenity=shelter + basic_hut) dentro del
     Parque Nacional de los Picos de Europa y de la provincia de Palencia al norte de 42,78°. Nombre, plazas, chimenea,
     descripción, fecha de revisión (check_date) y fecha de la última edición del objeto.
  2. Estado deducido de lo que dicen los propios datos: «derruido», «en ruinas», «buen estado», llave en el pueblo…
  3. Noticias recientes (Google News, último año): búsquedas por zona y por los refugios con nombre propio. Cada noticia
     que nombra un refugio se le asigna y se clasifica como aviso (quemado, derrumbe, cerrado…) o mejora (rehabilitado,
     reabierto…). Solo se enlazan titulares, fecha y medio; no se copia el texto.
  4. Altitud: la de OSM o, si falta, la del MDT de Open-Meteo.

Escribe data/refugios-libres.json. Si una fuente falla se conserva lo anterior de esa fuente.
"""
import datetime, email.utils, html, json, math, pathlib, re, shutil, subprocess, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEST = ROOT / 'data' / 'refugios-libres.json'
UA = {'User-Agent': 'Mozilla/5.0 (compatible; TrailMeteo/17; +https://github.com/wilderwests/Trailmeteo)', 'Accept': 'application/json', 'Accept-Language': 'es,en;q=0.8'}
MIRRORS = ['https://overpass-api.de/api/interpreter', 'https://overpass.private.coffee/api/interpreter', 'https://overpass.kumi.systems/api/interpreter']
ZONES = {
    'picos': {'name': 'Picos de Europa', 'area': 'area["name"~"Picos de Europa"]["boundary"~"national_park|protected_area"]->.z;', 'bbox': None,
              'box': (43.04, -5.22, 43.36, -4.56),
              # Contorno aproximado del Parque Nacional (lon, lat), solo para cuando Overpass no resuelve el área
              'poly': [(-5.13, 43.34), (-4.93, 43.34), (-4.75, 43.31), (-4.6, 43.26), (-4.6, 43.11), (-4.75, 43.06), (-4.95, 43.06), (-5.12, 43.11), (-5.2, 43.22)],
              'queries': ['refugio libre "Picos de Europa"', '"Picos de Europa" refugio cerrado OR derrumbe OR quemado OR vandalizado OR rehabilitado OR reabre', '"Picos de Europa" cabaña OR chozo OR vivac refugio montaña']},
    'palentina': {'name': 'Montaña Palentina', 'area': 'area["boundary"="administrative"]["admin_level"="6"]["name"="Palencia"]->.z;', 'bbox': (42.78, -4.98, 43.1, -4.15),
                  'box': (42.78, -4.98, 43.08, -4.15),
                  # Norte de Palencia (lon, lat): la raya con León y Cantabria pasa por Peña Prieta, Piedrasluengas y Tres Mares
                  'poly': [(-4.865, 42.78), (-4.875, 42.97), (-4.82, 43.0), (-4.73, 43.025), (-4.6, 43.035), (-4.46, 43.043), (-4.4, 43.037), (-4.33, 43.0), (-4.25, 42.95), (-4.17, 42.85), (-4.2, 42.78)],
                  'queries': ['refugio "Montaña Palentina"', '"Fuentes Carrionas" refugio OR chozo', 'refugio montaña Velilla OR Cervera OR Brañosera OR Triollo OR Cardaño OR Vidrieros OR Camasobres']},
}
WARN = re.compile(r'quem|incendi|vandal|derrumb|hundi|cerrad|clausur|ruina|destroz|da[ñn]os|precint|okupa|robad|desprend|basur|sucied|peor huella|masific', re.I)
GOOD = re.compile(r'rehabilit|reform|renov|inaugur|reabr|reapertur|estren|restaur|arregl|limpi|mejora', re.I)
HUTWORD = re.compile(r'refugio|chozo|caba[ñn]a|caseta|vivac|invernal', re.I)
NOISE = re.compile(r'refugio clim|refugio fiscal|refugio de animales|perrera|protectora|valor refugio|activo refugio|oso|jabal|lobo|fauna|aves|reina|letizia|pueblo que|escapada|casas? rural|hotel|refugio para (los|las)|ni .* ni |bello|oto[ñn]al|ideal para', re.I)
MOUNTAIN = re.compile(r'monta[ñn]|vivac|guarda|pernoct|sender|cumbre|cima|picos|libre|chozo|caba[ñn]a|majada|rescat|alud|nieve|ruta|travesía|excursion', re.I)


def norm(s):
    s = unicodedata.normalize('NFD', s or '').encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9 ]+', ' ', s).strip()


def dist_m(a, b):
    k = math.pi / 180
    x = (b[1] - a[1]) * k * math.cos((a[0] + b[0]) / 2 * k)
    y = (b[0] - a[0]) * k
    return 6371000 * math.hypot(x, y)


# Overpass responde 406 a los User-Agent que imitan a un navegador («Mozilla/5.0 …»): para él va uno propio
OSM_UA = {'User-Agent': 'TrailMeteo/17 (https://github.com/wilderwests/Trailmeteo)', 'Accept': 'application/json'}


def get(url, timeout=60, data=None, headers=None):
    headers = headers or UA
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.URLError as e:
        # Algunos Python antiguos (LibreSSL) no negocian TLS con ciertos servidores: se reintenta con curl
        if data is not None or not shutil.which('curl') or 'SSL' not in str(e):
            raise
        out = subprocess.run(['curl', '-sfL', '-m', str(timeout), '-A', headers['User-Agent'], '-H', 'Accept: ' + headers.get('Accept', '*/*'), url], capture_output=True, timeout=timeout + 5)
        if out.returncode:
            raise
        return out.stdout


def overpass(q):
    last = None
    for attempt in range(2):
        for u in MIRRORS:
            try:
                return json.loads(get(u + '?' + urllib.parse.urlencode({'data': q}), timeout=100, headers=OSM_UA))
            except Exception as e:  # noqa: BLE001 — se prueba el siguiente servidor
                last = e
                print('  Overpass', u, e, file=sys.stderr)
        time.sleep(20)
    raise last


def inside(poly, lon, lat):
    """Punto dentro de polígono (rayos), con el polígono en (lon, lat)."""
    ok = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            ok = not ok
    return ok


def box_query(zone):
    b = '(%s,%s,%s,%s)' % ZONES[zone]['box']
    return (f'[out:json][timeout:90];(nwr["tourism"="wilderness_hut"]{b};nwr["amenity"="shelter"]["shelter_type"="basic_hut"]{b};'
            f'nwr["name"~"Cabaña Verónica|Cabana Veronica"]{b};);out center meta;')


def in_zone(zone, e):
    c = e.get('center') or e
    return 'lat' in c and inside(ZONES[zone]['poly'], c['lon'], c['lat'])


def query(zone):
    z = ZONES[zone]
    bb = '(%s,%s,%s,%s)' % z['bbox'] if z['bbox'] else ''
    sel = lambda f: f'nwr{f}(area.z){bb};'
    return ('[out:json][timeout:90];' + z['area'] + '(' + sel('["tourism"="wilderness_hut"]') +
            sel('["amenity"="shelter"]["shelter_type"="basic_hut"]') + sel('["name"~"Cabaña Verónica|Cabana Veronica"]') + ');out center meta;')


def condition(t):
    """Estado que se deduce de los propios datos de OSM (nombre, descripción y etiquetas)."""
    txt = ' '.join(t.get(k, '') for k in ('name', 'description', 'note', 'description:es', 'ruins', 'condition')).lower()
    if t.get('ruins') == 'yes' or t.get('disused') == 'yes' or t.get('abandoned') == 'yes' or re.search(r'derruid|en ruina|ruinas|hundid|sin tejado', txt):
        return 'ruina', 'OpenStreetMap lo marca como derruido o en ruinas'
    if re.search(r'llave|key', txt):
        return 'llave', 'La llave se pide en el pueblo (según OpenStreetMap)'
    if re.search(r'buen estado|limpio|reconstruid|rehabilitad|reformad|nuevo', txt):
        return 'bueno', 'Descrito en buen estado en OpenStreetMap'
    if re.search(r'mal estado|sucio|goteras|deteriorad|peque[ñn]o y', txt):
        return 'regular', 'Descrito en mal estado en OpenStreetMap'
    return None, ''


def elements_for(zone, local=None):
    """Elementos de OSM de la zona: por el área administrativa o protegida y, si falla o sale vacía, por caja + contorno."""
    if local is not None:
        return [e for e in local.get('elements', []) if in_zone(zone, e)]
    try:
        els = overpass(query(zone)).get('elements', [])
        if els:
            return els
        print('  El área no devuelve nada: se usa la caja con el contorno de la zona', file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        print('  Área no disponible:', e, file=sys.stderr)
    return [e for e in overpass(box_query(zone)).get('elements', []) if in_zone(zone, e)]


def huts_for(zone, local=None):
    out = []
    for e in elements_for(zone, local):
        t = e.get('tags', {})
        c = e.get('center') or e
        if 'lat' not in c:
            continue
        name = (t.get('name') or '').strip()
        cap = t.get('capacity') or t.get('beds')
        desc = (t.get('description:es') or t.get('description') or '').strip()
        if not name and not cap and not desc:
            continue  # cabañas sin nombre ni datos: no ayudan a decidir
        cond, why = condition(t)
        ele = None
        try:
            ele = round(float(str(t.get('ele', '')).replace(',', '.').split()[0]))
        except (ValueError, IndexError):
            pass
        out.append({
            'id': e['type'][0] + str(e['id']), 'osm': f"{e['type']}/{e['id']}", 'name': name or 'Refugio sin nombre', 'zone': zone,
            'lat': round(c['lat'], 5), 'lon': round(c['lon'], 5), 'ele': ele, 'eleSrc': 'osm' if ele else None,
            'cap': int(cap) if str(cap or '').isdigit() else None, 'fire': t.get('fireplace'), 'kind': t.get('tourism') or t.get('shelter_type'),
            'note': re.sub(r'\s+', ' ', ' '.join(x for x in (desc, t.get('note', '')) if x and 'Bing' not in x))[:260] or None,
            'access': t.get('access'), 'check': t.get('check_date') or t.get('survey:date'), 'edited': (e.get('timestamp') or '')[:10] or None,
            'cond': cond, 'condWhy': why, 'news': []})
    # El mismo refugio suele estar como punto y como edificio: se queda el que más datos tiene
    out.sort(key=lambda h: -(len([v for v in h.values() if v]) + (2 if h['id'][0] == 'w' else 0)))
    keep = []
    for h in out:
        if any(dist_m((h['lat'], h['lon']), (k['lat'], k['lon'])) < (90 if norm(h['name']) == norm(k['name']) else 25) for k in keep):
            continue
        keep.append(h)
    return keep


def elevations(huts):
    need = [h for h in huts if not h['ele']]
    for i in range(0, len(need), 90):
        part = need[i:i + 90]
        try:
            d = json.loads(get('https://api.open-meteo.com/v1/elevation?' + urllib.parse.urlencode({
                'latitude': ','.join(str(h['lat']) for h in part), 'longitude': ','.join(str(h['lon']) for h in part)}), timeout=30))
            for h, v in zip(part, d.get('elevation', [])):
                if isinstance(v, (int, float)):
                    h['ele'], h['eleSrc'] = round(v), 'mdt'
        except Exception as e:  # noqa: BLE001
            print('  Altitud MDT', e, file=sys.stderr)


def news(q):
    url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode({'q': q + ' when:1y', 'hl': 'es', 'gl': 'ES', 'ceid': 'ES:es'})
    try:
        s = get(url, timeout=25).decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        print('  Noticias', q, e, file=sys.stderr)
        return []
    out = []
    for it in re.findall(r'<item>(.*?)</item>', s, re.S):
        g = lambda tag: html.unescape(re.sub(r'<[^>]+>', ' ', (re.search(rf'<{tag}[^>]*>(.*?)</{tag}>', it, re.S) or [None, ''])[1])).strip()
        title, link, pub, src = g('title'), g('link'), g('pubDate'), g('source')
        try:
            day = email.utils.parsedate_to_datetime(pub).date().isoformat()
        except (TypeError, ValueError):
            day = None
        if src and title.endswith(' - ' + src):
            title = title[: -len(src) - 3]
        out.append({'t': title[:200], 'u': link, 'd': day, 'src': src[:60]})
    return out


def tone(text):
    return 'aviso' if WARN.search(text) else 'mejora' if GOOD.search(text) else 'info'


def distinctive(name):
    """Parte propia del nombre («Refugio de Vega Huerta» → «vega huerta»); vacía si es genérica."""
    n = norm(name)
    n = re.sub(r'^(refugio|chozo|chozu|cabana|caseta|choza|invernales?|majada)( (de|del|de la|de los|de las|la|el|los|las))?\s+', '', n).strip()
    return n if len(n) >= 5 and n not in ('pastores', 'pastor', 'cazadores', 'icona', 'sin nombre', 'montaneros') else ''


def attach_news(huts, zone):
    z = ZONES[zone]
    items = {}
    for q in z['queries']:
        for x in news(q):
            items.setdefault(x['u'], x)
        time.sleep(1.2)
    # Búsqueda propia de los refugios con más datos (los que la gente usa): como mucho 20 por zona
    named = [h for h in huts if distinctive(h['name'])]
    named.sort(key=lambda h: -((h['cap'] or 0) + (6 if h['note'] else 0) + (4 if h['check'] else 0) + (h['ele'] or 0) / 400))
    for h in named[:20]:
        for x in news(f'"{h["name"]}" {z["name"]}'):
            items.setdefault(x['u'], x)
        time.sleep(1.2)
    zone_news = []
    for x in items.values():
        tx = x['t']
        if not HUTWORD.search(tx) or NOISE.search(tx) or not MOUNTAIN.search(tx):
            continue
        x['tone'] = tone(tx)
        hit = False
        for h in huts:
            key = distinctive(h['name'])
            if key and re.search(r'\b' + re.escape(key) + r'\b', norm(tx)):
                h['news'].append(x)
                hit = True
        if hit or re.search(norm(z['name']).split()[-1], norm(tx)):
            zone_news.append(x)
    for h in huts:
        h['news'].sort(key=lambda x: x['d'] or '', reverse=True)
        h['news'] = h['news'][:4]
    zone_news.sort(key=lambda x: x['d'] or '', reverse=True)
    return zone_news[:10]


def main():
    # --osm fichero.json: usa una respuesta de Overpass ya descargada (caja que cubra las dos zonas), p. ej. si Overpass está saturado
    local = None
    if '--osm' in sys.argv:
        local = json.loads(pathlib.Path(sys.argv[sys.argv.index('--osm') + 1]).read_text())
    prev = {}
    if DEST.exists():
        try:
            prev = json.loads(DEST.read_text())
        except ValueError:
            prev = {}
    out = {'fetched': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
           'note': 'Refugios libres según OpenStreetMap (ODbL) y noticias del último año (Google News: solo titular, medio, fecha y enlace). El estado es orientativo: compruébalo antes de contar con él para pasar la noche.',
           'sources': [['OpenStreetMap', 'https://www.openstreetmap.org/copyright'], ['Google News', 'https://news.google.com/'], ['Open-Meteo (MDT)', 'https://open-meteo.com/']],
           'zones': {}, 'huts': [], 'errors': []}
    for zone, z in ZONES.items():
        print('Zona', z['name'])
        try:
            huts = huts_for(zone, local)
        except Exception as e:  # noqa: BLE001
            out['errors'].append(f'{z["name"]}: OpenStreetMap no respondió ({e})')
            huts = [h for h in prev.get('huts', []) if h.get('zone') == zone]
            for h in huts:
                h['news'] = []
        elevations(huts)
        zn = attach_news(huts, zone)
        if not zn and prev.get('zones', {}).get(zone, {}).get('news'):
            zn = prev['zones'][zone]['news']
        out['zones'][zone] = {'name': z['name'], 'count': len(huts), 'news': zn}
        out['huts'] += huts
        print(f'  {len(huts)} refugios, {sum(1 for h in huts if h["news"])} con noticias, {len(zn)} noticias de zona')
    if not out['huts'] and prev.get('huts'):
        print('Sin datos nuevos: se conserva la copia anterior', file=sys.stderr)
        return 0
    out['huts'].sort(key=lambda h: (h['zone'], -(h['ele'] or 0)))
    DEST.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')))
    print('Escrito', DEST.relative_to(ROOT), len(out['huts']), 'refugios')
    return 0


if __name__ == '__main__':
    sys.exit(main())
