"""Comprobaciones del compuesto Sentinel-2, la cota observada y la validación, sin red (escenas sintéticas)."""
import datetime, importlib.util, json, pathlib, tempfile
import numpy as np
spec = importlib.util.spec_from_file_location('sm', pathlib.Path(__file__).resolve().parents[1] / 'scripts/update-snowmap.py')
sm = importlib.util.module_from_spec(spec); spec.loader.exec_module(sm)

g = sm.grid()
assert 2000 < g['w'] < 3000 and 1200 < g['h'] < 2000, g
lo, la = sm.unmerc(*sm.merc(-4.8, 43.2)); assert abs(lo + 4.8) < 1e-9 and abs(la - 43.2) < 1e-9

# Escenas sintéticas en la propia malla: la más reciente con nubes en la mitad norte
H, W = g['h'], g['w']
newest = np.full((H, W), 4, np.uint8); newest[: H // 2] = 9; newest[H // 2:, : W // 4] = 11
older = np.full((H, W), 11, np.uint8); older[:, W // 2:] = 5; older[:10] = 0
scenes = {'a': newest, 'b': older}
items = [{'id': 'a', 'date': '2026-10-18', 'cloud': 40, 'scl': 'a'}, {'id': 'b', 'date': '2026-10-10', 'cloud': 5, 'scl': 'b'}]
cls, age, used = sm.composite(items, g, reader=lambda href, gg: scenes[href], today=datetime.date(2026, 10, 20))
assert [u['id'] for u in used] == ['a', 'b']
assert cls[H - 1, 0] == 2 and age[H - 1, 0] == 2, 'nieve vista en la escena reciente'
assert cls[H - 1, W - 1] == 1 and age[H - 1, W - 1] == 2, 'sin nieve en la reciente'
assert cls[H // 4, 0] == 2 and age[H // 4, 0] == 10, 'bajo nubes: se usa la escena anterior (nieve)'
assert cls[H // 4, W - 1] == 1 and age[H // 4, W - 1] == 10
assert cls[0, 0] == 0 and age[0, 0] == 255, 'sin dato en ninguna escena'

# Pendiente y orientación: el terreno sube hacia el norte → ladera orientada al sur
rows = np.arange(200)[:, None] * np.ones((1, 200))
dem = 2000 - rows * 5.0
s, a = sm.slope_aspect(dem, 43.2)
assert abs(a[100, 100] - 180) < 1, a[100, 100]
assert 13.5 < s[100, 100] < 15, s[100, 100]  # 5 m por píxel de ~19,7 m

# Cota observada: nieve por encima de 1.600 m
elev = np.repeat(np.arange(1000, 2400, 5.0), 60)
snow = elev >= 1600
r = sm.snowline(elev, snow)
assert r['line'] == 1600, r
assert sm.snowline(elev, np.zeros_like(snow))['line'] is None
assert sm.snowline(elev, np.ones_like(snow))['below_range'] is True

# Resumen de validación
hist = [{'err': 100, 'hit': 8, 'miss': 2, 'false': 1, 'neg': 9}, {'err': -50, 'hit': 5, 'miss': 0, 'false': 4, 'neg': 6}]
v = sm.summarize(hist)
assert v['n_line'] == 2 and v['bias'] == 25 and v['mae'] == 75, v
assert v['pod'] == round(13 / 15, 2) and v['far'] == round(5 / 18, 2) and v['points'] == 35, v

with tempfile.TemporaryDirectory() as d:
    rgba = np.zeros((4, 4, 4), np.uint8); sm.png(rgba, pathlib.Path(d) / 'x.png'); assert (pathlib.Path(d) / 'x.png').stat().st_size > 0
print('Sentinel-2: compuesto por píxel, nubes, orientación, cota observada y validación OK')
