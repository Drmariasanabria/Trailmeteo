"""Esquí de montaña en abierto para el mapa: itinerarios y salidas recientes de Camptocamp (CC BY-SA 3.0) y trazados
de travesía de OpenStreetMap (piste:type=skitour, ODbL), en Picos de Europa y la Cordillera Cantábrica.

- Camptocamp es una guía colaborativa: itinerario con dificultad (escala de esquí, exposición, Labande), orientaciones,
  desnivel, resumen, y salidas con fecha, estado de las condiciones y cota a la que se calzaron y descalzaron los esquís.
- OpenStreetMap aporta trazados dibujados por la comunidad.
La app carga data/skitour.json y, si el navegador lo permite, consulta también ambos servicios en directo.
Solo se reemplaza el archivo si llega algo útil; el resto de la publicación no depende de este paso.
"""
import datetime, json, math, pathlib, sys, time, urllib.parse, urllib.request

BBOX = (42.70, -6.70, 43.45, -3.30)  # sur, oeste, norte, este
C2C = 'https://api.camptocamp.org'
MIRRORS = ['https://maps.mail.ru/osm/tools/overpass/api/interpreter', 'https://overpass-api.de/api/interpreter', 'https://overpass.private.coffee/api/interpreter', 'https://overpass.kumi.systems/api/interpreter']
UA = {'User-Agent': 'TrailMeteo/17 (https://github.com/wilderwests/Trailmeteo)', 'Accept': 'application/json'}
R = 6378137.0
LANGS = ('es', 'en', 'fr', 'it', 'ca', 'eu', 'de')


def ll_to_merc(lat, lon):
    return R * math.radians(lon), R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def merc_to_ll(x, y):
    return math.degrees(2 * math.atan(math.exp(y / R)) - math.pi / 2), math.degrees(x / R)


def merc_bbox():
    s, w, n, e = BBOX
    x1, y1 = ll_to_merc(s, w)
    x2, y2 = ll_to_merc(n, e)
    return ','.join(str(round(v)) for v in (x1, y1, x2, y2))


def get(url, timeout=40):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def locale(doc):
    locs = {l.get('lang'): l for l in doc.get('locales') or [] if isinstance(l, dict)}
    for lang in LANGS:
        if lang in locs:
            return locs[lang]
    return next(iter(locs.values()), {})


def geojson(v):
    if not v:
        return None
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return None
    return v if isinstance(v, dict) else None


def lines_of(g):
    """Coordenadas de una geometría GeoJSON en EPSG:3857 -> lista de líneas [[lat, lon, ele?], ...]."""
    g = geojson(g)
    if not g:
        return []
    t, c = g.get('type'), g.get('coordinates') or []
    parts = [c] if t == 'LineString' else c if t == 'MultiLineString' else []
    out = []
    for part in parts:
        line = []
        for p in part:
            if len(p) < 2:
                continue
            lat, lon = merc_to_ll(p[0], p[1])
            q = [round(lat, 5), round(lon, 5)]
            if len(p) > 2 and isinstance(p[2], (int, float)) and -100 < p[2] < 5000:
                q.append(round(p[2]))
            line.append(q)
        if len(line) > 1:
            out.append(line)
    return out


def point_of(g):
    g = geojson(g)
    if g and g.get('type') == 'Point' and len(g.get('coordinates') or []) >= 2:
        lat, lon = merc_to_ll(*g['coordinates'][:2])
        return [round(lat, 5), round(lon, 5)]
    return None


def seg_dist(p, a, b):
    """Distancia aproximada (m) de p al segmento ab en un plano local."""
    k = math.cos(math.radians(p[0]))
    ax, ay, bx, by, px, py = a[1] * k, a[0], b[1] * k, b[0], p[1] * k, p[0]
    dx, dy = bx - ax, by - ay
    t = 0 if dx == dy == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy) * 111320


