"""Estado de las webcams de data/webcams.json: busca la imagen actual de cada cámara en su página de origen y comprueba
si está activa (imagen válida y reciente). Escribe data/webcams-live.json; la app nunca copia las imágenes, las muestra
desde la web de origen con crédito y enlace.

Estados: live (imagen de menos de 3 h), ok (imagen válida, antigüedad desconocida), stale (más de 3 h), down (sin imagen),
stream (emisión de YouTube que existe), link (solo se puede abrir en su web).
"""
import datetime, email.utils, hashlib, html, io, json, pathlib, re, sys, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
UA = {'User-Agent': 'Mozilla/5.0 (compatible; TrailMeteo/17; +https://github.com/wilderwests/Trailmeteo)'}
GOOD = re.compile(r'(webcam|cam\d|camara|cámara|snapshot|captura|imagen_?actual|current|live|ultima|última|foto)', re.I)
BAD = re.compile(r'(logo|banner|icon|sprite|avatar|publi|ads?[/_-]|facebook|twitter|instagram|whatsapp|flag|bandera|placeholder|loading|pixel|1x1|blank)', re.I)
IMG = re.compile(r'''(?:src|data-src|href|content)\s*=\s*["']([^"']+\.(?:jpe?g|png|webp)(?:\?[^"']*)?)["']''', re.I)
OG = re.compile(r'''<meta[^>]+(?:property|name)\s*=\s*["'](?:og:image|twitter:image)["'][^>]*content\s*=\s*["']([^"']+)["']''', re.I)
FRESH_H = 3


def fetch(url, limit=6_000_000, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(limit), dict(r.headers), r.geturl()


def candidates(page_html, base):
    """Imágenes de la página ordenadas por probabilidad de ser la captura de la cámara."""
    seen, out = set(), []
    for rank, rx in ((0, OG), (1, IMG)):
        for m in rx.finditer(page_html):
            u = urllib.parse.urljoin(base, html.unescape(m.group(1).strip()))
            if u in seen or not u.startswith('http') or BAD.search(u):
                continue
            seen.add(u)
            score = (0 if GOOD.search(u) else 2) + rank
            out.append((score, len(out), u))
    return [u for _, _, u in sorted(out)]


def image_info(data, headers):
    info = {'bytes': len(data), 'type': headers.get('Content-Type', '').split(';')[0]}
    lm = headers.get('Last-Modified')
    if lm:
        try:
            info['modified'] = email.utils.parsedate_to_datetime(lm).astimezone(datetime.timezone.utc).isoformat()
        except (TypeError, ValueError):
            pass
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        info['w'], info['h'] = im.size
        exif = im.getexif() if hasattr(im, 'getexif') else None
        dt = exif.get(306) if exif else None  # DateTime
        if dt and 'modified' not in info:
            try:
                info['exif'] = datetime.datetime.strptime(str(dt), '%Y:%m:%d %H:%M:%S').isoformat()
            except ValueError:
                pass
    except Exception:
        pass
    info['sha'] = hashlib.sha1(data).hexdigest()[:16]
    return info


def plausible(info):
    if not (info.get('type', '').startswith('image/') or info.get('w')):
        return False
    if info.get('w') and (info['w'] < 320 or info['h'] < 180):
        return False
    return info['bytes'] >= 12_000


def status_for(info, prev, now):
    mod = info.get('modified')
    if mod:
        age = (now - datetime.datetime.fromisoformat(mod)).total_seconds() / 3600
        return ('live' if age <= FRESH_H else 'stale'), mod
    if prev and prev.get('sha') and prev['sha'] != info.get('sha'):
        return 'live', now.isoformat()
    if prev and prev.get('sha') == info.get('sha') and prev.get('changed'):
        changed = datetime.datetime.fromisoformat(prev['changed'])
        return ('live' if (now - changed).total_seconds() / 3600 <= FRESH_H else 'stale'), prev['changed']
    return 'ok', None


def check(cam, prev, now):
    out = {'checked': now.isoformat()}
    try:
        if cam.get('type') == 'youtube' and cam.get('youtube'):
            q = urllib.parse.urlencode({'url': 'https://www.youtube.com/watch?v=' + cam['youtube'], 'format': 'json'})
            data, _, _ = fetch('https://www.youtube.com/oembed?' + q, 200_000)
            meta = json.loads(data)
            out.update(status='stream', title=meta.get('title', '')[:120])
            return out
        tries = [cam['img']] if cam.get('img') else []
        if not tries:
            page, headers, final = fetch(cam['page'], 2_000_000)
            enc = re.search(r'charset=([\w-]+)', headers.get('Content-Type', ''))
            text = page.decode(enc.group(1) if enc else 'utf-8', 'replace')
            tries = candidates(text, final)[:8]
        for u in tries:
            try:
                data, headers, _ = fetch(u)
            except Exception:
                continue
            info = image_info(data, headers)
            if not plausible(info):
                continue
            st, changed = status_for(info, prev if prev and prev.get('img') == u else None, now)
            out.update(status=st, img=u, changed=changed, **{k: info[k] for k in ('w', 'h', 'bytes', 'modified', 'exif', 'sha') if k in info})
            return out
        out['status'] = 'link'
    except Exception as e:
        out.update(status='down', error=str(e)[:160])
    return out


def main():
    cams = json.loads((ROOT / 'data/webcams.json').read_text())['cams']
    dest = ROOT / 'data/webcams-live.json'
    prev = {}
    try:
        prev = json.loads(dest.read_text()).get('cams', {})
    except Exception:
        pass
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    with ThreadPoolExecutor(6) as ex:
        res = dict(zip([c['id'] for c in cams], ex.map(lambda c: check(c, prev.get(c['id']), now), cams)))
    dest.write_text(json.dumps({'fetched': now.isoformat(), 'fresh_hours': FRESH_H, 'cams': res}, ensure_ascii=False, separators=(',', ':')))
    summary = {}
    for r in res.values():
        summary[r['status']] = summary.get(r['status'], 0) + 1
    print('Webcams:', summary)


if __name__ == '__main__':
    main()
