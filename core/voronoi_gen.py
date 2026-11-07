"""
Voronoi and Procedural Pattern Generator Module.

Implements Voronoi, Hexagonal, Triangular, and Square pattern generation
with jitter control, mirror/ghost points for boundary handling, boundary offsets,
cell gap insetting, and corner radius rounding.
"""

import math
from typing import List, Tuple, Dict, Any, Optional, Union
import numpy as np
from scipy.spatial import Voronoi
from scipy.ndimage import gaussian_filter1d
import shapely
from shapely.geometry import Polygon, MultiPolygon, Point, GeometryCollection


def to_shapely_polygon(boundary_input: Union[Polygon, MultiPolygon, dict, list, Any]) -> Polygon:
    """Normalize various boundary input formats to a single valid shapely Polygon."""
    if isinstance(boundary_input, Polygon):
        poly = boundary_input
    elif isinstance(boundary_input, MultiPolygon):
        # Pick the largest polygon by area
        poly = max(boundary_input.geoms, key=lambda p: p.area)
    elif isinstance(boundary_input, dict):
        if "coords" in boundary_input:
            poly = Polygon(boundary_input["coords"])
        elif "coordinates" in boundary_input:
            poly = Polygon(boundary_input["coordinates"])
        else:
            raise ValueError(f"Unrecognized boundary dict format: {boundary_input.keys()}")
    elif isinstance(boundary_input, (list, tuple)):
        # Check if list of region dicts was passed
        if len(boundary_input) > 0 and isinstance(boundary_input[0], dict):
            return to_shapely_polygon(boundary_input[0])
        poly = Polygon(boundary_input)
    else:
        raise ValueError(f"Cannot convert boundary of type {type(boundary_input)} to Polygon")

    if not poly.is_valid:
        valid_p = shapely.make_valid(poly)
        if isinstance(valid_p, Polygon):
            poly = valid_p
        elif isinstance(valid_p, MultiPolygon):
            poly = max(valid_p.geoms, key=lambda p: p.area)
        else:
            # Try buffer 0 fix
            poly = poly.buffer(0)

    if poly.is_empty or poly.area <= 1e-6:
        raise ValueError("Boundary polygon is empty or degenerate.")

    return poly


def rotate_point(x: float, y: float, cx: float, cy: float, angle_deg: float) -> Tuple[float, float]:
    """Rotate a point (x, y) around center (cx, cy) by angle_deg degrees."""
    if angle_deg % 360.0 == 0:
        return (x, y)
    rad = math.radians(angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    dx = x - cx
    dy = y - cy
    rx = cx + dx * cos_a - dy * sin_a
    ry = cy + dx * sin_a + dy * cos_a
    return (rx, ry)


def post_process_polygon(
    poly: Polygon,
    effective_boundary: Polygon,
    cell_gap: float = 0.0,
    corner_radius: float = 0.0,
    is_seamless: bool = False,
    smoothness: float = 0.0,
    cell_size: float = 15.0,
    cell_style: str = "line",
    spline_type: str = "pebble"
) -> List[List[List[float]]]:
    """
    Process polygon: clip against boundary, apply cell_gap, corner_radius, and curve styling.
    
    In LINE mode (cell_style == 'line'):
      - Pure standard CAD geometry: straight lines + true CAD circular corner fillets.
      - Uses buffer(-corner_radius, join_style=2) followed by buffer(+corner_radius, join_style=1).
      - Straight edges remain exact lines; corners become exact circular arcs.
      - Perfectly matches DXF LINE + ARC export entities.
      
    In SPLINE mode (cell_style == 'spline'):
      - Organic bionic lattice contours: combines corner_radius and smoothness.
      - 'pebble' (조약돌형, default): Morphological round closing + organic pebble curvature.
      - 'lattice' (래티스형): Tensioned Catmull-Rom spline with deep corner penetration.
    """
    if poly.is_empty or poly.area <= 1e-6:
        return []

    is_spline = (str(cell_style).lower() == "spline")

    if not is_spline:
        # ====================================================
        # LINE MODE (Exact CAD Lines + True ARC Fillets)
        # ====================================================
        if is_seamless:
            current = poly
            if cell_gap > 1e-4:
                current = current.buffer(-cell_gap / 2.0)
                if current.is_empty or current.area <= 1e-4:
                    return []

            if corner_radius > 1e-4:
                eroded = current.buffer(-corner_radius, join_style=2)
                if not eroded.is_empty and eroded.area > 1e-4:
                    current = eroded.buffer(corner_radius, join_style=1)
            if current.is_empty or current.area <= 1e-4:
                return []

            try:
                clipped = current.intersection(effective_boundary)
            except Exception:
                clipped = current.buffer(0).intersection(effective_boundary.buffer(0))

            if clipped.is_empty or clipped.area <= 1e-4:
                return []

            sub_polys: List[Polygon] = []
            if isinstance(clipped, Polygon):
                sub_polys = [clipped]
            elif isinstance(clipped, (MultiPolygon, GeometryCollection)):
                for g in clipped.geoms:
                    if isinstance(g, Polygon) and g.area > 1e-4:
                        sub_polys.append(g)

            result_coords: List[List[List[float]]] = []
            for sp in sub_polys:
                coords = [[round(float(c[0]), 4), round(float(c[1]), 4)] for c in sp.exterior.coords]
                if len(coords) >= 4:
                    result_coords.append(coords)
            return result_coords

        else:
            # Standard non-seamless mode
            try:
                clipped = poly.intersection(effective_boundary)
            except Exception:
                clipped = poly.buffer(0).intersection(effective_boundary.buffer(0))

            if clipped.is_empty or clipped.area <= 1e-4:
                return []

            sub_polys: List[Polygon] = []
            if isinstance(clipped, Polygon):
                sub_polys = [clipped]
            elif isinstance(clipped, (MultiPolygon, GeometryCollection)):
                for g in clipped.geoms:
                    if isinstance(g, Polygon) and g.area > 1e-4:
                        sub_polys.append(g)

            result_coords: List[List[List[float]]] = []

            for sp in sub_polys:
                current = sp
                if cell_gap > 1e-4:
                    current = current.buffer(-cell_gap / 2.0)
                    if current.is_empty or current.area <= 1e-4:
                        continue

                if corner_radius > 1e-4:
                    eroded = current.buffer(-corner_radius, join_style=2)
                    if not eroded.is_empty and eroded.area > 1e-4:
                        current = eroded.buffer(corner_radius, join_style=1)
                if current.is_empty or current.area <= 1e-4:
                    continue

                if isinstance(current, Polygon):
                    coords = [[round(float(c[0]), 4), round(float(c[1]), 4)] for c in current.exterior.coords]
                    if len(coords) >= 4:
                        result_coords.append(coords)
                elif isinstance(current, (MultiPolygon, GeometryCollection)):
                    for part in current.geoms:
                        if isinstance(part, Polygon) and part.area > 1e-4:
                            coords = [[round(float(c[0]), 4), round(float(c[1]), 4)] for c in part.exterior.coords]
                            if len(coords) >= 4:
                                result_coords.append(coords)

            return result_coords

    else:
        # ====================================================
        # SPLINE MODE (Organic continuous curves & rounded cells)
        # ====================================================
        if is_seamless:
            current = poly
            if cell_gap > 1e-4:
                current = current.buffer(-cell_gap / 2.0, join_style=2)
                if current.is_empty or current.area <= 1e-4:
                    return []

            current = organic_smooth_polygon(
                current,
                smoothness=smoothness,
                corner_radius=corner_radius,
                cell_size=cell_size,
                spline_type=spline_type
            )
            if current.is_empty or current.area <= 1e-4:
                return []

            try:
                clipped = current.intersection(effective_boundary)
            except Exception:
                clipped = current.buffer(0).intersection(effective_boundary.buffer(0))

            if clipped.is_empty or clipped.area <= 1e-4:
                return []

            sub_polys = []
            if isinstance(clipped, Polygon):
                sub_polys = [clipped]
            elif isinstance(clipped, (MultiPolygon, GeometryCollection)):
                for g in clipped.geoms:
                    if isinstance(g, Polygon) and g.area > 1e-4:
                        sub_polys.append(g)

            result_coords = []
            for sp in sub_polys:
                coords = [[round(float(c[0]), 4), round(float(c[1]), 4)] for c in sp.exterior.coords]
                if len(coords) >= 4:
                    result_coords.append(coords)
            return result_coords

        else:
            # Standard non-seamless mode
            try:
                clipped = poly.intersection(effective_boundary)
            except Exception:
                clipped = poly.buffer(0).intersection(effective_boundary.buffer(0))

            if clipped.is_empty or clipped.area <= 1e-4:
                return []

            sub_polys = []
            if isinstance(clipped, Polygon):
                sub_polys = [clipped]
            elif isinstance(clipped, (MultiPolygon, GeometryCollection)):
                for g in clipped.geoms:
                    if isinstance(g, Polygon) and g.area > 1e-4:
                        sub_polys.append(g)

            result_coords = []

            for sp in sub_polys:
                current = sp
                if cell_gap > 1e-4:
                    current = current.buffer(-cell_gap / 2.0, join_style=2)
                    if current.is_empty or current.area <= 1e-4:
                        continue

                current = organic_smooth_polygon(
                    current,
                    smoothness=smoothness,
                    corner_radius=corner_radius,
                    cell_size=cell_size,
                    spline_type=spline_type
                )
                if current.is_empty or current.area <= 1e-4:
                    continue

                if isinstance(current, Polygon):
                    coords = [[round(float(c[0]), 4), round(float(c[1]), 4)] for c in current.exterior.coords]
                    if len(coords) >= 4:
                        result_coords.append(coords)
                elif isinstance(current, (MultiPolygon, GeometryCollection)):
                    for part in current.geoms:
                        if isinstance(part, Polygon) and part.area > 1e-4:
                            coords = [[round(float(c[0]), 4), round(float(c[1]), 4)] for c in part.exterior.coords]
                            if len(coords) >= 4:
                                result_coords.append(coords)

            return result_coords


def resample_ring(ext, num_points: int = 36) -> np.ndarray:
    """Resample polygon exterior ring into equidistant points for smooth organic curvature."""
    total_len = ext.length
    if total_len <= 1e-4:
        return np.array(ext.coords)
    dists = np.linspace(0, total_len, num_points, endpoint=False)
    pts = np.array([[ext.interpolate(d).x, ext.interpolate(d).y] for d in dists])
    return pts


def chaikin_pass(pts: np.ndarray, alpha: float = 0.15) -> np.ndarray:
    """Single Chaikin corner-cutting smoothing step on cyclic point list."""
    n = len(pts)
    new_pts = []
    for i in range(n):
        p0 = pts[i]
        p1 = pts[(i + 1) % n]
        new_pts.append((1.0 - alpha) * p0 + alpha * p1)
        new_pts.append(alpha * p0 + (1.0 - alpha) * p1)
    return np.array(new_pts)


def catmull_rom_spline(control_points: List[tuple], num_samples_per_seg: int = 5, alpha: float = 0.5) -> Polygon:
    """
    Generate a closed Centripetal Catmull-Rom spline through a cyclic list of control points.
    Guarantees C1 continuity and passes smoothly through control points without self-loops or overshoot.
    """
    pts = np.array(control_points)
    n = len(pts)
    if n < 4:
        return Polygon(control_points)

    curve = []
    for i in range(n):
        p0 = pts[(i - 1) % n]
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n]

        def tj(ti, pi, pj):
            d = np.linalg.norm(pj - pi)
            return ti + (d ** alpha if d > 1e-6 else 1e-4)

        t0 = 0.0
        t1 = tj(t0, p0, p1)
        t2 = tj(t1, p1, p2)
        t3 = tj(t2, p2, p3)

        t_vals = np.linspace(t1, t2, num_samples_per_seg, endpoint=False)
        for val in t_vals:
            A1 = (t1 - val) / max(1e-5, t1 - t0) * p0 + (val - t0) / max(1e-5, t1 - t0) * p1
            A2 = (t2 - val) / max(1e-5, t2 - t1) * p1 + (val - t1) / max(1e-5, t2 - t1) * p2
            A3 = (t3 - val) / max(1e-5, t3 - t2) * p2 + (val - t2) / max(1e-5, t3 - t2) * p3

            B1 = (t2 - val) / max(1e-5, t2 - t0) * A1 + (val - t0) / max(1e-5, t2 - t0) * A2
            B2 = (t3 - val) / max(1e-5, t3 - t1) * A2 + (val - t1) / max(1e-5, t3 - t1) * A3

            C = (t2 - val) / max(1e-5, t2 - t1) * B1 + (val - t1) / max(1e-5, t2 - t1) * B2
            curve.append((round(float(C[0]), 4), round(float(C[1]), 4)))

    curve.append(curve[0])
    return Polygon(curve)


