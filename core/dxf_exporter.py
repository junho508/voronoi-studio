"""
DXF Exporter Module for Voronoi and Pattern Generator.

Exports generated pattern cells and boundaries to DXF files with dedicated layers.
When corner_radius > 0, rounded corners are exported as true ARC entities instead of
approximated polylines, for full CAD compatibility (Siemens NX, AutoCAD).
"""

import os
import math
from typing import List, Dict, Any, Union, Optional, Tuple
import ezdxf
from shapely.geometry import Polygon, MultiPolygon


def _extract_coords(item: Any) -> List[List[float]]:
    """Helper to extract coordinate list from various geometric representations."""
    if isinstance(item, dict):
        if "coords" in item:
            return item["coords"]
        elif "coordinates" in item:
            return item["coordinates"]
    elif isinstance(item, Polygon):
        return [[float(c[0]), float(c[1])] for c in item.exterior.coords]
    elif isinstance(item, (list, tuple)):
        if len(item) > 0:
            if isinstance(item[0], (list, tuple)) and len(item[0]) >= 2:
                return [[float(p[0]), float(p[1])] for p in item]
            elif isinstance(item[0], dict):
                return _extract_coords(item[0])
    return []


def _clean_closed_polygon_points(coords: List[List[float]]) -> List[tuple]:
    """Remove duplicate closing point and round to 6 decimal places."""
    if not coords or len(coords) < 3:
        return []

    pts = [(round(float(p[0]), 6), round(float(p[1]), 6)) for p in coords]

    if len(pts) >= 4 and pts[0] == pts[-1]:
        pts = pts[:-1]

    deduped = []
    for p in pts:
        if not deduped or p != deduped[-1]:
            deduped.append(p)

    if len(deduped) >= 3 and deduped[0] == deduped[-1]:
        deduped = deduped[:-1]

    return deduped if len(deduped) >= 3 else []


