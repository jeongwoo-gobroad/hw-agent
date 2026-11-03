from pathlib import Path
import json
import math
import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray

ROOT=Path(__file__).resolve().parent
DATA=json.loads((ROOT/'output/preview/meshes.json').read_text())
angle=math.radians(DATA['rotation'])
rotation=np.array([[1,0,0],[0,math.cos(angle),-math.sin(angle)],[0,math.sin(angle),math.cos(angle)]])


def render(name,position,exclude=(),exploded=False):
    renderer=vtk.vtkRenderer()
    renderer.SetBackground(0.953,0.96,0.96)
    for part in DATA['parts']:
        if any(part['name'].startswith(x) for x in exclude):
            continue
        vertices=np.array(part['v'])
        if exploded:
            vertices+=np.array(part['explode'])
        vertices=vertices@rotation.T+np.array([0,0,DATA['lift']])
        poly=vtk.vtkPolyData()
        points=vtk.vtkPoints(); points.SetData(numpy_to_vtk(vertices,deep=True)); poly.SetPoints(points)
        faces=np.array(part['f'],dtype=np.int64)
        cells=vtk.vtkCellArray()
        cells.SetCells(len(faces),numpy_to_vtkIdTypeArray(np.column_stack([np.full(len(faces),3),faces]).ravel(),deep=True))
        poly.SetPolys(cells)
        normals=vtk.vtkPolyDataNormals(); normals.SetInputData(poly); normals.SetFeatureAngle(45); normals.Update()
        mapper=vtk.vtkPolyDataMapper(); mapper.SetInputConnection(normals.GetOutputPort())
        actor=vtk.vtkActor(); actor.SetMapper(mapper)
        color=tuple(int(part['color'][i:i+2],16)/255 for i in (1,3,5))
        actor.GetProperty().SetColor(*color)
        actor.GetProperty().SetAmbient(0.25); actor.GetProperty().SetDiffuse(0.75)
        actor.GetProperty().SetSpecular(0.2); actor.GetProperty().SetSpecularPower(35)
        renderer.AddActor(actor)
    camera=renderer.GetActiveCamera()
    camera.SetPosition(*position); camera.SetFocalPoint(0,-20,93); camera.SetViewUp(0,0,1)
    camera.ParallelProjectionOn(); camera.SetParallelScale(150 if exploded else 132)
    window=vtk.vtkRenderWindow(); window.SetOffScreenRendering(1); window.AddRenderer(renderer)
    window.SetSize(1400,1100); window.SetMultiSamples(8); window.Render()
    capture=vtk.vtkWindowToImageFilter(); capture.SetInput(window); capture.Update()
    writer=vtk.vtkPNGWriter(); writer.SetFileName(str(ROOT/'output/preview'/name)); writer.SetInputConnection(capture.GetOutputPort()); writer.Write()
    window.Finalize()


if __name__=='__main__':
    render('assembled_front.png',(320,450,260))
    render('assembled_back.png',(-320,-460,280))
    render('interior.png',(-80,-420,360),exclude=('02_','03_','05_','06_'))
    render('exploded.png',(-330,-420,310),exploded=True)
