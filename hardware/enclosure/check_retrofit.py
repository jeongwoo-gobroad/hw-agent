"""Check ten through-bolt conversions against the existing v1.1 CAD."""
import json
from pathlib import Path
import cadquery as cq
from tqdm import tqdm
import build_model as m

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'retrofit'
OUT.mkdir(exist_ok=True)
parts = m.make_parts()
cover = next(p for p in parts if p.name == '02_rear_cover')
groups = [('A_stand', [(x,y) for x,y in m.STAND_HOLES if y == -10], 20, 65, -1),
          ('B_gate', m.GATE_SCREWS, 16, 61, -1),
          ('C_fan', m.FAN_SCREWS, 16, 46, 1)]
for _, points, _, _, _ in groups:
    for x, y in points:
        cover.shape = cover.shape.cut(m.cyl(3.4, 12, x, y, 47))
refs = m.references()
targets = {p.name:p.shape for p in parts}
targets.update(refs)
targets['fan_maximum'] = m.box(30.5,30.5,8,m.FAN_X,m.FAN_Y,38)
targets['heatsink'] = m.box(17,12,4,m.FAN_X,m.FAN_Y,m.PI_Z+3.654)
rows=[]
assembled=[]
for group, points, length, seat, direction in tqdm(groups,desc='Checking through bolts',unit='group'):
    for i,(x,y) in enumerate(points,1):
        # A round envelope bounds the hex nut in every rotational position.
        shaft = m.cyl(3,length,x,y,seat-length if direction<0 else seat)
        head = m.cyl(6.3,3,x,y,seat if direction<0 else seat-3)
        wz = 48.5 if direction<0 else 57
        nz = (46.6 if group=='B_gate' else 46.1) if direction<0 else 57.5
        washer = m.cyl(7,0.5,x,y,wz).cut(m.cyl(3.2,0.7,x,y,wz-0.1))
        nut = m.cyl(6.351,2.4,x,y,nz).cut(m.cyl(3.05,2.6,x,y,nz-0.1))
        # Gate holes are only 6.5 mm apart; 7 mm washers would overlap.
        pieces=[shaft,head,nut] if group=='B_gate' else [shaft,head,washer,nut]
        fastener=cq.Compound.makeCompound(pieces)
        assembled.append((f'{group}_{i}',fastener))
        clashes={}
        for name,shape in targets.items():
            vol=sum(s.Volume() for s in fastener.intersect(shape).Solids())
            if vol>0.01: clashes[name]=round(vol,5)
        rows.append(dict(group=group,index=i,x=x,y=y,length_mm=length,
                         nut_side='inside' if direction<0 else 'outside',
                         screw_tip_z=seat+direction*length,washer=group!='B_gate',clashes=clashes))
pair_clashes=[]
for i,(an,a) in enumerate(assembled):
    for bn,b in assembled[i+1:]:
        volume=sum(s.Volume() for s in a.intersect(b).Solids())
        if volume>0.01: pair_clashes.append(dict(a=an,b=bn,volume=volume))
report=dict(source='v1.1 parameters and official reference CAD',
            head_envelope=dict(diameter=6.3,height=3),nut=dict(across_flats=5.5,height=2.4),
            washer=dict(inner=3.2,outer=7,thickness=0.5),fasteners=rows,
            fastener_pair_clashes=pair_clashes,physical_tested=False,flexible_cables_checked=False)
(OUT/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
cq.exporters.export(cover.shape,str(OUT/'rear_cover_after_drilling.step'))
print(json.dumps(report,indent=2))
assert not any(row['clashes'] for row in rows), 'Retrofit hardware interference'
assert not pair_clashes, 'Fastener-to-fastener interference'