def _detect_arc_segments(
    pts: List[tuple],
    corner_radius: float,
    tolerance: float = 0.05
) -> List[Dict[str, Any]]:
    """
    Analyze a closed polygon (which was created by buffer erode-dilate rounding)
    and decompose it into alternating LINE and ARC segments.
    
    Returns list of segments:
      {'type': 'LINE', 'start': (x,y), 'end': (x,y)}
      {'type': 'ARC', 'center': (x,y), 'radius': r, 'start_angle': deg, 'end_angle': deg, 'ccw': bool}
    """
    if not pts or len(pts) < 3:
        return []

    segments = []
    n = len(pts)

    i = 0
    while i < n:
        p1 = pts[i]
        p2 = pts[(i + 1) % n]

        # Compute curvature between consecutive triplets to detect arc runs
        # Collect consecutive points that lie on the same circle of radius ≈ corner_radius
        # Strategy: group runs of points with consistent center
        arc_pts = [p1, p2]
        j = i + 2
        while j < n + i:
            p_next = pts[j % n]
            # Check if p1, p2, p_next are co-circular with radius ≈ corner_radius
            cx, cy, r = _circumcircle(arc_pts[-2], arc_pts[-1], p_next)
            if abs(r - corner_radius) < corner_radius * tolerance + tolerance:
                arc_pts.append(p_next)
                j += 1
            else:
                break

        if len(arc_pts) >= 3:
            # Fit a circle to all arc points
            cx, cy, r = _fit_circle_least_squares(arc_pts)
            if abs(r - corner_radius) < corner_radius * 0.5 + 0.5:
                # It's an arc — compute start/end angles
                start_angle = math.degrees(math.atan2(arc_pts[0][1] - cy, arc_pts[0][0] - cx)) % 360
                end_angle = math.degrees(math.atan2(arc_pts[-1][1] - cy, arc_pts[-1][0] - cx)) % 360

                # DXF arcs ALWAYS sweep Counter-Clockwise (CCW) from start_angle to end_angle.
                # Check whether the sample points progress CCW or CW along the circle.
                # If they progress CW, we MUST swap start_angle and end_angle so that the
                # DXF arc covers the correct short inner-corner arc (fillet), rather than
                # swinging 270+ degrees around the outside like a cloverleaf!
                mid_pt = arc_pts[len(arc_pts) // 2]
                mid_angle = math.degrees(math.atan2(mid_pt[1] - cy, mid_pt[0] - cx)) % 360

                sweep = (end_angle - start_angle) % 360
                mid_sweep = (mid_angle - start_angle) % 360

                if not (0.0 < mid_sweep < sweep) or sweep > 180.0:
                    start_angle, end_angle = end_angle, start_angle

                segments.append({
                    'type': 'ARC',
                    'center': (round(cx, 6), round(cy, 6)),
                    'radius': round(r, 6),
                    'start_angle': round(start_angle, 4),
                    'end_angle': round(end_angle, 4),
                    'start_pt': arc_pts[0],
                    'end_pt': arc_pts[-1],
                    'ccw': True
                })
                i = i + len(arc_pts) - 1
                continue

        # It's a line segment
        segments.append({
            'type': 'LINE',
            'start': p1,
            'end': p2
        })
        i += 1

    return segments


def _circumcircle(p1, p2, p3) -> Tuple[float, float, float]:
    """Compute circumcircle center (cx, cy) and radius r of triangle p1p2p3."""
    ax, ay = p1
    bx, by = p2
    cx, cy = p3

    D = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(D) < 1e-10:
        return 0.0, 0.0, float('inf')

    ux = ((ax**2 + ay**2) * (by - cy) + (bx**2 + by**2) * (cy - ay) + (cx**2 + cy**2) * (ay - by)) / D
    uy = ((ax**2 + ay**2) * (cx - bx) + (bx**2 + by**2) * (ax - cx) + (cx**2 + cy**2) * (bx - ax)) / D

    r = math.hypot(ax - ux, ay - uy)
    return ux, uy, r


def _fit_circle_least_squares(pts: List[tuple]) -> Tuple[float, float, float]:
    """Fit a circle to a list of points using algebraic least squares."""
    if len(pts) < 3:
        return _circumcircle(pts[0], pts[1], pts[min(2, len(pts)-1)])

    n = len(pts)
    sum_x = sum(p[0] for p in pts)
    sum_y = sum(p[1] for p in pts)
    sum_x2 = sum(p[0]**2 for p in pts)
    sum_y2 = sum(p[1]**2 for p in pts)
    sum_xy = sum(p[0]*p[1] for p in pts)
    sum_x3 = sum(p[0]**3 for p in pts)
    sum_y3 = sum(p[1]**3 for p in pts)
    sum_xy2 = sum(p[0]*p[1]**2 for p in pts)
    sum_x2y = sum(p[0]**2*p[1] for p in pts)

    A = n * sum_x2 - sum_x**2
    B = n * sum_xy - sum_x * sum_y
    C = n * sum_y2 - sum_y**2
    D = 0.5 * (n * (sum_x3 + sum_xy2) - sum_x * (sum_x2 + sum_y2))
    E = 0.5 * (n * (sum_x2y + sum_y3) - sum_y * (sum_x2 + sum_y2))

    denom = A * C - B**2
    if abs(denom) < 1e-10:
        return _circumcircle(pts[0], pts[len(pts)//2], pts[-1])

    cx = (D * C - B * E) / denom
    cy = (A * E - B * D) / denom
    r = math.sqrt((sum_x2 + sum_y2 - 2*cx*sum_x - 2*cy*sum_y) / n + cx**2 + cy**2)
    return cx, cy, r


def _add_cell_as_arcs(msp, pts: List[tuple], corner_radius: float, layer: str):
    """
    Export a closed polygon cell using LINE + ARC entities.
    Detects arc segments from rounded Shapely output and exports as true DXF ARCs.
    Falls back to LWPOLYLINE if arc detection fails.
    """
    if len(pts) < 3:
        return

    try:
        segments = _detect_arc_segments(pts, corner_radius)
        if not segments:
            raise ValueError("No segments detected")

        # Validate segments: at least some must be meaningful
        arc_count = sum(1 for s in segments if s['type'] == 'ARC')
        
        if arc_count == 0:
            # No arcs found — just export as polyline
            msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})
            return

        # Export as individual LINE and ARC entities
        for seg in segments:
            if seg['type'] == 'LINE':
                start = seg['start']
                end = seg['end']
                # Skip degenerate lines
                if math.hypot(end[0] - start[0], end[1] - start[1]) < 1e-4:
                    continue
                msp.add_line(
                    (start[0], start[1], 0),
                    (end[0], end[1], 0),
                    dxfattribs={"layer": layer}
                )
            elif seg['type'] == 'ARC':
                center = seg['center']
                radius = seg['radius']
                start_angle = seg['start_angle']
                end_angle = seg['end_angle']
                
                # DXF arc goes CCW from start_angle to end_angle
                msp.add_arc(
                    center=(center[0], center[1], 0),
                    radius=radius,
                    start_angle=start_angle,
                    end_angle=end_angle,
                    dxfattribs={"layer": layer}
                )

    except Exception:
        # Fallback: export as LWPOLYLINE
        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})


