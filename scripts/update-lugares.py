"""Nomenclátor de montaña para el buscador: picos, refugios, collados, majadas, fuentes, lagos, miradores y pueblos
de Picos de Europa y la Cordillera Cantábrica central y oriental, desde OpenStreetMap (ODbL).

El buscador de la app lo usa primero (sin red), y después consulta Nominatim y Photon en directo.
Solo reemplaza data/lugares.json si la respuesta trae suficientes elementos.
"""
import datetime, json, pathlib, sys, urllib.parse, urllib.request

BBOX = (42.80, -6.10, 43.45, -3.70)  # sur, oeste, norte, este
MIRRORS = ['https://overpass-api.de/api/interpreter', 'https://overpass.private.coffee/api/interpreter', 'https://overpass.kumi.systems/api/interpreter']
NAME_KEYS = ('name', 'name:es', 'name:ast', 'alt_name', 'alt_name:es', 'loc_name', 'old_name', 'official_name', 'short_name')


def query():
    b = ','.join(map(str, BBOX))
    return f"""[out:json][timeout:90];
(
node["natural"~"^(peak|saddle|spring|cave_entrance|ridge|valley|arete)$"]["name"]({b});
node["mountain_pass"="yes"]["name"]({b});
nwr["tourism"~"^(alpine_hut|wilderness_hut|viewpoint)$"]["name"]({b});
nwr["amenity"="shelter"]["name"]({b});
nwr["natural"="water"]["name"]({b});
node["place"~"^(town|village|hamlet|locality|isolated_dwelling)$"]["name"]({b});
nwr["aerialway"="station"]["name"]({b});
nwr["landuse"="meadow"]["name"~"^(Vega|Majada|Braña|Invernal)",i]({b});
);
out center tags qt;"""


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
    data = urllib.parse.urlencode({'data': query()}).encode()
    last = None
    for url in MIRRORS:
        try:
            req = urllib.request.Request(url, data=data, headers={'User-Agent': 'TrailMeteo/17 (https://github.com/wilderwests/Trailmeteo)'})
            with urllib.request.urlopen(req, timeout=100) as r:
                d = json.load(r)
            places = build(d.get('elements') or [])
            if len(places) < 200:
                raise ValueError(f'solo {len(places)} lugares')
            dest = pathlib.Path(__file__).resolve().parents[1] / 'data/lugares.json'
            dest.write_text(json.dumps({'fetched': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                        'source': 'OpenStreetMap contributors (ODbL)', 'bbox': BBOX,
                                        'fields': ['nombre', 'otros nombres', 'tipo', 'lat', 'lon', 'altitud', 'id OSM'],
                                        'places': places}, ensure_ascii=False, separators=(',', ':')))
            print('Lugares OSM:', len(places), 'desde', url)
            return
        except Exception as e:
            last = e
            print('Overpass', url, 'falló:', e, file=sys.stderr)
    sys.exit(f'Sin nomenclátor nuevo ({last}); se conserva el anterior')


if __name__ == '__main__':
    main()
