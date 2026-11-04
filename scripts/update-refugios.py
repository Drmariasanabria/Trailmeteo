"""Comprobación diaria de los refugios de Picos (data/refugios.json) contra varias fuentes, con pruebas.

1. Central de reservas (reservarefugios.com): precios federado/no federado, plazas y teléfono. La tabla de la central
   pone el precio ANTES del concepto («8€ | Breakfast»); se lee fila a fila y cada precio se valida (rangos razonables
   por concepto, desayuno < comida, federado ≤ no federado). Si algo no cuadra, ese refugio conserva los datos anteriores.
2. Web oficial del refugio: avisos de cierre o apertura («Refugio cerrado hasta primavera de 2027», «Abierto de mayo a
   octubre»), con la frase exacta como prueba. Si la web parece pirateada (publicidad de casinos, apuestas, fármacos…)
   se marca y la app deja de enlazarla.
3. OpenStreetMap: refugios guardados con parte libre (winter_room=yes) o con un refugio libre a menos de 150 m.

Escribe data/refugios-live.json: {refugios: {id: {prices, beds, phone, status, season, web_bad, libre, evidence[]}}}.
La app aplica el orden de prioridad: correcciones confirmadas (data/refugios.json) > aviso reciente de la web oficial >
temporada de la web oficial > central de reservas > datos de base.
"""
import datetime, html, json, pathlib, re, sys, time, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
UA = {'User-Agent': 'Mozilla/5.0 (compatible; TrailMeteo/17; +https://github.com/wilderwests/Trailmeteo)', 'Accept-Language': 'es,en;q=0.8'}
OSM_UA = {'User-Agent': 'TrailMeteo/17 (https://github.com/wilderwests/Trailmeteo)'}
MIRRORS = ['https://overpass-api.de/api/interpreter', 'https://overpass.private.coffee/api/interpreter', 'https://overpass.kumi.systems/api/interpreter']
CONCEPTS = [  # clave, patrón del concepto
    ('desayuno', r'^(?:breakfast|desayuno)$'),
    ('comida', r'^(?:lunch\s*/\s*dinner|comida\s*/\s*cena|lunch|comida)$'),
    ('cena', r'^(?:dinner|cena)$'),
    ('pernocta', r'^(?:overnight(?:\s+stay)?|pernocta(?:ci[oó]n)?)$'),
    ('picnic', r'^(?:picnic|pic-nic|bocadillo)$'),
    ('media pensión', r'^(?:half[\s-]*board|media\s+pensi[oó]n)$'),
    ('pensión completa', r'^(?:full[\s-]*board|pensi[oó]n\s+completa)$'),
]
RANGES = {'desayuno': (3, 16), 'comida': (8, 40), 'cena': (8, 40), 'pernocta': (5, 45), 'picnic': (5, 25), 'media pensión': (25, 80), 'pensión completa': (35, 110)}
MONTHS = {'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8, 'septiembre': 9, 'setiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12}
SEASONS = {'primavera': 3, 'verano': 6, 'otoño': 9, 'otono': 9, 'invierno': 12}
SPAM = re.compile(r'\b(casino|apuestas|slots?|tragaperras|viagra|cialis|porn|xxx|escort|bitcoin|crypto|préstamos? r[aá]pidos?|replica watches|bet\d*|togel|judi|gacor)\b', re.I)


def text_of(page):
    page = re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\1>', ' ', page)
    page = re.sub(r'(?i)<br\s*/?>|</(p|div|li|tr|td|th|h\d|section|article)>', '\n', page)
    page = html.unescape(re.sub(r'<[^>]+>', ' ', page))
    return re.sub(r'[ \t ]+', ' ', page)


def concept(label):
    l = ' '.join(label.lower().split())
    for key, pat in CONCEPTS:
        if re.match(pat, l):
            return key
    return None


def rows_of(block):
    """Filas (precio, concepto) de una tabla o de un texto en el que el precio va antes o después del concepto."""
    out = []
    for a, b in re.findall(r'(?is)<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>', block):
        a, b = text_of(a).strip(), text_of(b).strip()
        pa, pb = re.fullmatch(r'(\d{1,3}(?:[.,]\d{1,2})?)\s*€', a), re.fullmatch(r'(\d{1,3}(?:[.,]\d{1,2})?)\s*€', b)
        if pa and concept(b):
            out.append((float(pa.group(1).replace(',', '.')), concept(b)))
        elif pb and concept(a):
            out.append((float(pb.group(1).replace(',', '.')), concept(a)))
    if not out:  # texto plano «8€ breakfast» o «breakfast 8€», una fila por línea
        for line in text_of(block).split('\n'):
            line = line.strip()
            m = re.fullmatch(r'(\d{1,3}(?:[.,]\d{1,2})?)\s*€\s+(.+)', line) or None
            if m and concept(m.group(2)):
                out.append((float(m.group(1).replace(',', '.')), concept(m.group(2))))
                continue
            m = re.fullmatch(r'(.+?)\s*[:\-–]?\s*(\d{1,3}(?:[.,]\d{1,2})?)\s*€', line)
            if m and concept(m.group(1)):
                out.append((float(m.group(2).replace(',', '.')), concept(m.group(1))))
    prices = {}
    for v, k in out:
        prices.setdefault(k, v)
    if 'comida' in prices and 'cena' not in prices:
        prices['cena'] = prices['comida']
    return prices


