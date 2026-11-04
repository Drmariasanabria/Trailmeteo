"""Nomenclátor de montaña para el buscador: picos, refugios, collados, majadas, fuentes, lagos, miradores y pueblos
de Picos de Europa y la Cordillera Cantábrica central y oriental, desde OpenStreetMap (ODbL).

El buscador de la app lo usa primero (sin red), y después consulta Nominatim y Photon en directo.
Solo reemplaza data/lugares.json si la respuesta trae suficientes elementos.
"""
import datetime, json, pathlib, sys, urllib.parse, urllib.request

BBOX = (42.80, -6.10, 43.45, -3.70)  # sur, oeste, norte, este
MIRRORS = ['https://overpass-api.de/api/interpreter', 'https://overpass.private.coffee/api/interpreter', 'https://overpass.kumi.systems/api/interpreter']
NAME_KEYS = ('name', 'name:es', 'name:ast', 'alt_name', 'alt_name:es', 'loc_name', 'old_name', 'official_name', 'short_name')


BOXES = [(42.80, -6.10, 43.12, -4.90), (42.80, -4.90, 43.12, -3.70), (43.12, -6.10, 43.45, -4.90), (43.12, -4.90, 43.45, -3.70)]
GROUPS = [
    'node["natural"~"^(peak|saddle|ridge|arete)$"]["name"]({b});node["mountain_pass"="yes"]["name"]({b});',
    'nwr["tourism"~"^(alpine_hut|wilderness_hut|viewpoint)$"]["name"]({b});nwr["amenity"="shelter"]["name"]({b});nwr["aerialway"="station"]["name"]({b});node["natural"~"^(spring|cave_entrance|valley)$"]["name"]({b});',
    'nwr["natural"="water"]["name"]({b});node["place"~"^(town|village|hamlet|locality|isolated_dwelling)$"]["name"]({b});nwr["landuse"="meadow"]["name"~"^(Vega|Majada|Braña|Invernal)",i]({b});',
]


def query(box=BBOX, group=None):
    """Consulta Overpass. Sin grupo: la consulta completa (pruebas); con grupo: un trozo pequeño que no agota el tiempo."""
    b = ','.join(map(str, box))
    body = ''.join(g.format(b=b) for g in GROUPS) if group is None else GROUPS[group].format(b=b)
    return f"[out:json][timeout:60];({body});out center tags qt;"


def fetch_all():
    """Descarga por trozos (4 zonas × 3 grupos) con reintento en cada servidor; devuelve los elementos y los trozos fallidos."""
    import time
    els, failed = [], []
    for box in BOXES:
        for g in range(len(GROUPS)):
            data = urllib.parse.urlencode({'data': query(box, g)}).encode()
            ok = False
            for attempt in range(2):
                for url in MIRRORS:
                    try:
                        req = urllib.request.Request(url, data=data, headers={'User-Agent': 'TrailMeteo/17 (https://github.com/wilderwests/Trailmeteo)'})
                        with urllib.request.urlopen(req, timeout=75) as r:
                            els += json.load(r).get('elements') or []
                        ok = True
                        break
                    except Exception as e:
                        print('Overpass', url, box, g, 'falló:', e, file=sys.stderr)
                if ok:
                    break
                time.sleep(5)
            if not ok:
                failed.append((box, g))
                if len(failed) >= 3 and not els:
                    print('Overpass no responde: se aborta para no bloquear la publicación', file=sys.stderr)
                    return els, failed + [(b, k) for b in BOXES for k in range(len(GROUPS))][len(failed):]
            time.sleep(1)
    return els, failed


def kind(t):
    n = t.get('natural', '')
    if n == 'peak':
        return 'pico'
    if n in ('saddle',) or t.get('mountain_pass') == 'yes':
        return 'collado'
    if n == 'spring':
        return 'fuente'
    if n == 'cave_entrance':
        return 'cueva'
    if n in ('ridge', 'arete'):
        return 'cresta'
    if n == 'valley':
        return 'valle'
    tr = t.get('tourism', '')
    if tr == 'alpine_hut':
        return 'refugio'
    if tr == 'wilderness_hut' or t.get('amenity') == 'shelter':
        return 'cabaña'
    if tr == 'viewpoint':
        return 'mirador'
    if n == 'water':
        return 'lago'
    if t.get('aerialway') == 'station':
        return 'teleférico'
    p = t.get('place', '')
    if p in ('town', 'village', 'hamlet'):
        return 'pueblo'
    if p in ('locality', 'isolated_dwelling') or t.get('landuse') == 'meadow':
        return 'paraje'
    return 'lugar'


def ele(t):
    v = str(t.get('ele', '')).replace(',', '.').replace('m', '').strip()
    try:
        x = float(v)
        return round(x) if -100 < x < 5000 else None
    except ValueError:
        return None


def names(t):
    out = []
    for k in NAME_KEYS:
        for v in str(t.get(k, '')).split(';'):
            v = v.strip()
            if v and v not in out:
                out.append(v)
    return out


def build(elements):
    seen, places = set(), []
    for e in elements:
        t = e.get('tags') or {}
        lat = e.get('lat', (e.get('center') or {}).get('lat'))
        lon = e.get('lon', (e.get('center') or {}).get('lon'))
        nm = names(t)
        if lat is None or lon is None or not nm:
            continue
        k = kind(t)
        key = (nm[0].lower(), k, round(lat, 3), round(lon, 3))
        if key in seen:
            continue
        seen.add(key)
        places.append([nm[0], nm[1:6], k, round(lat, 5), round(lon, 5), ele(t), e.get('type', 'n')[0] + str(e.get('id', ''))])
    order = {'pico': 0, 'refugio': 1, 'collado': 2, 'cabaña': 3, 'lago': 4, 'paraje': 5, 'mirador': 6, 'fuente': 7, 'pueblo': 8}
    places.sort(key=lambda p: (order.get(p[2], 9), p[0]))
    return places


def main():
    dest = pathlib.Path(__file__).resolve().parents[1] / 'data/lugares.json'
    els, failed = fetch_all()
    places = build(els)
    if len(places) < 200:
        sys.exit(f'Sin nomenclátor nuevo ({len(places)} lugares, {len(failed)} trozos fallidos); se conserva el anterior')
    if failed and dest.exists():
        try:  # completa con el anterior lo que no haya llegado hoy
            old = json.loads(dest.read_text()).get('places', [])
            have = {(p[0].lower(), p[2], round(p[3], 3), round(p[4], 3)) for p in places}
            places += [p for p in old if (p[0].lower(), p[2], round(p[3], 3), round(p[4], 3)) not in have]
        except Exception:
            pass
    dest.write_text(json.dumps({'fetched': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'source': 'OpenStreetMap contributors (ODbL)', 'bbox': BBOX,
                                'partial': bool(failed), 'fields': ['nombre', 'otros nombres', 'tipo', 'lat', 'lon', 'altitud', 'id OSM'],
                                'places': places}, ensure_ascii=False, separators=(',', ':')))
    print('Lugares OSM:', len(places), '·', len(failed), 'trozos fallidos')


if __name__ == '__main__':
    main()
