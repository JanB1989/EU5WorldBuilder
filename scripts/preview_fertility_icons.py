"""Compare fertility artwork on native EU5 frames at real 30px UI size."""
from pathlib import Path
import tomllib
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'assets/geography_test/fertility'
NAMES=['very_low','low','moderate','high','very_high']
COLOURS=['#A8403B','#D77D40','#DBBF64','#8BB65E','#378B50']


def render():
    local=tomllib.loads((ROOT/'geography_test.local.toml').read_text())
    game=Path(local['paths']['game_root'])/'game'
    frame=Image.open(game/'main_menu/gfx/interface/icons/climate/continental_frame.dds').convert('RGBA').resize((30,30),Image.Resampling.LANCZOS)
    sheet=Image.new('RGB',(800,360),'#1c2e29');draw=ImageDraw.Draw(sheet)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',14)
    small=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',12)
    strip=Image.new('RGBA',(175,34),'#1c2e29')
    for i,name in enumerate(NAMES):
        master=Image.open(ASSETS/(name+'.png')).convert('RGBA')
        big=master.resize((112,112),Image.Resampling.LANCZOS)
        sheet.paste(big,(i*160+24,12),big)
        draw.rounded_rectangle((i*160+40,130,i*160+120,144),radius=3,fill=COLOURS[i])
        label=name.replace('_',' ').capitalize()
        draw.text((i*160+80,161),label,font=font,fill='#f0e2c6',anchor='mm')
        strip.alpha_composite(frame,(i*35,2))
        # Exactly the exported 64px texture, then the game's 30px display size.
        tiny=master.resize((64,64),Image.Resampling.LANCZOS).resize((30,30),Image.Resampling.LANCZOS)
        strip.alpha_composite(tiny,(i*35,2))
    sheet.paste(strip,((800-strip.width)//2,198),strip)
    draw.text((400,240),'Actual 30px icons on the native frame',font=small,fill='#ddd5bd',anchor='mm')
    zoom=strip.resize((525,102),Image.Resampling.NEAREST)
    sheet.paste(zoom,((800-525)//2,254),zoom)
    sheet.save(ASSETS/'preview.png')

if __name__=='__main__':render()
