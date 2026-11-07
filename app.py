"""
Flask Application for Voronoi and Procedural Pattern Generator.

Provides REST API for:
- DXF parsing and region extraction (/api/parse-dxf)
- Pattern generation (/api/generate)
- Interactive point manipulation (/api/update-point)
- DXF file export and download (/api/export-dxf)
- Static web client hosting (/)
"""

import os
import tempfile
from typing import Dict, Any, List
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

from core.dxf_parser import parse_dxf_to_regions, parse_dxf
from core.voronoi_gen import generate_pattern
from core.dxf_exporter import export_to_dxf

# Base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Ensure static folder exists
os.makedirs(STATIC_DIR, exist_ok=True)

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

# In-memory application state (single-user / desktop tool)
app_state: Dict[str, Any] = {
    "boundaries": [],
    "cells": [],
    "seed_points": [],
    "last_params": {},
    "filename": "voronoi_pattern.dxf"
}


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint for monitoring services (e.g. UptimeRobot, Render)."""
    return jsonify({"status": "ok", "app": "voronoi-pattern-generator"}), 200


@app.route("/", methods=["GET"])
def index():
    """Serve the static frontend or an informational welcome page."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(STATIC_DIR, "index.html")
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Voronoi Pattern Generator Backend</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                   margin: 40px; background: #0f172a; color: #f8fafc; line-height: 1.6; }
            .card { background: #1e293b; padding: 28px; border-radius: 12px; max-width: 680px; box-shadow: 0 4px 20px rgba(0,0,0,0.3); }
            h1 { color: #38bdf8; margin-top: 0; }
            code { background: #334155; padding: 3px 8px; border-radius: 4px; color: #f472b6; font-size: 0.9em; }
            ul { padding-left: 20px; }
            li { margin: 8px 0; }
            .status { display: inline-block; background: #10b981; color: #042f2e; padding: 4px 10px; border-radius: 9999px; font-weight: bold; font-size: 0.85em; }
        </style>
    </head>
    <body>
        <div class="card">
            <span class="status">● Server Online</span>
            <h1>Voronoi Pattern Generator API</h1>
            <p>The backend server is active on <code>http://localhost:5000</code>.</p>
            <h3>Available Endpoints:</h3>
            <ul>
                <li><code>POST /api/parse-dxf</code> - Upload DXF and extract closed boundary regions</li>
                <li><code>POST /api/generate</code> - Generate Voronoi, hexagonal, triangular, or square patterns</li>
                <li><code>POST /api/update-point</code> - Move seed points interactively and regenerate cells</li>
                <li><code>POST /api/export-dxf</code> - Download generated patterns and boundaries as DXF</li>
            </ul>
            <p>Place your frontend build files in the <code>static/</code> directory to serve the client UI directly.</p>
        </div>
    </body>
    </html>
    """, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/api/parse-dxf", methods=["POST"])
def api_parse_dxf():
    """
    Parse an uploaded DXF file and return closed boundary regions.
    Expects multipart/form-data with a 'file' field.
    """
    try:
        if "file" not in request.files:
            # Check if any file was uploaded
            if not request.files:
                return jsonify({"error": "No file uploaded. Please supply a 'file' field."}), 400
            file_obj = next(iter(request.files.values()))
        else:
            file_obj = request.files["file"]

        if not file_obj or file_obj.filename == "":
            return jsonify({"error": "Selected file is empty or missing filename."}), 400

        original_filename = secure_filename(file_obj.filename) or "upload.dxf"
        app_state["filename"] = original_filename

        # Parse regions from the DXF file
        regions = parse_dxf_to_regions(file_obj)

        if not regions:
            return jsonify({
                "regions": [],
                "message": "No closed boundary loops found in DXF. Check closed flags or joined lines."
            }), 200

        # Store parsed regions in global state
        app_state["boundaries"] = regions
        app_state["cells"] = []
        app_state["seed_points"] = []

        return jsonify({"regions": regions}), 200

    except Exception as e:
        return jsonify({"error": f"Failed to parse DXF: {str(e)}"}), 500


@app.route("/api/reset", methods=["POST"])
def api_reset():
    """Reset all in-memory state."""
    app_state["boundaries"] = []
    app_state["cells"] = []
    app_state["seed_points"] = []
    app_state["last_params"] = {}
    app_state["filename"] = "voronoi_pattern.dxf"
    return jsonify({"status": "reset", "message": "Backend state reset successfully"}), 200


@app.route("/api/generate", methods=["POST"])
def api_generate():
    """
    Generate Voronoi or geometric pattern cells for given boundaries and parameters.
    """
    try:
        data = request.get_json(silent=True) or {}

        # Resolve boundary inputs: prioritize explicit payload over in-memory state
        boundaries_input = data.get("boundaries") or data.get("regions") or data.get("boundary")
        if not boundaries_input:
            boundaries_input = app_state.get("boundaries")

        if not boundaries_input:
            # Default rectangular boundary if none provided
            boundaries_input = [{
                "id": "default_box",
                "coords": [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0], [0.0, 0.0]]
            }]

        # Parameters
        seamless = bool(data.get('seamless', False))
        density = float(data.get('density', 0.0))
        lloyd_iterations = int(data.get('lloyd_iterations', 0))
        params = {
            "n_points": int(data.get("n_points", 50)),
            "density": density,
            "seed": int(data.get("seed", 42)),
            "jitter": float(data.get("jitter", 0.5)),
            "lloyd_iterations": lloyd_iterations,
            "rotation": float(data.get("rotation", 0.0)),
            "boundary_offset": float(data.get("boundary_offset", 0.0)),
            "cell_gap": float(data.get("cell_gap", 0.0)),
            "corner_radius": float(data.get("corner_radius", 0.0)),
            "pattern_type": str(data.get("pattern_type", "voronoi")),
            "seed_points": data.get("seed_points"),
            "cell_size": float(data.get("cell_size", 0.0)),
            "pattern_offset_x": float(data.get("pattern_offset_x", 0.0)),
            "pattern_offset_y": float(data.get("pattern_offset_y", 0.0)),
            "seamless": seamless
        }

        # Normalize boundaries to a list
        if isinstance(boundaries_input, dict):
            boundary_list = [boundaries_input]
        elif isinstance(boundaries_input, list):
            # Check if it's a single coordinate list [[x, y], ...]
            if len(boundaries_input) > 0 and isinstance(boundaries_input[0], (list, tuple)) and len(boundaries_input[0]) == 2 and isinstance(boundaries_input[0][0], (int, float)):
                boundary_list = [boundaries_input]
            else:
                boundary_list = boundaries_input
        else:
            boundary_list = [boundaries_input]

        all_cells: List[Dict[str, Any]] = []
        all_seed_points: List[List[float]] = []
        seed_idx_offset = 0

        for b in boundary_list:
            cells, seeds = generate_pattern(b, params, seamless=seamless)
            for c in cells:
                c["seed_idx"] = c.get("seed_idx", 0) + seed_idx_offset
                all_cells.append(c)
            all_seed_points.extend(seeds)
            seed_idx_offset += len(seeds)

        # Update in-memory state
        app_state["boundaries"] = boundary_list
        app_state["cells"] = all_cells
        app_state["seed_points"] = all_seed_points
        app_state["last_params"] = params

        return jsonify({
            "cells": all_cells,
            "seed_points": all_seed_points,
            "adapted_cell_size": params.get("adapted_cell_size")
        }), 200

    except Exception as e:
        return jsonify({"error": f"Pattern generation failed: {str(e)}"}), 500


@app.route("/api/update-point", methods=["POST"])
def api_update_point():
    """
    Update a single seed point position and regenerate pattern.
    Expects JSON: {point_index, new_position: [x,y], current_seed_points, params, boundaries}
    """
    try:
        data = request.get_json(silent=True) or {}

        if "point_index" not in data or "new_position" not in data:
            return jsonify({"error": "Missing required 'point_index' or 'new_position'."}), 400

        point_idx = int(data["point_index"])
        new_pos = [float(data["new_position"][0]), float(data["new_position"][1])]

        current_seeds = data.get("current_seed_points") or app_state.get("seed_points", [])
        if not current_seeds or point_idx < 0 or point_idx >= len(current_seeds):
            return jsonify({"error": f"Invalid point_index {point_idx} for seed list of length {len(current_seeds)}"}), 400

        # Update seed point
        updated_seeds = [list(pt) for pt in current_seeds]
        updated_seeds[point_idx] = new_pos

        params = data.get("params") or app_state.get("last_params", {}).copy()
        params["seed_points"] = updated_seeds

        boundaries = data.get("boundaries") or app_state.get("boundaries")
        if not boundaries:
            boundaries = [{
                "id": "default_box",
                "coords": [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0], [0.0, 0.0]]
            }]

        boundary_target = boundaries[0] if isinstance(boundaries, list) else boundaries
        seamless = bool(params.get("seamless", False))
        cells, seeds = generate_pattern(boundary_target, params, seamless=seamless)

        # Update state
        app_state["cells"] = cells
        app_state["seed_points"] = updated_seeds
        app_state["last_params"] = params

        return jsonify({
            "cells": cells,
            "seed_points": updated_seeds
        }), 200

    except Exception as e:
        return jsonify({"error": f"Failed to update point: {str(e)}"}), 500


@app.route("/api/export-dxf", methods=["POST"])
def api_export_dxf():
    """
    Export cells and boundaries to DXF format and stream as file download.
    """
    try:
        data = request.get_json(silent=True) or {}

        cells = data.get("cells")
        if cells is None:
            cells = app_state.get("cells", [])

        boundaries = data.get("boundaries")
        if boundaries is None:
            boundaries = data.get("boundary")
        if boundaries is None:
            boundaries = app_state.get("boundaries", [])

        include_boundary = bool(data.get("include_boundary", True))
        corner_radius = float(data.get('corner_radius', 0.0))
        filename = data.get("filename") or app_state.get("filename", "voronoi_pattern.dxf")

        if not filename.lower().endswith(".dxf"):
            filename += ".dxf"
        filename = secure_filename(filename) or "voronoi_pattern.dxf"

        if not cells and not boundaries:
            return jsonify({"error": "No pattern cells or boundaries available to export."}), 400

        # Create temporary file for download
        temp_dir = tempfile.gettempdir()
        export_filepath = os.path.join(temp_dir, filename)

        options = {
            "include_boundary": include_boundary,
            "corner_radius": corner_radius
        }
        export_to_dxf(cells, boundaries, export_filepath, options=options)

        return send_file(
            export_filepath,
            as_attachment=True,
            download_name=filename,
            mimetype="application/dxf"
        )

    except Exception as e:
        return jsonify({"error": f"DXF export failed: {str(e)}"}), 500


@app.errorhandler(400)
def bad_request(error):
    return jsonify({"error": "Bad request", "details": str(error)}), 400


@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Resource not found"}), 404


@app.errorhandler(500)
def server_error(error):
    return jsonify({"error": "Internal server error", "details": str(error)}), 500


if __name__ == "__main__":
    print("=" * 60)
    print("Voronoi Pattern Generator Backend")
    print("Running on http://localhost:5000")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=True)