def simplify(line, tol=12):
    """Douglas-Peucker iterativo con tolerancia en metros."""
    if len(line) < 3:
        return line
    keep, stack = {0, len(line) - 1}, [(0, len(line) - 1)]
    while stack:
        i, j = stack.pop()
        best, idx = 0, None
        for k in range(i + 1, j):
            d = seg_dist(line[k], line[i], line[j])
            if d > best:
                best, idx = d, k
        if idx is not None and best > tol:
            keep.add(idx)
            stack += [(i, idx), (idx, j)]
    return [line[k] for k in sorted(keep)]


def in_bbox(lat, lon):
    s, w, n, e = BBOX
    return s <= lat <= n and w <= lon <= e


def c2c_route(doc, detail=None):
    d = detail or doc
    loc = locale(d)
    title = ' : '.join(x for x in (loc.get('title_prefix'), loc.get('title')) if x) or loc.get('title') or 'Itinerario'
    geom = d.get('geometry') or {}
    lines = [simplify(l) for l in lines_of(geom.get('geom_detail'))]
    pt = point_of(geom.get('geom')) or (lines[0][0][:2] if lines else None)
    if not pt or not in_bbox(*pt):
        return None
    summary = (loc.get('summary') or '').strip()
    if not summary:
        summary = ' '.join((loc.get('description') or '').split())[:420]
    rid = d.get('document_id') or doc.get('document_id')
    return {
        'id': 'c2c-' + str(rid), 'src': 'c2c', 'name': title, 'pt': pt, 'lines': lines,
        'ski': d.get('ski_rating'), 'expo': d.get('ski_exposition'), 'labande': d.get('labande_ski_rating'),
        'global': d.get('labande_global_rating') or d.get('global_rating'), 'orient': d.get('orientations') or [],
        'emin': d.get('elevation_min'), 'emax': d.get('elevation_max'), 'dup': d.get('height_diff_up'),
        'durations': d.get('durations') or [], 'summary': summary[:420], 'lang': loc.get('lang'),
        'url': f'https://www.camptocamp.org/routes/{rid}', 'license': 'CC BY-SA 3.0 · Camptocamp'}


def c2c_outing(doc, detail=None):
    d = detail or doc
    loc = locale(d)
    oid = d.get('document_id') or doc.get('document_id')
    pt = point_of((d.get('geometry') or {}).get('geom'))
    routes = [r.get('document_id') for r in ((d.get('associations') or {}).get('routes') or []) if isinstance(r, dict)]
    cond = ' '.join((loc.get('conditions') or '').split())[:320]
    return {
        'id': 'c2c-o' + str(oid), 'date': d.get('date_start') or d.get('date_end'), 'title': loc.get('title') or 'Salida',
        'cond': d.get('condition_rating'), 'snowQ': d.get('snow_quality'), 'snowN': d.get('snow_quantity'),
        'up': d.get('elevation_up_snow'), 'down': d.get('elevation_down_snow'), 'emax': d.get('elevation_max'),
        'aval': d.get('avalanche_signs') or [], 'text': cond, 'pt': pt, 'routes': ['c2c-' + str(r) for r in routes if r],
        'url': f'https://www.camptocamp.org/outings/{oid}'}


def camptocamp():
    routes, outings = [], []
    bb = merc_bbox()
    offset = 0
    while offset < 600:
        d = get(f'{C2C}/routes?' + urllib.parse.urlencode({'act': 'skitouring', 'bbox': bb, 'limit': 100, 'offset': offset, 'pl': 'es'}))
        docs = d.get('documents') or []
        for doc in docs:
            detail = None
            try:
                detail = get(f"{C2C}/routes/{doc['document_id']}")
                time.sleep(0.25)
            except Exception as e:
                print('c2c ruta', doc.get('document_id'), e, file=sys.stderr)
            r = c2c_route(doc, detail)
            if r:
                routes.append(r)
        offset += len(docs)
        if not docs or offset >= (d.get('total') or 0):
            break
    since = (datetime.date.today() - datetime.timedelta(days=150)).isoformat()
    d = get(f'{C2C}/outings?' + urllib.parse.urlencode({'act': 'skitouring', 'bbox': bb, 'limit': 40, 'pl': 'es'}))
    for doc in (d.get('documents') or [])[:40]:
        detail = None
        try:
            detail = get(f"{C2C}/outings/{doc['document_id']}")
            time.sleep(0.25)
        except Exception as e:
            print('c2c salida', doc.get('document_id'), e, file=sys.stderr)
        o = c2c_outing(doc, detail)
        if (o['date'] or '') >= since or len(outings) < 12:
            outings.append(o)
    outings.sort(key=lambda o: o['date'] or '', reverse=True)
    return routes, outings