def organic_smooth_polygon(
    poly: Polygon,
    smoothness: float = 0.0,
    corner_radius: float = 0.0,
    cell_size: float = 15.0,
    spline_type: str = "pebble"
) -> Polygon:
    """
    Apply organic smoothing and corner rounding in Spline mode.
    
    Subtypes:
      - 'pebble' (조약돌형, default): Full organic rounded cellular contours using morphological
        round closing with proportional inradius scaling and Chaikin subdivision.
      - 'lattice' (래티스형): Tensioned Catmull-Rom spline lattice that maintains deep corner
        penetration (uniform ribs) while organically curving edge segments.
      - 'dual_buffer' (듀얼버퍼형): Deep mitre negative offset + positive round expansion + round contraction.
      - 'metaball' (메타볼형): Multi-ray polar potential field with Log-Sum-Exp Soft-Min surface tension.
    """
    if poly.is_empty or poly.area <= 1e-6:
        return poly

    s_val = smoothness / 100.0 if smoothness > 1.0 else smoothness
    s_val = max(0.0, min(1.0, s_val))

    if s_val <= 0.001 and corner_radius <= 0.001:
        return poly

    current = poly
    st = str(spline_type).lower()

    if st == "lattice":
        # ====================================================
        # LATTICE MODE (래티스형):
        # Deep corner penetration + Centripetal Catmull-Rom spline curves
        # ====================================================
        approx_inradius = max(0.5, np.sqrt(max(1.0, current.area) / np.pi))
        max_fillet = min(cell_size * 0.22, approx_inradius * 0.55, 3.5)
        r_fillet = max(corner_radius, 0.4 + (max_fillet - 0.4) * s_val)

        if r_fillet > 1e-4:
            r_try = r_fillet
            eroded = None
            for _ in range(5):
                eroded = current.buffer(-r_try, join_style=2)
                if not eroded.is_empty and eroded.area > 1e-4:
                    break
                r_try *= 0.60

            if eroded is not None and not eroded.is_empty and eroded.area > 1e-4:
                if isinstance(eroded, MultiPolygon):
                    eroded = max(eroded.geoms, key=lambda g: g.area)
                dilated = eroded.buffer(r_try, join_style=1)
                if isinstance(dilated, MultiPolygon):
                    dilated = max(dilated.geoms, key=lambda g: g.area)
                current = dilated

        if s_val > 0.05 and isinstance(current, Polygon) and not current.is_empty:
            ext = current.exterior
            num_ctrl = max(10, min(24, int(round(ext.length / (cell_size * 0.35 * (1.25 - 0.45 * s_val))))))
            dists = np.linspace(0, ext.length, num_ctrl, endpoint=False)
            ctrl_pts = [ext.interpolate(d).coords[0] for d in dists]
            try:
                sp = catmull_rom_spline(ctrl_pts, num_samples_per_seg=5, alpha=0.5)
                if not sp.is_valid:
                    sp = shapely.make_valid(sp)
                    if isinstance(sp, MultiPolygon):
                        sp = max(sp.geoms, key=lambda g: g.area)
                if isinstance(sp, Polygon) and sp.area > 1e-4:
                    current = sp
            except Exception:
                pass

        return current

    elif st in ("dual_buffer", "dualbuffer", "dual"):
        # ====================================================
        # DUAL-BUFFER MODE (형태학적 듀얼 버퍼 라운딩):
        # Deep mitre negative offset + positive round expansion + round contraction
        # ====================================================
        approx_inradius = max(0.5, np.sqrt(max(1.0, current.area) / np.pi))
        max_erode = min(cell_size * 0.28, approx_inradius * 0.65)
        r_erode = max(corner_radius, 0.3 + (max_erode - 0.3) * s_val)

        r_try = r_erode
        eroded = None
        for _ in range(5):
            eroded = current.buffer(-r_try, join_style=2)
            if not eroded.is_empty and eroded.area > 1e-4:
                break
            r_try *= 0.60

        if eroded is not None and not eroded.is_empty and eroded.area > 1e-4:
            if isinstance(eroded, MultiPolygon):
                eroded = max(eroded.geoms, key=lambda g: g.area)

            delta = r_try * 0.25 * s_val
            dilated = eroded.buffer(r_try + delta, join_style=1)
            if isinstance(dilated, MultiPolygon):
                dilated = max(dilated.geoms, key=lambda g: g.area)

            if delta > 1e-4:
                contracted = dilated.buffer(-delta, join_style=1)
                if isinstance(contracted, MultiPolygon):
                    contracted = max(contracted.geoms, key=lambda g: g.area)
            else:
                contracted = dilated

            try:
                clipped = contracted.intersection(current)
                if isinstance(clipped, MultiPolygon):
                    clipped = max(clipped.geoms, key=lambda g: g.area)
                if isinstance(clipped, Polygon) and clipped.area > 1e-4:
                    current = clipped
                else:
                    current = contracted
            except Exception:
                current = contracted

        return current

    elif st in ("metaball", "sdf", "skeleton"):
        # ====================================================
        # METABALL / SDF SKELETON MODE (Log-Sum-Exp Soft-Min 등치선):
        # Continuous C-inf potential field avoiding any stepped notches or inward dents
        # ====================================================
        if not isinstance(current, Polygon) or current.is_empty:
            return current

        cx, cy = current.centroid.x, current.centroid.y
        verts = np.array(current.exterior.coords)
        if len(verts) < 4:
            return current

        a = verts[:-1]
        b = verts[1:]
        edge_vec = b - a
        edge_len = np.hypot(edge_vec[:, 0], edge_vec[:, 1])
        valid_edges = edge_len > 1e-4
        if not np.any(valid_edges):
            return current

        a = a[valid_edges]
        b = b[valid_edges]
        edge_vec = edge_vec[valid_edges]
        edge_len = edge_len[valid_edges]

        tx = edge_vec[:, 0] / edge_len
        ty = edge_vec[:, 1] / edge_len
        nx = -ty
        ny = tx
        dot_c = (cx - a[:, 0]) * nx + (cy - a[:, 1]) * ny
        flip = dot_c < 0
        nx = np.where(flip, -nx, nx)
        ny = np.where(flip, -ny, ny)
        D0 = (cx - a[:, 0]) * nx + (cy - a[:, 1]) * ny

        # Raycast across 64 radial directions
        n_rays = 64
        angles = np.linspace(0, 2.0 * np.pi, n_rays, endpoint=False)
        dx = np.cos(angles)
        dy = np.sin(angles)
        proj = -(dx[:, None] * nx[None, :] + dy[:, None] * ny[None, :])

        # Beta controls softness: higher beta = crisp corners, lower beta = wide organic curves
        # At s_val=0.0 (0% smoothness): beta=2.80 (crisp regular corners)
        # At s_val=1.0 (100% smoothness): beta=0.45 (deeply rounded organic curvature)
        beta = 0.45 + (1.0 - s_val) * 2.35
        target_gap = max(0.05, corner_radius * 0.3)

        r_low = np.zeros(n_rays)
        r_high = np.full(n_rays, max(cell_size * 2.0, 50.0))

        for _ in range(12):
            r_mid = 0.5 * (r_low + r_high)
            D_vals = D0[None, :] - r_mid[:, None] * proj
            max_neg = np.max(-beta * D_vals, axis=1, keepdims=True)
            lse = max_neg.squeeze() + np.log(np.sum(np.exp(-beta * D_vals - max_neg), axis=1))
            soft_min = -lse / beta
            too_small = soft_min > target_gap
            r_low = np.where(too_small, r_mid, r_low)
            r_high = np.where(too_small, r_high, r_mid)

        pts = np.column_stack([cx + r_low * dx, cy + r_low * dy])
        pts = np.vstack([pts, pts[0]])
        try:
            res_poly = Polygon(pts)
            if not res_poly.is_valid:
                res_poly = shapely.make_valid(res_poly)
                if isinstance(res_poly, MultiPolygon):
                    res_poly = max(res_poly.geoms, key=lambda g: g.area)
            if isinstance(res_poly, Polygon) and res_poly.area > 1e-4:
                # Chaikin pass to eliminate discrete angular sampling facets
                ring_pts = resample_ring(res_poly.exterior, num_points=36)
                for _ in range(2):
                    ring_pts = chaikin_pass(ring_pts, alpha=0.15)
                smooth_coords = ring_pts.tolist()
                smooth_coords.append(smooth_coords[0])
                current = Polygon(smooth_coords)
        except Exception:
            pass

        return current

    else:
        # ====================================================
        # PEBBLE MODE (조약돌형 - Default):
        # Morphological round closing + Chaikin organic cellular contours
        # ====================================================
        approx_inradius = max(0.5, np.sqrt(max(1.0, current.area) / np.pi))
        max_radius = min(cell_size * 0.35, approx_inradius * 0.85)

        r_smooth = max_radius * s_val if s_val > 0.001 else 0.0
        effective_r = max(corner_radius, r_smooth)

        if effective_r > 1e-4:
            r_try = effective_r
            for _ in range(3):
                eroded = current.buffer(-r_try, join_style=1)
                if not eroded.is_empty and eroded.area > 1e-4:
                    break
                r_try *= 0.5

            if not eroded.is_empty and eroded.area > 1e-4:
                if isinstance(eroded, MultiPolygon):
                    eroded = max(eroded.geoms, key=lambda g: g.area)
                dilated = eroded.buffer(r_try, join_style=1)
                if isinstance(dilated, MultiPolygon):
                    dilated = max(dilated.geoms, key=lambda g: g.area)
                current = dilated

        if s_val > 0.01 and isinstance(current, Polygon) and not current.is_empty:
            pts = resample_ring(current.exterior, num_points=36)
            alpha = 0.15 * s_val
            for _ in range(2):
                pts = chaikin_pass(pts, alpha=alpha)
            coords = pts.tolist()
            coords.append(coords[0])
            try:
                smoothed = Polygon(coords)
                if not smoothed.is_valid:
                    smoothed = shapely.make_valid(smoothed)
                    if isinstance(smoothed, MultiPolygon):
                        smoothed = max(smoothed.geoms, key=lambda g: g.area)
                if isinstance(smoothed, Polygon) and smoothed.area > 1e-4:
                    current = smoothed
            except Exception:
                pass

        return current


