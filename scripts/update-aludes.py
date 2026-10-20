"""Boletines de peligro de aludes de AEMET (PDF públicos, reproducción autorizada citando la fuente).

Descarga cada PDF, extrae el texto y guarda en data/aludes.json lo que se puede leer con seguridad:
fecha de emisión, estado de la campaña, nivel de peligro por día (escala europea), problemas de aludes
citados fuera de la leyenda, cota de nieve, isoterma, viento en altura y un extracto literal del estado del manto.
Lo que no se reconoce se deja vacío: la app enlaza siempre al PDF original.
"""
import datetime, json, pathlib, re, shutil, subprocess, sys, tempfile, unicodedata, urllib.request

BASE = 'https://www.aemet.es/documentos/es/eltiempo/prediccion/montana/boletin_peligro_aludes/'
PAGE = 'https://www.aemet.es/es/eltiempo/prediccion/montana/boletin_peligro_aludes'
ZONES = {
    'picos': ('Picos de Europa', 'BPA_PN_Picos_Europa.pdf', [42.95, -5.30, 43.40, -4.45], 'semanal'),
    'cordel': ('Sierra del Cordel y Peña Labra', 'BPA_sierra_Cordel_PLabra.pdf', [42.90, -4.60, 43.15, -4.05], 'semanal'),
    'pir_nav_ara': ('Pirineo navarro y aragonés', 'BPA_Pirineo_Nav_Ara.pdf', [42.45, -1.40, 43.00, 0.80], 'diario'),
    'pir_cat': ('Pirineo catalán', 'BPA_Pirineo_Cat.pdf', [42.15, 0.60, 42.90, 2.60], 'diario'),
    'guadarrama': ('Sierra de Guadarrama', 'BPA_PN_Guadarrama.pdf', [40.65, -4.30, 41.10, -3.60], 'semanal'),
}
LEVELS = {'debil': 1, 'limitado': 2, 'notable': 3, 'fuerte': 4, 'muy fuerte': 5}
PROBLEMS = [('nieve reciente', 'Nieve reciente'), ('nieve venteada', 'Nieve venteada (placas)'), ('placas de viento', 'Nieve venteada (placas)'),
            ('capas debiles persistentes', 'Capas débiles persistentes'), ('nieve humeda', 'Nieve húmeda'), ('deslizamientos basales', 'Deslizamientos basales')]
MONTHS = {m: i + 1 for i, m in enumerate(['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'])}
ASPECTS = r'\b(N|NE|E|SE|S|SW|SO|W|O|NW|NO|norte|noreste|este|sureste|sur|suroeste|oeste|noroeste)\b'


def fold(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s.lower()) if unicodedata.category(c) != 'Mn')


def num(s):
    return int(s.replace('.', '').replace(' ', ''))


def pdf_text(data):
    with tempfile.TemporaryDirectory() as d:
        f = pathlib.Path(d, 'b.pdf'); f.write_bytes(data)
        if shutil.which('pdftotext'):
            return subprocess.run(['pdftotext', '-layout', str(f), '-'], capture_output=True, text=True, check=True).stdout
        from pypdf import PdfReader  # respaldo si no hay poppler
        return '\n'.join(p.extract_text() or '' for p in PdfReader(str(f)).pages)


