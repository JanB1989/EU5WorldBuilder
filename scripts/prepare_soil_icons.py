"""Prepare generated soil cutouts for the same RGBA -> DDS workflow as buildings.

The generated artwork is retained unchanged in originals/. This stage only keys
the prescribed production background and normalizes the texture canvas.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'assets/geography_test/soil_types'


def prepare(assets=ASSETS):
    manifest = json.loads((assets/'generation.json').read_text())
    for item in manifest['assets']:
        source = assets/'originals'/(item['name']+'.png')
        im = Image.open(source).convert('RGBA')
        pixels = np.asarray(im, dtype=float).copy()
        if item['chroma_key']:
            rgb = pixels[:,:,:3]
            excess = np.minimum(rgb[:,:,0],rgb[:,:,2])-rgb[:,:,1]
            alpha = 1-np.clip((excess-12)/65,0,1)
            edge = (alpha>0)&(alpha<1)
            rgb[edge] = np.clip((rgb[edge]-(1-alpha[edge,None])*[255,0,255])/alpha[edge,None],0,255)
            pixels[:,:,3] *= alpha
        # Ignore barely visible generated alpha dust when fitting the silhouette.
        pixels[pixels[:,:,3]<4] = 0
        im = Image.fromarray(pixels.astype('uint8'))
        bbox = im.getchannel('A').point(lambda x:255 if x>4 else 0).getbbox()
        if not bbox: raise ValueError(f'Empty icon: {source}')
        if manifest.get('normalization') == 'fixed_canvas':
            # Fertility is an ordered size progression with a common soil anchor.
            # Fitting each alpha bbox to the same size destroys that information.
            if im.width != im.height:
                raise ValueError(f'Fixed-canvas icon must be square: {source}')
            icon = im.resize((512,512),Image.Resampling.LANCZOS)
        else:
            crop = im.crop(bbox)
            crop.thumbnail((448,448),Image.Resampling.LANCZOS)
            icon = Image.new('RGBA',(512,512))
            icon.alpha_composite(crop,((512-crop.width)//2,(512-crop.height)//2))
        icon.save(assets/(item['name']+'.png'))
        item['original_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
        item['prepared_sha256'] = hashlib.sha256((assets/(item['name']+'.png')).read_bytes()).hexdigest()
    (assets/'generation.json').write_text(json.dumps(manifest,indent=2)+'\n')
    sheet = Image.new('RGB',(160*len(manifest['assets']),260),'#23352f');draw=ImageDraw.Draw(sheet)
    for i,item in enumerate(manifest['assets']):
        im=Image.open(assets/(item['name']+'.png'))
        for size,y in [(128,15),(30,175)]:
            icon=im.resize((size,size),Image.Resampling.LANCZOS)
            sheet.paste(icon,(i*160+(160-size)//2,y),icon)
        draw.text((i*160+55,225),item['name'].replace('_',' ').capitalize(),fill='#ede1c5')
    sheet.save(assets/'preview.png')


if __name__=='__main__': prepare()