def generate_seed_points(
    boundary_polygon: Polygon,
    n_points: int = 50,
    cell_size: float = 0.0,
    density: float = 0.0,
    seed: int = 42,
    jitter: float = 0.5,
    lloyd_iterations: int = 0,
    rotation: float = 0.0
) -> List[List[float]]:
    """
    Generate grid-based seed points with jitter control and optional Lloyd's relaxation.
    
    Args:
        boundary_polygon: Shapely Polygon boundary.
        n_points: Approximate number of points (used if cell_size <= 0 and density <= 0).
        cell_size: Approximate cell diameter in mm (highest priority).
        density: Points per cm² (used if cell_size <= 0).
        seed: Random seed for deterministic generation.
        jitter: 0.0 (perfect grid) to 1.0 (maximum jitter).
        lloyd_iterations: Number of Lloyd's relaxation iterations (0 = disabled).
        rotation: Degrees to rotate points around boundary centroid.
        
    Returns:
        List of [x, y] coordinates.
    """
    minx, miny, maxx, maxy = boundary_polygon.bounds
    width = max(1e-3, maxx - minx)
    height = max(1e-3, maxy - miny)
    poly_area = boundary_polygon.area
    bbox_area = width * height

    # 1. cell_size has highest priority
    if cell_size > 0:
        area_per_cell = 0.866025 * (cell_size ** 2)
        n_points = max(4, int(round(poly_area / max(1e-4, area_per_cell))))
        dx = max(1.0, cell_size)
        dy = max(1.0, cell_size * 0.866025)
        nx = max(2, int(round(width / dx)) + 2)
        ny = max(2, int(round(height / dy)) + 2)
    # 2. density (points per cm²)
    elif density > 0:
        area_cm2 = poly_area / 100.0
        n_points = max(4, int(round(area_cm2 * density)))
        area_ratio = bbox_area / max(1e-4, poly_area)
        est_box_pts = max(n_points, int(n_points * area_ratio * 1.35))
        aspect = max(0.05, width / height)
        nx = max(2, int(round(math.sqrt(est_box_pts * aspect))))
        ny = max(2, int(round(math.sqrt(est_box_pts / aspect))))
        dx = width / nx
        dy = height / ny
    # 3. fallback to n_points
    else:
        n_points = max(4, n_points)
        area_ratio = bbox_area / max(1e-4, poly_area)
        est_box_pts = max(n_points, int(n_points * area_ratio * 1.35))
        aspect = max(0.05, width / height)
        nx = max(2, int(round(math.sqrt(est_box_pts * aspect))))
        ny = max(2, int(round(math.sqrt(est_box_pts / aspect))))
        dx = width / nx
        dy = height / ny

    jitter = max(0.0, min(1.0, jitter))
    rng = np.random.default_rng(seed)

    cx, cy = boundary_polygon.centroid.x, boundary_polygon.centroid.y

    candidate_points: List[Tuple[float, float]] = []
    for i in range(nx):
        for j in range(ny):
            gx = minx + (i + 0.5) * dx
            gy = miny + (j + 0.5) * dy
            if jitter > 0:
                jx = rng.uniform(-0.5, 0.5) * dx * jitter
                jy = rng.uniform(-0.5, 0.5) * dy * jitter
                px, py = gx + jx, gy + jy
            else:
                px, py = gx, gy

            # Apply rotation around centroid
            rx, ry = rotate_point(px, py, cx, cy, rotation)
            candidate_points.append((rx, ry))

    # Keep points that fall inside or very close to boundary
    inside_points = [
        pt for pt in candidate_points
        if boundary_polygon.contains(Point(pt[0], pt[1])) or boundary_polygon.distance(Point(pt[0], pt[1])) < 1e-3
    ]

    # Adjust point count to be close to n_points
    if len(inside_points) > n_points:
        # Deterministically sample n_points
        indices = rng.choice(len(inside_points), size=n_points, replace=False)
        selected = [inside_points[i] for i in sorted(indices)]
    elif len(inside_points) < n_points:
        selected = list(inside_points)
        # Rejection sampling to fill up to n_points
        attempts = 0
        while len(selected) < n_points and attempts < n_points * 200:
            attempts += 1
            rand_x = rng.uniform(minx, maxx)
            rand_y = rng.uniform(miny, maxy)
            rx, ry = rotate_point(rand_x, rand_y, cx, cy, rotation)
            if boundary_polygon.contains(Point(rx, ry)):
                selected.append((rx, ry))
    else:
        selected = inside_points

    # Guarantee at least 4 valid points
    if len(selected) < 4:
        # Fallback to centroid and cross points
        selected = [
            (cx, cy),
            (cx + width * 0.15, cy),
            (cx, cy + height * 0.15),
            (cx - width * 0.15, cy - height * 0.15)
        ]

    result = [[round(p[0], 4), round(p[1], 4)] for p in selected]
    
    # Lloyd's Relaxation: iteratively move each seed to the centroid of its Voronoi cell
    if lloyd_iterations > 0 and len(result) >= 3:
        from scipy.spatial import Voronoi as ScipyVoronoi
        for _iter in range(lloyd_iterations):
            pts_arr = np.array(result, dtype=np.float64)
            minx, miny, maxx, maxy = boundary_polygon.bounds
            margin = max((maxx - minx), (maxy - miny)) * 0.5
            # Add ghost points for boundary
            ghost = []
            for x, y in pts_arr:
                ghost.append([2*(minx - margin) - x, y])
                ghost.append([2*(maxx + margin) - x, y])
                ghost.append([x, 2*(miny - margin) - y])
                ghost.append([x, 2*(maxy + margin) - y])
            all_vor_pts = np.vstack([pts_arr, np.array(ghost, dtype=np.float64)])
            try:
                vor = ScipyVoronoi(all_vor_pts)
            except Exception:
                break
            new_pts = []
            for i in range(len(pts_arr)):
                region_idx = vor.point_region[i]
                region = vor.regions[region_idx]
                if not region or -1 in region:
                    new_pts.append(list(pts_arr[i]))
                    continue
                verts = vor.vertices[region]
                cell_poly = Polygon(verts)
                try:
                    clipped = cell_poly.intersection(boundary_polygon)
                    if not clipped.is_empty and clipped.area > 1e-6:
                        c = clipped.centroid
                        new_pts.append([c.x, c.y])
                    else:
                        new_pts.append(list(pts_arr[i]))
                except Exception:
                    new_pts.append(list(pts_arr[i]))
            result = [[round(p[0], 4), round(p[1], 4)] for p in new_pts]
    
    return result


