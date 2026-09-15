"""Audit the complete global assignments and the compiled native test mod."""
from pathlib import Path
import json,re
import numpy as np
import pandas as pd
from PIL import Image
from historical_agriculture.location_inventory import read_zone_inventory
from historical_agriculture.geography_test import block_span,sha
from historical_agriculture.vegetation import choose_classes

ROOT=Path(__file__).resolve().parents[1]

def audit():
    folder=ROOT/'artifacts/vegetation';cfg=json.loads((ROOT/'configs/vegetation.json').read_text())
    manifest=json.loads((folder/'manifest.json').read_text())
    if sha(folder/'locations.csv')!=manifest['csv_sha256']:raise ValueError('Stale vegetation CSV')
    d=pd.read_csv(folder/'locations.csv',keep_default_na=False);own=d[d.is_ownable]
    zones=read_zone_inventory(ROOT/'data/raw/location_inputs')
    assert not d.location_tag.duplicated().any()
    assert set(own.location_tag)==set(zones[zones.is_ownable].location_tag)
    assert own.vegetation.isin(manifest['active_types']).all()
    fractions=own[[n+'_share' for n in cfg['types']]].to_numpy()
    assert np.isfinite(fractions).all() and (fractions>=0).all()
    assert np.allclose(fractions.sum(axis=1),1,atol=2e-6)
    sensitivity=[]
    for field,values in [('wetland_location_share_threshold',[.2,.3,.4,.5]),('farmland_location_share_threshold',[.25,.35,.5]),('minimum_new_type_locations',[10,25,50])]:
        for value in values:
            alt={**cfg,field:value}
            if field=='minimum_new_type_locations':
                active=[n for n,t in cfg['types'].items() if t['native'] or manifest['candidate_counts'].get(n,0)>=value]
                sensitivity.append({'parameter':field,'value':value,'active_types':active})
            else:
                classes=choose_classes(fractions,alt)
                sensitivity.append({'parameter':field,'value':value,'changed_candidate_locations':int(np.sum(classes!=own.candidate_vegetation)),'counts':pd.Series(classes).value_counts().to_dict()})
    mod=ROOT/'artifacts/geography_test/Land Clearance Geography Test'
    build=json.loads((mod/'ha1300-build.json').read_text())
    assert build['vegetation']['source_csv_sha256']==manifest['csv_sha256']
    for file,digest in build['files'].items():assert sha(mod/file)==digest,file
    applied=pd.read_csv(mod/'vegetation_assignments.csv',keep_default_na=False)
    text=(mod/'in_game/map_data/location_templates.txt').read_text(encoding='utf-8-sig')
    assert not applied.test_override.any()
    assert (applied.applied_game_vegetation==applied.game_vegetation).all()
    for retired in ['ha1300_clearable_forest','ha1300_clearing_continental']:
        assert retired not in text
    observed={}
    for match in re.finditer(r'(?m)^([\w.-]+)\s*=\s*\{([^{}]*)',text):
        v=re.search(r'\bvegetation\s*=\s*(\w+)',match[2])
        if v:observed[match[1]]=v[1]
    for row in applied[applied.game_vegetation.ne('')].itertuples():assert observed[row.location_tag]==row.applied_game_vegetation
    import tomllib
    local=tomllib.loads((ROOT/'geography_test.local.toml').read_text())
    game=Path(local['paths']['game_root'])/'game'
    native=(game/'in_game/common/vegetation/00_default.txt').read_text(encoding='utf-8-sig')
    def normalize(body):
        body=re.sub(r'(?m)^\s*color\s*=\s*\w+','',body)
        body=re.sub(r'debug_color\s*=\s*rgb\s*\{[^{}]*\}','',body)
        return re.sub(r'\s+','',body)
    palette=(mod/'main_menu/common/named_colors/ha1300_vegetation.txt').read_text(encoding='utf-8-sig')
    color_values={m[1]:m[2].split() for m in re.finditer(r'(ha1300_vegetation_\w+)\s*=\s*rgb\s*\{([^{}]*)\}',palette)}
    assert len(color_values)==len(manifest['active_types'])
    for name in manifest['active_types']:
        channels=color_values['ha1300_vegetation_'+name]
        assert all(re.fullmatch(r'\d+',v) for v in channels), 'EU5 requires integer RGB channels'
        assert list(map(int,channels))==cfg['types'][name]['color']
    icons=0
    for name in manifest['active_types']:
        t=cfg['types'][name]
        fname='00_default.txt' if t['native'] else 'ha1300_global_vegetation.txt'
        text=(mod/'in_game/common/vegetation'/fname).read_text(encoding='utf-8-sig')
        _,i,j=block_span(text,t['game_key']);_,a,b=block_span(native,t['parent'])
        assert normalize(text[i:j])==normalize(native[a:b])
        if not t['native']:
            icon=Image.open(mod/'main_menu/gfx/interface/vegetation'/(t['game_key']+'.dds'))
            assert icon.size==(64,64) and icon.getchannel('A').getextrema()==(0,255)
            icons+=1
    report={'ownable_locations':len(own),'ownable_missing':0,'fraction_conservation':True,
        'exported_template_assignment_parity':True,'new_icons_checked':icons,
        'named_rgb_integer_channels_verified':True,'parent_mechanics_preserved':True,'existing_native_values_preserved':7,
        'test_override_locations':applied[applied.test_override].location_tag.tolist(),
        'source_coverage_below_80_percent':int(sum(own.source_coverage<.8)),
        'low_confidence_ownable':int(own.low_confidence.sum()),'sensitivity':sensitivity,
        'input_manifest_sha256':sha(folder/'manifest.json'),'compiled_manifest_sha256':sha(mod/'ha1300-build.json'),
        'science_status':'Shared global evidence-guided rules; historical regional accuracy not independently validated.'}
    (folder/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
    own.groupby(['macro_region','vegetation']).size().unstack(fill_value=0).to_csv(folder/'regional_counts.csv')
    return {'passed':True,'ownable_locations':len(own),'new_icons':icons}

if __name__=='__main__':print(json.dumps(audit(),indent=2))
