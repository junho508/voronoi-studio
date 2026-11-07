# Voronoi Pattern Generator — Project Guide

> **Quick Start**: `cd E:\Antigravity\voronoi && python app.py` → open http://localhost:5000

---

## Purpose
Generates 2D CAD patterns (Voronoi, Hexagon, Triangle, Square) optimized for 3D printing.
Workflow: Siemens NX → export sketch as DXF → load here → generate pattern → export DXF → reimport to NX.

## Stack
- **Backend**: Python 3.x, Flask, scipy, shapely, numpy, ezdxf
- **Frontend**: Vanilla JS + SVG canvas (no framework), dark theme
- **Install**: `pip install flask flask-cors ezdxf scipy shapely numpy`

## Project Structure
```
voronoi/
├── app.py                  # Flask server + REST API endpoints
├── core/
│   ├── voronoi_gen.py      # Pattern generation (Voronoi, Hex, Tri, Square)
│   ├── dxf_parser.py       # DXF region extraction (closed loops)
│   └── dxf_exporter.py     # DXF export (LINE + ARC entities)
└── static/
    ├── index.html          # Main UI (single-page, tabbed left panel + SVG canvas)
    ├── css/style.css       # Dark theme styles
    └── js/
        ├── api.js          # REST API client wrappers
        ├── canvas.js       # SVG canvas manager (pan/zoom/interact)
        └── app.js          # Application controller
```

## API Endpoints
| Endpoint | Method | Description |
|---|---|---|
| `GET /` | GET | Serve frontend |
| `/api/parse-dxf` | POST | Parse DXF → closed boundary regions |
| `/api/generate` | POST | Generate pattern cells |
| `/api/export-dxf` | POST | Download result as DXF |
| `/api/reset` | POST | Clear backend in-memory state |

## Key Parameters (POST /api/generate)
| Field | Type | Description |
|---|---|---|
| `boundary` | array | Polygon coordinates [[x,y],...] |
| `pattern_type` | string | `voronoi` / `hexagon` / `triangle` / `square` |
| `cell_size` | float | Cell size in mm (unified across all patterns) |
| `pattern_offset_x` | float | X offset in mm for regular patterns (Hex, Tri, Square) |
| `pattern_offset_y` | float | Y offset in mm for regular patterns (Hex, Tri, Square) |
| `jitter` | float | 0.0=regular grid, 1.0=random (Voronoi) |
| `lloyd_iterations` | int | Lloyd's relaxation passes (0=disabled) |
| `rotation` | float | Pattern rotation in degrees (-90 to 90) |
| `boundary_offset` | float | Inset from boundary in mm |
| `cell_gap` | float | Gap between cells (rib width) in mm |
| `corner_radius` | float | Fillet radius in mm |
| `seamless` | bool | Enable infinite tiling (rect boundaries) |
| `seed` | int | Random seed for reproducibility |
| `seed_points` | array | Manual seed point override [[x,y],...] |

## Coordinate System
- **DXF / Backend**: Y-up (CAD convention), mm units
- **SVG Canvas**: Y-down (screen convention)
- **Conversion**: SVG `y = -world_y`, done in `canvas.js worldToSvg()`

## UI Layout
- **Left panel**: 3 tabs — 경계설정 (Boundary) | 패턴설정 (Pattern) | 내보내기 (Export)
- **Right**: SVG canvas with pan (drag)/zoom (wheel), seed points draggable
- **Canvas interactions**:
  - Click cell = select (Shift = multi-select)
  - Right-click / Del key = delete cell
  - Drag seed point = real-time Voronoi preview (d3-delaunay), backend recalc on release
  - Click canvas in "씨드 추가" mode or press `+` key at cursor = add seed point immediately

## Pattern Generation Flow
1. `generate_seed_points()` → grid + jitter → optional Lloyd's relaxation
2. `scipy.spatial.Voronoi` with ghost/periodic mirror points (3x3 periodic grid for seamless)
3. `post_process_polygon()` → clip to boundary → cell_gap buffer → corner rounding