def valid(prices):
    """Precios verosímiles y coherentes entre sí; si no, no se usan."""
    for k, (f, n) in prices.items():
        lo, hi = RANGES[k]
        if not (lo <= f <= hi and lo <= n <= hi) or f > n:
            return False
    d, c = prices.get('desayuno'), prices.get('comida')
    if d and c and not (d[1] < c[1]):
        return False
    return 'pernocta' in prices


def parse(page):
    """Central de reservas → {'prices': {clave: [federado, no federado]}, 'beds': n, 'phone': [...]}."""
    res = {}
    fed = re.search(r'(?is)field--name-field-federated.*?</table>', page)
    nofed = re.search(r'(?is)field--name-field-not-federated.*?</table>', page)
    if fed and nofed:
        f, n = rows_of(fed.group(0)), rows_of(nofed.group(0))
    else:
        t = text_of(page)
        parts = re.split(r'(?i)\bnon[\s-]*federated\b|\bno\s+federad[oa]s?\b', t, maxsplit=1)
        f = n = {}
        if len(parts) == 2:
            f = rows_of(re.split(r'(?i)\bfederated\b|\bfederad[oa]s?\b', parts[0])[-1][:800])
            n = rows_of(parts[1][:800])
    both = {k: [f[k], n[k]] for k in f if k in n}
    if both and valid(both):
        res['prices'] = both
    t = text_of(page)
    m = re.search(r'(?i)\b(?:occupancy|capacity|capacidad|plazas)\s*:?\s*(\d{1,3})\b', t)
    if m and 2 <= int(m.group(1)) <= 200:
        res['beds'] = int(m.group(1))
    tel = re.search(r'(?is)(?:telephone|tel[eé]fono)\s*(.{0,80})', t)
    phones = []
    for p in re.findall(r'(?:\(\+34\)|\+34)?\s*([6789](?:[\s.]?\d){8})(?!\d)', tel.group(1) if tel else ''):
        d = re.sub(r'\D', '', p)
        if len(d) == 9 and (f := f'{d[:3]} {d[3:6]} {d[6:]}') not in phones:
            phones.append(f)
    if phones:
        res['phone'] = phones[:3]
    return res


def month_of(word):
    w = word.lower().strip()
    return MONTHS.get(w) or SEASONS.get(w)


def official(page, today):
    """Web oficial → avisos de cierre/apertura y temporada, con la frase de prueba. Devuelve dict (puede ir vacío)."""
    t = ' '.join(text_of(page).split())
    out = {}
    spam = SPAM.findall(t)
    if len(spam) >= 2 or re.search(r'[Ѐ-ӿ぀-ヿ一-鿿]{40,}', t):
        out['web_bad'] = 'La web muestra contenido ajeno al refugio (posible web pirateada): ' + ', '.join(sorted(set(s.lower() for s in spam))[:4])
        return out
    m = re.search(r'(?i)(refugio\s+)?(cerrad[oa]|cerramos|cerró sus puertas)[^.]{0,40}?\bhasta\s+(?:el\s+)?(?:(\d{1,2})\s+de\s+)?(\w+)(?:\s+de)?\s*(\d{4})?', t)
    if m:
        mon = month_of(m.group(4) or '')
        if mon:
            y = int(m.group(5)) if m.group(5) else (today.year + (1 if mon < today.month else 0))
            day = int(m.group(3)) if m.group(3) else 1
            try:
                until = datetime.date(y, mon, min(day, 28)).isoformat()
            except ValueError:
                until = None
            if until and until > today.isoformat():
                s, e = max(0, m.start() - 60), min(len(t), m.end() + 80)
                out['status'] = {'closed': True, 'until': until, 'quote': t[s:e].strip()[:240]}
    m = re.search(r'(?i)\b(?:abierto|abrimos|temporada|guardado)\b[^.]{0,30}?\b(?:de|desde)\s+(\w+)\s+(?:a|hasta)\s+(\w+)', t)
    if m and month_of(m.group(1)) and month_of(m.group(2)) and m.group(1).lower() in MONTHS and m.group(2).lower() in MONTHS:
        a, b = MONTHS[m.group(1).lower()], MONTHS[m.group(2).lower()]
        last = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][b - 1]
        s, e = max(0, m.start() - 20), min(len(t), m.end() + 40)
        out['season'] = {'open': [[f'{a:02d}-01', f'{b:02d}-{last:02d}']], 'quote': t[s:e].strip()[:200]}
    return out


