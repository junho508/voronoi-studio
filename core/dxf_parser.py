"""
DXF Parser Module for Voronoi Pattern Generator.

Extracts closed boundary polygons from DXF files using ezdxf and shapely.
Supports LWPOLYLINE, POLYLINE, LINE, ARC, and CIRCLE entities.
"""

import math
import tempfile
import os
from typing import List, Tuple, Union, Any
import numpy as np
import ezdxf
from shapely.geometry import Polygon, MultiPolygon, LineString
from shapely.ops import polygonize, unary_union
import shapely


def arc_to_polyline(
    center: Tuple[float, float],
    radius: float,
    start_angle: float,
    end_angle: float,
    num_points: int = 32
) -> List[Tuple[float, float]]:
    """
    Approximate a circular arc as a polyline segment with num_points.
    
    Args:
        center: (cx, cy) tuple.
        radius: Arc radius.
        start_angle: Start angle in degrees (counter-clockwise from X axis).
        end_angle: End angle in degrees (counter-clockwise from X axis).
        num_points: Number of discrete points to generate along the arc.
        
    Returns:
        List of (x, y) coordinates representing the arc polyline.
    """
    if radius <= 0:
        return [center]
        
    # DXF arcs run counter-clockwise from start_angle to end_angle
    span = (end_angle - start_angle) % 360.0
    if span <= 1e-7 and end_angle != start_angle:
        span = 360.0
    effective_end = start_angle + span

    angles = np.linspace(
        math.radians(start_angle),
        math.radians(effective_end),
        max(2, num_points)
    )
    cx, cy = center
    return [(float(cx + radius * math.cos(a)), float(cy + radius * math.sin(a))) for a in angles]


def _is_duplicate_polygon(poly: Polygon, existing_list: List[Polygon], tol: float = 1e-3) -> bool:
    """Check if a polygon is a duplicate of one already in existing_list."""
    p_area = poly.area
    b1 = poly.bounds
    for ep in existing_list:
        if abs(p_area - ep.area) < 1e-3 * max(1.0, ep.area):
            b2 = ep.bounds
            if all(abs(a - b) < tol * 5 for a, b in zip(b1, b2)):
                if poly.equals_exact(ep, tol):
                    return True
                sym_diff = poly.symmetric_difference(ep).area
                if sym_diff < 1e-4 * max(1.0, ep.area):
                    return True
    return False