def generate_voronoi_pattern(
    boundary_polygon: Polygon,
    params: dict,
    seamless: bool = False
) -> Tuple[List[Dict[str, Any]], List[List[float]]]:
    """
    Generate Voronoi pattern with mirror/ghost points or 3x3 periodic grid for seamless tiling.
    """
    n_points = int(params.get("n_points", 50))
    cell_size = float(params.get("cell_size", 0.0))
    seed = int(params.get("seed", 42))
    jitter = float(params.get("jitter", 0.5))
    density = float(params.get("density", 0.0))
    lloyd_iterations = int(params.get("lloyd_iterations", 0))
    rotation = float(params.get("rotation", 0.0))
    boundary_offset = float(params.get("boundary_offset", 0.0))
    cell_gap = float(params.get("cell_gap", 0.0))
    corner_radius = float(params.get("corner_radius", 0.0))
    smoothness = float(params.get("smoothness", 0.0))
    if smoothness > 1.0:
        smoothness = smoothness / 100.0
    cell_style = str(params.get("cell_style", "line")).lower()
    spline_type = str(params.get("spline_type", "pebble")).lower()
    seamless = seamless or bool(params.get("seamless", False))

    # Apply boundary_offset
    effective_boundary = boundary_polygon
    if abs(boundary_offset) > 1e-4:
        # Positive offset insets the boundary
        buffered = boundary_polygon.buffer(-boundary_offset)
        if buffered.is_empty or buffered.area <= 1e-4:
            return ([], [])
        if isinstance(buffered, MultiPolygon):
            effective_boundary = max(buffered.geoms, key=lambda p: p.area)
        else:
            effective_boundary = buffered

    # Seed points override or generate
    seed_override = params.get("seed_points")
    if seed_override and len(seed_override) >= 3:
        seed_points = [[float(p[0]), float(p[1])] for p in seed_override]
    else:
        seed_points = generate_seed_points(
            effective_boundary,
            n_points=n_points,
            cell_size=cell_size,
            density=density,
            seed=seed,
            jitter=jitter,
            lloyd_iterations=lloyd_iterations,
            rotation=rotation
        )

    if len(seed_points) < 3:
        return ([], seed_points)

    pts = np.array(seed_points, dtype=np.float64)
    minx, miny, maxx, maxy = effective_boundary.bounds

    if seamless:
        W = max(maxx - minx, 1e-3)
        H = max(maxy - miny, 1e-3)
        # True periodic tiling: replicate points into 3x3 tile grid
        tiled_pts = []
        for dx_tile in [-W, 0, W]:
            for dy_tile in [-H, 0, H]:
                if dx_tile == 0 and dy_tile == 0:
                    continue
                for x, y in pts:
                    tiled_pts.append([x + dx_tile, y + dy_tile])
        all_pts = np.vstack([pts, np.array(tiled_pts, dtype=np.float64)])
    else:
        margin_x = max((maxx - minx) * 0.25, 10.0)
        margin_y = max((maxy - miny) * 0.25, 10.0)

        b_left = minx - margin_x
        b_right = maxx + margin_x
        b_bottom = miny - margin_y
        b_top = maxy + margin_y

        # Generate mirror/ghost points to bound the Voronoi cells of all interior points
        ghost_pts = []
        for x, y in pts:
            ghost_pts.append([2.0 * b_left - x, y])
            ghost_pts.append([2.0 * b_right - x, y])
            ghost_pts.append([x, 2.0 * b_bottom - y])
            ghost_pts.append([x, 2.0 * b_top - y])
            ghost_pts.append([2.0 * b_left - x, 2.0 * b_bottom - y])
            ghost_pts.append([2.0 * b_right - x, 2.0 * b_top - y])
            ghost_pts.append([2.0 * b_left - x, 2.0 * b_top - y])
            ghost_pts.append([2.0 * b_right - x, 2.0 * b_bottom - y])

        all_pts = np.vstack([pts, np.array(ghost_pts, dtype=np.float64)])

    try:
        vor = Voronoi(all_pts)
    except Exception:
        jittered = all_pts + np.random.default_rng(seed).normal(0, 1e-4, size=all_pts.shape)
        vor = Voronoi(jittered)

    cells: List[Dict[str, Any]] = []

    # In seamless mode, process ALL points (center + 8 neighboring tiles)
    # because neighbor cells penetrate into effective_boundary to close seams!
    points_to_process = range(len(all_pts)) if seamless else range(len(pts))

    for idx in points_to_process:
        seed_idx = idx % len(pts)
        seed_pt = [round(float(pts[seed_idx, 0]), 4), round(float(pts[seed_idx, 1]), 4)]
        region_idx = vor.point_region[idx]
        region = vor.regions[region_idx]

        if not region or -1 in region:
            continue

        poly_coords = vor.vertices[region]
        if len(poly_coords) < 3:
            continue

        raw_cell = Polygon(poly_coords)
        if not raw_cell.is_valid:
            raw_cell = shapely.make_valid(raw_cell)
            if not isinstance(raw_cell, Polygon):
                continue

        # Quick rejection: does it intersect effective_boundary?
        if not raw_cell.intersects(effective_boundary):
            continue

        processed_coords_list = post_process_polygon(
            raw_cell,
            effective_boundary,
            cell_gap=cell_gap,
            corner_radius=corner_radius,
            is_seamless=seamless,
            smoothness=smoothness,
            cell_size=cell_size,
            cell_style=cell_style,
            spline_type=spline_type
        )

        for coords in processed_coords_list:
            cells.append({
                "coords": coords,
                "seed_idx": seed_idx,
                "seed_point": seed_pt
            })

    return (cells, seed_points)


