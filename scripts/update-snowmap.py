"""Nieve observada en Picos de Europa con Sentinel-2 L2A (Copernicus, vía Earth Search en AWS; sin clave).

Para cada píxel de 20 m se guarda la ÚLTIMA observación sin nubes de los últimos 30 días según la capa de
clasificación de escena (SCL): 11 = nieve; 2, 4, 5, 6, 7 = suelo/vegetación/agua sin nieve; el resto (nubes,
sombras de nube, saturado, sin dato) no cuenta como observación. Salidas:
  data/snow-s2.png       imagen para el mapa (nieve en azul, sin observación en gris claro)
  data/snow-s2-data.png  R = clase (0 sin observación, 1 sin nieve, 2 nieve), G = días desde la observación
  data/snow-s2.json      límites, escenas usadas, cobertura y cota de nieve observada por orientación (MDT)
  data/validation.json   historial: cota observada frente a la estimada con el modelo y aciertos del espesor modelado
Contiene datos modificados de Copernicus Sentinel.
"""
import datetime, io, json, math, pathlib, statistics, sys, urllib.parse, urllib.request
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
BBOX = (-5.13, 43.07, -4.52, 43.35)          # lon/lat de Picos de Europa
PIX = 27.0                                    # m de Mercator ≈ 20 m sobre el terreno a 43° N
STAC = 'https://earth-search.aws.element84.com/v1/search'
VALID_NOSNOW, SNOW = {2, 4, 5, 6, 7}, 11
ASPECTS = ['N', 'NE', 'E', 'SE', 'S', 'SO', 'O', 'NO']
UA = {'User-Agent': 'TrailMeteo/16 (https://github.com/wilderwests/Trailmeteo)'}
R = 6378137.0


def merc(lon, lat):
    return R * math.radians(lon), R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def unmerc(x, y):
    return math.degrees(x / R), math.degrees(2 * math.atan(math.exp(y / R)) - math.pi / 2)


def grid():
    x0, y0 = merc(BBOX[0], BBOX[1]); x1, y1 = merc(BBOX[2], BBOX[3])
    w, h = int(round((x1 - x0) / PIX)), int(round((y1 - y0) / PIX))
    return {'x0': x0, 'y1': y1, 'w': w, 'h': h, 'x1': x0 + w * PIX, 'y0': y1 - h * PIX}


