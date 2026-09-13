"""Acquire the two global wet-setting datasets and prepare the native-grid cache."""
from pathlib import Path
import hashlib
import json
import shutil
import urllib.request
from historical_agriculture.water_management_inputs import prepare

root = Path(__file__).resolve().parents[1]
cfg = json.loads((root/'configs/water_management.json').read_text())
raw = root/cfg['source_directory']
raw.mkdir(parents=True, exist_ok=True)
for name, url in [('glwd_metadata.json', 'https://api.figshare.com/v2/articles/28519994'),
                  ('wetloss.json', 'https://zenodo.org/api/records/7616651')]:
    if not (raw/name).exists():
        with urllib.request.urlopen(url, timeout=90) as r:
            (raw/name).write_bytes(r.read())
g = next(f for f in json.loads((raw/'glwd_metadata.json').read_text())['files']
         if f['name'] == 'GLWD_v2_0_area_by_class_pct_tif.zip')
w = next(f for f in json.loads((raw/'wetloss.json').read_text())['files'] if f['key'] == 'wetland_loss.zip')
for name, url, size, md5 in [(g['name'], g['download_url'], g['size'], g['computed_md5']),
    ('wetland_loss.zip', w['links']['self'], w['size'], w['checksum'].split(':')[-1])]:
    dest = raw/name
    if not dest.exists():
        temp = dest.with_suffix('.part')
        with urllib.request.urlopen(url, timeout=90) as r, temp.open('wb') as f:
            shutil.copyfileobj(r, f, 8*1024*1024)
        temp.replace(dest)
    with dest.open('rb') as f:
        actual_md5 = hashlib.file_digest(f, 'md5').hexdigest()
    if dest.stat().st_size != size or actual_md5 != md5:
        raise ValueError('Download checksum mismatch: '+name)
print(prepare(root, cfg))