def export_to_dxf(
    cells: List[Union[Dict[str, Any], List[List[float]]]],
    boundaries: Union[List[Any], Dict[str, Any], Any],
    output_path: str,
    options: Optional[Dict[str, Any]] = None
) -> str:
    """
    Export cells and boundaries to a DXF file.
    
    Args:
        cells: List of cell dicts ({'coords': [...]}) or coordinate lists.
        boundaries: List of boundary dicts, coordinate lists, or Polygons.
        output_path: Target path to write the DXF file.
        options: Optional export settings:
            - 'include_boundary' (bool): Whether to export boundary layer (default True).
            - 'dxf_version' (str): DXF release, default 'R2010'.
            - 'corner_radius' (float): If > 0, export rounded corners as true ARC entities.
            
    Returns:
        output_path on success.
    """
    if options is None:
        options = {}

    include_boundary = bool(options.get("include_boundary", True))
    dxf_version = str(options.get("dxf_version", "R2010"))
    corner_radius = float(options.get("corner_radius", 0.0))

    target_dir = os.path.dirname(os.path.abspath(output_path))
    if target_dir and not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)

    doc = ezdxf.new(dxf_version)

    if "VORONOI_PATTERN" not in doc.layers:
        doc.layers.add("VORONOI_PATTERN", color=1)
    if "BOUNDARY" not in doc.layers:
        doc.layers.add("BOUNDARY", color=3)

    msp = doc.modelspace()

    # 1. Export Cells
    for cell in cells:
        coords = _extract_coords(cell)
        clean_pts = _clean_closed_polygon_points(coords)
        if len(clean_pts) < 3:
            continue

        if corner_radius > 0.1 and len(clean_pts) < 30:
            # Export with true ARC entities for rounded corners
            _add_cell_as_arcs(msp, clean_pts, corner_radius, "VORONOI_PATTERN")
        else:
            # High-resolution closed polyline for smooth organic or standard cells
            msp.add_lwpolyline(
                clean_pts,
                close=True,
                dxfattribs={"layer": "VORONOI_PATTERN"}
            )

    # 2. Export Boundaries
    if include_boundary and boundaries:
        boundary_list = boundaries if isinstance(boundaries, list) else [boundaries]
        
        if boundary_list and isinstance(boundary_list[0], (list, tuple)) and len(boundary_list[0]) == 2 and isinstance(boundary_list[0][0], (int, float)):
            boundary_list = [boundary_list]

        for b in boundary_list:
            if isinstance(b, MultiPolygon):
                for p in b.geoms:
                    clean_pts = _clean_closed_polygon_points(_extract_coords(p))
                    if len(clean_pts) >= 3:
                        msp.add_lwpolyline(
                            clean_pts,
                            close=True,
                            dxfattribs={"layer": "BOUNDARY"}
                        )
            else:
                coords = _extract_coords(b)
                clean_pts = _clean_closed_polygon_points(coords)
                if len(clean_pts) >= 3:
                    msp.add_lwpolyline(
                        clean_pts,
                        close=True,
                        dxfattribs={"layer": "BOUNDARY"}
                    )

    doc.saveas(output_path)
    return output_path