def generate_hexagonal_pattern(
    boundary_polygon: Polygon,
    params: dict
) -> Tuple[List[Dict[str, Any]], List[List[float]]]:
    """
    Generate Hexagonal grid pattern clipped to boundary.
    """
    rotation = float(params.get("rotation", 0.0))
    boundary_offset = float(params.get("boundary_offset", 0.0))
    cell_gap = float(params.get("cell_gap", 0.0))
    corner_radius = float(params.get("corner_radius", 0.0))
    smoothness = float(params.get("smoothness", 0.0))
    if smoothness > 1.0:
        smoothness = smoothness / 100.0
    cell_style = str(params.get("cell_style", "line")).lower()
    spline_type = str(params.get("spline_type", "pebble")).lower()
    n_points = int(params.get("n_points", 50))

    density = float(params.get("density", 0.0))
    if density > 0 and boundary_offset == 0:
        area_cm2 = boundary_polygon.area / 100.0
        n_points = max(4, int(round(area_cm2 * density)))
        area_per_cell = (100.0 / max(density, 1e-6))
        r_hex_from_density = math.sqrt(area_per_cell / (1.5 * math.sqrt(3)))
        if params.get("cell_size", 0) <= 0:
            params = dict(params)
            params["cell_size"] = max(2.0, 2.0 * r_hex_from_density)

    effective_boundary = boundary_polygon
    if abs(boundary_offset) > 1e-4:
        buffered = boundary_polygon.buffer(-boundary_offset)
        if buffered.is_empty or buffered.area <= 1e-4:
            return ([], [])
        effective_boundary = max(buffered.geoms, key=lambda p: p.area) if isinstance(buffered, MultiPolygon) else buffered

    # Cell size calculation
    cell_size = float(params.get("cell_size", 0.0))
    if cell_size <= 1e-3:
        area_per_hex = effective_boundary.area / max(1, n_points)
        r_hex = math.sqrt(area_per_hex / (1.5 * math.sqrt(3)))
        cell_size = max(2.0, 2.0 * r_hex)
    else:
        r_hex = cell_size / 2.0

    r_hex = max(0.5, r_hex)
    w_hex = math.sqrt(3) * r_hex
    h_step = 1.5 * r_hex

    offset_x = float(params.get("pattern_offset_x", 0.0))
    offset_y = float(params.get("pattern_offset_y", 0.0))

    minx, miny, maxx, maxy = effective_boundary.bounds
    cx, cy = effective_boundary.centroid.x, effective_boundary.centroid.y
    W = maxx - minx
    H = maxy - miny

    seamless = bool(params.get("seamless", False))
    if seamless and W > 1e-3 and H > 1e-3:
        # Periodic quantization for regular Hexagonal grid (pointy-topped)
        # Finds optimal (nx, ny) to minimize aspect ratio distortion while keeping cell size near target
        R_target = max(1.0, cell_size / 2.0)
        nx_base = max(1, int(round(W / (math.sqrt(3) * R_target))))
        ny_base = max(1, int(round(H / (3.0 * R_target))))

        candidates = []
        for nx_cand in range(max(1, nx_base - 3), nx_base + 4):
            for ny_cand in range(max(1, ny_base - 3), ny_base + 4):
                Rx_cand = W / (nx_cand * math.sqrt(3))
                Ry_cand = H / (3.0 * ny_cand)
                R_avg = (Rx_cand + Ry_cand) / 2.0
                distortion = abs(Rx_cand - Ry_cand) / R_avg
                size_error = abs(2.0 * R_avg - cell_size) / max(1.0, cell_size)
                # Heavily penalize distortion to preserve regular hexagon proportions
                score = distortion * 5.0 + size_error
                candidates.append((score, nx_cand, ny_cand, Rx_cand, Ry_cand, R_avg))

        candidates.sort(key=lambda c: c[0])
        _, nx, ny, Rx, Ry, R_avg = candidates[0]

        w_hex = W / nx
        h_step = H / (2 * ny)
        adapted_cell_size = round(2.0 * R_avg, 2)
        params["adapted_cell_size"] = adapted_cell_size

        j_min = int(math.floor(-offset_y / h_step)) - 2
        j_max = 2 * ny + int(math.ceil(-offset_y / h_step)) + 2
        i_min = int(math.floor(-offset_x / w_hex)) - 2
        i_max = nx + int(math.ceil(-offset_x / w_hex)) + 2

        cells: List[Dict[str, Any]] = []
        seed_points: List[List[float]] = []
        seed_idx = 0

        for j in range(j_min, j_max + 1):
            y = miny + j * h_step + offset_y
            x_offset = (w_hex / 2.0) if (j % 2 == 1) else 0.0
            for i in range(i_min, i_max + 1):
                x = minx + i * w_hex + x_offset + offset_x
                center_x, center_y = rotate_point(x, y, cx, cy, rotation)

                hex_verts = []
                for k in range(6):
                    angle = math.pi / 6.0 + k * math.pi / 3.0
                    vx = x + Rx * math.cos(angle)
                    vy = y + Ry * math.sin(angle)
                    rvx, rvy = rotate_point(vx, vy, cx, cy, rotation)
                    hex_verts.append((rvx, rvy))

                hex_poly = Polygon(hex_verts)
                if not hex_poly.intersects(effective_boundary):
                    continue

                processed = post_process_polygon(
                    hex_poly,
                    effective_boundary,
                    cell_gap=cell_gap,
                    corner_radius=corner_radius,
                    is_seamless=True,
                    smoothness=smoothness,
                    cell_size=cell_size,
                    cell_style=cell_style,
                    spline_type=spline_type
                )
                if processed:
                    seed_pt = [round(center_x, 4), round(center_y, 4)]
                    seed_points.append(seed_pt)
                    for coords in processed:
                        cells.append({
                            "coords": coords,
                            "seed_idx": seed_idx,
                            "seed_point": seed_pt
                        })
                    seed_idx += 1

        return (cells, seed_points)

    diag = math.hypot(maxx - minx, maxy - miny) + r_hex * 4

    j_min = int(math.floor((cy - diag - offset_y) / h_step))
    j_max = int(math.ceil((cy + diag - offset_y) / h_step))
    i_min = int(math.floor((cx - diag - offset_x) / w_hex))
    i_max = int(math.ceil((cx + diag - offset_x) / w_hex))

    cells: List[Dict[str, Any]] = []
    seed_points: List[List[float]] = []
    seed_idx = 0

    for j in range(j_min, j_max + 1):
        y = j * h_step + offset_y
        x_offset = (w_hex / 2.0) if (j % 2 == 1) else 0.0
        for i in range(i_min, i_max + 1):
            x = i * w_hex + x_offset + offset_x
            center_x, center_y = rotate_point(x, y, cx, cy, rotation)

            # Hexagon vertices (pointy-topped)
            hex_verts = []
            for k in range(6):
                angle = math.pi / 6.0 + k * math.pi / 3.0
                vx = x + r_hex * math.cos(angle)
                vy = y + r_hex * math.sin(angle)
                rvx, rvy = rotate_point(vx, vy, cx, cy, rotation)
                hex_verts.append((rvx, rvy))

            hex_poly = Polygon(hex_verts)
            if not hex_poly.intersects(effective_boundary):
                continue

            processed = post_process_polygon(
                hex_poly,
                effective_boundary,
                cell_gap=cell_gap,
                corner_radius=corner_radius,
                is_seamless=False,
                smoothness=smoothness,
                cell_size=cell_size,
                cell_style=cell_style,
                spline_type=spline_type
            )
            if processed:
                seed_pt = [round(center_x, 4), round(center_y, 4)]
                seed_points.append(seed_pt)
                for coords in processed:
                    cells.append({
                        "coords": coords,
                        "seed_idx": seed_idx,
                        "seed_point": seed_pt
                    })
                seed_idx += 1

    return (cells, seed_points)


