"""Raster-only river compatibility: keep native size checks and bonuses."""
from collections import defaultdict, deque
import numpy as np
from scipy.spatial import cKDTree

# Junction markers are treated as the largest river by the engine export model.
LEVELS = np.array([0,5,5,1,1,1,2,2,2,3,3,3,4,4,4,5]+[0]*240, dtype=np.uint8)
PALETTE = {1:3, 2:6, 3:9, 4:12, 5:15}


def close_short_gaps(rows, width, maximum):
    """Fill only short unselected runs of the existing eight-connected river.

    Both ends must already qualify in the same hydrological basin. Historical
    exclusions are never filled and this cannot draw a canal across dry land.
    """
    data={int(r.y)*width+int(r.x):r for r in rows.itertuples()}
    selected={p for p,r in data.items() if r.state>0}
    additions={}
    for seed in sorted(selected):
        r=data[seed]
        todo=deque([(seed,[])])
        seen={seed}
        while todo:
            p,path=todo.popleft()
            for dy in (-1,0,1):
                for dx in (-1,0,1):
                    q=p+dy*width+dx
                    if not (dx or dy) or abs(q%width-p%width)>1 or q in seen or q not in data:continue
                    seen.add(q);other=data[q]
                    if other.main_basin_id!=r.main_basin_id:continue
                    if q in selected:
                        if path:
                            for cell in path:additions[cell]=max(additions.get(cell,0),r.state,other.state)
                        continue
                    if other.evidence!='physical_screen' or len(path)>=maximum:continue
                    todo.append((q,path+[q]))
    indices={int(r.y)*width+int(r.x):i for i,r in zip(rows.index,rows.itertuples())}
    for p,state in additions.items():
        rows.at[indices[p],'state']=state
        rows.at[indices[p],'evidence']='bounded_native_gap'
    return len(additions)


def preserve_levels(river, original, after, land, inventory, geometry_boxes=()):
    """Erase converted channels and retain one ordinary size pixel on each bank.

    These pixels preserve engine has_river/size semantics; no scripted duplicate
    supply, development, fishing or building-cap modifiers are required.
    """
    cleaned=river.copy();before_levels=defaultdict(int)
    ys,xs=np.where(river<16)
    for y,x in zip(ys,xs):
        c=int(original[y,x])
        if c in land:before_levels[c]=max(before_levels[c],int(LEVELS[river[y,x]]))
    # Replaced local alignments must not leave their old parallel channel.
    for x0,y0,x1,y1 in geometry_boxes:cleaned[y0:y1,x0:x1]=255
    converted=original!=after
    water=converted & ~np.isin(after,list(land))
    cleaned[water]=254
    # Small bank transfers must not promote the recipient's river size.
    ys,xs=np.where(cleaned<16)
    remaining=defaultdict(int)
    for y,x in zip(ys,xs):
        c=int(after[y,x])
        if c not in land:continue
        target=before_levels[c];level=int(LEVELS[cleaned[y,x]])
        if level>target:cleaned[y,x]=PALETTE[target] if target else 255
        remaining[c]=max(remaining[c],min(level,target))
    rows=[]
    by_color={int(r.map_color_rgb,16):r for r in inventory.itertuples()}
    for c,level in sorted(before_levels.items()):
        if not level or remaining[c]==level:continue
        r=by_color[c];x0,x1=int(r.bbox_min_x),int(r.bbox_max_x)+1;y0,y1=int(r.bbox_min_y),int(r.bbox_max_y)+1
        yy,xx=np.where(after[y0:y1,x0:x1]==c)
        oy,ox=np.where((original[y0:y1,x0:x1]==c)&(LEVELS[river[y0:y1,x0:x1]]==level))
        if not len(xx) or not len(ox):raise ValueError('No river-bank preservation candidate')
        # Closest remaining bank pixel to the old channel; never an arbitrary dot inland.
        distances,_=cKDTree(np.column_stack((ox,oy))).query(np.column_stack((xx,yy)))
        k=int(np.argmin(distances));x=int(xx[k]+x0);y=int(yy[k]+y0)
        cleaned[y,x]=PALETTE[level];remaining[c]=level
        rows.append({'location_tag':r.location_tag,'river_level':level,'x':x,'y':y,'distance_pixels':float(distances[k])})
    assert all(remaining[c]==level for c,level in before_levels.items())
    assert not np.any(cleaned[water]<16)
    return cleaned,rows,before_levels


def snap_mouths(pixel_rows, original, land, seas, maximum):
    """Close bounded registration gaps between a river outlet and game coastline.

    One mouth per existing connected component, no lakes, wasteland, or large
    overland links. Only lowland source reaches near their hydrological outlet
    qualify. These approximations are retained in the evidence column.
    """
    from scipy import ndimage
    h,w=original.shape;flat=original.ravel()
    wet=np.isin(original,list(seas))
    boundary=wet & ndimage.binary_dilation(~wet)
    yy,xx=np.where(boundary);coast=np.column_stack((xx,yy))
    if not len(coast):return pixel_rows,[]
    tree=cKDTree(coast)
    selected=set(map(int,pixel_rows.index[(pixel_rows.state>0)&pixel_rows.land_location.ne('')]))
    selected={p for p in selected if int(flat[p]) in land}
    pending=set(selected);additions={};audit=[]
    while pending:
        seed=min(pending);pending.remove(seed);todo=deque([seed]);group=[]
        while todo:
            p=todo.popleft();group.append(p)
            for dy in (-1,0,1):
                for dx in (-1,0,1):
                    q=p+dy*w+dx
                    if abs(q%w-p%w)<=1 and q in pending:pending.remove(q);todo.append(q)
        pts=np.array(group);xy=np.column_stack((pts%w,pts//w));distance,ix=tree.query(xy)
        if distance.min()<=1:continue
        order=np.argsort(distance)
        for k in order:
            if distance[k]>maximum:break
            source=pixel_rows.loc[group[k]]
            if source.state==3 or source.distance_downstream_km>150:continue
            start=group[k];tx,ty=coast[ix[k]];target=int(ty)*w+int(tx)
            queue=deque([start]);previous={start:None};found=False
            while queue:
                p=queue.popleft()
                if p==target:found=True;break
                for q in (p-w,p+w,p-1,p+1):
                    if not 0<=q<flat.size or abs(q%w-p%w)>1 or q in previous:continue
                    if abs(q%w-start%w)+abs(q//w-start//w)>maximum*1.5:continue
                    if q!=target and int(flat[q]) not in land:continue
                    if q in selected and q!=start:continue
                    previous[q]=p;queue.append(q)
            if not found:continue
            path=[];p=previous[target]
            while p!=start:path.append(p);p=previous[p]
            for p in path:
                row=source.copy();row['x']=p%w;row['y']=p//w;row['evidence']='mouth_alignment_snap';additions[p]=row
            audit.append({'from_x':start%w,'from_y':start//w,'to_x':int(tx),'to_y':int(ty),'pixels':len(path)})
            break
    if additions:
        import pandas as pd
        pixel_rows=pixel_rows.drop(index=[p for p in additions if p in pixel_rows.index])
        pixel_rows=pd.concat([pixel_rows,pd.DataFrame.from_dict(additions,orient='index')])
    return pixel_rows,audit