def osm_libres():
    """Refugios guardados de Picos con parte libre según OpenStreetMap (winter_room o refugio libre a menos de 150 m)."""
    q = """[out:json][timeout:60];
(nwr["tourism"="alpine_hut"](43.05,-5.15,43.35,-4.55);)->.g;
(nwr["tourism"="wilderness_hut"](43.05,-5.15,43.35,-4.55);nwr["amenity"="shelter"]["shelter_type"!="public_transport"](43.05,-5.15,43.35,-4.55);)->.l;
.g out center tags qt;.l out center tags qt;"""
    data = urllib.parse.urlencode({'data': q}).encode()
    for u in MIRRORS:
        try:
            with urllib.request.urlopen(urllib.request.Request(u, data=data, headers=OSM_UA), timeout=70) as r:
                return json.load(r).get('elements') or []
        except Exception as e:
            print('Overpass', u, e, file=sys.stderr)
    return None


def dist_m(a, b):
    import math
    k = math.cos(math.radians(a[0]))
    return math.hypot((a[0] - b[0]) * 111320, (a[1] - b[1]) * 111320 * k)


def libres_for(base, els):
    if not els:
        return {}
    pt = lambda e: (e.get('lat', (e.get('center') or {}).get('lat')), e.get('lon', (e.get('center') or {}).get('lon')))
    guarded = [e for e in els if (e.get('tags') or {}).get('tourism') == 'alpine_hut' and pt(e)[0] is not None]
    free = [e for e in els if (e.get('tags') or {}).get('tourism') != 'alpine_hut' and pt(e)[0] is not None]
    out = {}
    for r in base:
        near = [g for g in guarded if dist_m(pt(g), (r['lat'], r['lon'])) < 2500 and any(m in (g.get('tags', {}).get('name', '') or '').lower() for m in r.get('match', []))]
        if not near:
            continue
        g = min(near, key=lambda g: dist_m(pt(g), (r['lat'], r['lon'])))
        tags = g.get('tags') or {}
        if tags.get('winter_room') in ('yes', 'designated'):
            out[r['id']] = {'libre': 'Parte libre (winter room) según OpenStreetMap', 'src': f"https://www.openstreetmap.org/{g['type']}/{g['id']}"}
            continue
        for f in free:
            if dist_m(pt(f), pt(g)) < 150:
                ft = f.get('tags') or {}
                out[r['id']] = {'libre': f"Refugio libre junto al guardado: {ft.get('name') or 'sin nombre'} (OpenStreetMap)", 'src': f"https://www.openstreetmap.org/{f['type']}/{f['id']}"}
                break
    return out


def fetch(url, timeout=25):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read(2_000_000).decode('utf-8', 'replace')


def main():
    base = json.loads((ROOT / 'data/refugios.json').read_text())['refugios']
    dest = ROOT / 'data/refugios-live.json'
    try:
        old = json.loads(dest.read_text()).get('refugios', {})
    except Exception:
        old = {}
    today = datetime.date.today()
    out, ok = {}, 0
    libres = libres_for(base, osm_libres())
    for r in base:
        prev = {k: v for k, v in old.get(r['id'], {}).items() if k != 'prices' or valid(v)}
        cur = dict(prev)
        ev = []
        url = r.get('book') or ''
        if 'reservarefugios.com' in url:
            try:
                got = parse(fetch(url))
                if got:
                    cur.update(got)
                    ok += 1
                    ev.append({'src': url, 'what': 'precios, plazas y teléfono', 'date': today.isoformat()})
                time.sleep(0.4)
            except Exception as e:
                print('Central', r['id'], e, file=sys.stderr)
        web = r.get('web') or ''
        if web.startswith('http') and 'facebook.com' not in web and 'instagram.com' not in web and 'cantur.com' not in web:
            try:
                info = official(fetch(web), today)
                cur.pop('web_bad', None)
                cur.update(info)
                if 'status' not in info:
                    cur.pop('status', None)
                for k in ('status', 'season', 'web_bad'):
                    if k in info:
                        ev.append({'src': web, 'what': k, 'quote': (info[k].get('quote') if isinstance(info[k], dict) else info[k]), 'date': today.isoformat()})
                time.sleep(0.4)
            except Exception as e:
                print('Web', r['id'], e, file=sys.stderr)
        if r['id'] in libres:
            cur['libre'] = libres[r['id']]['libre']
            ev.append({'src': libres[r['id']]['src'], 'what': 'refugio libre', 'date': today.isoformat()})
        if ev:
            cur['checked'] = today.isoformat()
            cur['evidence'] = ev
        if cur:
            out[r['id']] = cur
    if not out:
        sys.exit('Sin datos nuevos de refugios; se conserva lo anterior')
    dest.write_text(json.dumps({'fetched': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'), 'source': 'reservarefugios.com, webs oficiales y OpenStreetMap', 'refugios': out}, ensure_ascii=False, separators=(',', ':')))
    print('Refugios comprobados:', ok, 'en la central;', len(out), 'con datos;', len(libres), 'con parte libre en OSM')


if __name__ == '__main__':
    main()
