/**
 * canvas.js - SVG Viewport & Interactive Canvas Manager
 * Handles CAD-accurate coordinate transformation (DXF Y-up to SVG Y-down),
 * adaptive millimeter grid, zoom/pan navigation, cell selection/deletion,
 * and real-time draggable seed points.
 */

class CanvasManager {
  /**
   * @param {string} svgId - ID of the main SVG element ('main-svg')
   */
  constructor(svgId) {
    this.svg = document.getElementById(svgId);
    this.wrapper = document.getElementById('canvas-wrapper');
    this.canvasGroup = document.getElementById('canvas-group');
    this.gridLayer = document.getElementById('grid-layer');
    this.boundaryLayer = document.getElementById('boundary-layer');
    this.cellsLayer = document.getElementById('cells-layer');
    this.seedsLayer = document.getElementById('seeds-layer');
    this.tooltip = document.getElementById('seed-tooltip');

    // View Transformation (tx, ty in SVG pixels; scale = screen px / mm)
    this.tx = 0;
    this.ty = 0;
    this.scale = 4.0; // default initial scale (4px per mm)

    // Interaction State
    this.mode = 'select'; // 'select' | 'edit'
    this.isPanning = false;
    this.panStartX = 0;
    this.panStartY = 0;
    this.panStartTx = 0;
    this.panStartTy = 0;

    // Draggable Seed Points State
    this.seedPoints = []; // current seed points [[x, y], ...]
    this.draggedSeedIdx = null;
    this.isDraggingSeed = false;
    this.showSeeds = true;

    // Cells State & Selection
    this.cells = [];
    this.selectedCellIds = new Set();

    // Content World Bounding Box (in mm)
    this.worldBounds = { minx: 0, miny: 0, maxx: 100, maxy: 100 };

    // Event Callbacks
    this.seedMovedCallback = null;
    this.cellDeletedCallback = null;
    this.cursorMoveCallback = null;
    this.selectionChangeCallback = null;
    this.zoomChangeCallback = null;
    this.backgroundClickCallback = null;
    this.addSeedCallback = null;

    // Pattern Type & Interactive Pattern Drag State
    this.patternType = 'voronoi';
    this.isDraggingPattern = false;
    this.hasMovedPattern = false;
    this.patternDragStartX = 0;
    this.patternDragStartY = 0;
    this.patternDragDeltaMmX = 0;
    this.patternDragDeltaMmY = 0;
    this.patternDragEndCallback = null;

    // Interactive Seed Add State
    this.isAddSeedMode = false;
    this.currentCursorWorld = null;

    // Initialize all canvas events
    this.init();
  }

  /**
   * Initialize canvas listeners and setup viewport
   */
  init() {
    this.setupPanZoom();
    this.setupKeyboardShortcuts();
    this.setupCursorTracking();

    // Resize observer to keep grid updated
    if (window.ResizeObserver) {
      const resizeObserver = new ResizeObserver(() => {
        this.updateGrid();
      });
      resizeObserver.observe(this.wrapper);
    } else {
      window.addEventListener('resize', () => this.updateGrid());
    }

    // Set default initial transform
    this.setTransform(60, 450, 4.0);
  }

  /* ------------------------------------------------------------------------
     1. Coordinate Transformation
     ------------------------------------------------------------------------ */

  /**
   * Convert SVG screen pixel coordinates (clientX/Y relative to SVG) to mm World coordinates
   * Accounting for CAD Y-axis flip (DXF +Y is up, SVG +Y is down)
   * @param {number} screenX - Client X pixel on SVG
   * @param {number} screenY - Client Y pixel on SVG
   * @returns {{x: number, y: number}} World coordinates in mm
   */
  svgToWorld(screenX, screenY) {
    const rect = this.svg.getBoundingClientRect();
    const px = screenX - rect.left;
    const py = screenY - rect.top;

    // Unapply pan and zoom
    const svgX = (px - this.tx) / this.scale;
    const svgY = (py - this.ty) / this.scale;

    // Convert SVG Y-down to CAD Y-up
    const worldX = svgX;
    const worldY = -svgY;

    return { x: worldX, y: worldY };
  }

  /**
   * Convert mm World coordinates to SVG coordinate space inside canvas-group
   * @param {number} wx - mm World X
   * @param {number} wy - mm World Y
   * @returns {{x: number, y: number}} SVG group coordinates
   */
  worldToSvg(wx, wy) {
    return {
      x: wx,
      y: -wy,
    };
  }

  /* ------------------------------------------------------------------------
     2. View Transform & Pan/Zoom
     ------------------------------------------------------------------------ */