def parse(text, today=None):
    today = today or datetime.date.today()
    t = re.sub(r'[ \t]+', ' ', text.replace('\r', ''))
    ft = fold(t)
    out = {'status': 'unknown', 'issued': None, 'days': [], 'level_max': None, 'problems': [], 'snowline': None,
           'freezing': None, 'winds': [], 'snowpack': [], 'excerpt': '', 'flags': []}
    m = re.search(r'(lunes|martes|miercoles|jueves|viernes|sabado|domingo)?,?\s*(?:dia\s+)?(\d{1,2}) de (' + '|'.join(MONTHS) + r') de (\d{4})', ft)
    if m:
        try:
            out['issued'] = datetime.date(int(m.group(4)), MONTHS[m.group(3)], int(m.group(2))).isoformat()
        except ValueError:
            pass
    if re.search(r'(finaliza|da por finalizada|fin de) (la )?campana', ft):
        out['status'] = 'off'; out['flags'].append('Campaña de predicción finalizada')
    elif re.search(r'(comienzo|inicio) de (la )?campana|todavia no|aun no se emite', ft):
        out['status'] = 'off'
    # La leyenda de la escala repite todos los nombres: se recorta antes de buscar niveles y problemas.
    cut = len(ft)
    for key in ('escala europea de peligro de aludes', 'escala europea de peligro'):
        i = ft.rfind(key)
        if i > len(ft) * 0.4:
            cut = min(cut, i)
    body = ft[:cut]
    head = body.find('estimacion del nivel de peligro')
    zone = body[head:head + 900] if head >= 0 else body
    heads = list(re.finditer(r'(pronostico|avance) para el (\w+),? dia (\d{1,2})', zone))
    for k, m in enumerate(heads):
        seg = zone[m.end():heads[k + 1].start() if k + 1 < len(heads) else m.end() + 160]
        lv = re.search(r'\b(muy fuerte|fuerte|notable|limitado|debil)\b', seg)
        if lv:
            out['days'].append({'kind': 'pronóstico' if m.group(1) == 'pronostico' else 'avance', 'day': m.group(2), 'date': int(m.group(3)), 'level': LEVELS[lv.group(1)]})
    if not out['days']:
        lv = re.findall(r'(?:nivel|peligro)[^.\n]{0,40}?\b(muy fuerte|fuerte|notable|limitado|debil)\b(?:\s*\((\d)\))?', body)
        if lv:
            out['days'].append({'kind': 'pronóstico', 'day': '', 'date': None, 'level': LEVELS[lv[0][0]]})
    if out['days']:
        out['level_max'] = max(d['level'] for d in out['days'])
    seen = []
    for key, label in PROBLEMS:
        if key in body and label not in seen:
            seen.append(label)
    out['problems'] = seen
    m = re.search(r'cota de nieve:?\s*([\d.]{3,5})\s*(?:a|-)\s*([\d.]{3,5})', body)
    if m:
        out['snowline'] = [num(m.group(1)), num(m.group(2))]
    m = re.search(r'isoterma de 0\s*[ºo°]?\s*c:?\s*([\d.]{3,5})', body)
    if m:
        out['freezing'] = num(m.group(1))
    for m in re.finditer(r'viento a ([\d.]{3,5}) m:?\s*([nsewo]{1,3}|variable|calma)\s*(\d{1,3})?\s*(?:km/h)?', body):
        out['winds'].append({'alt': num(m.group(1)), 'dir': m.group(2).upper().replace('O', 'W') if m.group(2) not in ('variable', 'calma') else m.group(2), 'kmh': int(m.group(3)) if m.group(3) else None})
    for m in re.finditer(r'(?:en )?cota ([\d.]{3,5})[^.]{0,40}?(\d{1,3}) ?cm', body):
        out['snowpack'].append({'alt': num(m.group(1)), 'cm': int(m.group(2))})
    i = ft.find('estado del manto')
    src = t[i:] if i >= 0 else t
    out['excerpt'] = re.sub(r'\s+', ' ', src)[:1400].strip()
    out['aspects'] = sorted(set(a.upper() for a in re.findall(ASPECTS, t[:cut]) if len(a) <= 2)) or None
    if out['status'] == 'unknown':
        if out['issued']:
            age = (today - datetime.date.fromisoformat(out['issued'])).days
            out['status'] = 'valid' if age <= 8 and out['level_max'] else 'stale' if age > 8 else 'nolevel'
        else:
            out['status'] = 'nolevel'
    return out


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'TrailMeteo/15 (https://github.com/wilderwests/Trailmeteo)'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read(), r.headers.get('Last-Modified')


def main():
    zones = []
    for code, (name, file, bbox, period) in ZONES.items():
        z = {'code': code, 'name': name, 'bbox': bbox, 'period': period, 'pdf': BASE + file, 'page': PAGE}
        try:
            data, modified = get(BASE + file)
            z.update(parse(pdf_text(data))); z['modified'] = modified
        except Exception as e:  # se conserva la zona con su enlace aunque falle la lectura
            z.update({'status': 'error', 'error': str(e)[:200]})
        zones.append(z)
    if all(z['status'] == 'error' for z in zones):
        sys.exit('Ningún boletín de aludes legible; se conserva el archivo anterior')
    dest = pathlib.Path(__file__).resolve().parents[1] / 'data/aludes.json'
    dest.write_text(json.dumps({'fetched': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'source': 'AEMET · Boletines de peligro de aludes',
                                'license': 'AEMET autoriza la reproducción citando la fuente', 'zones': zones}, ensure_ascii=False, indent=1))
    print('Aludes:', ', '.join(f"{z['code']}={z['status']}" for z in zones))


if __name__ == '__main__':
    main()
