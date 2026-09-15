"""Normalize generated terrain art and remove only edge-connected backdrop."""
from pathlib import Path
import json,hashlib
import numpy as np
from scipy.ndimage import binary_propagation
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'assets/geography_test/topography'

def main():
 manifest=json.loads((ASSETS/'generation.json').read_text())
 for item in manifest['assets']:
  source=ASSETS/'originals'/(item['name']+'.png')
  im=Image.open(source).convert('RGBA');a=np.array(im);rgb=a[:,:,:3].astype(float)
  # Built-in generation returned RGB with a neutral checkerboard instead of
  # alpha. Restrict removal to bright neutral pixels reachable from the edge;
  # the enclosed ivory rock highlights remain untouched.
  neutral=(rgb.max(axis=2)-rgb.min(axis=2)<24)&(rgb.min(axis=2)>155)
  seed=np.zeros(neutral.shape,bool);seed[0]=neutral[0];seed[-1]=neutral[-1];seed[:,0]=neutral[:,0];seed[:,-1]=neutral[:,-1]
  bg=binary_propagation(seed,mask=neutral)
  a[bg]=0
  im=Image.fromarray(a);box=im.getchannel('A').getbbox()
  if box is None or box==(0,0,im.width,im.height):raise ValueError('Backdrop extraction failed')
  crop=im.crop(box);crop.thumbnail((448,448),Image.Resampling.LANCZOS)
  icon=Image.new('RGBA',(512,512));icon.alpha_composite(crop,((512-crop.width)//2,(512-crop.height)//2))
  path=ASSETS/(item['name']+'.png');icon.save(path)
  item['original_sha256']=hashlib.sha256(source.read_bytes()).hexdigest();item['prepared_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
 (ASSETS/'generation.json').write_text(json.dumps(manifest,indent=2)+'\n')
 sheet=Image.new('RGB',(640,250),'#24312a');draw=ImageDraw.Draw(sheet)
 for i,item in enumerate(manifest['assets']):
  im=Image.open(ASSETS/(item['name']+'.png'))
  for size,y in [(128,10),(30,170)]:
   icon=im.resize((size,size),Image.Resampling.LANCZOS);sheet.paste(icon,(i*160+(160-size)//2,y),icon)
  draw.text((i*160+30,220),item['name'],fill='white')
 sheet.save(ASSETS/'preview.png')

if __name__=='__main__':main()