def parse_dxf(file_source: Union[str, bytes, Any]) -> List[Polygon]:
    """
    Parse a DXF file source and extract closed boundary polygons.
    
    Args:
        file_source: File path (str), raw bytes, or file-like object (e.g. Flask FileStorage).
        
    Returns:
        List of shapely Polygon objects representing closed regions found in DXF.
    """
    temp_path = None
    try:
        # Resolve file path
        if isinstance(file_source, str) and os.path.isfile(file_source):
            filepath = file_source
        elif hasattr(file_source, "read"):
            # File-like object (e.g., Flask request.files)
            file_source.seek(0)
            content = file_source.read()
            with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tf:
                if isinstance(content, str):
                    tf.write(content.encode("utf-8", errors="ignore"))
                else:
                    tf.write(content)
                temp_path = tf.name
            filepath = temp_path
        elif isinstance(file_source, bytes):
            with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tf:
                tf.write(file_source)
                temp_path = tf.name
            filepath = temp_path
        else:
            raise ValueError(f"Unsupported file source type: {type(file_source)}")

        # Read DXF document using ezdxf
        doc = ezdxf.readfile(filepath)
        msp = doc.modelspace()

        candidate_polygons: List[Polygon] = []
        open_lines: List[LineString] = []

        for entity in msp:
            dxftype = entity.dxftype()

            try:
                # 1. Closed and open LWPOLYLINE
                if dxftype == "LWPOLYLINE":
                    pts = [(float(p[0]), float(p[1])) for p in entity.get_points(format="xy")]
                    if len(pts) < 2:
                        continue
                    
                    is_closed = bool(entity.is_closed or entity.closed)
                    if not is_closed and len(pts) >= 4 and pts[0] == pts[-1]:
                        is_closed = True

                    if is_closed and len(pts) >= 3:
                        poly = Polygon(pts)
                        if poly.is_valid and poly.area > 1e-4:
                            candidate_polygons.append(poly)
                        elif not poly.is_valid:
                            valid_p = shapely.make_valid(poly)
                            if isinstance(valid_p, Polygon) and valid_p.area > 1e-4:
                                candidate_polygons.append(valid_p)
                            elif isinstance(valid_p, MultiPolygon):
                                candidate_polygons.extend([p for p in valid_p.geoms if p.area > 1e-4])
                    else:
                        open_lines.append(LineString(pts))

                # 2. 2D / 3D POLYLINE
                elif dxftype == "POLYLINE":
                    pts = [(float(v.dxf.location.x), float(v.dxf.location.y)) for v in entity.vertices]
                    if len(pts) < 2:
                        continue
                    
                    is_closed = bool(entity.is_closed)
                    if not is_closed and len(pts) >= 4 and pts[0] == pts[-1]:
                        is_closed = True

                    if is_closed and len(pts) >= 3:
                        poly = Polygon(pts)
                        if poly.is_valid and poly.area > 1e-4:
                            candidate_polygons.append(poly)
                        elif not poly.is_valid:
                            valid_p = shapely.make_valid(poly)
                            if isinstance(valid_p, Polygon) and valid_p.area > 1e-4:
                                candidate_polygons.append(valid_p)
                            elif isinstance(valid_p, MultiPolygon):
                                candidate_polygons.extend([p for p in valid_p.geoms if p.area > 1e-4])
                    else:
                        open_lines.append(LineString(pts))

                # 3. CIRCLE
                elif dxftype == "CIRCLE":
                    cx = float(entity.dxf.center.x)
                    cy = float(entity.dxf.center.y)
                    radius = float(entity.dxf.radius)
                    if radius > 1e-4:
                        angles = np.linspace(0, 2 * math.pi, 33)[:-1]
                        circle_pts = [(cx + radius * math.cos(a), cy + radius * math.sin(a)) for a in angles]
                        poly = Polygon(circle_pts)
                        if poly.is_valid and poly.area > 1e-4:
                            candidate_polygons.append(poly)

                # 4. LINE
                elif dxftype == "LINE":
                    p1 = (float(entity.dxf.start.x), float(entity.dxf.start.y))
                    p2 = (float(entity.dxf.end.x), float(entity.dxf.end.y))
                    if p1 != p2:
                        open_lines.append(LineString([p1, p2]))

                # 5. ARC
                elif dxftype == "ARC":
                    cx = float(entity.dxf.center.x)
                    cy = float(entity.dxf.center.y)
                    radius = float(entity.dxf.radius)
                    start_angle = float(entity.dxf.start_angle)
                    end_angle = float(entity.dxf.end_angle)
                    if radius > 1e-4:
                        arc_pts = arc_to_polyline((cx, cy), radius, start_angle, end_angle, num_points=32)
                        if len(arc_pts) >= 2:
                            open_lines.append(LineString(arc_pts))

            except Exception as ent_err:
                # Log entity issue and continue parsing other entities
                continue

        # Polygonize open lines (LINE, ARC segments, open polylines)
        if open_lines:
            try:
                # unary_union nodes intersecting LineStrings
                noded = unary_union(open_lines)
                polygonized = list(polygonize(noded))
                for poly in polygonized:
                    if poly.is_valid and poly.area > 1e-4:
                        candidate_polygons.append(poly)
            except Exception:
                pass

        # Deduplicate and finalize polygons
        unique_polygons: List[Polygon] = []
        for poly in candidate_polygons:
            if not poly.is_valid:
                poly = shapely.make_valid(poly)
            
            sub_polys = []
            if isinstance(poly, Polygon):
                sub_polys = [poly]
            elif isinstance(poly, MultiPolygon):
                sub_polys = list(poly.geoms)

            for sp in sub_polys:
                if sp.area > 1e-4 and not _is_duplicate_polygon(sp, unique_polygons):
                    unique_polygons.append(sp)

        return unique_polygons

    except Exception as e:
        raise RuntimeError(f"Failed to parse DXF: {str(e)}") from e

    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def parse_dxf_to_regions(file_source: Union[str, bytes, Any]) -> List[dict]:
    """
    Parse a DXF file and return structured region dicts suitable for API response.
    
    Returns:
        List of dicts: [{'id': str, 'coords': [[x,y],...], 'area': float, 'bounds': [minx,miny,maxx,maxy]}]
    """
    polygons = parse_dxf(file_source)
    regions = []
    for idx, poly in enumerate(polygons):
        coords = [[round(float(c[0]), 4), round(float(c[1]), 4)] for c in poly.exterior.coords]
        b = [round(float(val), 4) for val in poly.bounds]
        regions.append({
            "id": f"region_{idx + 1}",
            "coords": coords,
            "area": round(float(poly.area), 4),
            "bounds": {
                "minx": b[0],
                "miny": b[1],
                "maxx": b[2],
                "maxy": b[3]
            }
        })
    return regions
