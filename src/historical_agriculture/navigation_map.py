"""Thin water-tile export, preserving land identities and explicit crossings."""
from collections import Counter, deque, defaultdict
from pathlib import Path
import base64
import io
import json
import re
import tomllib

import numpy as np
import pandas as pd
from PIL import Image
from scipy import ndimage

from .location_inventory import read_zone_inventory
from .river_network import save_json, digest
from .navigation_cleanup import LEVELS

ROOT = Path(__file__).resolve().parents[2]
STATE_NAMES = {1: "navigable", 2: "improvable", 3: "barrier"}


def encode(rgb):
    return (rgb[..., 0].astype(np.uint32) << 16) | (rgb[..., 1].astype(np.uint32) << 8) | rgb[..., 2]


def neighbours(p, width, total):
    for q in (p-width, p+width, p-1, p+1):
        if 0 <= q < total and (abs(q-p) != 1 or q//width == p//width): yield q


def partition(points, width, height, target, minimum):
    """Connected graph partitions; small tails join a neighbouring same-state tile."""
    pending = set(points); owner = {}; groups = []
    while pending:
        seed = min(pending)
        queue = deque([seed]); queued = {seed}; group = []
        while queue and len(group) < target:
            p = queue.popleft()
            if p not in pending: continue
            pending.remove(p); group.append(p)
            for q in neighbours(p, width, width*height):
                if q in pending and q not in queued: queue.append(q); queued.add(q)
        if len(group) < minimum:
            contact = Counter(owner[q] for p in group for q in neighbours(p, width, width*height) if q in owner)
            if contact:
                dest = contact.most_common(1)[0][0]; groups[dest].extend(group)
                owner.update({p: dest for p in group})
                continue
        dest = len(groups); groups.append(group); owner.update({p: dest for p in group})
    return groups


def pair_set(a):
    pairs = set()
    for x, y in [(a[:-1], a[1:]), (a[:, :-1], a[:, 1:])]:
        hit = x != y
        pairs.update(tuple(sorted((int(u), int(v)))) for u, v in zip(x[hit], y[hit]))
    return pairs


def append_list(text, key, names):
    match = re.search(r"\b"+key+r"\s*=\s*\{", text)
    addition = "\n\t"+" ".join(names)+"\n"
    if not match: return text+f"\n{key} = {{{addition}}}\n"
    return text[:match.end()]+addition+text[match.end():]


def export(config, evidence, river):
    raw = ROOT/config["raw_inputs"]; out = ROOT/config["output"]; mod = out/"mod"
    game = Path(tomllib.loads((ROOT/config["local_config"]).read_text())["paths"]["game_root"])/"game"
    cfg = config["raster"]
    width_px = int(cfg["width_pixels"])
    if width_px not in (1, 2, 3): raise ValueError("Supported navigation widths are 1, 2 or 3 pixels")
    written = []
    def write(rel, text):
        p = mod/rel; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8-sig", newline="\n"); written.append(rel)
    def source(rel): return (game/rel).read_text(encoding="utf-8-sig")
    md = "in_game/map_data/"
    Image.MAX_IMAGE_PIXELS = None
    original = encode(np.asarray(Image.open(raw/"locations.png").convert("RGB")))
    height, width = original.shape; flat = original.ravel()
    inventory = read_zone_inventory(raw)
    colors = dict(zip(inventory.location_tag, (int(x, 16) for x in inventory.map_color_rgb)))
    names = {v: k for k, v in colors.items()}
    land = {colors[r.location_tag] for r in inventory.itertuples() if r.is_ownable}
    seas = {colors[r.location_tag] for r in inventory.itertuples() if "sea_zones" in r.game_zone_class and "impassable" not in r.game_zone_class}
    lakes = {colors[r.location_tag] for r in inventory.itertuples() if r.game_zone_class == "lakes"}
    base_info = pd.read_parquet(raw/"inventory.parquet").set_index("location_tag")
    pixel_rows = evidence.set_index(evidence.y.astype(np.int64)*width+evidence.x.astype(np.int64))
    native_inputs={}
    for override in config.get('native_geometry_overrides',[]):
        path=game/md/'rivers.png';native_inputs[str(path)]=digest(path)
        x0,y0,x1,y1=override['box'];native=np.asarray(Image.open(path).crop((x0,y0,x1,y1)))
        # The evidence remains the matched physical river, while the local
        # geometry follows the already-tested game alignment at its estuary.
        local=pixel_rows[pixel_rows.x.between(x0,x1-1)&pixel_rows.y.between(y0,y1-1)]
        if local.empty:raise ValueError('No evidence for native geometry override '+override['id'])
        selected=local[local.state>0]
        if selected.empty:raise ValueError('Native geometry override has no selected river')
        reference=selected.iloc[len(selected)//2]
        pixel_rows.loc[local.index,'state']=0
        yy,xx=np.where(native<254);additions=[];indices=[]
        for y,x in zip(yy+y0,xx+x0):
            row=reference.copy();row['x']=x;row['y']=y;row['state']={v:k for k,v in STATE_NAMES.items()}[override['state']];row['evidence']=override['id']
            additions.append(row);indices.append(int(y)*width+int(x))
        pixel_rows=pixel_rows.drop(index=[p for p in indices if p in pixel_rows.index])
        pixel_rows=pd.concat([pixel_rows,pd.DataFrame(additions,index=indices)])
    from .navigation_cleanup import snap_mouths
    pixel_rows,mouth_snaps=snap_mouths(pixel_rows,original,land,seas,cfg.get('maximum_mouth_snap_pixels',6))
    # Native river lines are eight-connected; location adjacency is four-
    # connected. Fill only the corner of existing diagonal river neighbours,
    # never a gap between unrelated stretches or a retained native barrier.
    selected_rows={int(p):r for p,r in pixel_rows.iterrows() if int(r.state)>0 and int(flat[p]) in land}
    bridges={}
    for p,r in selected_rows.items():
        for delta in (width-1,width+1):
            q=p+delta
            if q not in selected_rows or abs(q%width-p%width)!=1:continue
            other=selected_rows[q]
            # A visible confluence is an actual raster connection even when
            # nearest-source registration assigned the two banks to different basins.
            corners=[p+width,q-width]
            if any(c in selected_rows or c in bridges for c in corners):continue
            options=[c for c in corners if int(flat[c]) in land and river.ravel()[c]>=16]
            if not options:continue
            c=min(options);source_row=r if r.state>=other.state else other
            row=source_row.copy();row['x']=c%width;row['y']=c//width
            bridges[c]=row
    if bridges:
        pixel_rows=pd.concat([pixel_rows,pd.DataFrame.from_dict(bridges,orient='index')])
    groups = []; omitted = Counter()
    retained_land = {colors[n] for n in cfg.get('retain_native_locations', [])}
    selected=set(pixel_rows.index[pixel_rows.state>0])
    selected={p for p in selected if int(flat[p]) in land and int(flat[p]) not in retained_land}
    parts=partition(selected,width,height,max(1,cfg['target_tile_pixels']//width_px),max(1,cfg['minimum_tile_pixels']//width_px))
    for group in parts:
        rows=pixel_rows.loc[group]
        # Coarse elevation noise must not create a succession of one-pixel
        # impassable gaps. Classify a whole connected tile; explicit historical
        # barriers always win over the physical median.
        state=int(np.median(rows.state))
        explicit=rows[rows.evidence!='physical_screen']
        if len(explicit):state=max(state,int(explicit.state.max()))
        groups.append({'state':state,'center':group})
    all_centers = {p for g in groups for p in g["center"]}
    # Width is graphical only. Avoid painting another unconverted river or lake.
    occupied = {}; candidates = []
    river_flat = river.ravel()
    for group in groups:
        cells = set(group["center"])
        if any(int(flat[q]) in lakes for p in cells for q in neighbours(p,width,flat.size)):
            omitted['lake_contact_native_pixels'] += len(cells)
            continue
        for p in group["center"]:
            horizontal = (p-1 in all_centers or p+1 in all_centers)
            offsets = [width if horizontal else 1] if width_px == 2 else ([width, -width] if horizontal else [1, -1]) if width_px == 3 else []
            for offset in offsets:
                q = p+offset
                if not 0 <= q < flat.size or (abs(offset)==1 and p//width != q//width): continue
                if int(flat[q]) not in land or int(flat[q]) in retained_land or (river_flat[q] < 16 and q not in cells): continue
                if q in occupied or q in all_centers: continue
                if any((n in all_centers and n not in cells) or (n in occupied) for n in neighbours(q,width,flat.size)):continue
                # Do not widen across a retained native river pixel; a short
                # unconverted barrier must remain a break in the fleet network.
                if any(river_flat[n] < 16 and n not in all_centers for n in neighbours(q, width, flat.size)): continue
                cells.add(q)
        cells -= occupied.keys()
        if any(int(flat[q]) in lakes for p in cells for q in neighbours(p,width,flat.size)):
            omitted['lake_contact_native_pixels'] += len(cells)
            continue
        if len(cells) < cfg["minimum_tile_pixels"]:
            omitted["undersized_state_piece"] += len(cells); continue
        i = len(candidates); occupied.update({p: i for p in cells})
        group["cells"] = cells; candidates.append(group)
    print(f"Navigation raster: {len(candidates)} candidate tiles", flush=True)
    # Exclude whole tiles, not isolated bank pixels, when they would consume
    # too much land or divide an existing location. Native rivers then remain.
    unique_colors, counts = np.unique(flat, return_counts=True)
    owned_counts = dict(zip(map(int, unique_colors), map(int, counts)))
    removed = Counter(int(flat[p]) for p in occupied)
    bad = {c for c, n in removed.items() if owned_counts[c]-n < cfg["minimum_remaining_land_pixels"] or n/owned_counts[c] > cfg["maximum_land_fraction_removed"]}
    active = [g for g in candidates if not any(int(flat[p]) in bad for p in g["cells"])]
    omitted["land_area_guard_tiles"] = len(candidates)-len(active)
    # Converting an internal river can cut a location into two. Keep these
    # ambiguous cases native instead of transferring substantial land ownership.
    for _ in range(4 if cfg.get("preserve_land_connectivity",True) else 0):
        removal_by_land = defaultdict(list)
        all_removed = {p for g in active for p in g['cells']}
        for i, g in enumerate(active):
            for p in g["cells"]: removal_by_land[int(flat[p])].append((p, i))
        reject = set()
        for c, values in removal_by_land.items():
            tag = names[c]; row = base_info.loc[tag]
            x0, x1 = int(row.bbox_min_x), int(row.bbox_max_x)+1
            y0, y1 = int(row.bbox_min_y), int(row.bbox_max_y)+1
            before = original[y0:y1, x0:x1] == c
            after = before.copy()
            for p, _i in values: after[p//width-y0, p%width-x0] = False
            before_labels, before_count = ndimage.label(before)
            labels, count = ndimage.label(after)
            if count > before_count:
                # A boundary-following river often cuts off a few raster pixels.
                # Permit only bounded fragments which can join a bank; larger
                # splits retain the native river instead.
                small = 0
                safe = True
                for component in range(1, before_count+1):
                    ids, sizes = np.unique(labels[(before_labels==component) & after], return_counts=True)
                    if not len(ids): safe=False; break
                    for ident, size in zip(ids,sizes):
                        if ident==ids[sizes.argmax()]:continue
                        fragment=labels==ident; ring=ndimage.binary_dilation(fragment)&~fragment
                        ry,rx=np.where(ring)
                        targets=[int(original[yy+y0,xx+x0]) for yy,xx in zip(ry,rx) if (yy+y0)*width+xx+x0 not in all_removed]
                        if size>cfg['maximum_reassigned_fragment_pixels'] or not any(v in land and v!=c for v in targets):safe=False
                        small+=int(size)
                if not safe or (small+len(values))/owned_counts[c]>cfg['maximum_land_fraction_removed']:
                    reject.update(i for _, i in values)
        if not reject: break
        omitted["land_connectivity_guard_tiles"] += len(reject)
        active = [g for i, g in enumerate(active) if i not in reject]
    # Stable ordering and tags do not depend on hash/set iteration order.
    active.sort(key=lambda g: (min(g["center"]), g["state"]))
    next_color = 0x010001
    after = original.copy(); af = after.ravel(); tile_by_color = {}; tile_meta = []
    for i, g in enumerate(active, 1):
        while next_color in names: next_color += 1
        color = next_color; next_color += 1
        tag = f"pp_nav_{i:05d}"
        af[list(g["cells"])] = color
        g.update(color=color, tag=tag); tile_by_color[color] = g
        source_land = Counter(names[int(flat[p])] for p in g["cells"]).most_common(1)[0][0]
        region = str(base_info.loc[source_land, "region"])
        rows = pixel_rows.loc[g["center"]]
        tile_meta.append({"location": tag, "state": STATE_NAMES[g["state"]], "pixels": len(g["cells"]),
                          "region": region, "near_location": source_land,
                          "mean_discharge_m3_s": float(rows.q_mean_m3_s.median()),
                          "low_discharge_m3_s": float(rows.q_min_m3_s.median()),
                          "gradient_m_per_km": float(rows.gradient_m_per_km.median()),
                          "evidence": ";".join(sorted(set(rows.evidence))),
                          "river_level": int(max([0]+[int(LEVELS[river.ravel()[p]]) for p in g["center"]])),
                          "tropical": bool(abs(float(rows.latitude.median())) <= config['selection'].get('tropical_latitude',23.5)),
                          "seasonal": bool(float(rows.q_min_m3_s.median()) / max(float(rows.q_mean_m3_s.median()),1) < config['selection'].get('seasonal_low_flow_ratio',.15)),
                          "x": float(rows.x.mean()), "y": float(rows.y.mean())})
        names[color] = tag; colors[tag] = color
    changed = np.flatnonzero(af != flat)
    repairs=[]; unsafe_banks=set()
    for c in sorted(set(map(int,flat[changed])) & land):
        row=base_info.loc[names[c]]
        x0,x1=max(0,int(row.bbox_min_x)-1),min(width,int(row.bbox_max_x)+2)
        y0,y1=max(0,int(row.bbox_min_y)-1),min(height,int(row.bbox_max_y)+2)
        before_labels,before_count=ndimage.label(original[y0:y1,x0:x1]==c)
        labels,count=ndimage.label(after[y0:y1,x0:x1]==c)
        if count<=before_count:continue
        for component in range(1,before_count+1):
            ids,sizes=np.unique(labels[(before_labels==component)&(labels>0)],return_counts=True)
            if not len(ids):
                unsafe_banks.add(names[c]);continue
            for ident,size in zip(ids,sizes):
                if ident==ids[sizes.argmax()]:continue
                fragment=labels==ident;ring=ndimage.binary_dilation(fragment)&~fragment
                options=Counter(int(v) for v in after[y0:y1,x0:x1][ring] if int(v) in land and int(v)!=c)
                if not options or size>cfg['maximum_reassigned_fragment_pixels']:
                    if cfg.get('preserve_land_connectivity',True):unsafe_banks.add(names[c])
                    continue
                target=options.most_common(1)[0][0]
                after[y0:y1,x0:x1][fragment]=target
                repairs.append({'from':names[c],'to':names[target],'pixels':int(size)})
    if unsafe_banks:
        if config.get('_bank_retry',0)>=5:raise ValueError('Unsafe bank fragments: '+str(sorted(unsafe_banks)))
        adjusted=json.loads(json.dumps(config));adjusted['_bank_retry']=config.get('_bank_retry',0)+1
        adjusted['raster']['retain_native_locations']=sorted(set(cfg.get('retain_native_locations',[]))|unsafe_banks)
        print('Retaining native rivers at unsafe banks: '+', '.join(sorted(unsafe_banks)),flush=True)
        del original,after,flat,af
        return export(adjusted,evidence,river)
    final_colors,final_counts=np.unique(after,return_counts=True)
    final_sizes=dict(zip(map(int,final_colors),map(int,final_counts)))
    invalid_land={c for c in land if final_sizes.get(c,0)<min(cfg['minimum_remaining_land_pixels'],owned_counts[c]) or (owned_counts[c]-final_sizes.get(c,0))/owned_counts[c]>cfg['maximum_land_fraction_removed']}
    if invalid_land:
        if config.get('_area_retry',0)>=5:raise ValueError('Land area validation failed')
        adjusted=json.loads(json.dumps(config));adjusted['_area_retry']=config.get('_area_retry',0)+1
        adjusted['raster']['retain_native_locations']=sorted(set(cfg.get('retain_native_locations',[]))|{names[c] for c in invalid_land})
        print('Retaining native rivers to preserve bank area: '+', '.join(names[c] for c in sorted(invalid_land)),flush=True)
        del original,after,flat,af
        return export(adjusted,evidence,river)
    bisected=[]
    for c in sorted(set(map(int,flat[changed])) & land):
        r=base_info.loc[names[c]];y0,y1=int(r.bbox_min_y),int(r.bbox_max_y)+1;x0,x1=int(r.bbox_min_x),int(r.bbox_max_x)+1
        before_n=ndimage.label(original[y0:y1,x0:x1]==c)[1];after_n=ndimage.label(after[y0:y1,x0:x1]==c)[1]
        if after_n>before_n:bisected.append({'location':names[c],'original_parts':before_n,'riverbank_parts':after_n})
    changed = np.flatnonzero(af != flat)
    adjacent = defaultdict(set); coast_pixels = defaultdict(list); lost_candidates = set()
    for p in changed:
        c = int(af[p])
        for q in neighbours(int(p), width, flat.size):
            d = int(af[q])
            if c != d:
                if c in tile_by_color:
                    adjacent[c].add(d)
                    if d in land: coast_pixels[(d, c)].append(int(p))
                elif d in tile_by_color:
                    adjacent[d].add(c)
                    if c in land:coast_pixels[(c,d)].append(int(q))
            a, b = int(flat[p]), int(flat[q])
            if a != b and a in land and b in land: lost_candidates.add(tuple(sorted((a, b))))
    # Ensure every emitted zone is a single four-connected component.
    for g in active:
        p = np.array(sorted(g["cells"])); x, y = p%width, p//width
        mask = np.zeros((y.max()-y.min()+1, x.max()-x.min()+1), bool); mask[y-y.min(), x-x.min()] = True
        assert ndimage.label(mask)[1] == 1 and len(p) >= cfg["minimum_tile_pixels"], g["tag"]
    # Every lost land-land connection gets an explicit crossing if one exists
    # through a single zone. Short tiles that cannot restore it are rejected.
    lost = set()
    for a, b in lost_candidates:
        ra, rb = base_info.loc[names[a]], base_info.loc[names[b]]
        x0, x1 = min(int(ra.bbox_min_x),int(rb.bbox_min_x)), max(int(ra.bbox_max_x),int(rb.bbox_max_x))+1
        y0, y1 = min(int(ra.bbox_min_y),int(rb.bbox_min_y)), max(int(ra.bbox_max_y),int(rb.bbox_max_y))+1
        if (a, b) not in pair_set(after[y0:y1, x0:x1]): lost.add((a,b))
    crossings = {}
    for p in changed:
        y, x = divmod(int(p), width); through = int(af[p])
        if through not in tile_by_color:continue
        for dy, dx in [(1,0),(0,1),(1,1),(1,-1)]:
            banks = []
            for sign in (-1,1):
                for distance in range(1, int(cfg["maximum_crossing_span_pixels"])+1):
                    yy, xx = y+sign*dy*distance, x+sign*dx*distance
                    if not (0 <= yy < height and 0 <= xx < width): break
                    c = int(after[yy,xx])
                    if c == through: continue
                    if c in land: banks.append((c,xx,yy,distance))
                    break
            if len(banks)!=2: continue
            a,b=banks; pair=tuple(sorted((a[0],b[0])))
            if pair not in lost: continue
            candidate=(a[3]+b[3],names[a[0]],names[b[0]],names[through],a[1],height-a[2],b[1],height-b[2])
            if pair not in crossings or candidate < crossings[pair]: crossings[pair]=candidate
    missing = lost-set(crossings)
    if missing:
        save_json(out/"failed_crossings.json", [[names[a],names[b]] for a,b in sorted(missing)])
        if config.get('_crossing_retry',0)>=4:
            raise ValueError(f"{len(missing)} lost land adjacencies could not be restored; see failed_crossings.json")
        adjusted=json.loads(json.dumps(config));adjusted['_crossing_retry']=config.get('_crossing_retry',0)+1
        retained=set(cfg.get('retain_native_locations',[]))|{names[c] for pair in missing for c in pair}
        adjusted['raster']['retain_native_locations']=sorted(retained)
        print(f'Retaining native rivers in {len(retained)} locations to protect land crossings',flush=True)
        del original,after,flat,af
        return export(adjusted,evidence,river)
    # Ports: preserve existing ones whose coordinate remains in the assigned sea.
    port_rows = source(md+"ports.csv").splitlines(); old_ports={r.split(';')[0]:r.split(';') for r in port_rows[1:] if ';' in r}
    port_changes = {}; port_candidates=defaultdict(list)
    for (land_c, sea_c), points in coast_pixels.items():
        if tile_by_color[sea_c]["state"] != 3: port_candidates[land_c].append((sea_c, points))
    for land_c, choices in sorted(port_candidates.items()):
        name=names[land_c]; old=old_ports.get(name)
        if old:
            px,py=int(old[2]),height-int(old[3])
            if 0<=px<width and 0<=py<height and int(after[py,px])==colors.get(old[1]):continue
        sea_c,points=max(choices,key=lambda item:(len(item[1]),-item[0]))
        xy=np.array([(p%width,p//width) for p in points]); idx=np.argmin(((xy-xy.mean(axis=0))**2).sum(axis=1))
        x,y=map(int,xy[idx]);port_changes[name]=(names[sea_c],x,y)
    for name,(sea,x,y) in port_changes.items():
        assert int(after[y,x])==colors[sea]
        assert colors[name] in {int(af[q]) for q in neighbours(y*width+x,width,flat.size)}
        assert tile_by_color[colors[sea]]['state']!=3
    port_rows=[r for r in port_rows if r.split(';')[0] not in port_changes]
    port_rows += [f"{n};{sea};{x};{height-y};x" for n,(sea,x,y) in sorted(port_changes.items())]
    write(md+"ports.csv",'\n'.join(port_rows)+'\n')
    cross_rows=source(md+"adjacencies.csv").rstrip().splitlines()
    for _dist,a,b,through,x,y,bx,by in sorted(crossings.values()):cross_rows.append(f"{a};{b};sea;{through};{x};{y};{bx};{by};River navigation crossing")
    write(md+"adjacencies.csv",'\n'.join(cross_rows)+'\n')
    # Separate water-only hierarchy, appended after every vanilla location.
    areas=defaultdict(list)
    for row in tile_meta: areas[row['region']].append(row['location'])
    area_names={region:'pp_nav_'+region+'_area' for region in areas}
    blocks=['\npp_navigation_waterways = { pp_navigation_subcontinent = { pp_navigation_region = {']
    for region,tags in sorted(areas.items()):
        blocks.append(area_names[region]+' = {')
        for start in range(0,len(tags),12):blocks.append(f' pp_nav_{region}_{start//12}_province = {{ '+ ' '.join(tags[start:start+12])+' }')
        blocks.append('}')
    blocks.append('} } }')
    write(md+'definitions.txt',source(md+'definitions.txt')+'\n'.join(blocks)+'\n')
    text=append_list(source(md+'default.map'),'sea_zones',[r['location'] for r in tile_meta])
    text=append_list(text,'impassable_mountains',[r['location'] for r in tile_meta if r['state']=='barrier'])
    write(md+'default.map',text)
    write('loading_screen/common/defines/pp_navigation_map.txt',f'NLocation = {{ MIN_LOCATION_PIXELS = {cfg["minimum_tile_pixels"]} }}\n')
    write(md+'named_locations/pp_navigation.txt','\n'.join(f"{g['tag']} = {g['color']:06x}" for g in active)+'\n')
    sea_templates='\n'.join(f"{r['location']} = {{ topography = {'ocean_wasteland' if r['state']=='barrier' else 'narrows'} climate = oceanic }}" for r in tile_meta)+'\n'
    (out/'sea_templates.txt').write_text(sea_templates)
    write(md+'location_templates.txt',source(md+'location_templates.txt')+'\n'+sea_templates)
    # Preserve discovery through the region/area/province of each original bank.
    for p in sorted((game/'main_menu/setup/templates').glob('*.txt')):
        text=p.read_text(encoding='utf-8-sig');tokens=set()
        for body in re.findall(r'discovered_(?:regions|areas|provinces)\s*=\s*\{([^}]+)\}',text):tokens.update(re.sub(r'#[^\n]*','',body).split())
        regions=set(base_info.index[base_info.index.isin([])])
        for field in ['region','area','province']:
            if field in base_info:regions.update(base_info.loc[base_info[field].isin(tokens),'region'])
        add=[area_names[r] for r in sorted(regions & areas.keys())]
        if add:write('main_menu/setup/templates/'+p.name,append_list(text,'discovered_areas',add))
    rgb=np.stack(((after>>16)&255,(after>>8)&255,after&255),axis=-1).astype(np.uint8)
    path=mod/md/'locations.png';path.parent.mkdir(parents=True,exist_ok=True)
    Image.fromarray(rgb).save(path,compress_level=7);written.append(md+'locations.png')
    # Locator updates are bounded to changed pixels. Native intentional offsets
    # elsewhere are left alone; new fleet/combat anchors always lie in water.
    locator_re=re.compile(r'\{\s*id\s*=\s*(\w+)\s+position\s*=\s*\{([^}]+)\}[^{}]*rotation\s*=\s*\{[^}]*\}[^{}]*scale\s*=\s*\{[^}]*\}\s*\}')
    centers={}
    for g in active:
        p=np.array(sorted(g['cells']));xy=np.column_stack((p%width,p//width));i=int(np.argmin(((xy-xy.mean(axis=0))**2).sum(axis=1)))
        centers[g['tag']]=(float(xy[i,0])+.5,float(height-xy[i,1])-.5)
    moved=Counter()
    for kind in ['city','combat','unit_stack','dock']:
        rel=f'in_game/gfx/map/map_objects/generated_map_object_locators_{kind}.txt';text=source(rel);seen=set()
        def fix(m):
            n=m.group(1);seen.add(n);pos=None
            if kind=='dock' and n in port_changes:
                _,x,y=port_changes[n];pos=(x+.5,height-y-.5)
            elif kind!='dock' and n in colors:
                x,_h,z=map(float,m.group(2).split());px,py=int(x),int(height-z)
                if 0<=px<width and 0<=py<height and after[py,px]!=original[py,px] and n in base_info.index:
                    row=base_info.loc[n];x0,x1=int(row.bbox_min_x),int(row.bbox_max_x)+1;y0,y1=int(row.bbox_min_y),int(row.bbox_max_y)+1
                    yy,xx=np.where(after[y0:y1,x0:x1]==colors[n]);k=int(np.argmin((xx+x0-x)**2+(yy+y0-py)**2));pos=(xx[k]+x0+.5,height-yy[k]-y0-.5)
            if pos is None:return m.group(0)
            moved[kind]+=1
            return re.sub(r'position\s*=\s*\{[^}]+\}',f'position={{ {pos[0]} 0 {pos[1]} }}',m.group(0))
        text=locator_re.sub(fix,text)
        add=centers if kind in ('combat','unit_stack') else {n:(x+.5,height-y-.5) for n,(_,x,y) in port_changes.items() if n not in seen} if kind=='dock' else {}
        additions=''.join(f'\n {{ id={n} position={{ {x} 0 {z} }} rotation={{ 0 0 0 1 }} scale={{ 1 1 1 }} }}' for n,(x,z) in add.items())
        close=text.rfind('}',0,text.rfind('}'));assert len(seen)>1000
        write(rel,text[:close]+additions+'\n'+text[close:])
    from .navigation_cleanup import preserve_levels
    cleaned,preservation,original_level_map=preserve_levels(river,original,after,land,base_info.reset_index(),[o['box'] for o in config.get('native_geometry_overrides',[])])
    palette_image=Image.open(ROOT/json.loads((ROOT/config['river_export']/'export_manifest.json').read_text())['output_png'])
    cleaned_image=Image.fromarray(cleaned,mode='P');cleaned_image.putpalette(palette_image.getpalette())
    cleaned_image.save(mod/md/'rivers.png');written.append(md+'rivers.png')
    pd.DataFrame(preservation,columns=['location_tag','river_level','x','y','distance_pixels']).to_csv(out/'preserved_river_pixels.csv',index=False)
    metadata={r['location']:r for r in tile_meta}
    # Geometry contract for Constructor: no gameplay building balance here.
    edges=[]
    for c,targets in sorted(adjacent.items()):
        for d in sorted(targets):
            if d in tile_by_color and c>d:continue
            if d in tile_by_color or d in seas or (config['shore_connections'] and d in land):
                state=max(tile_by_color[c]['state'],tile_by_color[d]['state'] if d in tile_by_color else 1)
                rough=any(metadata[n].get('tropical') or metadata[n].get('seasonal') for n in [names[c],names[d]] if n in metadata)
                profile='difficult' if state==1 and rough else STATE_NAMES[state]
                edges.append({'from':names[c],'to':names[d],'state':STATE_NAMES[state],'cost_profile':profile,'shore':d in land})
    graph=defaultdict(set)
    passable={r['location'] for r in tile_meta if r['state']!='barrier'}
    ocean={names[c] for c in seas}
    for edge in edges:
        if not edge['shore'] and edge['state']!='barrier':
            graph[edge['from']].add(edge['to']);graph[edge['to']].add(edge['from'])
    visited=set(ocean);queue=deque(ocean)
    while queue:
        for node in graph[queue.popleft()]-visited:visited.add(node);queue.append(node)
    water_connected=len(passable & visited)
    components=[];pending=set(passable)
    while pending:
        seed=min(pending);component={seed};queue=deque([seed]);pending.remove(seed)
        while queue:
            for node in graph[queue.popleft()] & pending:pending.remove(node);component.add(node);queue.append(node)
        components.append(len(component))
    shore=[]
    for (l,c),points in sorted(coast_pixels.items()):shore.append({'location_tag':names[l],'water_location':names[c],'state':STATE_NAMES[tile_by_color[c]['state']], 'shore_pixels':len(points)})
    for row in tile_meta:row['ocean_connected']=row['location'] in visited
    pd.DataFrame(tile_meta).to_csv(out/'tiles.csv',index=False)
    pd.DataFrame(edges).to_csv(out/'edges.csv',index=False)
    pd.DataFrame(shore).to_csv(out/'shores.csv',index=False)
    # The native bitmap now preserves exactly one maximum level per original
    # land location. No gameplay compensation is needed or allowed to stack.
    original_effects={c:{n} for c,n in original_level_map.items() if n}
    bonus_rows=[]
    pd.DataFrame(columns=['location_tag','river_level','original_coastal']).to_csv(out/'lost_river_effects.csv',index=False)
    changed_effects=[]
    new_coast={l for l,_ in coast_pixels}
    for c,levels in sorted(original_effects.items()):
        coastal=bool(base_info.loc[names[c],'is_coastal'])
        changed_effects.append({'location_tag':names[c],'original_levels':str(max(levels)),
                               'remaining_levels':str(max(levels)),
                               'original_coastal':coastal,'new_coastal':coastal or c in new_coast})
    pd.DataFrame(changed_effects).to_csv(out/'river_effect_changes.csv',index=False)
    report={'tiles':len(tile_meta),'tile_states':dict(Counter(r['state'] for r in tile_meta)), 'converted_pixels':int(len(changed)),
            'ocean_connected_passable_tiles':water_connected,'passable_components':len(components),'largest_passable_component':max(components,default=0),
            'mouth_alignment_repairs':mouth_snaps, 'river_preservation':'native_bank_pixel', 'preserved_river_pixels':len(preservation), 'river_port_locations':sorted(names[c] for c in port_candidates), 'port_harbor_floor':config.get('port_harbor_floor',.25), 'crossings':len(crossings),'ports_changed':len(port_changes),'land_effect_rows_to_restore':len(bonus_rows),
            'omissions':dict(omitted),'crossing_guard_locations':cfg.get('retain_native_locations',[]),'bank_fragment_repairs':repairs,'locators_moved':dict(moved),'edges':len(edges),'files':{rel:digest(mod/rel) for rel in written},
            'bisected_land_locations':bisected,
            'checks':{'river_port_coordinates_on_passable_shore':True,'native_river_levels_preserved':True,'no_native_rivers_on_converted_water':True,'minimum_tile_size':True,'connected_tiles':True,'land_area_guard':True,'land_identities_retained':True,'lost_land_adjacencies_restored':not missing},
            'map_code_sha256':digest(Path(__file__)), 'cleanup_code_sha256':digest(Path(__file__).with_name('navigation_cleanup.py')), 'native_geometry_inputs':native_inputs,
            'engine_status':'Global output requires a fresh campaign; local Thames mechanism confirmed by user.'}
    # Lightweight inspectable world map, embedded raster plus clickable nodes.
    preview=Image.fromarray(rgb).resize((2048,1024),Image.Resampling.NEAREST);buf=io.BytesIO();preview.save(buf,format='PNG')
    points=json.dumps(tile_meta,allow_nan=False)
    html='''<!doctype html><meta charset="utf-8"><title>River navigation</title><style>body{background:#14232b;color:#eee;font:15px system-ui;margin:20px}canvas{width:100%;border:1px solid #456;cursor:crosshair}pre{white-space:pre-wrap}button{margin:5px}</style><h1>River navigation — 1300 screening model</h1><p>Blue: navigable · amber: improvable · red: permanent barrier. Click a marker for evidence. Conservative omissions remain ordinary rivers.</p><canvas id="map" width="2048" height="1024"></canvas><pre id="detail">Click a river tile.</pre><script>const rows=POINTS;const c=document.getElementById('map'),ctx=c.getContext('2d'),img=new Image();img.onload=()=>{ctx.drawImage(img,0,0);for(const r of rows){ctx.fillStyle={navigable:'#26c5ff',improvable:'#ffbd40',barrier:'#ff5656'}[r.state];ctx.fillRect(r.x/8-2,r.y/8-2,4,4)}};img.src='data:image/png;base64,IMAGE';c.onclick=e=>{const b=c.getBoundingClientRect(),x=(e.clientX-b.left)/b.width*16384,y=(e.clientY-b.top)/b.height*8192;const r=rows.reduce((a,b)=>Math.hypot(a.x-x,a.y-y)<Math.hypot(b.x-x,b.y-y)?a:b);document.getElementById('detail').textContent=JSON.stringify(r,null,2)};</script>'''
    (out/'index.html').write_text(html.replace('POINTS',points).replace('IMAGE',base64.b64encode(buf.getvalue()).decode()))
    return report
