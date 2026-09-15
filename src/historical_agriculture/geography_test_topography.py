"""Export topography into the native game attribute and existing map mode."""
import json,re
import pandas as pd
from .geography_test import ROOT,write_text,sha
from .geography_test_vegetation import named_rgb,vegetation_definition
from .geography_test_global_soils import write_soil_texture


def patch_topography(source,assignments):
 starts=list(re.finditer(r'(?m)^([\w.-]+)\s*=\s*\{',source));seen=set()
 result=[source[:starts[0].start()]] if starts else [source]
 for i,m in enumerate(starts):
  end=starts[i+1].start() if i+1<len(starts) else len(source)
  text=source[m.start():end]
  if m[1] in assignments:
   text,n=re.subn(r'\btopography\s*=\s*\w+',lambda _: 'topography = '+assignments[m[1]],text)
   if n!=1:raise ValueError('Missing/duplicate topography: '+m[1])
   seen.add(m[1])
  result.append(text)
 if set(assignments)-seen:raise ValueError('Unknown template assignment')
 return ''.join(result)


def emit_topography(output,game):
 cfg=json.loads((ROOT/'configs/topography.json').read_text());folder=ROOT/cfg['output_directory']
 manifest=json.loads((folder/'manifest.json').read_text());d=pd.read_csv(folder/'locations.csv',keep_default_na=False)
 if sha(folder/'locations.csv')!=manifest['csv_sha256']:raise ValueError('Stale topography assignments')
 native=game/'in_game/common/topography/00_default.txt';source=native.read_text(encoding='utf-8-sig')
 audit=json.loads((ROOT/'reports/topography_game_audit.json').read_text())
 if sha(native)!=audit['sha256']:raise ValueError('Native topography changed; refresh audit')
 definitions=[];colors=['colors = {'];entries={};assets=ROOT/'assets/geography_test/topography'
 for name,t in cfg['types'].items():
  key=t['game_key'];color='ha1300_topography_'+name
  definitions.append(vegetation_definition(source,t['parent'],key,color,t['color']))
  colors.append(named_rgb(color,t['color']));entries[key]=t['label'];entries[key+'_desc']=t['description']
  write_soil_texture(assets/(name+'.png'),output/'main_menu/gfx/interface/topography'/(key+'.dds'),64)
 colors.append('}')
 # Original file is deliberately not shadowed: all 22 native keys/effects stay.
 write_text(output,'in_game/common/topography/ha1300_topography.txt','\n'.join(definitions))
 write_text(output,'main_menu/common/named_colors/ha1300_topography.txt','\n'.join(colors)+'\n')
 write_text(output,'main_menu/localization/english/ha1300_topography_l_english.yml','l_english:\n'+''.join(f' {k}: "{v}"\n' for k,v in entries.items()))
 if sha(game/'in_game/map_data/location_templates.txt')!=manifest['inputs']['data/raw/location_inputs/game_templates.txt']:raise ValueError('Game templates changed')
 # Patch the current COMPILED templates, preserving globally mapped vegetation.
 target=output/'in_game/map_data/location_templates.txt'
 write_text(output,'in_game/map_data/location_templates.txt',patch_topography(target.read_text(encoding='utf-8-sig'),d.set_index('location_tag').game_topography.to_dict()))
 write_text(output,'topography_assignments.csv',d.to_csv(index=False))
 write_text(output,'topography_source_manifest.json',json.dumps(manifest,indent=2))
 readme=(output/'README.md').read_text(encoding='utf-8-sig')
 readme+='\n## Global topography\n\nRolling Terrain, Valleys, Floodplains and Deltas refine ordinary terrain using published global landform data. All 22 original types remain defined, including water/wasteland classes. All ownable locations receive a value. Native Topography map mode, icon and blue concept tooltip are used, with no new UI slot or monthly event.\n\nNew values inherit flatland effects for this isolated prototype. Scripts checking exact vanilla keys will need later integration. Modern landforms approximate 1300; delta boundaries and river courses are explicitly uncertain.\n\nReproduce: `uv run ha1300 topography`, then `uv run ha1300 geography-test`. Assignment/source manifest includes fractions, coverage, thresholds and source licenses. Topography maps and assignments derived from EcoTapestry are CC-BY-SA-4.0 with all upstream attribution retained.\n'
 write_text(output,'README.md',readme)
 return {'ownable_locations':manifest['ownable_locations'],'ownable_missing':0,'new_types':list(cfg['types']),'counts':manifest['ownable_distribution'],'source_csv_sha256':manifest['csv_sha256'],'native_topography_sha256':sha(native),'icon_manifest_sha256':sha(assets/'generation.json')}
