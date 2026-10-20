"""Catálogo de canales de Picos de Europa desde OpenStreetMap, precalculado para que la app no dependa de Overpass en directo.

Misma consulta que canales.js (mantener sincronizadas). Prueba varios servidores Overpass y solo reemplaza
data/canales.json si la respuesta trae elementos.
"""
import datetime, json, pathlib, sys, urllib.parse, urllib.request

PICOS = (43.07, -5.13, 43.35, -4.52)
RE = '"^((La|El) )?(Canal|Canalón|Canalon|Canaleta|Canalona|Canalu|Canalín|Canalina|Canalejas)( |$)",i'
MIRRORS = ['https://overpass-api.de/api/interpreter', 'https://overpass.private.coffee/api/interpreter', 'https://overpass.kumi.systems/api/interpreter']


def query():
    b = ','.join(map(str, PICOS))
    return f"""[out:json][timeout:90];
(way["name"~{RE}]["waterway"!~"."]["man_made"!~"."]["highway"!~"^(motorway|trunk|primary|secondary|tertiary|residential|unclassified)$"]({b});
relation["name"~{RE}]["waterway"!~"."]({b});
node["name"~{RE}]["natural"]({b});
node["name"~{RE}]["place"~"^(locality|hamlet)$"]({b});
);
out tags geom qt;"""


def main():
    data = urllib.parse.urlencode({'data': query()}).encode()
    last = None
    for url in MIRRORS:
        try:
            req = urllib.request.Request(url, data=data, headers={'User-Agent': 'TrailMeteo/15 (https://github.com/wilderwests/Trailmeteo)'})
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.load(r)
            els = d.get('elements') or []
            if not els:
                raise ValueError('respuesta sin elementos')
            dest = pathlib.Path(__file__).resolve().parents[1] / 'data/canales.json'
            dest.write_text(json.dumps({'fetched': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'source': 'OpenStreetMap contributors (ODbL)',
                                        'server': url, 'elements': els}, ensure_ascii=False, separators=(',', ':')))
            print('Canales OSM:', len(els), 'elementos desde', url)
            return
        except Exception as e:
            last = e
            print('Overpass', url, 'falló:', e, file=sys.stderr)
    sys.exit(f'Sin catálogo nuevo ({last}); se conserva el anterior')


if __name__ == '__main__':
    main()
