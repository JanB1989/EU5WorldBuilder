"""Exact spherical overlap of game pixels with native geographic grid cells.

The registered game map is separable in x/y; pixel edges are transformed,
not centroids. Projection uncertainty is recorded separately from overlap error.
"""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import sparse
from .provenance import digest, write_json

RADIUS_KM=6371.0088

def axis_segments(edges, origin, step, count, wrap=False):
    result=[]
    for a,b in zip(edges[:-1],edges[1:]):
        lo,hi=sorted([float(a),float(b)])
        if not wrap:lo=max(lo,origin);hi=min(hi,origin+step*count)
        first=int(np.floor((lo-origin)/step));last=int(np.ceil((hi-origin)/step))
        result.append([(j%count,max(lo,origin+j*step),min(hi,origin+(j+1)*step)) for j in range(first,last) if min(hi,origin+(j+1)*step)>max(lo,origin+j*step)])
    return result

def overlap_matrix(root, inventory, output):
    src=root/'data/raw/location_inputs';png=src/'locations.png';tf=src/'transform.json'
    key={'map':digest(png),'transform':digest(tf),'inventory':digest(src/'inventory.parquet'),'code':digest(Path(__file__))}
    cached=output/'overlap.npz';stamp=output/'overlap_manifest.json'
    if cached.exists() and stamp.exists() and json.loads(stamp.read_text()).get('inputs')==key:
        return sparse.load_npz(cached),json.loads(stamp.read_text())
    cfg=json.loads(tf.read_text());Image.MAX_IMAGE_PIXELS=None
    a=np.asarray(Image.open(png).convert('RGB'));height,width=a.shape[:2]
    lut=np.zeros(2**24,dtype=np.int32)
    colours=[int(str(x),16) for x in inventory.map_color_rgb]
    if len(set(colours))!=len(colours):raise ValueError('Duplicated location colours')
    lut[colours]=np.arange(1,len(inventory)+1)
    x=(np.arange(width+1)-.5-cfg['x_mean'])/cfg['x_scale']
    y=(np.arange(height+1)-.5-cfg['y_mean'])/cfg['y_scale']
    lon=np.polynomial.polynomial.polyval(x,cfg['lon_coefficients'])
    lat=np.polynomial.polynomial.polyval(y,cfg['lat_coefficients'])
    if not (np.all(np.diff(lon)>0) and np.all(np.diff(lat)<0)):raise ValueError('Non-monotonic map registration')
    xs=axis_segments(lon,-180,1/12,4320,True)
    ys=axis_segments(lat,-90,1/12,2160)
    px=np.array([i for i,parts in enumerate(xs) for _ in parts],dtype=np.int32)
    gx=np.array([s[0] for parts in xs for s in parts],dtype=np.int32)
    dx=np.deg2rad(np.array([s[2]-s[1] for parts in xs for s in parts]))
    matrix=sparse.csr_matrix((len(inventory),2160*4320),dtype=np.float64)
    counts=np.zeros(len(inventory),dtype=np.int64);physical=np.zeros(len(inventory))
    for start in range(0,height,128):
        rr=[];cc=[];ww=[]
        for row in range(start,min(start+128,height)):
            rgb=a[row].astype(np.int32);ids=lut[(rgb[:,0]<<16)|(rgb[:,1]<<8)|rgb[:,2]]-1
            valid=ids>=0;counts+=np.bincount(ids[valid],minlength=len(inventory))
            row_area=RADIUS_KM**2*np.deg2rad(np.diff(lon))*abs(np.sin(np.deg2rad(lat[row]))-np.sin(np.deg2rad(lat[row+1])))
            physical+=np.bincount(ids[valid],weights=row_area[valid],minlength=len(inventory))
            loc=ids[px];valid=loc>=0
            for gy,low,high in ys[row]:
                weights=RADIUS_KM**2*dx*(np.sin(np.deg2rad(high))-np.sin(np.deg2rad(low)))
                rr.append(loc[valid]);cc.append((2159-gy)*4320+gx[valid]);ww.append(weights[valid])
        if rr:
            block=sparse.coo_matrix((np.concatenate(ww),(np.concatenate(rr),np.concatenate(cc))),shape=matrix.shape).tocsr()
            matrix+=block
        if start%1024==0:print(f'Geometry overlap {start}/{height} rows',flush=True)
    actual=np.asarray(matrix.sum(axis=1)).ravel()
    if np.any(counts==0):raise ValueError('Locations missing from game map')
    if not np.array_equal(counts,inventory.pixel_count.to_numpy(dtype=int)):raise ValueError('Inventory/map pixel count mismatch')
    error=np.max(np.abs(actual-physical)/np.maximum(physical,1e-10))
    if error>1e-9:raise ValueError('Overlap area is not conserved')
    result={'inputs':key,'location_count':len(inventory),'represented_game_pixels':int(counts.sum()),'location_cell_intersections':int(matrix.nnz),'max_relative_area_error':float(error),'geometry_note':'Exact overlap under imported separable game-map registration; geographic alignment remains approximate. Game land masks may cross real coastlines.'}
    sparse.save_npz(cached,matrix);write_json(stamp,result)
    return matrix,result