## Seamless Tiling (무한 반복 타일링)
- **Voronoi**: Uses 3×3 periodic tile grid of seed points. Insets and fillets before clipping so boundary seams stay open and connect across tiles seamlessly.
- **Regular Patterns (Hexagon, Triangle, Square)**: Integer Period Quantization. Automatically adapts the user's `cell_size` to the closest integer division of boundary width $W$ and height $H$.
  - Square: $P_x = s, P_y = s$
  - Hexagon (pointy-topped): $P_x = \frac{\sqrt{3}}{2} s, P_y = 1.5 s$ (2 rows per period)
  - Triangle: $P_x = s, P_y = \sqrt{3} s$ (2 rows per period)
  - Result: Perfect 100% mathematical periodic tiling across left/right and top/bottom edges, with actual adapted size shown in UI hint (e.g. `(타일링 보정: 15.6mm)`).

## DXF Export
- Cells without rounding → `LWPOLYLINE` entities
- Cells with `corner_radius > 0` → `LINE` + `ARC` entities (true circular arcs)
- Layer `VORONOI_PATTERN` (color red) + `BOUNDARY` layer (color green)
- NX import: `File > Import > DXF/DWG` → 2D Wireframe to Sketch

## Known Issues / Notes
- Lloyd's relaxation with many iterations can be slow for dense patterns (>200 points)
- Seamless tiling works best with rectangular boundaries and no boundary_offset
- Hexagon/Triangle/Square patterns ignore `seed` and `jitter` (deterministic grids)

## Recent Changes (2026-11)
- Fixed DXF mode Tile Preview: DXF region bounds format unified to `{minx, miny, maxx, maxy}`, resolving NaN dimension calculation and enabling 3x3 Tile Preview in DXF boundary mode
- Contextual shortcut guidance: in Hexagon/Triangle/Square modes, disabled shortcuts (+ 씨드추가, Del, 우클릭, Shift+클릭) are automatically hidden in the left panel footer, showing only Ctrl+Z and 드래그 위치 이동
- Regular pattern aspect ratio preservation in seamless tiling: Optimal $(nx, ny)$ quantization search simultaneously balances width and height to keep regular geometric proportions (정사각형 100% 비율 유지, 정육각형/정삼각형 왜곡률 1% 이내)
- Regular patterns (Hexagon, Triangle, Square) Seamless Tiling: Added Integer Period Quantization with open-seam clipping and UI hint feedback (e.g. `(타일링 보정: 15.6mm)`)
- Regular patterns (Hexagon, Triangle, Square) interactive drag: Left-click & drag on canvas shifts the entire pattern grid position in real-time
- Disabled cell selection, Del/Backspace deletion, right-click deletion, and '+' addition in regular pattern modes
- Selection toggle: clicking a selected Voronoi cell deselects it (removes red highlight)
- Korean UI headers: "보로노이 생성기", "NX CAD/CAM 파라메트릭 패턴", balanced "새로 시작" header layout
- Unified cell size control: Voronoi and all patterns now use `cell_size` (mm) with dynamic cell count estimation
- Fixed hexagon pattern generation: regular hexagons now generate accurately
- Adaptive UI: Hexagon, Triangle, and Square modes hide seed controls, jitter, and Lloyd relaxation
- Canvas toolbar: removed "씨드 추가" button (adding seeds exclusively via `+` shortcut at mouse cursor)
- Fixed toolbar wrapping: "씨드 표시" and "타일 미리보기" remain single-line on window resize
- Fixed seed visibility toggle bug: seed DOM is kept in sync when adding/deleting while hidden
- Reduced seed controller radius by 50%
- Fixed DXF export ARC fillet reversal: all corner fillets now correctly sweep inward (true CAD arcs)
- Added Lloyd's Relaxation algorithm (`lloyd_iterations` param)
- Seamless tiling: 3×3 periodic Voronoi connects seamlessly across boundaries
- Korean labels: Seamless Tiling → 무한 반복 타일링
