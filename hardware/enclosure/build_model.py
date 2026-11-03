"""Parametric enclosure; millimetres. See README_KO.md for assembly and limits."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path

import cadquery as cq
import numpy as np
import trimesh
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent
P = json.loads((ROOT / 'parameters.json').read_text(encoding='utf-8'))
W, H, D = P['body_width'], P['body_height'], P['body_depth']
T, FRONT, R = P['wall'], P['front_thickness'], P['corner_radius']
SY, SZ = P['display_y'], P['display_face_z']
LID = P['lid_thickness']
ROT = 180 - P['desk_angle_deg']
LIFT = P['front_bottom_height'] + H / 2 * math.sin(math.radians(ROT))
INSERT, M3 = P['m3_insert_bore'], P['m3_clearance']
BACK_SCREWS = [(x,y) for x in (-98.0,98.0) for y in (-70.0,0.0,70.0)]
CLIP_ROWS = (SY-35.355, SY+35.355)
TRAY_Z = SZ+14.96
PI_X = -23.71+P['pi_offset_x']
PI_Y = SY-28.0+P['pi_offset_y']
PI_Z = TRAY_Z+P['pi_tray_thickness']+P['pi_standoff_height']-0.03
FAN_X, FAN_Y = PI_X+33.15, PI_Y+22.75
FAN_Z = P['fan_plate_z']
FAN_SCREWS = [(FAN_X+x,FAN_Y+y) for x in (-20,20) for y in (-20,20)]
CAM_Y = P['camera_lens_y']
CAM_HOLES = [(x,CAM_Y+dy) for x in (-10.5,10.5) for dy in (-0.1,12.4)]
DISPLAY_MOUNT_Z = SZ+9.46
STAND_HOLES = [(x,y) for x in (-77.0,77.0) for y in (-58.0,-10.0)]
CABLE_ANCHORS = [(70,-24),(70,-52),(-70,-52),(0,-51)]
GATE_SCREWS = [(x,y) for x in (-39,39) for y in (-69,-75.5)]
GATE_CABLES = list(zip((-31.5,-22.5,-13.5,-4.5,4.5,13.5,22.5,31.5), (6.5,6.5,6.5,6.5,8.5,5.5,5.5,5.5)))


def box(w,h,d,x=0,y=0,z=0):
    return cq.Workplane('XY').box(w,h,d,centered=(True,True,False)).translate((x,y,z)).val()


def rounded(w,h,d,r,x=0,y=0,z=0):
    return (cq.Workplane('XY').box(w,h,d,centered=(True,True,False))
            .edges('|Z').fillet(r).translate((x,y,z)).val())


def cyl(d,h,x=0,y=0,z=0):
    return cq.Solid.makeCylinder(d/2,h,cq.Vector(x,y,z))


def slot(length,d,depth,x=0,y=0,z=0,angle=0):
    return cq.Workplane('XY').slot2D(length,d,angle).extrude(depth).translate((x,y,z)).val()


def fuse(shapes):
    return shapes[0].fuse(*shapes[1:]).clean() if len(shapes)>1 else shapes[0]


def cut(shape,cutters):
    return shape.cut(*cutters).clean() if cutters else shape


def desk(shape):
    return shape.rotate((0,0,0),(1,0,0),ROT).translate((0,0,LIFT))


def desk_inverse(shape):
    return shape.translate((0,0,-LIFT)).rotate((0,0,0),(1,0,0),-ROT)


def on_bed(shape):
    b=shape.BoundingBox()
    return shape.translate((-b.xmin,-b.ymin,-b.zmin))


@dataclass
class Part:
    name: str
    shape: cq.Shape
    color: str
    quantity: int = 1
    print_shape: cq.Shape | None = None
    group: str = 'printed'
    explode: tuple = (0,0,0)


def front_shell():
    shell=rounded(W,H,D,R)
    c=P['display_edge_clearance']
    holes=[rounded(W-2*T,H-2*T,D+5,R-T,z=8),
           rounded(189.32+2*c,120.24+2*c,10,8+c,y=SY,z=FRONT),
           rounded(186.32,117.24,FRONT+2,6.5,y=SY,z=-1),
           rounded(27,26.5,10,1,y=CAM_Y+2.469,z=FRONT),
           cyl(P['camera_aperture_diameter'],FRONT+2,0,CAM_Y,-1)]
    shell=cut(shell,holes)
    bosses=[]
    for x,y in BACK_SCREWS:
        bosses.append(cyl(8,D-8,x,y,8))
    for y in CLIP_ROWS:
        for x in (-98.8,98.8):
            bosses.append(cyl(6.4,DISPLAY_MOUNT_Z-FRONT,x,y,FRONT))
    for x,y in CAM_HOLES:
        bosses.append(cyl(4.2,P['camera_pcb_front_z']-FRONT,x,y,FRONT))
    shell=fuse([shell]+bosses)
    cutters=[cyl(INSERT,6.2,x,y,D-6) for x,y in BACK_SCREWS]
    cutters += [cyl(INSERT,5.2,x,y,DISPLAY_MOUNT_Z-5) for y in CLIP_ROWS for x in (-98.8,98.8)]
    cutters += [cyl(P['m2_camera_pilot'],5.5,x,y,P['camera_pcb_front_z']-5.3) for x,y in CAM_HOLES]
    cutters += [rounded(35.8,9.6,2.8,2,x,y,DISPLAY_MOUNT_Z) for y in CLIP_ROWS for x in (-84.4,84.4)]
    for x in range(-78,79,8):
        cutters.append(box(4,8,22,x,H/2,22))
    for x in list(range(-78,-36,8))+list(range(44,79,8)):
        cutters.append(box(4,8,22,x,-H/2,22))
    return cut(shell,cutters)


def lid():
    plate=rounded(W,H,LID,R,z=D)
    # Four shallow tabs align the cover without a long, tight-fitting rim.
    tabs=[box(28,2,2,x,y,D-2) for x in (-52,52) for y in (-H/2+T+1.4,H/2-T-1.4)]
    pillars=[cyl(8,D-(FAN_Z+3),x,y,FAN_Z+3) for x,y in FAN_SCREWS]
    mounts=[cyl(10,8,x,y,D+LID-8) for x,y in STAND_HOLES]
    mounts += [cyl(9,8,x,y,D+LID-8) for x,y in GATE_SCREWS]
    anchors=[rounded(24,10,11.5,2,x,y,D-11.5) for x,y in CABLE_ANCHORS]
    plate=fuse([plate]+tabs+pillars+mounts+anchors)
    cutters=[cyl(M3,LID+2,x,y,D-1) for x,y in BACK_SCREWS]
    cutters += [cyl(INSERT,5.2,x,y,FAN_Z+3-0.1) for x,y in FAN_SCREWS]
    cutters += [cyl(INSERT,6.2,x,y,D+LID-6) for x,y in STAND_HOLES]
    cutters += [cyl(INSERT,6.2,x,y,D+LID-6) for x,y in GATE_SCREWS]
    cutters += [box(26,3.2,3.2,x,y,D-8) for x,y in CABLE_ANCHORS]
    cutters += [rounded(72,16,LID+2,2,0,-73,D-1)]
    for y in np.arange(FAN_Y-18,FAN_Y+19,6):
        cutters.append(slot(38,4,LID+2,FAN_X,float(y),D-1))
    for x in (-56,0,56):
        for y in (43,50,57,64):
            cutters.append(slot(40,4,LID+2,x,y,D-1))
    return cut(plate,cutters)


def pi_tray():
    z=TRAY_Z
    shape=rounded(106,67,3,3,-6.71,-8,z)
    shape=shape.cut(rounded(94,55,5,2,-6.71,-8,z-1))
    rails=[box(106,8,3,-6.71,y,z) for y in (-28.5,12.5)]
    holes=[(PI_X+x,PI_Y+y) for x in (3.5,61.5) for y in (3.5,52.5)]
    supports=[cyl(7,9,x,y,z) for x,y in holes]
    shape=fuse([shape]+rails+supports)
    cutters=[cyl(2.1,5.5,x,y,z+3.7) for x,y in holes]
    cutters += [cyl(2.9,5,x,y,z-1) for x in (-20.21,37.79) for y in (SY-24.5,SY+24.5)]
    return cut(shape,cutters)


def cable_gate(upper):
    yc=-69 if upper else -77
    shape=rounded(84,8,4,1.2,0,yc,D+LID)
    cutters=[cyl(d,6,x,-73,D+LID-1) for x,d in GATE_CABLES]
    cutters += [cyl(M3,6,x,(-69 if upper else -75.5),D+LID-1) for x in (-39,39)]
    return cut(shape,cutters)


def display_clip(sign,y):
    xmid=sign*(70+98.8)/2
    shape=rounded(35.2,9,2.4,2,xmid,y,DISPLAY_MOUNT_Z)
    cutters=[slot(4,2.8,4,sign*70,y,DISPLAY_MOUNT_Z-1),
             cyl(M3,4,sign*98.8,y,DISPLAY_MOUNT_Z-1)]
    return cut(shape,cutters)


def fan_plate():
    shape=rounded(48,48,3,4,FAN_X,FAN_Y,FAN_Z)
    cutters=[cyl(27.0,5,FAN_X,FAN_Y,FAN_Z-1)]
    cutters += [cyl(M3,5,x,y,FAN_Z-1) for x,y in FAN_SCREWS]
    pitch=P['fan_hole_pitch']/2
    for sx in (-1,1):
        for sy in (-1,1):
            cutters.append(slot(4.8,2.8,5,FAN_X+sx*pitch,FAN_Y+sy*pitch,FAN_Z-1,45 if sx==sy else -45))
    # Optional ties go around the frame only, never across the moving blades.
    for sx in (-1,1):
        for sy in (-1,1):
            cutters.append(box(3,6,5,FAN_X+sx*17.5,FAN_Y+sy*10,FAN_Z-1))
    return cut(shape,cutters)


def stand():
    angle=math.radians(ROT)
    def rear_point(y):
        return (y*math.cos(angle)-(D+LID)*math.sin(angle),
                y*math.sin(angle)+(D+LID)*math.cos(angle)+LIFT)
    low,high=rear_point(-68),rear_point(4)
    pts=[(-115,0),(55,0),(55,6),(-12,6),low,high,(-65,94),(-115,6)]
    world=cq.Workplane('YZ').polyline(pts).close().extrude(18).translate((-9,0,0)).val()
    # A triangular opening saves material but leaves a broad, continuous foot.
    opening=cq.Workplane('YZ').polyline([(-96,13),(-31,13),(-64,75)]).close().extrude(22).translate((-11,0,0)).val()
    world=world.cut(opening)
    local=desk_inverse(world)
    local=local.cut(rounded(W+0.4,H+0.4,D+LID,R,z=0)).clean()
    holes=[]
    for y in (-58,-10):
        holes += [cyl(M3,85,0,y,D+LID-1), cyl(6.5,75,0,y,D+LID+8)]
    return cut(local,holes)


def fit_coupon():
    # Exact lower-left seating corner, trimmed from the real front part.
    corner=rounded(W,H,8,R)
    c=P['display_edge_clearance']
    corner=cut(corner,[rounded(189.32+2*c,120.24+2*c,10,8+c,y=SY,z=FRONT),
                       rounded(186.32,117.24,FRONT+2,6.5,y=SY,z=-1)])
    corner=corner.intersect(box(44,36,10,-W/2+22,-H/2+18,-1)).clean()
    return corner


def hole_coupon():
    shape=rounded(54,23,8,2)
    for i,d in enumerate((4.0,4.1,4.2,4.3,4.4)):
        shape=shape.cut(cyl(d,6,-20+i*10,3,2))
    for i,d in enumerate((1.7,2.8,3.4)):
        shape=shape.cut(cyl(d,10,-15+i*15,-6,-1))
    return shape.clean()


def references():
    for stem in ('pi5_step','camera3_step'):
        cached=ROOT/'reference'/f'{stem}.brep'
        if not cached.exists():
            source=next((ROOT/'reference').glob(f'{stem}.st*p'),None)
            if source is None:
                raise FileNotFoundError('Run download_references.py before reference checks.')
            cq.importers.importStep(str(source)).val().exportBrep(str(cached))
    display=cq.importers.importStep(str(ROOT/'reference/display_7_step.step')).val()
    display=display.rotate((0,0,0),(1,0,0),180).rotate((0,0,0),(0,0,1),90)
    display=display.translate((-2.935,SY,SZ+5.02))
    pi=cq.Shape.importBrep(str(ROOT/'reference/pi5_step.brep')).translate((PI_X,PI_Y,PI_Z))
    camera=cq.Shape.importBrep(str(ROOT/'reference/camera3_step.brep'))
    camera=camera.rotate((0,0,0),(0,0,1),-90).translate((-12.5,CAM_Y+14.4,P['camera_pcb_front_z']+0.701))
    return {'display':display,'pi5':pi,'camera3':camera}


def simple_references():
    glass=rounded(189.32,120.24,0.7,8,0,SY,SZ)
    active=box(154.56,86.94,0.08,0,SY,SZ-0.08)
    back=box(166.55,99.71,5,0,SY,SZ+0.7)
    pcb=box(85,56,1.31,PI_X+42.5,PI_Y+28,PI_Z)
    ports=fuse([box(21.24,15.57,14.62,PI_X+77.25,PI_Y+10.25,PI_Z),
                box(17.53,14.5,17.526,PI_X+79.235,PI_Y+29,PI_Z),
                box(17.45,14.5,17.361,PI_X+79.055,PI_Y+47,PI_Z)])
    camera_board=box(25,23.862,1.12,0,CAM_Y+2.469,P['camera_pcb_front_z'])
    camera_lens=cyl(7,6.98,0,CAM_Y,P['camera_pcb_front_z']-6.98)
    camera_lens=fuse([camera_lens,box(10.8,10.8,3,0,CAM_Y,P['camera_pcb_front_z']-5.5)])
    thickness=P['fan_thickness']
    fan=box(P['fan_body_size'],P['fan_body_size'],thickness,FAN_X,FAN_Y,FAN_Z-thickness)
    fan=fan.cut(cyl(27,thickness+2,FAN_X,FAN_Y,FAN_Z-thickness-1))
    for x in (-P['fan_hole_pitch']/2,P['fan_hole_pitch']/2):
        for y in (-P['fan_hole_pitch']/2,P['fan_hole_pitch']/2):
            fan=fan.cut(cyl(P['fan_mount_hole_diameter'],thickness+2,FAN_X+x,FAN_Y+y,FAN_Z-thickness-1))
    fan=fuse([fan,cyl(9,thickness,FAN_X,FAN_Y,FAN_Z-thickness),box(28,2,1,FAN_X,FAN_Y,FAN_Z-3)])
    sink=box(17,12,4,FAN_X,FAN_Y,PI_Z+3.654)
    return [Part('Touch Display 2 glass',glass,'#242a30',group='hardware'),
            Part('Display active area',active,'#6e9b9b',group='hardware'),
            Part('Display rear envelope',back,'#b6bfc4',group='hardware'),
            Part('Pi 5 PCB',pcb,'#417e5b',group='hardware'),
            Part('USB and Ethernet envelopes',ports,'#b6bfc4',group='hardware'),
            Part('Camera 3 PCB',camera_board,'#417e5b',group='hardware'),
            Part('Camera lens envelope',camera_lens,'#242a30',group='hardware'),
            Part('Case fan CC3007 nominal envelope',fan,'#434b50',group='hardware'),
            Part('Original case heatsink',sink,'#929da3',group='hardware')]


def make_parts():
    shell=front_shell()
    cover=lid()
    bracket=fan_plate()
    leg=stand()
    parts=[Part('01_front_shell',shell,'#d9dbd8'),
           Part('02_rear_cover',cover,'#aab3b1',print_shape=cover.rotate((0,0,0),(1,0,0),180),explode=(0,0,40)),
           Part('03_fan_bracket',bracket,'#648b87',explode=(0,0,23))]
    for i,(sign,y) in enumerate([(s,y) for y in CLIP_ROWS for s in (-1,1)]):
        parts.append(Part(f'04_display_clip_{i+1}',display_clip(sign,y),'#648b87',explode=(0,0,12)))
    parts += [Part('05_stand_left',leg.translate((-77,0,0)),'#8b9995',
                   print_shape=desk(leg).rotate((0,0,0),(0,1,0),90),explode=(-22,0,28)),
              Part('06_stand_right',leg.translate((77,0,0)),'#8b9995',
                   print_shape=desk(leg).rotate((0,0,0),(0,1,0),90),explode=(22,0,28))]
    parts += [Part('09_pi_offset_tray',pi_tray(),'#648b87',explode=(0,0,8)),
              Part('10_cable_gate_upper',cable_gate(True),'#648b87',explode=(0,6,43)),
              Part('11_cable_gate_lower',cable_gate(False),'#648b87',explode=(0,-6,43))]
    return parts


def mesh_data(shape):
    vertices,triangles=shape.tessellate(0.35,0.3)
    return {'v':[[round(p.x,3),round(p.y,3),round(p.z,3)] for p in vertices], 'f':triangles}


def check_mesh(path):
    mesh=trimesh.load_mesh(path,process=True)
    return {'watertight':bool(mesh.is_watertight),'winding_consistent':bool(mesh.is_winding_consistent),
            'positive_volume':bool(mesh.volume>0),'components':len(mesh.split()),
            'bounds_mm':np.round(mesh.extents,3).tolist(),'volume_cm3':round(mesh.volume/1000,3),
            'triangles':len(mesh.faces)}


def export(parts,out):
    for name in ('stl','step','preview'):
        (out/name).mkdir(parents=True,exist_ok=True)
    manifest=[]
    for part in tqdm(parts,desc='Exporting printable parts',unit='part'):
        shape=on_bed(part.print_shape if part.print_shape is not None else part.shape)
        if not shape.isValid() or len(shape.Solids())!=1:
            raise ValueError(f'{part.name}: expected one valid solid, got {len(shape.Solids())}')
        cq.exporters.export(shape,str(out/'stl'/f'{part.name}.stl'),tolerance=P['stl_tolerance'],angularTolerance=P['stl_angular_tolerance'])
        cq.exporters.export(part.shape,str(out/'step'/f'{part.name}.step'))
        stats=check_mesh(out/'stl'/f'{part.name}.stl')
        stats.update(name=part.name,cad_valid=True,quantity=part.quantity)
        stats['fits_220_bed']=all(a<=b-8 for a,b in zip(stats['bounds_mm'][:2],P['printer_bed_xy']))
        if not all(stats[k] for k in ('watertight','winding_consistent','positive_volume','fits_220_bed')) or stats['components']!=1:
            raise ValueError(f'Mesh validation failed: {stats}')
        manifest.append(stats)
    assembly=cq.Assembly(name='Home_Control_Centre_v1_1')
    for part in parts:
        if part.group=='coupon':
            continue
        color=tuple(int(part.color[i:i+2],16)/255 for i in (1,3,5))
        assembly.add(desk(part.shape),name=part.name,color=cq.Color(*color))
    assembly.save(str(out/'home_control_center_assembly.step'))
    (out/'part_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    preview=[]
    for part in parts+simple_references():
        if part.group=='coupon':
            continue
        preview.append(dict(name=part.name,color=part.color,group=part.group,explode=part.explode,**mesh_data(part.shape)))
    (out/'preview/meshes.json').write_text(json.dumps({'parts':preview,'rotation':ROT,'lift':LIFT},separators=(',',':')),encoding='utf-8')
    return manifest


def verify(parts,out,check_references=True):
    checks=[]
    printable=[p for p in parts if p.group!='coupon']
    for i,a in enumerate(tqdm(printable,desc='Checking assembly',unit='part')):
        for b in printable[i+1:]:
            overlap=sum(s.Volume() for s in a.shape.intersect(b.shape).Solids())
            checks.append({'a':a.name,'b':b.name,'overlap_mm3':round(overlap,6)})
    issues=[r for r in checks if r['overlap_mm3']>0.01]
    refs=references() if check_references else {}
    hardware_checks=[]
    # Use the official camera geometry; simple block proxies hide component clashes.
    pairs=[('01_front_shell','camera3'),('01_front_shell','display')]
    pairs += [(p.name,'display') for p in printable if p.name.startswith('04_')]
    pairs += [('09_pi_offset_tray','display'),('09_pi_offset_tray','pi5'),('03_fan_bracket','pi5'),('02_rear_cover','pi5')]
    if not check_references:
        pairs=[]
    for name,hardware in tqdm(pairs,desc='Checking reference geometry',unit='pair'):
        shape=next(p.shape for p in parts if p.name==name)
        # A zero-thickness STEP face has no occupied volume, even if its mass API returns a value.
        volume=sum(s.Volume() for s in shape.intersect(refs[hardware]).Solids())
        hardware_checks.append({'part':name,'reference':hardware,'overlap_mm3':round(volume,6)})
    hardware_issues=[r for r in hardware_checks if r['overlap_mm3']>0.05]
    # Reserve the full tolerance box, including the area swept by the blades.
    fan_size=P['fan_body_size']+P['fan_body_size_tolerance']
    fan_depth=P['fan_thickness']+P['fan_thickness_tolerance']
    fan_bottom=FAN_Z-fan_depth
    fan_envelope=box(fan_size,fan_size,fan_depth,FAN_X,FAN_Y,fan_bottom)
    fan_targets={p.name:p.shape for p in printable}
    fan_targets.update(refs)
    fan_targets['case_heatsink_envelope']=box(17,12,4,FAN_X,FAN_Y,PI_Z+3.654)
    fan_checks=[]
    for name,shape in fan_targets.items():
        overlap=sum(s.Volume() for s in fan_envelope.intersect(shape).Solids())
        fan_checks.append({'target':name,'overlap_mm3':round(overlap,6)})
    fan_issues=[r for r in fan_checks if r['overlap_mm3']>0.05]
    bounds=cq.Compound.makeCompound([desk(p.shape) for p in printable]).BoundingBox()
    report={'revision':'1.1','printable_pair_checks':checks,'reference_checks':hardware_checks,
            'fan_envelope_checks':fan_checks,'fan_envelope_intersections':fan_issues,
            'fan_design_envelope_mm':[fan_size,fan_size,fan_depth],
            'fan_source':'reference/fan_sources.json',
            'reference_checks_performed':check_references,
            'intersections':issues,'reference_intersections':hardware_issues,
            'assembled_bounds_mm':[round(bounds.xlen,2),round(bounds.ylen,2),round(bounds.zlen,2)],
            'pi_connector_top_z':round(PI_Z+17.526,3),'fan_lower_z':fan_bottom,
            'fan_to_heatsink_min_gap_mm':round(fan_bottom-(PI_Z+3.654+4),3),
            'usb_ethernet_to_inner_wall_mm':round(W/2-T-(PI_X+88.05),2),
            'bottom_connectors_to_inner_wall_mm':round(PI_Y-1.63-(-H/2+T),2),
            'rear_cable_exit_mm':[72,16],
            'physical_fit_tested':False,'thermal_tested':False,'slicer_tested':False,
            'limitations':['Fan identification is supported by owner reports; geometry uses the current manufacturer CC3007 family drawing, not a Pi OEM revision-specific drawing.',
                          'STEP models are manufacturer reference data, not production tolerances.',
                          'Flexible cables, connector boots, threads and printer shrinkage require a real assembly test.']}
    (out/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    if issues or hardware_issues or fan_issues:
        raise ValueError(f'Assembly intersections: {issues}; hardware: {hardware_issues}; fan: {fan_issues}')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'output')
    parser.add_argument('--skip-reference-check',action='store_true')
    args=parser.parse_args()
    parts=make_parts()
    parts += [Part('07_display_fit_coupon',fit_coupon(),'#648b87',group='coupon'),
              Part('08_fastener_fit_coupon',hole_coupon(),'#648b87',group='coupon')]
    export(parts,args.output)
    verify(parts,args.output,check_references=not args.skip_reference_check)
    print(f'Output: {args.output}')


if __name__=='__main__':
    main()
