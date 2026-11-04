"""Pruebas sin red de los recolectores de TrailMeteo 17: nomenclátor, esquí de montaña y webcams."""
import datetime, importlib.util, json, math, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'scripts' / f'{name}.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


lug, ski, cam = load('update-lugares'), load('update-skitour'), load('update-webcams')

# ---------- Nomenclátor ----------
els = [
    {'type': 'node', 'id': 1, 'lat': 43.2403, 'lon': -4.8158, 'tags': {'natural': 'peak', 'name': 'Picu Urriellu', 'alt_name': 'Naranjo de Bulnes', 'ele': '2519'}},
    {'type': 'way', 'id': 2, 'center': {'lat': 43.2, 'lon': -4.75}, 'tags': {'tourism': 'alpine_hut', 'name': 'Casetón de Ándara', 'ele': '1725 m'}},
    {'type': 'node', 'id': 3, 'lat': 43.2, 'lon': -4.8, 'tags': {'tourism': 'alpine_hut', 'name': 'Refugio Jou de Cabrones', 'loc_name': 'Refugio de Cabrones;Cabrones'}},
    {'type': 'node', 'id': 4, 'lat': 43.2, 'lon': -4.8, 'tags': {'natural': 'saddle', 'name': 'Collado Jermoso', 'ele': 'x'}},
    {'type': 'node', 'id': 5, 'lat': 43.2403, 'lon': -4.8158, 'tags': {'natural': 'peak', 'name': 'Picu Urriellu'}},  # duplicado
    {'type': 'node', 'id': 6, 'lat': 43.3, 'lon': -4.9, 'tags': {'place': 'locality', 'name': 'Majada de Ondón'}},
    {'type': 'node', 'id': 7, 'tags': {'natural': 'peak', 'name': 'Sin coordenadas'}},
]
p = lug.build(els)
names = [x[0] for x in p]
assert names[0] == 'Picu Urriellu' and names.count('Picu Urriellu') == 1, names
assert p[0][1] == ['Naranjo de Bulnes'] and p[0][2] == 'pico' and p[0][5] == 2519
hut = next(x for x in p if x[0] == 'Casetón de Ándara')
assert hut[2] == 'refugio' and hut[5] == 1725 and hut[3] == 43.2
cab = next(x for x in p if x[0].startswith('Refugio Jou'))
assert 'Refugio de Cabrones' in cab[1] and 'Cabrones' in cab[1]
assert next(x for x in p if x[0] == 'Collado Jermoso')[2:6:3] == ['collado', None]
assert next(x for x in p if x[0] == 'Majada de Ondón')[2] == 'paraje'
assert 'Sin coordenadas' not in names
assert 'peak' in lug.query() and 'alpine_hut' in lug.query()

# ---------- Esquí de montaña ----------
lat, lon = 43.15, -4.85
x, y = ski.ll_to_merc(lat, lon)
la2, lo2 = ski.merc_to_ll(x, y)
assert abs(la2 - lat) < 1e-9 and abs(lo2 - lon) < 1e-9
assert len(ski.merc_bbox().split(',')) == 4
line = [[43.15 + i * 1e-4, -4.85] for i in range(50)]
assert len(ski.simplify(line)) == 2  # recta -> extremos
zig = [[43.15 + i * 1e-3, -4.85 + (0.002 if i % 2 else 0)] for i in range(10)]
assert len(ski.simplify(zig)) == 10
pts = [list(ski.ll_to_merc(43.16 + i * 0.002, -4.86 + i * 0.001)) + [1200 + i * 50] for i in range(6)]
doc = {'document_id': 123, 'ski_rating': '2.3', 'ski_exposition': 'E1', 'labande_ski_rating': 'S3', 'labande_global_rating': 'PD',
       'orientations': ['N', 'NE'], 'elevation_min': 1100, 'elevation_max': 2100, 'height_diff_up': 1000,
       'locales': [{'lang': 'fr', 'title': 'Couloir'}, {'lang': 'es', 'title': 'Canal de la Jenduda', 'title_prefix': 'Peña Vieja', 'summary': 'Clásica'}],
       'geometry': {'geom': json.dumps({'type': 'Point', 'coordinates': pts[0][:2]}), 'geom_detail': json.dumps({'type': 'LineString', 'coordinates': pts})}}