def osm_query():
    b = ','.join(map(str, BBOX))
    return f"""[out:json][timeout:60];
(way["piste:type"="skitour"]({b});relation["piste:type"="skitour"]({b});relation["route"="ski"]({b}););
out tags geom qt;"""


def osm_routes(elements):
    out, used = [], set()
    for e in elements:
        t = e.get('tags') or {}
        if e.get('type') == 'relation':
            lines = [[[round(g['lat'], 5), round(g['lon'], 5)] for g in m.get('geometry') or [] if g]
                     for m in e.get('members') or [] if m.get('type') == 'way']
            for m in e.get('members') or []:
                if m.get('type') == 'way':
                    used.add(m.get('ref'))
        elif e.get('type') == 'way':
            if e.get('id') in used:
                continue
            lines = [[[round(g['lat'], 5), round(g['lon'], 5)] for g in e.get('geometry') or [] if g]]
        else:
            continue
        lines = [simplify(l) for l in lines if len(l) > 1]
        if not lines:
            continue
        out.append({'id': f"osm-{e['type'][0]}{e['id']}", 'src': 'osm', 'name': t.get('name') or t.get('piste:name') or 'Travesía de esquí (OSM)',
                    'pt': lines[0][0], 'lines': lines, 'ski': None, 'expo': None, 'labande': None, 'global': t.get('piste:difficulty'),
                    'orient': [], 'emin': None, 'emax': None, 'dup': None, 'durations': [], 'summary': t.get('description', '')[:300],
                    'url': f"https://www.openstreetmap.org/{e['type']}/{e['id']}", 'license': 'ODbL · OpenStreetMap'})
    return out


def overpass():
    data = urllib.parse.urlencode({'data': osm_query()}).encode()
    for url in MIRRORS:
        try:
            req = urllib.request.Request(url, data=data, headers=UA)
            with urllib.request.urlopen(req, timeout=70) as r:
                return osm_routes(json.load(r).get('elements') or [])
        except Exception as e:
            print('Overpass', url, 'falló:', e, file=sys.stderr)
    return None


def main():
    dest = pathlib.Path(__file__).resolve().parents[1] / 'data/skitour.json'
    old = {}
    try:
        old = json.loads(dest.read_text())
    except Exception:
        pass
    status = {}
    try:
        routes, outings = camptocamp()
        status['camptocamp'] = 'ok'
    except Exception as e:
        print('Camptocamp falló:', e, file=sys.stderr)
        routes, outings = [r for r in old.get('routes', []) if r.get('src') == 'c2c'], old.get('outings', [])
        status['camptocamp'] = 'copia anterior' if routes else 'sin datos'
    osm = overpass()
    if osm is None:
        osm = [r for r in old.get('routes', []) if r.get('src') == 'osm']
        status['osm'] = 'copia anterior' if osm else 'sin datos'
    else:
        status['osm'] = 'ok'
    if not routes and not osm and not outings:
        sys.exit('Sin datos de esquí de montaña; se conserva el archivo anterior')
    dest.write_text(json.dumps({'fetched': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'bbox': BBOX, 'status': status,
                                'sources': {'c2c': 'Camptocamp.org · CC BY-SA 3.0', 'osm': 'OpenStreetMap contributors · ODbL'},
                                'routes': routes + osm, 'outings': outings}, ensure_ascii=False, separators=(',', ':')))
    print('Esquí de montaña:', len(routes), 'itinerarios Camptocamp,', len(osm), 'trazados OSM,', len(outings), 'salidas')


if __name__ == '__main__':
    main()
