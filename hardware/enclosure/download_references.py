from pathlib import Path
import hashlib
import json
import re
import urllib.request
import zipfile

opener = urllib.request.build_opener()
opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
urllib.request.install_opener(opener)

ROOT = Path(__file__).resolve().parent / 'reference'
ROOT.mkdir(exist_ok=True)
URLS = {
    'display_7_brief.pdf': 'https://pip-assets.raspberrypi.com/categories/1083-raspberry-pi-touch-display-2/documents/RP-010429-MM-3-touch-display-2-7-inch-product-brief.pdf',
    'display_7_step.zip': 'https://pip-assets.raspberrypi.com/categories/1083-raspberry-pi-touch-display-2/documents/RP-009154-DD-3-raspberry-pi-touch-display-2-step-7inch.zip',
    'camera3_drawing.pdf': 'https://datasheets.raspberrypi.com/camera/camera-module-3-standard-mechanical-drawing.pdf',
    'pi5_drawing.pdf': 'https://datasheets.raspberrypi.com/rpi5/raspberry-pi-5-mechanical-drawing.pdf',
    'case_brief.pdf': 'https://datasheets.raspberrypi.com/case/case-for-raspberry-pi-5-product-brief.pdf',
}
for page, key, contains in [
    ('https://pip.raspberrypi.com/categories/892-raspberry-pi-5', 'pi5_step.zip', 'small'),
    ('https://pip.raspberrypi.com/categories/1207-design-files', 'camera3_step.zip', 'step'),
]:
    html = urllib.request.urlopen(page).read().decode()
    links = re.findall(r'href="([^"]+\.zip[^"]*)"', html)
    picked = [u for u in links if contains.lower() in u.lower()]
    if picked:
        URLS[key] = picked[0].replace('&amp;', '&')

manifest = []
for name, url in URLS.items():
    path = ROOT / name
    if not path.exists():
        try:
            urllib.request.urlretrieve(url, path)
        except Exception:
            print(f'Download failed: {name}: {url}')
            raise
    manifest.append({'file': name, 'url': url, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'retrieved': '2026-10-21'})
    if path.suffix == '.zip':
        with zipfile.ZipFile(path) as archive:
            members = [m for m in archive.infolist() if Path(m.filename).suffix.lower() in ('.stp', '.step') and '__MACOSX' not in m.filename]
            member = max(members, key=lambda m: m.file_size)
            target = ROOT / (path.stem + Path(member.filename).suffix.lower())
            target.write_bytes(archive.read(member))
            manifest[-1]['extracted'] = target.name
(ROOT / 'sources.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps(manifest, indent=2))