def generate_triangular_pattern(
    boundary_polygon: Polygon,
    params: dict
) -> Tuple[List[Dict[str, Any]], List[List[float]]]:
    """
    Generate Triangular grid pattern clipped to boundary.
    """
    rotation = float(params.get("rotation", 0.0))
    boundary_offset = float(params.get("boundary_offset", 0.0))
    cell_gap = float(params.get("cell_gap", 0.0))
    corner_radius = float(params.get("corner_radius", 0.0))
    smoothness = float(params.get("smoothness", 0.0))
    if smoothness > 1.0:
        smoothness = smoothness / 100.0
    cell_style = str(params.get("cell_style", "line")).lower()
    spline_type = str(params.get("spline_type", "pebble")).lower()
    n_points = int(params.get("n_points", 50))

    density = float(params.get("density", 0.0))
    if density > 0 and boundary_offset == 0:
        area_cm2 = boundary_polygon.area / 100.0
        n_points = max(4, int(round(area_cm2 * density)))

    effective_boundary = boundary_polygon
    if abs(boundary_offset) > 1e-4:
        buffered = boundary_polygon.buffer(-boundary_offset)
        if buffered.is_empty or buffered.area <= 1e-4:
            return ([], [])
        effective_boundary = max(buffered.geoms, key=lambda p: p.area) if isinstance(buffered, MultiPolygon) else buffered

    cell_size = float(params.get("cell_size", 0.0))
    if cell_size <= 1e-3:
        tri_area = effective_boundary.area / max(1, n_points)
        cell_size = max(2.0, math.sqrt(tri_area / (math.sqrt(3) / 4.0)))

    s = max(1.0, cell_size)
    h = s * math.sqrt(3) / 2.0

    offset_x = float(params.get("pattern_offset_x", 0.0))
    offset_y = float(params.get("pattern_offset_y", 0.0))

    minx, miny, maxx, maxy = effective_boundary.bounds
    cx, cy = effective_boundary.centroid.x, effective_boundary.centroid.y
    W = maxx - minx
    H = maxy - miny

    seamless = bool(params.get("seamless", False))
    if seamless and W > 1e-3 and H > 1e-3:
        # Periodic quantization for regular Triangular grid
        # Finds optimal (nx, ny) to preserve equilateral triangle proportions
        nx_base = max(1, int(round(W / max(1.0, cell_size))))
        ny_base = max(1, int(round(H / (math.sqrt(3) * max(1.0, cell_size)))))

        candidates = []
        for nx_cand in range(max(1, nx_base - 3), nx_base + 4):
            for ny_cand in range(max(1, ny_base - 3), ny_base + 4):
                sx_cand = W / nx_cand
                sy_cand = H / (ny_cand * math.sqrt(3))
                s_avg = (sx_cand + sy_cand) / 2.0
                distortion = abs(sx_cand - sy_cand) / s_avg
                size_error = abs(s_avg - cell_size) / max(1.0, cell_size)
                score = distortion * 5.0 + size_error
                candidates.append((score, nx_cand, ny_cand, sx_cand, sy_cand, s_avg))

        candidates.sort(key=lambda c: c[0])
        _, nx, ny, sx_best, sy_best, s_avg = candidates[0]

        s = W / nx
        h = H / (2 * ny)
        adapted_cell_size = round(s_avg, 2)
        params["adapted_cell_size"] = adapted_cell_size

        j_min = int(math.floor(-offset_y / h)) - 2
        j_max = 2 * ny + int(math.ceil(-offset_y / h)) + 2
        i_min = int(math.floor(-offset_x / s)) - 2
        i_max = nx + int(math.ceil(-offset_x / s)) + 2

        cells: List[Dict[str, Any]] = []
        seed_points: List[List[float]] = []
        seed_idx = 0

        for j in range(j_min, j_max + 1):
            base_y = miny + j * h + offset_y
            row_offset = (s / 2.0) if (j % 2 == 1) else 0.0

            for i in range(i_min, i_max + 1):
                base_x = minx + i * s + row_offset + offset_x

                # 1. Upward triangle
                v_up = [
                    (base_x, base_y),
                    (base_x + s, base_y),
                    (base_x + s / 2.0, base_y + h)
                ]
                up_centroid = (
                    (v_up[0][0] + v_up[1][0] + v_up[2][0]) / 3.0,
                    (v_up[0][1] + v_up[1][1] + v_up[2][1]) / 3.0
                )
                v_up_rot = [rotate_point(vx, vy, cx, cy, rotation) for vx, vy in v_up]
                up_poly = Polygon(v_up_rot)

                if up_poly.intersects(effective_boundary):
                    processed = post_process_polygon(
                        up_poly,
                        effective_boundary,
                        cell_gap=cell_gap,
                        corner_radius=corner_radius,
                        is_seamless=True,
                        smoothness=smoothness,
                        cell_size=cell_size,
                        cell_style=cell_style,
                        spline_type=spline_type
                    )
                    if processed:
                        c_rot = rotate_point(up_centroid[0], up_centroid[1], cx, cy, rotation)
                        seed_pt = [round(c_rot[0], 4), round(c_rot[1], 4)]
                        seed_points.append(seed_pt)
                        for coords in processed:
                            cells.append({
                                "coords": coords,
                                "seed_idx": seed_idx,
                                "seed_point": seed_pt
                            })
                        seed_idx += 1

                # 2. Downward triangle
                v_down = [
                    (base_x + s / 2.0, base_y + h),
                    (base_x + 1.5 * s, base_y + h),
                    (base_x + s, base_y)
                ]
                down_centroid = (
                    (v_down[0][0] + v_down[1][0] + v_down[2][0]) / 3.0,
                    (v_down[0][1] + v_down[1][1] + v_down[2][1]) / 3.0
                )
                v_down_rot = [rotate_point(vx, vy, cx, cy, rotation) for vx, vy in v_down]
                down_poly = Polygon(v_down_rot)

                if down_poly.intersects(effective_boundary):
                    processed = post_process_polygon(
                        down_poly,
                        effective_boundary,
                        cell_gap=cell_gap,
                        corner_radius=corner_radius,
                        is_seamless=True,
                        smoothness=smoothness,
                        cell_size=cell_size,
                        cell_style=cell_style,
                        spline_type=spline_type
                    )
                    if processed:
                        c_rot = rotate_point(down_centroid[0], down_centroid[1], cx, cy, rotation)
                        seed_pt = [round(c_rot[0], 4), round(c_rot[1], 4)]
                        seed_points.append(seed_pt)
                        for coords in processed:
                            cells.append({
                                "coords": coords,
                                "seed_idx": seed_idx,
                                "seed_point": seed_pt
                            })
                        seed_idx += 1

        return (cells, seed_points)

    diag = math.hypot(maxx - minx, maxy - miny) + s * 4

    j_min = int(math.floor((cy - diag - offset_y) / h))
    j_max = int(math.ceil((cy + diag - offset_y) / h))
    i_min = int(math.floor((cx - diag - offset_x) / s))
    i_max = int(math.ceil((cx + diag - offset_x) / s))

    cells: List[Dict[str, Any]] = []
    seed_points: List[List[float]] = []
    seed_idx = 0

    for j in range(j_min, j_max + 1):
        base_y = j * h + offset_y
        row_offset = (s / 2.0) if (j % 2 == 1) else 0.0

        for i in range(i_min, i_max + 1):
            base_x = i * s + row_offset + offset_x

            # 1. Upward triangle
            v_up = [
                (base_x, base_y),
                (base_x + s, base_y),
                (base_x + s / 2.0, base_y + h)
            ]
            up_centroid = (
                (v_up[0][0] + v_up[1][0] + v_up[2][0]) / 3.0,
                (v_up[0][1] + v_up[1][1] + v_up[2][1]) / 3.0
            )
            v_up_rot = [rotate_point(vx, vy, cx, cy, rotation) for vx, vy in v_up]
            up_poly = Polygon(v_up_rot)

            if up_poly.intersects(effective_boundary):
                processed = post_process_polygon(
                    up_poly,
                    effective_boundary,
                    cell_gap=cell_gap,
                    corner_radius=corner_radius,
                    is_seamless=False,
                    smoothness=smoothness,
                    cell_size=cell_size,
                    cell_style=cell_style,
                    spline_type=spline_type
                )
                if processed:
                    c_rot = rotate_point(up_centroid[0], up_centroid[1], cx, cy, rotation)
                    seed_pt = [round(c_rot[0], 4), round(c_rot[1], 4)]
                    seed_points.append(seed_pt)
                    for coords in processed:
                        cells.append({
                            "coords": coords,
                            "seed_idx": seed_idx,
                            "seed_point": seed_pt
                        })
                    seed_idx += 1

            # 2. Downward triangle
            v_down = [
                (base_x + s / 2.0, base_y + h),
                (base_x + 1.5 * s, base_y + h),
                (base_x + s, base_y)
            ]
            down_centroid = (
                (v_down[0][0] + v_down[1][0] + v_down[2][0]) / 3.0,
                (v_down[0][1] + v_down[1][1] + v_down[2][1]) / 3.0
            )
            v_down_rot = [rotate_point(vx, vy, cx, cy, rotation) for vx, vy in v_down]
            down_poly = Polygon(v_down_rot)

            if down_poly.intersects(effective_boundary):
                processed = post_process_polygon(
                    down_poly,
                    effective_boundary,
                    cell_gap=cell_gap,
                    corner_radius=corner_radius,
                    is_seamless=False,
                    smoothness=smoothness,
                    cell_size=cell_size,
                    cell_style=cell_style,
                    spline_type=spline_type
                )
                if processed:
                    c_rot = rotate_point(down_centroid[0], down_centroid[1], cx, cy, rotation)
                    seed_pt = [round(c_rot[0], 4), round(c_rot[1], 4)]
                    seed_points.append(seed_pt)
                    for coords in processed:
                        cells.append({
                            "coords": coords,
                            "seed_idx": seed_idx,
                            "seed_point": seed_pt
                        })
                    seed_idx += 1

    return (cells, seed_points)