  /**
   * Apply translation and scale transform to canvas group
   * @param {number} tx - Translation X in px
   * @param {number} ty - Translation Y in px
   * @param {number} scale - Zoom scale factor
   */
  setTransform(tx, ty, scale) {
    this.tx = tx;
    this.ty = ty;
    this.scale = Math.min(Math.max(scale, 0.05), 100);

    // Apply matrix transformation to main canvas group
    this.canvasGroup.setAttribute(
      'transform',
      `matrix(${this.scale}, 0, 0, ${this.scale}, ${this.tx}, ${this.ty})`
    );

    // Recompute adaptive mm grid
    this.updateGrid();

    // Notify zoom change
    if (this.zoomChangeCallback) {
      this.zoomChangeCallback(this.scale);
    }
  }

  /**
   * Zoom by factor centered at specific SVG pixel coordinates
   * @param {number} factor - Zoom multiplier (e.g., 1.2 or 0.8)
   * @param {number} [cx] - Center X in px (defaults to SVG viewport center)
   * @param {number} [cy] - Center Y in px (defaults to SVG viewport center)
   */
  zoomTo(factor, cx, cy) {
    const rect = this.svg.getBoundingClientRect();
    const centerX = cx !== undefined ? cx : rect.width / 2;
    const centerY = cy !== undefined ? cy : rect.height / 2;

    const newScale = Math.min(Math.max(this.scale * factor, 0.05), 100);

    // Zoom centered on (centerX, centerY)
    const svgX = (centerX - this.tx) / this.scale;
    const svgY = (centerY - this.ty) / this.scale;

    const newTx = centerX - svgX * newScale;
    const newTy = centerY - svgY * newScale;

    this.setTransform(newTx, newTy, newScale);
  }

  /**
   * Fit all current boundary and cell content inside viewport with padding
   */
  fitToContent() {
    const rect = this.svg.getBoundingClientRect();
    const vw = rect.width || 800;
    const vh = rect.height || 600;

    const b = this.worldBounds;
    const contentW = Math.max(b.maxx - b.minx, 5);
    const contentH = Math.max(b.maxy - b.miny, 5);

    // Add padding (40px on all sides)
    const padding = 60;
    const availW = Math.max(vw - padding * 2, 50);
    const availH = Math.max(vh - padding * 2, 50);

    const scaleX = availW / contentW;
    const scaleY = availH / contentH;
    const scale = Math.min(scaleX, scaleY);

    // Center of content in world coords
    const worldCenterX = (b.minx + b.maxx) / 2;
    const worldCenterY = (b.miny + b.maxy) / 2;

    // Center in SVG group coords: x = cx, y = -cy
    const svgCenterX = worldCenterX;
    const svgCenterY = -worldCenterY;

    // Viewport center
    const vpCenterX = vw / 2;
    const vpCenterY = vh / 2;

    const tx = vpCenterX - svgCenterX * scale;
    const ty = vpCenterY - svgCenterY * scale;

    this.setTransform(tx, ty, scale);
  }

