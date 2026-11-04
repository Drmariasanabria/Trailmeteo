"""Complemento del nomenclátor (scripts/update-lugares.mjs lo saca antes de las teselas del mapa): añade lo que solo trae Overpass,
como fuentes, cuevas, majadas y parajes. Si Overpass está saturado no pasa nada: se conserva lo de las teselas.

Nomenclátor de montaña para el buscador: picos, refugios, collados, majadas, fuentes, lagos, miradores y pueblos
de Picos de Europa y la Cordillera Cantábrica central y oriental, desde OpenStreetMap (ODbL).

El buscador de la app lo usa primero (sin red), y después consulta Nominatim y Photon en directo.
Solo reemplaza data/lugares.json si la respuesta trae suficientes elementos.
"""
import datetime, json, pathlib, sys, urllib.parse, urllib.request

BBOX = (42.80, -6.10, 43.45, -3.70)  # sur, oeste, norte, este
MIRRORS = ['https://maps.mail.ru/osm/tools/overpass/api/interpreter', 'https://overpass-api.de/api/interpreter', 'https://overpass.private.coffee/api/interpreter', 'https://overpass.kumi.systems/api/interpreter']
BUDGET = 260  # segundos: termina y guarda antes de que el paso de publicación lo corte
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


def fetch_all(budget=BUDGET):
    """Descarga por trozos (4 zonas × 3 grupos). Cada trozo prueba los servidores en orden y pasa al siguiente si uno falla;
    los servidores que fallan van al final de la cola. Nunca supera el presupuesto de tiempo: devuelve lo que tenga."""
    import time
    t0, els, failed, mirrors = time.time(), [], [], list(MIRRORS)
    chunks = [(b, g) for b in BOXES for g in range(len(GROUPS))]
    for box, g in chunks:
        ok = False
        for url in list(mirrors):
            left = budget - (time.time() - t0)
            if left < 20:
                break
            try:
                data = urllib.parse.urlencode({'data': query(box, g)}).encode()
                req = urllib.request.Request(url, data=data, headers={'User-Agent': 'TrailMeteo/18 (https://github.com/wilderwests/Trailmeteo)'})
                with urllib.request.urlopen(req, timeout=min(90, left)) as r:
                    got = json.load(r).get('elements')
                if got is None:
                    raise ValueError('respuesta sin elementos')
                els += got
                ok = True
                break
            except Exception as e:
                print('Overpass', url, box, g, 'falló:', e, file=sys.stderr)
                mirrors.remove(url)
                mirrors.append(url)
                time.sleep(2)
        if not ok:
            failed.append((box, g))
        if budget - (time.time() - t0) < 20:
            failed += chunks[chunks.index((box, g)) + 1:]
            print('Presupuesto de tiempo agotado: se guarda lo descargado', file=sys.stderr)
            break
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
    if dest.exists():
        try:  # completa lo de las teselas (scripts/update-lugares.mjs, que va antes) con lo que solo trae Overpass
            old = json.loads(dest.read_text()).get('places', [])
            have = {(p[0].lower(), p[2], round(p[3], 2), round(p[4], 2)) for p in places}
            places = [p for p in old if (p[0].lower(), p[2], round(p[3], 2), round(p[4], 2)) not in have] + places
        except Exception:
            pass
    if len(places) < 200:
        sys.exit(f'Sin nomenclátor nuevo ({len(places)} lugares, {len(failed)} trozos fallidos); se conserva el anterior')
    dest.write_text(json.dumps({'fetched': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'source': 'OpenStreetMap contributors (ODbL)', 'bbox': BBOX,
                                'partial': bool(failed), 'fields': ['nombre', 'otros nombres', 'tipo', 'lat', 'lon', 'altitud', 'id OSM'],
                                'places': places}, ensure_ascii=False, separators=(',', ':')))
    print('Lugares OSM:', len(places), '·', len(failed), 'trozos fallidos')


if __name__ == '__main__':
    main()