def http_json(url, body=None, timeout=60):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None, headers={**UA, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def search(days=30, today=None):
    today = today or datetime.datetime.now(datetime.timezone.utc)
    body = {'collections': ['sentinel-2-l2a'], 'bbox': list(BBOX), 'limit': 60,
            'datetime': f"{(today - datetime.timedelta(days=days)).strftime('%Y-%m-%dT00:00:00Z')}/{today.strftime('%Y-%m-%dT23:59:59Z')}",
            'query': {'eo:cloud_cover': {'lt': 95}}, 'sortby': [{'field': 'properties.datetime', 'direction': 'desc'}]}
    items = http_json(STAC, body).get('features', [])
    out = [{'id': f['id'], 'date': f['properties']['datetime'][:10], 'cloud': f['properties'].get('eo:cloud_cover'), 'scl': f['assets']['scl']['href']} for f in items if 'scl' in f.get('assets', {})]
    return sorted(out, key=lambda x: x['date'], reverse=True)


def read_scl(href, g):
    """SCL reproyectada a la malla Mercator (vecino más próximo), leyendo solo lo necesario del COG."""
    import rasterio
    from rasterio.vrt import WarpedVRT
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif', GDAL_HTTP_TIMEOUT='60'):
        with rasterio.open(href) as src, WarpedVRT(src, crs='EPSG:3857', transform=from_origin(g['x0'], g['y1'], PIX, PIX), width=g['w'], height=g['h'], resampling=Resampling.nearest, nodata=0) as vrt:
            return vrt.read(1)


def composite(items, g, reader=read_scl, today=None, log=print):
    today = today or datetime.date.today()
    cls = np.zeros((g['h'], g['w']), np.uint8); age = np.full((g['h'], g['w']), 255, np.uint8); used = []
    for it in items:
        if (cls == 0).sum() == 0:
            break
        try:
            scl = reader(it['scl'], g)
        except Exception as e:
            log('S2', it['id'], 'no legible:', e); continue
        fill = (cls == 0) & (np.isin(scl, list(VALID_NOSNOW)) | (scl == SNOW))
        n = int(fill.sum())
        if not n:
            continue
        cls[fill & (scl == SNOW)] = 2; cls[fill & (scl != SNOW)] = 1
        age[fill] = min(254, (today - datetime.date.fromisoformat(it['date'])).days)
        used.append({**{k: it[k] for k in ('id', 'date', 'cloud')}, 'pixels': n})
    return cls, age, used


def terrarium_dem(g, z=12):
    """MDT AWS Terrain Tiles (terrarium) remuestreado a la malla."""
    from PIL import Image
    n = 2 ** z; world = 2 * math.pi * R
    tx0, tx1 = int((g['x0'] + world / 2) / world * n), int((g['x1'] + world / 2) / world * n)
    ty0, ty1 = int((world / 2 - g['y1']) / world * n), int((world / 2 - g['y0']) / world * n)
    mosaic = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256), np.float32)
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            req = urllib.request.Request(f'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{tx}/{ty}.png', headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                a = np.asarray(Image.open(io.BytesIO(r.read())).convert('RGB'), np.float32)
            mosaic[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768
    res = world / (n * 256); mx0 = tx0 * 256 * res - world / 2; my1 = world / 2 - ty0 * 256 * res
    cols = ((g['x0'] + (np.arange(g['w']) + .5) * PIX) - mx0) / res; rows = (my1 - (g['y1'] - (np.arange(g['h']) + .5) * PIX)) / res
    return mosaic[np.clip(rows.astype(int), 0, mosaic.shape[0] - 1)[:, None], np.clip(cols.astype(int), 0, mosaic.shape[1] - 1)[None, :]]


def slope_aspect(dem, lat):
    ground = PIX * math.cos(math.radians(lat))
    dy, dx = np.gradient(dem, ground)                     # filas hacia el sur
    slope = np.degrees(np.arctan(np.hypot(dx, dy)))
    aspect = (np.degrees(np.arctan2(-dx, dy)) + 360) % 360  # 0 = ladera orientada al norte
    return slope, aspect


def snowline(elev, snow, min_px=40, step=50):
    """Cota más baja desde la que la nieve cubre ≥50 % de los píxeles observados de forma sostenida (3 bandas)."""
    if elev.size < min_px:
        return None
    bins = np.arange(math.floor(elev.min() / step) * step, elev.max() + step, step)
    frac = []
    for b in bins:
        m = (elev >= b) & (elev < b + step)
        frac.append((b, snow[m].mean() if m.sum() >= min_px else None))
    ok = [(b, f) for b, f in frac if f is not None]
    for i, (b, f) in enumerate(ok):
        nxt = [x for _, x in ok[i:i + 3]]
        if len(nxt) == 3 and all(x >= .5 for x in nxt):
            return {'line': int(b), 'below_range': i == 0}
    return {'line': None, 'none': True}


def observed_lines(cls, age, dem, slope, aspect, max_age=10):
    m = (cls > 0) & (age <= max_age) & (slope < 45) & np.isfinite(dem)
    out = {'all': snowline(dem[m], cls[m] == 2)}
    idx = (np.round(aspect / 45) % 8).astype(int)
    for k, a in enumerate(ASPECTS):
        mm = m & (idx == k)
        out[a] = snowline(dem[mm], cls[mm] == 2)
    return out


def png(arr, path):
    from PIL import Image
    Image.fromarray(arr).save(path, optimize=True)


def model_check(g, cls, age, dem, used, when):
    """Compara con Open-Meteo: cota estimada (isoterma − 300 m) y espesor modelado ≥1 cm frente a nieve observada."""
    lat, lon = (BBOX[1] + BBOX[3]) / 2, (BBOX[0] + BBOX[2]) / 2
    q = urllib.parse.urlencode({'latitude': lat, 'longitude': lon, 'hourly': 'freezing_level_height', 'past_days': 35, 'forecast_days': 1, 'timezone': 'UTC', 'timeformat': 'unixtime'})
    d = http_json('https://api.open-meteo.com/v1/forecast?' + q)
    t0 = datetime.datetime.combine(when, datetime.time(11), tzinfo=datetime.timezone.utc).timestamp()
    times = d['hourly']['time']; i = min(range(len(times)), key=lambda k: abs(times[k] - t0))
    fz = d['hourly']['freezing_level_height'][i]
    rng = np.random.default_rng(int(t0))
    ys, xs = np.nonzero((cls > 0) & (age == (datetime.date.today() - when).days) & np.isfinite(dem))
    pts = []
    if len(ys):
        order = np.argsort(dem[ys, xs]); pick = order[np.linspace(0, len(order) - 1, min(80, len(order))).astype(int)]
        for k in pick:
            y, x = ys[k], xs[k]; lo, la = unmerc(g['x0'] + (x + .5) * PIX, g['y1'] - (y + .5) * PIX)
            pts.append((round(la, 4), round(lo, 4), int(dem[y, x]), int(cls[y, x] == 2)))
    cont = {'hit': 0, 'miss': 0, 'false': 0, 'neg': 0}
    for c in range(0, len(pts), 40):
        part = pts[c:c + 40]
        q = urllib.parse.urlencode({'latitude': ','.join(str(p[0]) for p in part), 'longitude': ','.join(str(p[1]) for p in part), 'elevation': ','.join(str(p[2]) for p in part),
                                    'hourly': 'snow_depth', 'past_days': 35, 'forecast_days': 1, 'timezone': 'UTC', 'timeformat': 'unixtime'})
        res = http_json('https://api.open-meteo.com/v1/forecast?' + q)
        res = res if isinstance(res, list) else [res]
        for p, r in zip(part, res):
            tt = r['hourly']['time']; j = min(range(len(tt)), key=lambda k: abs(tt[k] - t0)); m = (r['hourly']['snow_depth'][j] or 0) >= .01
            cont['hit' if m and p[3] else 'miss' if p[3] else 'false' if m else 'neg'] += 1
    return {'model_line': None if fz is None else int(round((fz - 300) / 50) * 50), 'freezing': fz, 'points': len(pts), **cont}


def summarize(hist):
    errs = [h['err'] for h in hist if h.get('err') is not None]
    tot = {k: sum(h.get(k, 0) for h in hist) for k in ('hit', 'miss', 'false', 'neg')}
    pod = tot['hit'] / (tot['hit'] + tot['miss']) if tot['hit'] + tot['miss'] else None
    far = tot['false'] / (tot['hit'] + tot['false']) if tot['hit'] + tot['false'] else None
    acc = (tot['hit'] + tot['neg']) / sum(tot.values()) if sum(tot.values()) else None
    return {'n_line': len(errs), 'bias': round(statistics.mean(errs)) if errs else None, 'mae': round(statistics.mean(abs(e) for e in errs)) if errs else None,
            'pod': None if pod is None else round(pod, 2), 'far': None if far is None else round(far, 2), 'acc': None if acc is None else round(acc, 2), 'points': sum(tot.values())}


def main():
    g = grid(); today = datetime.date.today()
    items = search()
    if not items:
        sys.exit('Sin escenas Sentinel-2 en 30 días')
    cls, age, used = composite(items, g)
    if not used:
        sys.exit('Ninguna escena legible')
    rgba = np.zeros((g['h'], g['w'], 4), np.uint8)
    rgba[cls == 2] = (64, 168, 235, 200); rgba[cls == 0] = (150, 160, 165, 70)
    data = np.zeros((g['h'], g['w'], 4), np.uint8); data[..., 0] = cls; data[..., 1] = age; data[..., 3] = 255
    (ROOT / 'data').mkdir(exist_ok=True)
    png(rgba, ROOT / 'data/snow-s2.png'); png(data, ROOT / 'data/snow-s2-data.png')
    lines, dem_ok = None, False
    try:
        dem = terrarium_dem(g); slope, aspect = slope_aspect(dem, (BBOX[1] + BBOX[3]) / 2); lines = observed_lines(cls, age, dem, slope, aspect); dem_ok = True
    except Exception as e:
        print('MDT no disponible:', e)
    west, south = unmerc(g['x0'], g['y0']); east, north = unmerc(g['x1'], g['y1'])
    obs = cls > 0
    meta = {'fetched': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'source': 'Copernicus Sentinel-2 L2A (SCL) vía Earth Search', 'license': 'Contiene datos modificados de Copernicus Sentinel',
            'bounds': [[south, west], [north, east]], 'size': [g['w'], g['h']], 'pixel_m': round(PIX * math.cos(math.radians(43.2)), 1), 'scenes': used,
            'coverage': round(float(obs.mean()), 3), 'snow_share': round(float((cls == 2).sum() / max(1, obs.sum())), 3), 'lines': lines, 'newest': used[0]['date']}
    (ROOT / 'data/snow-s2.json').write_text(json.dumps(meta, ensure_ascii=False))
    vpath = ROOT / 'data/validation.json'
    try:
        old = json.loads(vpath.read_text())
    except Exception:
        old = {'history': []}
    hist = [h for h in old.get('history', []) if h.get('date') != used[0]['date']]
    if dem_ok and lines and lines['all'] and lines['all'].get('line') is not None:
        try:
            when = datetime.date.fromisoformat(used[0]['date']); chk = model_check(g, cls, age, dem, used, when)
            obsl = lines['all']['line']; err = None if chk['model_line'] is None or lines['all'].get('below_range') else obsl - chk['model_line']
            hist.append({'date': used[0]['date'], 'observed_line': obsl, **chk, 'err': err, 'by_aspect': {a: (lines[a] or {}).get('line') for a in ASPECTS}})
        except Exception as e:
            print('Validación no disponible:', e)
    hist = sorted(hist, key=lambda h: h['date'])[-150:]
    vpath.write_text(json.dumps({'updated': meta['fetched'], 'method': 'Cota observada Sentinel-2 (≥50 % de píxeles con nieve, 3 bandas de 50 m) frente a isoterma 0 °C − 300 m de Open-Meteo; espesor modelado ≥1 cm frente a nieve observada en hasta 80 píxeles', 'summary': summarize(hist), 'history': hist}, ensure_ascii=False))
    print('Sentinel-2:', len(used), 'escenas · cobertura', meta['coverage'], '· nieve', meta['snow_share'], '· cota', (lines or {}).get('all'))


if __name__ == '__main__':
    main()