r = ski.c2c_route(doc)
assert r['name'] == 'Peña Vieja : Canal de la Jenduda' and r['lang'] == 'es' and r['summary'] == 'Clásica'
assert r['ski'] == '2.3' and r['orient'] == ['N', 'NE'] and r['url'].endswith('/routes/123')
assert abs(r['pt'][0] - 43.16) < 1e-4 and r['lines'] and r['lines'][0][0][2] == 1200
far = dict(doc, geometry={'geom': json.dumps({'type': 'Point', 'coordinates': list(ski.ll_to_merc(45.9, 6.8))})})
assert ski.c2c_route(far) is None, 'fuera de la zona'
o = ski.c2c_outing({'document_id': 9, 'date_start': '2026-02-01', 'condition_rating': 'good', 'elevation_up_snow': 1300,
                    'snow_quality': 'good', 'locales': [{'lang': 'es', 'title': 'Jenduda', 'conditions': ' Polvo   en norte '}],
                    'associations': {'routes': [{'document_id': 123}]}})
assert o['routes'] == ['c2c-123'] and o['up'] == 1300 and o['text'] == 'Polvo en norte' and o['cond'] == 'good'
osm = ski.osm_routes([
    {'type': 'relation', 'id': 5, 'tags': {'route': 'ski', 'name': 'Travesía'}, 'members': [{'type': 'way', 'ref': 50, 'geometry': [{'lat': 43.1, 'lon': -4.8}, {'lat': 43.11, 'lon': -4.81}]}]},
    {'type': 'way', 'id': 50, 'tags': {'piste:type': 'skitour'}, 'geometry': [{'lat': 43.1, 'lon': -4.8}, {'lat': 43.11, 'lon': -4.81}]},
    {'type': 'way', 'id': 51, 'tags': {'piste:type': 'skitour'}, 'geometry': [{'lat': 43.2, 'lon': -4.8}, {'lat': 43.21, 'lon': -4.81}]}])
assert [x['id'] for x in osm] == ['osm-r5', 'osm-w51'], osm
assert osm[1]['name'].startswith('Travesía de esquí')

# ---------- Webcams ----------
page = '''<html><head><meta property="og:image" content="/img/logo.png"><meta property="og:image" content="https://x.es/webcams/cam43.jpg?t=1"></head>
<body><img src="/banner.jpg"><img data-src="fotos/ultima_imagen.jpg"><img src="https://x.es/social/facebook.png"></body></html>'''
c = cam.candidates(page, 'https://x.es/pagina/')
assert c[0] == 'https://x.es/webcams/cam43.jpg?t=1', c
assert 'https://x.es/pagina/fotos/ultima_imagen.jpg' in c and not any('logo' in u or 'banner' in u or 'facebook' in u for u in c)
assert cam.plausible({'bytes': 80000, 'type': 'image/jpeg', 'w': 1280, 'h': 720})
assert not cam.plausible({'bytes': 3000, 'type': 'image/jpeg'}) and not cam.plausible({'bytes': 90000, 'type': 'text/html'})
assert not cam.plausible({'bytes': 90000, 'type': 'image/png', 'w': 120, 'h': 60})
now = datetime.datetime(2026, 11, 4, 12, tzinfo=datetime.timezone.utc)
assert cam.status_for({'modified': '2026-11-04T11:30:00+00:00'}, None, now)[0] == 'live'
assert cam.status_for({'modified': '2026-11-03T11:30:00+00:00'}, None, now)[0] == 'stale'
assert cam.status_for({'sha': 'b'}, {'sha': 'a'}, now) == ('live', now.isoformat())
assert cam.status_for({'sha': 'a'}, {'sha': 'a', 'changed': '2026-11-04T06:00:00+00:00'}, now)[0] == 'stale'
assert cam.status_for({'sha': 'a'}, None, now) == ('ok', None)
cams = json.loads((ROOT / 'data/webcams.json').read_text())['cams']
ids = [c['id'] for c in cams]
assert len(ids) == len(set(ids)) >= 15
for c in cams:
    assert c['type'] in ('image', 'youtube') and c['page'].startswith('http') and 42 < c['lat'] < 44 and -7 < c['lon'] < -3, c
    assert c['type'] != 'youtube' or c.get('youtube')
ref = load('update-refugios')
page = '''<html><body><h1>Vega de Urriellu</h1><p>Telephone</p><p>(+34) 984 090 981</p><p>Occupancy</p><p>96</p>
<div><h3>Federated</h3><ul><li>Breakfast 8€</li><li>Lunch/Dinner 19€</li><li>Overnight stay 15€</li></ul>
<h3>Non federated</h3><ul><li>Breakfast 8 €</li><li>Lunch/Dinner 19 €</li><li>Overnight stay 20,50 €</li><li>Picnic 12€</li></ul></div></body></html>'''
got = ref.parse(page)
assert got['prices']['pernocta'] == [15, 20.5] and got['prices']['desayuno'] == [8, 8], got
assert got['prices']['comida'] == [19, 19] and got['prices']['cena'] == [19, 19]
assert 'picnic' not in got['prices'], 'solo si están los dos precios'
assert got['beds'] == 96 and got['phone'] == ['984 090 981'], got
# Tabla real de la central: el precio va ANTES del concepto (fallo que dio precios cruzados en Vegarredonda)
row = lambda p, c: f'<tr><td>{p}€\n</td><td>{c}\n</td></tr>'
real = ('<p>Telephone</p><p>(+34) 985 922 952 / (+34) 626 34 33 66</p><p>Occupancy</p><p>63</p>'
        '<div class="field field--name-field-federated"><table><tbody>' + row(8, 'Breakfast') + row(19, 'Lunch/Dinner') + row(15, 'Overnight stay') + row(12, 'Picnic') + '</tbody></table></div>'
        '<div class="field field--name-field-not-federated"><table><tbody>' + row(8, 'Breakfast') + row(19, 'Lunch/Dinner') + row(20, 'Overnight stay') + row(12, 'Picnic') + '</tbody></table></div>')
