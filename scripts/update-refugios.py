"""Actualiza cada día precios, plazas y teléfono de los refugios de Picos desde la central de reservas
(reservarefugios.com). Escribe data/refugios-live.json; la app lo superpone a data/refugios.json.

Solo se guarda un dato si se ha leído con claridad y es verosímil (precios entre 3 y 120 €, plazas entre 2 y 200).
Si una página no responde o cambia de formato, ese refugio conserva los datos anteriores.
"""
import datetime, html, json, pathlib, re, sys, time, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
UA = {'User-Agent': 'Mozilla/5.0 (compatible; TrailMeteo/17; +https://github.com/wilderwests/Trailmeteo)', 'Accept-Language': 'es,en;q=0.8'}
LABELS = [  # (clave en la app, patrón)
    ('pernocta', r'(?:overnight(?:\s+stay)?|pernocta(?:ci[oó]n)?)'),
    ('desayuno', r'(?:breakfast|desayuno)'),
    ('comida', r'(?:lunch(?:\s*/\s*dinner)?|comida(?:\s*/\s*cena)?)'),
    ('cena', r'(?:dinner|cena)'),
    ('picnic', r'(?:picnic|picnics?|bocadillo)'),
    ('media pensión', r'(?:half[\s-]*board|media\s+pensi[oó]n)'),
    ('pensión completa', r'(?:full[\s-]*board|pensi[oó]n\s+completa)'),
]
PRICE = r'\s*[:\-–]?\s*(\d{1,3}(?:[.,]\d{1,2})?)\s*(?:€|eur|euros)'


def text_of(page):
    page = re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\1>', ' ', page)
    page = re.sub(r'(?i)<br\s*/?>|</(p|div|li|tr|td|th|h\d)>', '\n', page)
    page = html.unescape(re.sub(r'<[^>]+>', ' ', page))
    return re.sub(r'[ \t ]+', ' ', page)


def prices_in(part):
    out = {}
    for key, pat in LABELS:
        m = re.search(pat + PRICE, part, re.I)
        if m:
            v = float(m.group(1).replace(',', '.'))
            if 3 <= v <= 120:
                out[key] = v
    # «Lunch/Dinner» en una sola línea vale para comida y cena
    if 'comida' in out and 'cena' not in out and re.search(r'lunch\s*/\s*dinner|comida\s*/\s*cena', part, re.I):
        out['cena'] = out['comida']
    return out


def parse(page):
    """Devuelve {'prices': {clave: [federado, no federado]}, 'beds': n, 'phone': [...]} con lo que se lea con claridad."""
    t = text_of(page)
    res = {}
    split = re.split(r'(?i)\bnon[\s-]*federated\b|\bno\s+federad[oa]s?\b', t, maxsplit=1)
    if len(split) == 2:
        fed_part = re.split(r'(?i)\bfederated\b|\bfederad[oa]s?\b', split[0])[-1]
        f, n = prices_in(fed_part), prices_in(split[1][:1500])
        both = {k: [f[k], n[k]] for k in f if k in n}
        if 'pernocta' in both:
            res['prices'] = both
    m = re.search(r'(?i)(?:occupancy|capacity|capacidad|plazas)\s*:?\s*(\d{1,3})', t)
    if m and 2 <= int(m.group(1)) <= 200:
        res['beds'] = int(m.group(1))
    phones = []
    for p in re.findall(r'(?:\(\+34\)|\+34)?\s*((?:6|7|8|9)\d{2}\s?\d{2,3}\s?\d{2,3}\s?\d{0,3})', t):
        d = re.sub(r'\D', '', p)
        if len(d) == 9:
            f = f'{d[:3]} {d[3:6]} {d[6:]}'
            if f not in phones:
                phones.append(f)
    if phones:
        res['phone'] = phones[:3]
    return res


def main():
    base = json.loads((ROOT / 'data/refugios.json').read_text())
    dest = ROOT / 'data/refugios-live.json'
    try:
        old = json.loads(dest.read_text()).get('refugios', {})
    except Exception:
        old = {}
    today = datetime.date.today().isoformat()
    out, ok = {}, 0
    for r in base['refugios']:
        url = r.get('book') or ''
        prev = old.get(r['id'], {})
        if 'reservarefugios.com' not in url:
            if prev:
                out[r['id']] = prev
            continue
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=25) as resp:
                page = resp.read(2_000_000).decode('utf-8', 'replace')
            got = parse(page)
            if got:
                out[r['id']] = {**prev, **got, 'checked': today, 'source': url}
                ok += 1
            elif prev:
                out[r['id']] = prev
            time.sleep(0.5)
        except Exception as e:
            print('Refugio', r['id'], 'sin actualizar:', e, file=sys.stderr)
            if prev:
                out[r['id']] = prev
    if not out:
        sys.exit('Sin datos nuevos de refugios; se conserva lo anterior')
    dest.write_text(json.dumps({'fetched': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'), 'source': 'reservarefugios.com', 'refugios': out}, ensure_ascii=False, separators=(',', ':')))
    print('Refugios actualizados:', ok, 'de', len(base['refugios']))


if __name__ == '__main__':
    main()
