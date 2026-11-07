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
    smoothness: float = 0.0
) -> List[List[List[float]]]:
    """
    Process polygon: clip against boundary, apply cell_gap, corner_radius, and organic smoothness.
    
    In seamless mode:
      Applies cell_gap, corner_radius, and smoothness before clipping against boundary.
      This leaves clean open seams along boundary edges that match the opposite side!
    
    In standard mode:
      Clips to boundary first, then insets by cell_gap/2, fillets corners, and applies smoothness.
    """
    if poly.is_empty or poly.area <= 1e-6:
        return []

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
            else:
                return []

        if smoothness > 1e-3:
            current = chaikin_smooth_polygon(current, smoothness=smoothness)

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
                if eroded.is_empty or eroded.area <= 1e-4:
                    continue
                current = eroded.buffer(corner_radius, join_style=1)
                if current.is_empty or current.area <= 1e-4:
                    continue

            if smoothness > 1e-3:
                current = chaikin_smooth_polygon(current, smoothness=smoothness)

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


def chaikin_smooth_polygon(poly: Polygon, smoothness: float = 0.0, iterations: int = 3) -> Polygon:
    """
    Apply Chaikin corner-cutting subdivision to smooth sharp polygon edges
    into an organic curved pebble/spline contour.
    """
    if smoothness <= 0.001 or poly.is_empty:
        return poly

    ext_coords = list(poly.exterior.coords)
    if len(ext_coords) < 4:
        return poly

    pts = np.array(ext_coords[:-1], dtype=np.float64)
    # alpha controls the cutting depth: from 0.0 to 0.25
    alpha = 0.25 * min(1.0, max(0.0, smoothness))

    for _ in range(iterations):
        n = len(pts)
        new_pts = []
        for i in range(n):
            p0 = pts[i]
            p1 = pts[(i + 1) % n]
            q = (1.0 - alpha) * p0 + alpha * p1
            r = alpha * p0 + (1.0 - alpha) * p1
            new_pts.append(q)
            new_pts.append(r)
        pts = np.array(new_pts)

    smoothed_coords = pts.tolist()
    smoothed_coords.append(smoothed_coords[0])
    try:
        smoothed_poly = Polygon(smoothed_coords)
        if not smoothed_poly.is_valid:
            smoothed_poly = shapely.make_valid(smoothed_poly)
            if isinstance(smoothed_poly, MultiPolygon):
                smoothed_poly = max(smoothed_poly.geoms, key=lambda g: g.area)
        return smoothed_poly if isinstance(smoothed_poly, Polygon) and smoothed_poly.area > 1e-4 else poly
    except Exception:
        return poly


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
            smoothness=smoothness
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
                    smoothness=smoothness
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
                smoothness=smoothness
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
                        smoothness=smoothness
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
                        smoothness=smoothness
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
                    smoothness=smoothness
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
                    smoothness=smoothness
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
                    smoothness=smoothness
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
                smoothness=smoothness
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