g2 = ref.parse(real)
assert g2['prices'] == {'desayuno': [8, 8], 'comida': [19, 19], 'pernocta': [15, 20], 'picnic': [12, 12], 'cena': [19, 19]}, g2
assert g2['beds'] == 63 and g2['phone'] == ['985 922 952', '626 343 366'], g2
assert not ref.valid({'pernocta': [12, 12], 'desayuno': [19, 19], 'comida': [15, 20]}), 'desayuno más caro que la comida: se descarta'
assert ref.parse('<p>Página en obras</p>') == {}
assert 'prices' not in ref.parse('<p>Federated</p><p>900€ Overnight</p><p>Non federated</p><p>950€ Overnight</p>'), 'precios inverosímiles'
today = datetime.date(2026, 11, 4)
o = ref.official('<h2>REFUGIO CERRADO HASTA PRIMAVERA DE 2027</h2><p>El refugio Vega de Ario cerró sus puertas el 01 de noviembre de 2026 y volverá abrir sus puertas en la primavera de 2027.</p>', today)
assert o['status']['closed'] and o['status']['until'] == '2027-03-01' and 'CERRADO HASTA' in o['status']['quote'], o
o = ref.official('<p>Calefacción</p><p>Abierto de mayo a octubre</p>', today)
assert o['season']['open'] == [['05-01', '10-31']] and 'Abierto de mayo a octubre' in o['season']['quote'], o
assert 'status' not in o
o = ref.official('<p>Mejores casino online y apuestas deportivas, slots gratis</p>', today)
assert 'web_bad' in o and 'casino' in o['web_bad'], o
assert ref.official('<p>Refugio cerrado hasta el 15 de marzo de 2026</p>', today) == {}, 'un aviso de cierre ya pasado no cuenta'
base = [{'id': 'urriellu', 'lat': 43.2433, 'lon': -4.8226, 'match': ['urriellu']}]
els = [{'type': 'node', 'id': 1, 'lat': 43.2434, 'lon': -4.8224, 'tags': {'tourism': 'alpine_hut', 'name': 'Refugio de Urriellu'}},
       {'type': 'node', 'id': 2, 'lat': 43.2436, 'lon': -4.8222, 'tags': {'tourism': 'wilderness_hut', 'name': 'Refugio de invierno'}}]
assert 'Refugio de invierno' in ref.libres_for(base, els)['urriellu']['libre']
els[0]['tags']['winter_room'] = 'yes'
assert 'winter room' in ref.libres_for(base, els)['urriellu']['libre']

# ---------- Refugios libres (v17.1) ----------
lib = load('update-refugios-libres')
assert lib.condition({'name': 'Chozo Bernabé (semi-derruido)'})[0] == 'ruina'
assert lib.condition({'name': 'Refugio Montañeros de Liébana', 'description': 'LLave de acceso en el Bar de Somaniezo'})[0] == 'llave'
assert lib.condition({'name': 'Refugio del Berbegón', 'description': 'En buen estado, cuenta con todo'})[0] == 'bueno'
assert lib.condition({'name': 'Refugio de Vega Huerta'})[0] is None
assert lib.distinctive('Refugio de Vega Huerta') == 'vega huerta' and lib.distinctive('Chozo de Pastores') == '' and lib.distinctive('Cabaña del ICONA') == ''
assert lib.NOISE.search('el otro refugio del oso pardo') and lib.NOISE.search('El pueblo que esconde el refugio de la reina') and not lib.NOISE.search('Vandalizan y queman un refugio de la Montaña Palentina')
assert lib.tone('Vandalizan y queman un refugio de la Montaña Palentina') == 'aviso' and lib.tone('Rehabilitan el refugio del Frade') == 'mejora' and lib.tone('La vida en los refugios') == 'info'
q = lib.query('palentina')
assert 'wilderness_hut' in q and 'basic_hut' in q and '"Palencia"' in q and '(area.z)(42.78' in q and 'out center meta' in q
assert 'national_park' in lib.query('picos')
print('v17 recolectores: OK')
