"""Preserve generated transparency, normalize icon size, and build a small preview."""
import json,shutil,hashlib
from pathlib import Path,PureWindowsPath
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];assets=ROOT/'assets/geography_test/climate'
input_path=assets/'generation_inputs.json'
if not input_path.exists():input_path=assets/'generation.json'
inputs=json.loads(input_path.read_text());entries=inputs.get('entries') or inputs['icons']
cfg=json.loads((ROOT/'configs/climate.json').read_text())
originals=assets/'originals';originals.mkdir(exist_ok=True)
report={'tool':inputs['tool'],'processing':'Original RGBA alpha preserved; crop transparent margins and scale to 464px within 512px canvas. Native 60px frames are copied unchanged.','icons':{}}
items=[]
for name,t in cfg['types'].items():
    if t['native']:continue
    entry=entries[name];dest=originals/(name+'.png')
    if not dest.exists():
        wp=PureWindowsPath(entry['generated_path']);src=Path('/mnt')/wp.drive[0].lower()/Path(*wp.parts[1:])
        shutil.copy2(src,dest)
    im=Image.open(dest).convert('RGBA')
    if im.getchannel('A').getextrema()!=(0,255):raise ValueError('Image lacks transparent alpha: '+name)
    im=im.crop(im.getchannel('A').getbbox());im.thumbnail((464,464),Image.Resampling.LANCZOS)
    result=Image.new('RGBA',(512,512),(0,0,0,0));result.alpha_composite(im,((512-im.width)//2,(512-im.height)//2));result.save(assets/(name+'.png'))
    report['icons'][name]={'prompt':entry['prompt'],'original':'originals/'+name+'.png','original_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'master_sha256':hashlib.sha256((assets/(name+'.png')).read_bytes()).hexdigest()}
    items.append((name,result))
canvas=Image.new('RGB',(800,340),(37,42,36));draw=ImageDraw.Draw(canvas)
for i,(name,im) in enumerate(items):
    x=(i%5)*160;y=(i//5)*170
    p=im.resize((70,70),Image.Resampling.LANCZOS);canvas.paste(p,(x+42,y+4),p)
    p=im.resize((30,30),Image.Resampling.LANCZOS);canvas.paste(p,(x+62,y+80),p)
    words=name.replace('_',' ').split();label=' '.join(words[:2])+'\n'+' '.join(words[2:])
    draw.text((x+8,y+122),label,fill='white')
canvas.save(assets/'preview.png');(assets/'generation.json').write_text(json.dumps(report,indent=2)+'\n')
print('Prepared',len(items),'RGBA icons')
