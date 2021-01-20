from math import sqrt
import Draft
import Arch
import Part
import FreeCAD as App
import FreeCADGui as Gui
import pandas as pd
from safe.punch import safe
from safe.punch.axis import create_grids
from safe.punch.punch_funcs import remove_obj
from safe.punch import foundation
from safe.punch.punch import make_punch


class Geom(object):

    def __init__(self, filename=None, form=None):
        self.progressbar = form.progressBar
        self.bar_label = form.bar_label
        if filename:
            self._safe = safe.Safe(filename)
            self.solid_slabs = self._safe.solid_slabs
            self.slab_prop_assignment = self._safe.slab_prop_assignment
            self.load_combinations = self._safe.load_combinations
            self.point_loads = self._safe.points_loads

    def create_vectors(self, points_prop=None):
        vectors = {}
        self.bar_label.setText("Reading Points Geometry")
        for key, value in points_prop.items():
            vectors[key] = App.Vector(round(value.x, 4), round(value.y, 4), int(value.z))
        return vectors

    def create_areas(self, areas_prop):
        areas = {}
        self.bar_label.setText("Creating Areas Geometry")
        for key, points_id in areas_prop.items():
            points = [self.obj_geom_points[point_id] for point_id in points_id]
            points.append(points[0])
            areas[key] = Part.Face(Part.makePolygon(points))
        return areas

    def create_structures(self, areas):
        self.bar_label.setText("Creating structures Geometry")
        areas_thickness = self._safe.get_thickness(areas)
        structures = {}
        for key, area in areas.items():
            thickness = areas_thickness[key] - 93
            structures[key] = area.extrude(App.Vector(0, 0, -thickness))
        return structures

    def create_fusion(self, structures):
        self.bar_label.setText("Creating One Slab Geometry")
        slab_struc = []
        slab_opening = []
        for key, value in structures.items():
            if self.slab_prop_assignment[key] == 'None':
                slab_opening.append(value)
            else:
                slab_struc.append(value)
        if len(slab_struc) == 1:
            print('one slab')
            fusion = slab_struc[0]
        else:
            s1 = slab_struc[0]
            fusion = s1.fuse(slab_struc[1:])
        if bool(slab_opening):
            print('openings')
            fusion = fusion.cut(slab_opening)
            
        return fusion

    def create_foundation(self, fusion):
        self.bar_label.setText("Creating Foundation Geometry")
        if hasattr(fusion, "removeSplitter"):
            return fusion.removeSplitter()
        return fusion

    def create_punches(self):
        self.bar_label.setText("Creating Punch Objects")
        for f in self.foundation.Faces:
            if f.BoundBox.ZLength == 0 and f.BoundBox.ZMax == 0:
                foundation_plane = f
                break
        d = self.foundation.BoundBox.ZLength
        cover = 93
        h = d + cover
        fc = self._safe.fc
        foun_obj = foundation.make_foundation(foundation_plane, height=h, cover=cover, fc=fc)
        punchs = {}

        for key in self.columns_number:
            value = self._safe.point_loads[key]
            bx = value['xdim']
            by = value['ydim']
            combos_load = self._safe.points_loads_combinations[self._safe.points_loads_combinations['Point'] == key]
            d = {}
            for row in combos_load.itertuples():
                combo = row.Combo
                F = row.Fgrav
                Mx = row.Mx
                My = row.My
                d[combo] = f"{F}, {Mx}, {My}"
            point = self._safe.obj_geom_points[key]
            center_of_load = App.Vector(point.x, point.y, 0)
            p = make_punch(
                foundation_plane,
                foun_obj,
                bx,
                by,
                center_of_load,
                d,
                )
            App.ActiveDocument.recompute()
            length = bx * 1.5
            height = by * 1.5
            l = p.Location
            if l in ('Corner1', 'Corner4', 'Edge4', 'Interier'):
                length *= -1
            elif l in ('Edge1', 'Interier'):
                height *= -1
            v = self.obj_geom_points[key]
            x = v.x + length
            y = v.y + height
            pl = App.Vector(x, y, 4100)
            t = '0.0'
            p.Ratio = t
            text = Draft.make_text([t, l], placement=pl)
            text.ViewObject.FontSize = 200
            p.text = text
            p.number = int(key)
            punchs[key] = p
        return punchs

    def grid_lines(self):
        if not App.ParamGet("User parameter:BaseApp/Preferences/Mod/Civil").GetBool("draw_grid", True):
            return

        gridLines = self._safe.grid_lines()
        if gridLines is None:
            return
        x_grids = gridLines['x']
        y_grids = gridLines['y']
        b = self.foundation.BoundBox
        create_grids(x_grids, b, 'x')
        create_grids(y_grids, b, 'y')

    def plot(self):
        self.obj_geom_points = self.create_vectors(self._safe.obj_geom_points)
        obj_geom_areas = self.create_areas(self._safe.obj_geom_areas)
        self.columns_number = list(self._safe.point_loads.keys())
        structures = self.create_structures(obj_geom_areas)
        del obj_geom_areas
        fusion = self.create_fusion(structures)
        Gui.SendMsgToActiveView("ViewFit")
        self.foundation = self.create_foundation(fusion)
        self.grid_lines()
        self.punchs = self.create_punches()
        App.ActiveDocument.recompute()
        Gui.SendMsgToActiveView("ViewFit")
        Gui.activeDocument().activeView().viewAxonometric()
        self.bar_label.setText("")