  /**
   * Setup pan and zoom navigation handlers
   */
  setupPanZoom() {
    // Mouse Wheel Zoom centered on cursor
    this.wrapper.addEventListener('wheel', (e) => {
      e.preventDefault();
      const rect = this.svg.getBoundingClientRect();
      const cursorX = e.clientX - rect.left;
      const cursorY = e.clientY - rect.top;

      const zoomFactor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
      this.zoomTo(zoomFactor, cursorX, cursorY);
    }, { passive: false });

    // Panning & Pattern Dragging
    this.wrapper.addEventListener('pointerdown', (e) => {
      const isMiddleClick = e.button === 1;
      const isAltLeftClick = e.button === 0 && e.altKey;
      const isLeftClick = e.button === 0 && !e.altKey;
      const isTargetCell = e.target.closest && e.target.closest('.voronoi-cell');
      const isTargetSeed = e.target.closest && e.target.closest('.seed-point-group');

      if (isMiddleClick || isAltLeftClick) {
        // Middle click or Alt+Click always pans viewport
        e.preventDefault();
        this.isPanning = true;
        this.hasMovedPan = false;
        this.panStartX = e.clientX;
        this.panStartY = e.clientY;
        this.panStartTx = this.tx;
        this.panStartTy = this.ty;

        this.wrapper.classList.add('is-panning');
        try {
          this.svg.setPointerCapture(e.pointerId);
        } catch (_) {}
        return;
      }

      if (isLeftClick) {
        // In Non-Voronoi modes (Hexagon, Triangle, Square): Left click & drag shifts pattern position!
        if (this.patternType !== 'voronoi') {
          e.preventDefault();
          this.isDraggingPattern = true;
          this.hasMovedPattern = false;
          this.patternDragStartX = e.clientX;
          this.patternDragStartY = e.clientY;
          this.patternDragDeltaMmX = 0;
          this.patternDragDeltaMmY = 0;
          this.wrapper.classList.add('is-dragging-pattern');
          try {
            this.svg.setPointerCapture(e.pointerId);
          } catch (_) {}
          return;
        }

        // In Voronoi mode: Left click on background (not cell, not seed) pans the viewport
        if (!isTargetCell && !isTargetSeed) {
          e.preventDefault();
          this.isPanning = true;
          this.hasMovedPan = false;
          this.panStartX = e.clientX;
          this.panStartY = e.clientY;
          this.panStartTx = this.tx;
          this.panStartTy = this.ty;

          this.wrapper.classList.add('is-panning');
          try {
            this.svg.setPointerCapture(e.pointerId);
          } catch (_) {}
        }
      }
    });

    this.wrapper.addEventListener('pointermove', (e) => {
      if (this.isPanning) {
        const dx = e.clientX - this.panStartX;
        const dy = e.clientY - this.panStartY;
        if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
          this.hasMovedPan = true;
        }
        this.setTransform(this.panStartTx + dx, this.panStartTy + dy, this.scale);
      } else if (this.isDraggingPattern) {
        const screenDx = e.clientX - this.patternDragStartX;
        const screenDy = e.clientY - this.patternDragStartY;
        if (Math.abs(screenDx) > 2 || Math.abs(screenDy) > 2) {
          this.hasMovedPattern = true;
        }
        const dxMm = screenDx / this.scale;
        const dyMm = -screenDy / this.scale;
        this.patternDragDeltaMmX = dxMm;
        this.patternDragDeltaMmY = dyMm;
        // SVG coordinate: X is dxMm, Y is -dyMm (flip CAD Y-axis)
        this.cellsLayer.setAttribute('transform', `translate(${dxMm}, ${-dyMm})`);
        const tileLayer = document.getElementById('tile-preview-layer');
        if (tileLayer) {
          tileLayer.setAttribute('transform', `translate(${dxMm}, ${-dyMm})`);
        }
      }
    });

    const stopPanOrDrag = (e) => {
      if (this.isPanning) {
        // If it was a clean click without significant drag on background, deselect cells
        if (!this.hasMovedPan && e.button === 0 && !e.altKey && this.patternType === 'voronoi') {
          if (this.isAddSeedMode) {
            const worldPos = this.svgToWorld(e.clientX, e.clientY);
            if (this.addSeedCallback) {
              this.addSeedCallback(worldPos.x, worldPos.y);
            }
            this.isPanning = false;
            this.hasMovedPan = false;
            this.wrapper.classList.remove('is-panning');
            return;
          }

          this.deselectAll();
          // Notify background click with world coordinates
          if (this.backgroundClickCallback) {
            const worldPos = this.svgToWorld(e.clientX, e.clientY);
            this.backgroundClickCallback(worldPos.x, worldPos.y);
          }
        }

        this.isPanning = false;
        this.hasMovedPan = false;
        this.wrapper.classList.remove('is-panning');
        try {
          if (e.pointerId !== undefined) {
            this.svg.releasePointerCapture(e.pointerId);
          }
        } catch (_) {}
      }

      if (this.isDraggingPattern) {
        this.isDraggingPattern = false;
        this.wrapper.classList.remove('is-dragging-pattern');
        this.cellsLayer.removeAttribute('transform');
        const tileLayer = document.getElementById('tile-preview-layer');
        if (tileLayer) {
          tileLayer.removeAttribute('transform');
        }
        try {
          if (e.pointerId !== undefined) {
            this.svg.releasePointerCapture(e.pointerId);
          }
        } catch (_) {}

        if (this.hasMovedPattern && (Math.abs(this.patternDragDeltaMmX) > 0.05 || Math.abs(this.patternDragDeltaMmY) > 0.05)) {
          if (this.patternDragEndCallback) {
            this.patternDragEndCallback(this.patternDragDeltaMmX, this.patternDragDeltaMmY);
          }
        }
      }
    };

    this.wrapper.addEventListener('pointerup', stopPanOrDrag);
    this.wrapper.addEventListener('pointercancel', stopPanOrDrag);

