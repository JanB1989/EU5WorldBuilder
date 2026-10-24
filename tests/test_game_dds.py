"""Interface DDS of the geography export are in the game format; map-mode icons sit in main_menu only."""
from pathlib import Path
import pytest
from PIL import Image
from historical_agriculture import game_dds
from historical_agriculture.geography_test import ROOT, MOD_NAME
from historical_agriculture.geography_test_global_soils import write_soil_texture, write_map_mode_icon

EXPORT = ROOT/'artifacts/geography_test'/MOD_NAME
PIPELINE_DDS = ROOT.parent/'eu5-building-pipeline/src/eu5_building_pipeline/dds.py'


def max_side(relative):
    # Same rule as vanilla and the constructor's interface_dds: icons/** (not
    # illustrations) at most 128 px, advance icons 256, everything else keeps its size.
    inner = relative.parts[relative.parts.index('interface')+1:]
    if inner and inner[0]=='icons' and 'illustrations' not in inner:return 128
    if len(inner)==2 and inner[0]=='advance':return 256
    return None


def interface_dds_problems(mod):
    problems = []
    for layer in ['main_menu','in_game']:
        for path in sorted((mod/layer/'gfx/interface').rglob('*.dds')):
            relative = path.relative_to(mod)
            if not game_dds.is_game_format(path,max_side=max_side(relative)):
                info = game_dds.dds_info(path)
                problems.append(f'{relative}: {info}')
                continue
            with Image.open(path) as image:image.load()
    if (mod/'in_game/gfx/interface/icons/map_modes').exists():
        problems.append('in_game/gfx/interface/icons/map_modes exists (map-mode icons belong in main_menu only)')
    return problems


def master(path, color=(90,140,60)):
    image = Image.new('RGBA',(512,512),(0,0,0,0))
    image.paste(Image.new('RGBA',(400,400),(*color,255)),(56,56))
    for x in range(56):image.putpixel((x,10),(*color,x*4))  # soft alpha ramp
    image.putpixel((0,0),(*color,255))
    image.save(path)
    return path


def test_written_textures_are_game_format(tmp_path):
    source = master(tmp_path/'master.png')
    out = tmp_path/'mod'
    write_soil_texture(source,out/'main_menu/gfx/interface/soil_types/loam.dds',64)
    write_soil_texture(source,out/'main_menu/gfx/interface/icons/climate/ha1300_x.dds',70)
    write_map_mode_icon(source,out,'ha1300_soil_types')
    assert interface_dds_problems(out)==[]
    info = game_dds.dds_info(out/'main_menu/gfx/interface/icons/map_modes/ha1300_soil_types.dds')
    assert (info.format,info.width,info.mip_count)==('DXT5',128,8)
    assert game_dds.dds_info(out/'main_menu/gfx/interface/icons/climate/ha1300_x.dds').mip_count==7
    with Image.open(out/'main_menu/gfx/interface/soil_types/loam.dds') as image:
        assert image.size==(64,64) and image.convert('RGBA').getchannel('A').getextrema()==(0,255)


def test_checker_rejects_uncompressed_and_in_game_map_mode_icons(tmp_path):
    out = tmp_path/'mod'
    p = out/'in_game/gfx/interface/icons/map_modes/x.dds';p.parent.mkdir(parents=True)
    Image.new('RGBA',(128,128),(1,2,3,255)).save(p,format='DDS')
    assert len(interface_dds_problems(out))==2


@pytest.mark.skipif(not EXPORT.is_dir(),reason='geography export not built')
def test_built_export_interface_dds_are_game_format():
    assert interface_dds_problems(EXPORT)==[]


@pytest.mark.skipif(not PIPELINE_DDS.is_file(),reason='eu5-building-pipeline checkout absent')
def test_vendored_encoder_matches_building_pipeline():
    # Same encoder as the constructor's DDS pass, so its copies of the export stay byte-identical.
    vendored = Path(game_dds.__file__).read_text().split('\n',4)[4]
    assert vendored==PIPELINE_DDS.read_text()