def generate_square_pattern(
    boundary_polygon: Polygon,
    params: dict
) -> Tuple[List[Dict[str, Any]], List[List[float]]]:
    """
    Generate Square grid pattern clipped to boundary.
    """
    rotation = float(params.get("rotation", 0.0))
    boundary_offset = float(params.get("boundary_offset", 0.0))
    cell_gap = float(params.get("cell_gap", 0.0))
    corner_radius = float(params.get("corner_radius", 0.0))
    smoothness = float(params.get("smoothness", 0.0))
    if smoothness > 1.0:
        smoothness = smoothness / 100.0
    cell_style = str(params.get("cell_style", "line")).lower()
    spline_type = str(params.get("spline_type", "pebble")).lower()
    n_points = int(params.get("n_points", 50))

    density = float(params.get("density", 0.0))
    if density > 0 and boundary_offset == 0:
        area_cm2 = boundary_polygon.area / 100.0
        n_points = max(4, int(round(area_cm2 * density)))

    effective_boundary = boundary_polygon
    if abs(boundary_offset) > 1e-4:
        buffered = boundary_polygon.buffer(-boundary_offset)
        if buffered.is_empty or buffered.area <= 1e-4:
            return ([], [])
        effective_boundary = max(buffered.geoms, key=lambda p: p.area) if isinstance(buffered, MultiPolygon) else buffered

    cell_size = float(params.get("cell_size", 0.0))
    if cell_size <= 1e-3:
        sq_area = effective_boundary.area / max(1, n_points)
        cell_size = max(2.0, math.sqrt(sq_area))

    s = max(1.0, cell_size)

    minx, miny, maxx, maxy = effective_boundary.bounds
    cx, cy = effective_boundary.centroid.x, effective_boundary.centroid.y
    W = maxx - minx
    H = maxy - miny

    offset_x = float(params.get("pattern_offset_x", 0.0))
    offset_y = float(params.get("pattern_offset_y", 0.0))

    seamless = bool(params.get("seamless", False))
    if seamless and W > 1e-3 and H > 1e-3:
        if abs(W - H) < 1e-3:
            # Equilateral square boundary: strictly equal width & height (0% distortion)
            nx = max(1, int(round(W / max(1.0, cell_size))))
            ny = nx
            sx = W / nx
            sy = sx
            s_avg = sx
        else:
            # Rectangular boundary: find (nx, ny) to keep cells as close to square as possible
            nx_base = max(1, int(round(W / max(1.0, cell_size))))
            ny_base = max(1, int(round(H / max(1.0, cell_size))))
            candidates = []
            for nx_c in range(max(1, nx_base - 3), nx_base + 4):
                for ny_c in range(max(1, ny_base - 3), ny_base + 4):
                    sx_c = W / nx_c
                    sy_c = H / ny_c
                    s_avg_c = (sx_c + sy_c) / 2.0
                    distortion = abs(sx_c - sy_c) / s_avg_c
                    size_error = abs(s_avg_c - cell_size) / max(1.0, cell_size)
                    score = distortion * 5.0 + size_error
                    candidates.append((score, nx_c, ny_c, sx_c, sy_c, s_avg_c))
            candidates.sort(key=lambda c: c[0])
            _, nx, ny, sx, sy, s_avg = candidates[0]

        adapted_cell_size = round(s_avg, 2)
        params["adapted_cell_size"] = adapted_cell_size

        j_min = int(math.floor(-offset_y / sy)) - 2
        j_max = ny + int(math.ceil(-offset_y / sy)) + 2
        i_min = int(math.floor(-offset_x / sx)) - 2
        i_max = nx + int(math.ceil(-offset_x / sx)) + 2

        cells: List[Dict[str, Any]] = []
        seed_points: List[List[float]] = []
        seed_idx = 0

        for j in range(j_min, j_max + 1):
            base_y = miny + j * sy + offset_y
            for i in range(i_min, i_max + 1):
                base_x = minx + i * sx + offset_x
                center_x = base_x + sx / 2.0
                center_y = base_y + sy / 2.0

                sq_verts = [
                    (base_x, base_y),
                    (base_x + sx, base_y),
                    (base_x + sx, base_y + sy),
                    (base_x, base_y + sy)
                ]
                sq_rot = [rotate_point(vx, vy, cx, cy, rotation) for vx, vy in sq_verts]
                sq_poly = Polygon(sq_rot)

                if not sq_poly.intersects(effective_boundary):
                    continue

                processed = post_process_polygon(
                    sq_poly,
                    effective_boundary,
                    cell_gap=cell_gap,
                    corner_radius=corner_radius,
                    is_seamless=True,
                    smoothness=smoothness,
                    cell_size=cell_size,
                    cell_style=cell_style,
                    spline_type=spline_type
                )
                if processed:
                    c_rot = rotate_point(center_x, center_y, cx, cy, rotation)
                    seed_pt = [round(c_rot[0], 4), round(c_rot[1], 4)]
                    seed_points.append(seed_pt)
                    for coords in processed:
                        cells.append({
                            "coords": coords,
                            "seed_idx": seed_idx,
                            "seed_point": seed_pt
                        })
                    seed_idx += 1

        return (cells, seed_points)

    diag = math.hypot(maxx - minx, maxy - miny) + s * 4

    offset_x = float(params.get("pattern_offset_x", 0.0))
    offset_y = float(params.get("pattern_offset_y", 0.0))

    j_min = int(math.floor((cy - diag - offset_y) / s))
    j_max = int(math.ceil((cy + diag - offset_y) / s))
    i_min = int(math.floor((cx - diag - offset_x) / s))
    i_max = int(math.ceil((cx + diag - offset_x) / s))

    cells: List[Dict[str, Any]] = []
    seed_points: List[List[float]] = []
    seed_idx = 0

    for j in range(j_min, j_max + 1):
        base_y = j * s + offset_y
        for i in range(i_min, i_max + 1):
            base_x = i * s + offset_x
            center_x = base_x + s / 2.0
            center_y = base_y + s / 2.0

            sq_verts = [
                (base_x, base_y),
                (base_x + s, base_y),
                (base_x + s, base_y + s),
                (base_x, base_y + s)
            ]
            sq_rot = [rotate_point(vx, vy, cx, cy, rotation) for vx, vy in sq_verts]
            sq_poly = Polygon(sq_rot)

            if not sq_poly.intersects(effective_boundary):
                continue

            processed = post_process_polygon(
                sq_poly,
                effective_boundary,
                cell_gap=cell_gap,
                corner_radius=corner_radius,
                is_seamless=False,
                smoothness=smoothness,
                cell_size=cell_size,
                cell_style=cell_style,
                spline_type=spline_type
            )
            if processed:
                c_rot = rotate_point(center_x, center_y, cx, cy, rotation)
                seed_pt = [round(c_rot[0], 4), round(c_rot[1], 4)]
                seed_points.append(seed_pt)
                for coords in processed:
                    cells.append({
                        "coords": coords,
                        "seed_idx": seed_idx,
                        "seed_point": seed_pt
                    })
                seed_idx += 1

    return (cells, seed_points)