    // Prevent default context menu on canvas for custom right-click cell delete
    this.wrapper.addEventListener('contextmenu', (e) => {
      e.preventDefault();
    });
  }

  /**
   * Track cursor movements to report mm coordinates
   */
  setupCursorTracking() {
    this.wrapper.addEventListener('mousemove', (e) => {
      const worldPos = this.svgToWorld(e.clientX, e.clientY);
      this.currentCursorWorld = worldPos;
      if (this.cursorMoveCallback) {
        this.cursorMoveCallback(worldPos.x, worldPos.y);
      }
    });

    this.wrapper.addEventListener('mouseleave', () => {
      this.currentCursorWorld = null;
    });
  }

  /**
   * Setup keyboard shortcuts (Delete to delete cells, + to add seed at cursor)
   */
  setupKeyboardShortcuts() {
    window.addEventListener('keydown', (e) => {
      // Don't intercept if user is typing in an input
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
        return;
      }

      if (e.key === 'Delete' || e.key === 'Backspace') {
        if (this.patternType === 'voronoi' && this.selectedCellIds.size > 0) {
          e.preventDefault();
          this.deleteSelectedCells();
        }
      }

      // Add seed at current mouse cursor with '+' or '='
      if (e.key === '+' || e.key === '=') {
        if (this.patternType === 'voronoi' && this.currentCursorWorld && this.addSeedCallback) {
          e.preventDefault();
          this.addSeedCallback(this.currentCursorWorld.x, this.currentCursorWorld.y);
        }
      }
    });
  }

  /* ------------------------------------------------------------------------
     3. Adaptive Millimeter Grid Rendering
     ------------------------------------------------------------------------ */

  /**
   * Calculate nice grid division step in mm based on zoom scale
   * @param {number} scale - Current scale (screen px per mm)
   * @returns {number} Step in mm
   */
  getNiceGridStep(scale) {
    const minPixelSpacing = 35; // minimum pixels between grid lines
    const targetMm = minPixelSpacing / scale;
    const exponent = Math.floor(Math.log10(targetMm));
    const fraction = targetMm / Math.pow(10, exponent);

    let niceFraction = 1;
    if (fraction <= 1) niceFraction = 1;
    else if (fraction <= 2) niceFraction = 2;
    else if (fraction <= 5) niceFraction = 5;
    else niceFraction = 10;

    return niceFraction * Math.pow(10, exponent);
  }

  /**
   * Render dynamic adaptive grid lines in mm
   */
  updateGrid() {
    if (!this.gridLayer) return;

    const rect = this.svg.getBoundingClientRect();
    const vw = rect.width || 800;
    const vh = rect.height || 600;

    // Viewport bounds in world mm
    const minWx = (0 - this.tx) / this.scale;
    const maxWx = (vw - this.tx) / this.scale;
    const minWy = -(vh - this.ty) / this.scale;
    const maxWy = -(0 - this.ty) / this.scale;

    const step = this.getNiceGridStep(this.scale);
    const majorStep = step * 5;

    // Fragment for fast DOM insertion
    const fragment = document.createDocumentFragment();

    const startX = Math.floor(minWx / step) * step;
    const endX = Math.ceil(maxWx / step) * step;
    const startY = Math.floor(minWy / step) * step;
    const endY = Math.ceil(maxWy / step) * step;

    // Vertical Lines (constant X in world mm)
    for (let x = startX; x <= endX; x += step) {
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      const isZero = Math.abs(x) < step * 0.001;
      const isMajor = Math.abs(x % majorStep) < step * 0.001;

      line.setAttribute('x1', x);
      line.setAttribute('y1', -minWy);
      line.setAttribute('x2', x);
      line.setAttribute('y2', -maxWy);

      if (isZero) {
        line.setAttribute('class', 'grid-axis-y');
      } else if (isMajor) {
        line.setAttribute('class', 'grid-line-major');
      } else {
        line.setAttribute('class', 'grid-line-minor');
      }
      fragment.appendChild(line);
    }

    // Horizontal Lines (constant Y in world mm)
    for (let y = startY; y <= endY; y += step) {
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      const isZero = Math.abs(y) < step * 0.001;
      const isMajor = Math.abs(y % majorStep) < step * 0.001;

      line.setAttribute('x1', minWx);
      line.setAttribute('y1', -y);
      line.setAttribute('x2', maxWx);
      line.setAttribute('y2', -y);

      if (isZero) {
        line.setAttribute('class', 'grid-axis-x');
      } else if (isMajor) {
        line.setAttribute('class', 'grid-line-major');
      } else {
        line.setAttribute('class', 'grid-line-minor');
      }
      fragment.appendChild(line);
    }

    // Replace grid children
    this.gridLayer.innerHTML = '';
    this.gridLayer.appendChild(fragment);
  }

  /* ------------------------------------------------------------------------
     4. Boundary & Cell Rendering
     ------------------------------------------------------------------------ */

  /**
   * Render boundary polygon contours
   * @param {Array<Object>|Object} regions - Boundary region(s) [{id, coords:[[x,y],...], bounds}]
   */
  renderBoundary(regions) {
    this.boundaryLayer.innerHTML = '';
    if (!regions) return;

    const list = Array.isArray(regions) ? regions : [regions];
    if (list.length === 0) return;

    let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;

    list.forEach((region) => {
      const coords = region.coords || region;
      if (!Array.isArray(coords) || coords.length === 0) return;

      let d = 'M ';
      coords.forEach((pt, i) => {
        const x = pt[0];
        const y = pt[1];
        d += `${x} ${-y} `;
        if (i === 0) d += 'L ';

        if (x < minx) minx = x;
        if (x > maxx) maxx = x;
        if (y < miny) miny = y;
        if (y > maxy) maxy = y;
      });
      d += 'Z';

      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', d);
      path.setAttribute('class', 'boundary-polygon');
      if (region.id !== undefined) {
        path.setAttribute('data-region-id', region.id);
      }
      this.boundaryLayer.appendChild(path);
    });

    if (minx !== Infinity) {
      this.worldBounds = { minx, miny, maxx, maxy };
    }
  }

  /**
   * Render Voronoi / parametric cells as interactive SVG paths
   * @param {Array<Object>} cells - Cell array [{coords:[[x,y],...], seed_idx, id}]
   * @param {string} [patternType] - 'voronoi' | 'hexagon' | 'triangle' | 'square'
   */
  renderCells(cells, patternType) {
    if (patternType) {
      this.patternType = patternType;
    }
    this.wrapper.classList.toggle('mode-pattern-draggable', this.patternType !== 'voronoi');
    this.clearCells();
    if (!cells || !Array.isArray(cells)) return;

    this.cells = cells;
    const fragment = document.createDocumentFragment();

    cells.forEach((cell, index) => {
      const coords = cell.coords;
      if (!coords || coords.length < 3) return;

      const cellId = cell.id !== undefined ? String(cell.id) : String(index);
      const seedIdx = cell.seed_idx !== undefined ? cell.seed_idx : index;

      // Construct SVG path data
      let d = 'M ';
      coords.forEach((pt, i) => {
        d += `${pt[0]} ${-pt[1]} `;
        if (i === 0) d += 'L ';
      });
      d += 'Z';

      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', d);
      path.setAttribute('class', 'voronoi-cell');
      path.setAttribute('data-id', cellId);
      path.setAttribute('data-seed-idx', seedIdx);

      if (this.patternType === 'voronoi') {
        // Restore selection state
        if (this.selectedCellIds.has(cellId)) {
          path.classList.add('selected');
        }

        // Interaction: Click to select / Shift-click multi-select, or add seed in add mode
        path.addEventListener('click', (e) => {
          e.stopPropagation();
          if (this.isAddSeedMode) {
            const world = this.svgToWorld(e.clientX, e.clientY);
            if (this.addSeedCallback) {
              this.addSeedCallback(world.x, world.y);
            }
            return;
          }
          const isMulti = e.shiftKey || e.ctrlKey || e.metaKey;
          this.toggleCellSelection(cellId, isMulti);
        });

        // Interaction: Right-click to delete cell immediately
        path.addEventListener('contextmenu', (e) => {
          e.preventDefault();
          e.stopPropagation();
          this.handleCellRightClick(cellId, seedIdx);
        });
      } else {
        // Non-Voronoi modes (Hexagon, Triangle, Square):
        // Prevent default context menu, do NOT select cell or delete cell
        path.addEventListener('contextmenu', (e) => {
          e.preventDefault();
        });
      }

      fragment.appendChild(path);
    });

    this.cellsLayer.appendChild(fragment);
  }

  /* ------------------------------------------------------------------------
     5. Seed Points Rendering & Real-time Dragging
     ------------------------------------------------------------------------ */

  /**
   * Render draggable seed point circles
   * @param {Array<Array<number>>} seedPoints - Coordinates [[x,y], ...]
   */
  renderSeeds(seedPoints) {
    this.clearSeeds();
    this.seedPoints = seedPoints || [];
    if (!this.seedPoints.length) {
      return;
    }

    const fragment = document.createDocumentFragment();

    this.seedPoints.forEach((pt, idx) => {
      const wx = pt[0];
      const wy = pt[1];

      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.setAttribute('class', 'seed-point-group');
      g.setAttribute('data-idx', idx);
      g.setAttribute('transform', `translate(${wx}, ${-wy})`);

      // Large invisible hit area
      const hitArea = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      hitArea.setAttribute('cx', 0);
      hitArea.setAttribute('cy', 0);
      hitArea.setAttribute('r', 3);
      hitArea.setAttribute('class', 'seed-hit-area');

      // Outer glowing halo
      const halo = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      halo.setAttribute('cx', 0);
      halo.setAttribute('cy', 0);
      halo.setAttribute('r', 1.5);
      halo.setAttribute('class', 'seed-halo');

      // Inner cyan dot
      const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      dot.setAttribute('cx', 0);
      dot.setAttribute('cy', 0);
      dot.setAttribute('r', 0.75);
      dot.setAttribute('class', 'seed-dot');

      g.appendChild(hitArea);
      g.appendChild(halo);
      g.appendChild(dot);

      // Tooltip on Hover
      g.addEventListener('mouseenter', (e) => {
        if (!this.isDraggingSeed) {
          this.showSeedTooltip(e.clientX, e.clientY, idx, wx, wy);
        }
      });

      g.addEventListener('mouseleave', () => {
        if (!this.isDraggingSeed) {
          this.hideSeedTooltip();
        }
      });

      // Draggable Pointer Events
      g.addEventListener('pointerdown', (e) => {
        if (e.button !== 0) return; // Left click only
        e.stopPropagation();

        this.startSeedDrag(idx, g, e);
      });

      fragment.appendChild(g);
    });

    this.seedsLayer.appendChild(fragment);
    this.seedsLayer.style.display = this.showSeeds ? 'block' : 'none';
  }

  /**
   * Start dragging a seed point
   * @param {number} idx - Index of the seed
   * @param {SVGGElement} group - Seed SVG group
   * @param {PointerEvent} e - Pointer down event
   */
  startSeedDrag(idx, group, e) {
    this.isDraggingSeed = true;
    this.draggedSeedIdx = idx;
    group.classList.add('dragging');

    const onPointerMove = (moveEvent) => {
      if (!this.isDraggingSeed) return;

      const world = this.svgToWorld(moveEvent.clientX, moveEvent.clientY);
      // Move the seed point SVG element immediately (60fps)
      group.setAttribute('transform', `translate(${world.x}, ${-world.y})`);
      this.seedPoints[idx] = [world.x, world.y];

      // Live preview: recompute Voronoi in-browser with d3-delaunay
      if (window.d3 && window.d3.Delaunay && this.seedPoints.length >= 3) {
        this._renderLiveVoronoi(this.seedPoints, this._liveBoundaryCoords);
      }

      this.showSeedTooltip(moveEvent.clientX, moveEvent.clientY, idx, world.x, world.y);
      if (this.cursorMoveCallback) {
        this.cursorMoveCallback(world.x, world.y);
      }
    };

    const onPointerUp = (upEvent) => {
      this.isDraggingSeed = false;
      group.classList.remove('dragging');
      this.hideSeedTooltip();

      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
      window.removeEventListener('pointercancel', onPointerUp);

      const finalWorld = this.svgToWorld(upEvent.clientX, upEvent.clientY);
      this.seedPoints[idx] = [finalWorld.x, finalWorld.y];

      // Restore permanent cells (hide live preview)
      if (this._livePreviewActive) {
        this._livePreviewActive = false;
        const livePaths = this.cellsLayer.querySelectorAll('path.live-preview');
        livePaths.forEach(p => p.remove());
        const permPaths = this.cellsLayer.querySelectorAll('path:not(.live-preview)');
        permPaths.forEach(p => p.style.display = '');
      }

      // Notify application of seed move
      if (this.seedMovedCallback) {
        this.seedMovedCallback(idx, [finalWorld.x, finalWorld.y]);
      }
    };

    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
    window.addEventListener('pointercancel', onPointerUp);
  }

  showSeedTooltip(screenX, screenY, idx, wx, wy) {
    if (!this.tooltip) return;
    const rect = this.wrapper.getBoundingClientRect();
    const relX = screenX - rect.left;
    const relY = screenY - rect.top;

    this.tooltip.style.left = `${relX}px`;
    this.tooltip.style.top = `${relY}px`;
    this.tooltip.innerHTML = `<strong>Seed #${idx + 1}</strong> (${wx.toFixed(1)}, ${wy.toFixed(1)} mm)`;
    this.tooltip.style.display = 'block';
  }

  hideSeedTooltip() {
    if (this.tooltip) {
      this.tooltip.style.display = 'none';
    }
  }

  /**
   * Store boundary coords for live Voronoi preview during drag
   */
  setLiveBoundary(coords) {
    this._liveBoundaryCoords = coords || null;
  }

  /**
   * Render a fast in-browser Voronoi preview using d3-delaunay during seed drag.
   * This shows approximate cell shapes WITHOUT offset/rounding for speed.
   * @param {Array<[number,number]>} seedPoints - mm coordinates
   * @param {Array<[number,number]>|null} boundaryCoords - boundary polygon coords in mm
   */
  _renderLiveVoronoi(seedPoints, boundaryCoords) {
    if (!window.d3 || !window.d3.Delaunay) return;
    if (!seedPoints || seedPoints.length < 3) return;

    try {
      // Convert mm seed points to SVG pixel coordinates for d3
      const svgPts = seedPoints.map(p => [p[0], -p[1]]); // world to SVG Y-flip

      // Build bounding box for Voronoi extent
      let xmin = Infinity, ymin = Infinity, xmax = -Infinity, ymax = -Infinity;
      if (boundaryCoords && boundaryCoords.length > 0) {
        boundaryCoords.forEach(([bx, by]) => {
          xmin = Math.min(xmin, bx);
          ymin = Math.min(ymin, -by); // flip Y
          xmax = Math.max(xmax, bx);
          ymax = Math.max(ymax, -by);
        });
      } else {
        svgPts.forEach(([px, py]) => {
          xmin = Math.min(xmin, px - 50);
          ymin = Math.min(ymin, py - 50);
          xmax = Math.max(xmax, px + 50);
          ymax = Math.max(ymax, py + 50);
        });
      }

      const delaunay = window.d3.Delaunay.from(svgPts);
      const voronoi = delaunay.voronoi([xmin - 10, ymin - 10, xmax + 10, ymax + 10]);

      // Clear and redraw cells layer with approximate paths
      const cellsLayer = this.cellsLayer;
      const existingPaths = cellsLayer.querySelectorAll('path.live-preview');
      const existingPermanent = cellsLayer.querySelectorAll('path:not(.live-preview)');

      // Hide permanent cells during live drag, show live paths
      existingPermanent.forEach(p => p.style.display = 'none');
      existingPaths.forEach(p => p.remove());

      const fragment = document.createDocumentFragment();
      for (let i = 0; i < seedPoints.length; i++) {
        const pathData = voronoi.renderCell(i);
        if (!pathData) continue;

        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', pathData);
        path.setAttribute('class', 'voronoi-cell live-preview');
        path.style.vectorEffect = 'non-scaling-stroke';
        fragment.appendChild(path);
      }
      cellsLayer.appendChild(fragment);

      // Store a flag so onPointerUp can restore permanent cells
      this._livePreviewActive = true;
    } catch (e) {
      // Silently fail if d3 computation fails
    }
  }

  /**
   * Show a 2x2 tiling preview of the current cells
   * @param {Array} cells - cell array from state
   * @param {Object} bounds - {minx, miny, maxx, maxy} of boundary
   * @param {boolean} show - whether to show or hide
   */
  renderTilePreview(cells, bounds, show) {
    let tileLayer = document.getElementById('tile-preview-layer');
    if (!show) {
      if (tileLayer) tileLayer.innerHTML = '';
      return;
    }
    if (!tileLayer) {
      tileLayer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      tileLayer.setAttribute('id', 'tile-preview-layer');
      // Insert before cells layer so it renders behind
      this.canvasGroup.insertBefore(tileLayer, this.cellsLayer);
    }
    tileLayer.innerHTML = '';

    if (!cells || cells.length === 0) return;

    let b = bounds;
    if (Array.isArray(b) && b.length >= 4) {
      b = { minx: b[0], miny: b[1], maxx: b[2], maxy: b[3] };
    } else if (b && typeof b === 'object' && b.minx !== undefined && b.maxx !== undefined) {
      b = { minx: b.minx, miny: b.miny, maxx: b.maxx, maxy: b.maxy };
    } else if (this.worldBounds) {
      b = this.worldBounds;
    }

    if (!b || isNaN(b.minx) || isNaN(b.maxx) || isNaN(b.miny) || isNaN(b.maxy)) return;

    const W = b.maxx - b.minx;
    const H = b.maxy - b.miny;
    if (W <= 0 || H <= 0) return;

    // Draw 3x3 grid of tiles (center + 8 neighbors), with lower opacity for neighbors
    const offsets = [
      [0, 0], [W, 0], [-W, 0], [0, H], [0, -H],
      [W, H], [-W, H], [W, -H], [-W, -H]
    ];

    offsets.forEach(([dx, dy], tileIdx) => {
      if (tileIdx === 0) return; // skip center (already drawn in cells-layer)
      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.setAttribute('opacity', '0.35');

      cells.forEach(cell => {
        if (!cell.coords || cell.coords.length < 3) return;
        const shifted = cell.coords.map(([x, y]) => [x + dx, y + dy]);
        const d = 'M ' + shifted.map(([x, y]) => `${x},${-y}`).join(' L ') + ' Z';
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', d);
        path.setAttribute('class', 'voronoi-cell tile-ghost');
        path.style.vectorEffect = 'non-scaling-stroke';
        g.appendChild(path);
      });
      tileLayer.appendChild(g);
    });
  }

  /* ------------------------------------------------------------------------
     6. Cell Selection & Deletion
     ------------------------------------------------------------------------ */

  /**
   * Toggle or set cell selection
   * @param {string} cellId
   * @param {boolean} multi - Whether multi-select is active
   */
  toggleCellSelection(cellId, multi) {
    const el = this.cellsLayer.querySelector(`[data-id="${cellId}"]`);
    if (!el) return;

    if (!multi) {
      if (this.selectedCellIds.has(cellId)) {
        // Toggle off if already selected
        this.deselectAll();
      } else {
        // Clear previous selections and select this one
        this.deselectAll();
        this.selectedCellIds.add(cellId);
        el.classList.add('selected');
      }
    } else {
      if (this.selectedCellIds.has(cellId)) {
        this.selectedCellIds.delete(cellId);
        el.classList.remove('selected');
      } else {
        this.selectedCellIds.add(cellId);
        el.classList.add('selected');
      }
    }

    if (this.selectionChangeCallback) {
      this.selectionChangeCallback(this.selectedCellIds.size);
    }
  }

  /**
   * Deselect all currently selected cells
   */
  deselectAll() {
    this.selectedCellIds.clear();
    const selectedElements = this.cellsLayer.querySelectorAll('.voronoi-cell.selected');
    selectedElements.forEach((el) => el.classList.remove('selected'));

    if (this.selectionChangeCallback) {
      this.selectionChangeCallback(0);
    }
  }

  /**
   * Handle right-click on a cell (delete immediately)
   * @param {string} cellId
   * @param {number} seedIdx
   */
  handleCellRightClick(cellId, seedIdx) {
    if (this.cellDeletedCallback) {
      this.cellDeletedCallback([cellId], [seedIdx]);
    }
  }

  /**
   * Delete all selected cells
   */
  deleteSelectedCells() {
    if (this.patternType !== 'voronoi') return;
    if (this.selectedCellIds.size === 0) return;

    const cellIds = Array.from(this.selectedCellIds);
    const seedIndices = [];

    cellIds.forEach((id) => {
      const el = this.cellsLayer.querySelector(`[data-id="${id}"]`);
      if (el) {
        const seedIdx = parseInt(el.getAttribute('data-seed-idx'), 10);
        if (!isNaN(seedIdx)) {
          seedIndices.push(seedIdx);
        }
      }
    });

    this.deselectAll();

    if (this.cellDeletedCallback) {
      this.cellDeletedCallback(cellIds, seedIndices);
    }
  }

  /**
   * Set active pattern type and update drag/select state
   * @param {string} type - 'voronoi' | 'hexagon' | 'triangle' | 'square'
   */
  setPatternType(type) {
    this.patternType = type || 'voronoi';
    this.wrapper.classList.toggle('mode-pattern-draggable', this.patternType !== 'voronoi');
    if (this.patternType !== 'voronoi') {
      this.deselectAll();
    }
  }

  /* ------------------------------------------------------------------------
     7. Utilities & Layer Controls
     ------------------------------------------------------------------------ */

  /**
   * Toggle visibility of seed points layer
   * @param {boolean} visible
   */
  toggleSeedVisibility(visible) {
    this.showSeeds = visible;
    this.seedsLayer.style.display = visible ? 'block' : 'none';
    if (visible && this.seedsLayer.children.length === 0 && this.seedPoints && this.seedPoints.length > 0) {
      this.renderSeeds(this.seedPoints);
    }
  }

  /**
   * Set editing mode ('select' | 'edit')
   * @param {string} mode
   */
  setMode(mode) {
    this.mode = mode;
    this.wrapper.classList.remove('mode-select', 'mode-edit');
    this.wrapper.classList.add(`mode-${mode}`);
  }

  clearCells() {
    this.cellsLayer.innerHTML = '';
    this.cells = [];
  }

  clearSeeds() {
    this.seedsLayer.innerHTML = '';
  }

  clearAll() {
    this.clearCells();
    this.clearSeeds();
    this.boundaryLayer.innerHTML = '';
    this.selectedCellIds.clear();
  }

  /* ------------------------------------------------------------------------
     8. Callback Registration
     ------------------------------------------------------------------------ */

  onSeedMoved(callback) {
    this.seedMovedCallback = callback;
  }

  onCellDeleted(callback) {
    this.cellDeletedCallback = callback;
  }

  onCursorMove(callback) {
    this.cursorMoveCallback = callback;
  }

  onSelectionChange(callback) {
    this.selectionChangeCallback = callback;
  }

  onZoomChange(callback) {
    this.zoomChangeCallback = callback;
  }

  onBackgroundClick(callback) {
    this.backgroundClickCallback = callback;
  }

  onAddSeed(callback) {
    this.addSeedCallback = callback;
  }

  onPatternDragEnd(callback) {
    this.patternDragEndCallback = callback;
  }

  setAddSeedMode(enabled) {
    this.isAddSeedMode = enabled;
    this.wrapper.classList.toggle('mode-add-seed', enabled);
  }
}

// Export to window
window.CanvasManager = CanvasManager;
