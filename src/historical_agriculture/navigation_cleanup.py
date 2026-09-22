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


def repair_native_topology(pixels, owners, land):
    """Repair the valid native forest after cutting converted channel vertices."""
    from scipy import ndimage
    def degree(mask):
        d=np.zeros(mask.shape,np.uint8)
        d[1:]+=mask[:-1];d[:-1]+=mask[1:];d[:,1:]+=mask[:,:-1];d[:,:-1]+=mask[:,1:]
        return d
    h,w=pixels.shape
    def ns(y,x):
        return [(yy,xx) for yy,xx in [(y-1,x),(y+1,x),(y,x-1),(y,x+1)] if 0<=yy<h and 0<=xx<w]
    # Truncated tributary connectors become ordinary width pixels. Repeat
    # because removal of one connector changes neighbouring segment degrees.
    for _ in range(8):
        river=pixels<16;d=degree(river);sd=degree(river & (pixels!=1));bad=[]
        for y,x in np.argwhere(pixels==1):
            values=[int(sd[yy,xx]) for yy,xx in ns(y,x) if river[yy,xx]]
            if d[y,x]!=2 or sorted(values)!=[1,2]:bad.append((y,x))
        clumps=(river & (pixels!=1)) & (sd>2)
        if not bad and not clumps.any():break
        for y,x in bad:pixels[y,x]=15
        # A cut can collapse several former tributaries onto an endpoint.
        # Separate that junction instead of emitting an invalid affluent.
        pixels[clumps]=255
    # Isolated old green sources carry no size and no longer describe a river.
    pixels[(pixels==0)&(degree(pixels<16)==0)]=255
    river=pixels<16;labels,count=ndimage.label(river);d=degree(river)
    segments=river&(pixels!=1);sl,nseg=ndimage.label(segments);sd=degree(segments)
    children=set()
    for y,x in np.argwhere(pixels==1):
        for yy,xx in ns(y,x):
            if segments[yy,xx] and sd[yy,xx]==1:children.add(int(sl[yy,xx]))
    roots=set(range(1,nseg+1))-children
    sourced=set(map(int,labels[pixels==0]));ends={}
    for y,x in np.argwhere(river&(d==1)):
        if int(sl[y,x]) in roots:ends.setdefault(int(labels[y,x]),(int(y),int(x)))
    for ident in range(1,count+1):
        if ident in sourced:continue
        if ident in ends:
            y,x=ends[ident];pixels[y,x]=0
    # Single remaining width pixels get a source neighbour, preserving their
    # size. If no safe neighbour exists, drop it; bank restoration follows.
    for y,x in np.argwhere(river&(d==0)):
        c=int(owners[y,x]);options=[(yy,xx) for yy,xx in ns(y,x) if int(owners[yy,xx])==c and c in land and pixels[yy,xx]>=16 and sum(pixels[a,b]<16 for a,b in ns(yy,xx))==1]
        if options:pixels[options[0]]=0
        else:pixels[y,x]=255
    return pixels


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
    cleaned=repair_native_topology(cleaned,after,land)
    remaining=defaultdict(int)
    for y,x in zip(*np.where(cleaned<16)):
        c=int(after[y,x])
        if c in land:remaining[c]=max(remaining[c],int(LEVELS[cleaned[y,x]]))
    rows=[]
    by_color={int(r.map_color_rgb,16):r for r in inventory.itertuples()}
    for c,level in sorted(before_levels.items()):
        if not level or remaining[c]==level:continue
        r=by_color[c];x0,x1=int(r.bbox_min_x),int(r.bbox_max_x)+1;y0,y1=int(r.bbox_min_y),int(r.bbox_max_y)+1
        yy,xx=np.where(after[y0:y1,x0:x1]==c)
        oy,ox=np.where((original[y0:y1,x0:x1]==c)&(LEVELS[river[y0:y1,x0:x1]]==level))
        if not len(xx) or not len(ox):raise ValueError('No river-bank preservation candidate')
        distances,_=cKDTree(np.column_stack((ox,oy))).query(np.column_stack((xx,yy)))
        # Prefer an existing ordinary width pixel: changing its size leaves the
        # validated native tree intact. Otherwise create a two-pixel source/run.
        ordinary=[k for k in range(len(xx)) if 3<=cleaned[yy[k]+y0,xx[k]+x0]<16]
        added_source=False
        if ordinary:k=min(ordinary,key=lambda k:distances[k])
        else:
            k=None
            h,w=cleaned.shape
            def ns(y,x):return [(a,b) for a,b in [(y-1,x),(y+1,x),(y,x-1),(y,x+1)] if 0<=a<h and 0<=b<w]
            for candidate in np.argsort(distances):
                py,px=int(yy[candidate]+y0),int(xx[candidate]+x0)
                if cleaned[py,px]<16 or any(cleaned[a,b]<16 for a,b in ns(py,px)):continue
                sources=[(a,b) for a,b in ns(py,px) if int(after[a,b])==c and cleaned[a,b]>=16 and not any(cleaned[u,v]<16 for u,v in ns(a,b))]
                if not sources:continue
                k=int(candidate);cleaned[sources[0]]=0;added_source=True;break
            if k is None:raise ValueError('No isolated native bank segment fits '+r.location_tag)
        x=int(xx[k]+x0);y=int(yy[k]+y0)
        cleaned[y,x]=PALETTE[level];remaining[c]=level
        rows.append({'location_tag':r.location_tag,'river_level':level,'x':x,'y':y,'distance_pixels':float(distances[k]),'added_source':added_source})
    assert all(remaining[c]==level for c,level in before_levels.items())
    assert not np.any(cleaned[water]<16)
    from .river_map import validate_native_rivers
    validate_native_rivers(cleaned)
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