def generate_pattern(
    boundary_polygon: Union[Polygon, dict, list, Any],
    params: Optional[dict] = None,
    seamless: bool = False
) -> Tuple[List[Dict[str, Any]], List[List[float]]]:
    """
    Main dispatch function for pattern generation.
    
    Args:
        boundary_polygon: Shapely Polygon, region dict, or list of coordinates.
        params: Dictionary of generator parameters:
            - n_points (int)
            - density (float, points per cm²)
            - seed (int)
            - jitter (float 0-1)
            - lloyd_iterations (int)
            - rotation (degrees)
            - boundary_offset (mm)
            - cell_gap (mm)
            - corner_radius (mm)
            - pattern_type ('voronoi', 'hexagonal', 'triangular', 'square')
            - seed_points (optional list of [x, y])
            - cell_size (optional float for grid patterns)
            - seamless (bool)
        seamless: Enable seamless periodic boundary wrapping.
            
    Returns:
        (cells, seed_points) tuple where:
            cells = [{'coords': [[x,y],...], 'seed_idx': int, 'seed_point': [x,y]}]
            seed_points = [[x,y], ...]
    """
    if params is None:
        params = {}

    seamless = seamless or bool(params.get("seamless", False))
    params["seamless"] = seamless

    try:
        poly = to_shapely_polygon(boundary_polygon)
    except Exception as e:
        raise ValueError(f"Invalid boundary polygon: {str(e)}") from e

    pattern_type = str(params.get("pattern_type", "voronoi")).lower().strip()

    if pattern_type in ("hexagonal", "hex", "hexagon"):
        return generate_hexagonal_pattern(poly, params)
    elif pattern_type in ("triangular", "triangle", "tri"):
        return generate_triangular_pattern(poly, params)
    elif pattern_type in ("square", "grid"):
        return generate_square_pattern(poly, params)
    else:
        # Default: Voronoi
        return generate_voronoi_pattern(poly, params, seamless=seamless)
