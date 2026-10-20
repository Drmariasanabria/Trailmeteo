import datetime, importlib.util, pathlib
spec = importlib.util.spec_from_file_location('al', pathlib.Path(__file__).resolve().parents[1] / 'scripts/update-aludes.py')
al = importlib.util.module_from_spec(spec); spec.loader.exec_module(al)

SEASON = """Agencia Estatal de Meteorología
Boletín de información nivológica y de peligro de aludes
Picos de Europa
viernes, 9 de abril de 2021
(Válido fuera de pistas de esquí balizadas y abiertas)
ESTIMACIÓN DEL NIVEL DE PELIGRO EN LA ESCALA EUROPEA
Pronóstico para el viernes, día 9      Débil
Avance para el sábado, día 10          Limitado
Avance para el domingo, día 11         Limitado
Estado del manto y observaciones recientes
Cota de nieve: 2.000 a 2.200 metros. En cota 2.000 se superan los 200 cm en canales.
Evolución del manto y peligro de aludes para el viernes, día 9
Problemas: nieve húmeda en solanas por la tarde; nieve reciente en cotas altas, orientaciones N y NE.
Datos en la atmósfera libre:
Altitud de la isoterma de 0 ºC: 2.500 m
Viento a 1500 m: SW 15 km/h
Viento a 3000 m: W 30 km/h
""" + "relleno " * 200 + """
Escala europea de peligro de aludes
Nieve reciente  Nieve venteada  Capas débiles persistentes  Nieve húmeda  Deslizamientos basales
Débil Limitado Notable Fuerte Muy fuerte
"""
OFF = """Información nivológica para Picos de Europa
lunes, 20 de abril de 2026
El 20 de abril se da por finalizada la campaña de predicción del peligro de aludes en Picos de Europa."""

r = al.parse(SEASON, today=datetime.date(2021, 4, 9))
assert r['issued'] == '2021-04-09', r['issued']
assert r['status'] == 'valid', r['status']
assert [d['level'] for d in r['days']] == [1, 2, 2], r['days']
assert r['level_max'] == 2
assert r['problems'] == ['Nieve reciente', 'Nieve húmeda'], r['problems']  # la leyenda no cuenta
assert r['snowline'] == [2000, 2200] and r['freezing'] == 2500
assert r['winds'][0] == {'alt': 1500, 'dir': 'SW', 'kmh': 15}, r['winds']
assert {'alt': 2000, 'cm': 200} in r['snowpack'], r['snowpack']
assert 'N' in r['aspects'] and 'NE' in r['aspects']
assert r['excerpt'].startswith('Estado del manto')
assert al.parse(SEASON, today=datetime.date(2021, 4, 30))['status'] == 'stale'
o = al.parse(OFF, today=datetime.date(2026, 10, 20))
assert o['status'] == 'off' and o['issued'] == '2026-04-20' and o['level_max'] is None, o
print('Aludes: parser OK (temporada, caducado, fin de campaña, leyenda excluida)')
