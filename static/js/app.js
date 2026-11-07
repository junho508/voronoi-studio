/**
 * app.js - Main Application Controller for Voronoi Pattern Studio
 * Coordinates state, UI events, API requests, canvas rendering,
 * real-time parameter syncing, and undo/redo history.
 */

class VoronoiApp {
  constructor() {
    this.state = {
      boundaries: [],          // Boundary polygons: [{ id, coords:[[x,y],...], bounds, area }]
      selectedBoundaryIds: [], // IDs of currently selected boundaries
      seedPoints: null,        // Custom/current seed points [[x,y],...] or null for auto
      cells: [],               // Current Voronoi / parametric cells [{coords, seed_idx, id}]
      manualEdits: false,      // Whether user has manually dragged seeds or deleted cells
      history: [],             // Undo stack: [{ cells, seedPoints, manualEdits }]
      boundaryMode: 'rect', // 'rect' | 'dxf'
      patternOffsetX: 0,       // Pan offset X for regular patterns (Hex, Tri, Square) in mm
      patternOffsetY: 0,       // Pan offset Y for regular patterns (Hex, Tri, Square) in mm
    };

    // Instantiate SVG Canvas Manager
    this.canvas = new CanvasManager('main-svg');

    // Auto-update debounce timer (400ms)
    this.autoUpdateTimer = null;

    // Region list data from loaded DXF
    this.dxfRegions = [];
  }

  /**
   * Main initialization
   */
  init() {
    this.setupTabs();
    this.setupBoundaryControls();
    this.setupPatternControls();
    this.setupToolbarControls();
    this.setupExportControls();
    this.setupKeyboardShortcuts();
    this.setupCanvasCallbacks();
    this.setupNewFeatures();

    // Default: Apply initial 100x100mm rectangle boundary
    this.applyRectangle(false);

    // Initial pattern generation so canvas is immediately alive
    this.generate(false);

    // Initial zoom fit after brief layout settlement
    setTimeout(() => {
      this.canvas.fitToContent();
    }, 150);

    this._updateModeIndicator('rect');
  }

  /* ------------------------------------------------------------------------
     1. Tab Navigation
     ------------------------------------------------------------------------ */
  setupTabs() {
    const tabButtons = document.querySelectorAll('.tab-btn');
    const indicator = document.getElementById('tab-indicator');

    tabButtons.forEach((btn, index) => {
      btn.addEventListener('click', () => {
        const tabId = btn.getAttribute('data-tab');
        this.showTab(tabId, index);
      });
    });
  }

  showTab(tabId, index) {
    // Update active tab buttons
    const tabButtons = document.querySelectorAll('.tab-btn');
    tabButtons.forEach((btn) => btn.classList.remove('active'));

    const activeBtn = document.querySelector(`[data-tab="${tabId}"]`);
    if (activeBtn) activeBtn.classList.add('active');

    // Slide indicator
    const indicator = document.getElementById('tab-indicator');
    if (indicator) {
      const idx = index !== undefined ? index : Array.from(tabButtons).indexOf(activeBtn);
      indicator.style.transform = `translateX(${idx * 100}%)`;
    }

    // Toggle tab panes
    const panes = document.querySelectorAll('.tab-pane');
    panes.forEach((pane) => {
      pane.classList.remove('active');
      if (pane.id === tabId) {
        pane.classList.add('active');
      }
    });
  }

  /* ------------------------------------------------------------------------
     2. Boundary Setup (Rectangle & DXF Parsing)
     ------------------------------------------------------------------------ */
  setupBoundaryControls() {
    // Apply Rectangle Boundary Button
    const btnApplyRect = document.getElementById('btn-apply-rect');
    if (btnApplyRect) {
      btnApplyRect.addEventListener('click', () => {
        this.applyRectangle(true);
      });
    }

    // DXF Drag & Drop Zone
    const dropZone = document.getElementById('dxf-drop-zone');
    const fileInput = document.getElementById('dxf-file-input');

    if (dropZone && fileInput) {
      dropZone.addEventListener('click', () => fileInput.click());

      dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
      });

      dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
      });

      dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
          this.loadDxf(e.dataTransfer.files[0]);
        }
      });

      fileInput.addEventListener('change', () => {
        if (fileInput.files && fileInput.files.length > 0) {
          const selectedFile = fileInput.files[0];
          fileInput.value = '';
          this.loadDxf(selectedFile);
        }
      });
    }

    // Select/Deselect All Regions
    const btnSelectAll = document.getElementById('btn-select-all-regions');
    const btnDeselectAll = document.getElementById('btn-deselect-all-regions');
    const btnApplyRegions = document.getElementById('btn-apply-regions');

    if (btnSelectAll) {
      btnSelectAll.addEventListener('click', () => {
        const checkboxes = document.querySelectorAll('#region-list input[type="checkbox"]');
        checkboxes.forEach((cb) => (cb.checked = true));
      });
    }

    if (btnDeselectAll) {
      btnDeselectAll.addEventListener('click', () => {
        const checkboxes = document.querySelectorAll('#region-list input[type="checkbox"]');
        checkboxes.forEach((cb) => (cb.checked = false));
      });
    }

    if (btnApplyRegions) {
      btnApplyRegions.addEventListener('click', () => {
        this.applySelectedRegions();
      });
    }
  }

  /**
   * Apply a rectangular boundary from width and height inputs
   * @param {boolean} triggerGenerate - Whether to trigger pattern generation immediately
   */
  applyRectangle(triggerGenerate = true) {
    // Switch to rect mode and clear any DXF data
    this.state.boundaryMode = 'rect';
    this._updateModeIndicator('rect');
    this.dxfRegions = [];
    const regionListWrapper = document.getElementById('region-list-wrapper');
    if (regionListWrapper) regionListWrapper.style.display = 'none';
    const regionList = document.getElementById('region-list');
    if (regionList) regionList.innerHTML = '';
    const fileInput = document.getElementById('dxf-file-input');
    if (fileInput) fileInput.value = '';
    const badge = document.getElementById('region-count-badge');
    if (badge) badge.textContent = '감지된 영역: 0개';

    // Clear backend memory state so DXF data is eliminated
    API.resetState();

    // Clear existing canvas content completely  
    this.state.cells = [];
    this.state.seedPoints = null;
    this.state.history = [];
    this.state.patternOffsetX = 0;
    this.state.patternOffsetY = 0;
    this.canvas.clearAll();

    const w = parseFloat(document.getElementById('input-rect-width').value) || 100;
    const h = parseFloat(document.getElementById('input-rect-height').value) || 100;

    // Create 4-corner rectangle polygon (CAD Y-up: [0,0] bottom-left to [w,h] top-right)
    const coords = [
      [0, 0],
      [w, 0],
      [w, h],
      [0, h],
      [0, 0],
    ];

    const rectBoundary = {
      id: 'rect_default',
      coords: coords,
      bounds: { minx: 0, miny: 0, maxx: w, maxy: h },
      area: w * h,
    };

    this.state.boundaries = [rectBoundary];
    this.state.selectedBoundaryIds = ['rect_default'];
    this.state.manualEdits = false;
    this.state.seedPoints = null;
    this.updateCellSizeHint();

    // Render boundary on canvas immediately
    this.canvas.renderBoundary(this.state.boundaries);
    this.canvas.fitToContent();

    if (triggerGenerate) {
      this.showToast(`사각형 경계 적용 완료 (${w} × ${h} mm)`, 'success');
      this.generate(false);
    }
  }

  /**
   * Load and parse DXF file via API
   * @param {File} file
   */
  async loadDxf(file) {
    if (!file.name.toLowerCase().endsWith('.dxf')) {
      this.showToast('DXF 파일(.dxf)만 업로드할 수 있습니다.', 'error');
      return;
    }

    this.showLoading(true, 'DXF 파일 분석 중...');

    // Switch to DXF mode
    this.state.boundaryMode = 'dxf';
    this._updateModeIndicator('dxf');
    // Clear any existing rect-based pattern
    this.state.cells = [];
    this.state.seedPoints = null;
    this.state.manualEdits = false;
    this.canvas.clearCells();
    this.canvas.clearSeeds();

    try {
      const res = await API.parseDxf(file);
      if (!res.regions || res.regions.length === 0) {
        throw new Error('DXF 파일에서 닫힌 폐곡선(Closed Loop) 영역을 찾지 못했습니다.');
      }

      this.dxfRegions = res.regions;
      this.renderRegionList(res.regions);

      // Auto-select and apply all regions initially
      this.state.boundaries = res.regions;
      this.state.selectedBoundaryIds = res.regions.map((r) => r.id);
      this.state.manualEdits = false;
      this.state.seedPoints = null;
      this.updateCellSizeHint();

      this.canvas.renderBoundary(this.state.boundaries);
      this.canvas.fitToContent();

      this.showToast(`${res.regions.length}개의 경계 영역을 불러왔습니다.`, 'success');
      this.generate(false);
    } catch (err) {
      this.showToast(err.message, 'error');
    } finally {
      this.showLoading(false);
    }
  }

  /**
   * Render detected DXF regions into the left sidebar list
   * @param {Array<Object>} regions
   */
  renderRegionList(regions) {
    const wrapper = document.getElementById('region-list-wrapper');
    const list = document.getElementById('region-list');
    const badge = document.getElementById('region-count-badge');

    if (!wrapper || !list) return;

    wrapper.style.display = 'flex';
    list.innerHTML = '';
    if (badge) badge.textContent = `감지된 영역: ${regions.length}개`;

    regions.forEach((region, index) => {
      const item = document.createElement('div');
      item.className = 'region-item';

      let b = region.bounds;
      if (Array.isArray(b) && b.length >= 4) {
        b = { minx: b[0], miny: b[1], maxx: b[2], maxy: b[3] };
      }
      const w = b && !isNaN(b.maxx - b.minx) ? (b.maxx - b.minx).toFixed(1) : '-';
      const h = b && !isNaN(b.maxy - b.miny) ? (b.maxy - b.miny).toFixed(1) : '-';
      const area = region.area ? Math.round(region.area) : '-';

      item.innerHTML = `
        <label class="custom-checkbox-label" style="flex:1;">
          <input type="checkbox" data-region-id="${region.id}" checked>
          <span class="checkbox-box"></span>
          <span class="region-label">영역 #${index + 1} (${w}×${h}mm)</span>
        </label>
        <span class="region-badge">${area} mm²</span>
      `;

      list.appendChild(item);
    });
  }

  /**
   * Apply only checked regions from region list as current boundaries
   */
  applySelectedRegions() {
    const checkboxes = document.querySelectorAll('#region-list input[type="checkbox"]:checked');
    const selectedIds = Array.from(checkboxes).map((cb) => cb.getAttribute('data-region-id'));

    if (selectedIds.length === 0) {
      this.showToast('적용할 영역을 최소 1개 이상 선택하세요.', 'error');
      return;
    }

    const selectedBoundaries = this.dxfRegions.filter((r) => selectedIds.includes(String(r.id)));

    this.state.boundaries = selectedBoundaries;
    this.state.selectedBoundaryIds = selectedIds;
    this.state.manualEdits = false;
    this.state.seedPoints = null;
    this.updateCellSizeHint();

    this.canvas.renderBoundary(this.state.boundaries);
    this.canvas.fitToContent();

    this.showToast(`${selectedBoundaries.length}개 영역이 경계로 적용되었습니다.`, 'success');
    this.generate(false);
  }

  /* ------------------------------------------------------------------------
     3. Pattern Parameters & Controls
     ------------------------------------------------------------------------ */
  setupPatternControls() {
    // Pattern Type Radios
    const patternRadios = document.querySelectorAll('input[name="pattern_type"]');
    patternRadios.forEach((radio) => {
      radio.addEventListener('change', (e) => {
        this.onPatternTypeChange(e.target.value);
      });
    });

    // Cell / Edge Style Radios (Line vs Spline)
    const styleRadios = document.querySelectorAll('input[name="cell_style"]');
    styleRadios.forEach((radio) => {
      radio.addEventListener('change', (e) => {
        this.onCellStyleChange(e.target.value);
      });
    });

    // Spline Subtype Radios (Pebble vs Lattice)
    const splineTypeRadios = document.querySelectorAll('input[name="spline_type"]');
    splineTypeRadios.forEach((radio) => {
      radio.addEventListener('change', () => {
        this.scheduleAutoUpdate();
      });
    });

    // Synchronize Range Sliders & Number Steppers
    this.syncRangeNumber('input-density', 'input-density-num', () => this.resetManualEdits());
    this.syncRangeNumber('input-cell-size', 'input-cell-size-num', () => {
      this.updateCellSizeHint();
      this.resetManualEdits();
    });
    this.syncRangeNumber('input-boundary-offset', 'input-boundary-offset-num');
    this.syncRangeNumber('input-cell-gap', 'input-cell-gap-num');
    this.syncRangeNumber('input-corner-radius', 'input-corner-radius-num');
    this.syncRangeNumber('input-smoothness', 'input-smoothness-num');

    // Jitter Range & Label
    const jitterRange = document.getElementById('input-jitter');
    const jitterVal = document.getElementById('val-jitter');
    if (jitterRange && jitterVal) {
      jitterRange.addEventListener('input', () => {
        jitterVal.textContent = parseFloat(jitterRange.value).toFixed(2);
        this.resetManualEdits();
        this.scheduleAutoUpdate();
      });
    }

    this.syncRangeNumber('input-lloyd', 'input-lloyd-num', () => this.resetManualEdits());
    this.syncRangeNumber('input-rotation', 'input-rotation-num', () => this.resetManualEdits());

    // Seed Input & Randomize Button
    const seedInput = document.getElementById('input-seed');
    const btnRandomSeed = document.getElementById('btn-random-seed');
    if (seedInput) {
      seedInput.addEventListener('input', () => {
        this.resetManualEdits();
        this.scheduleAutoUpdate();
      });
    }
    if (btnRandomSeed && seedInput) {
      btnRandomSeed.addEventListener('click', () => {
        seedInput.value = Math.floor(Math.random() * 9000) + 1000;
        this.resetManualEdits();
        this.generate(false);
      });
    }

    // Generate Button
    const btnGenerate = document.getElementById('btn-generate');
    if (btnGenerate) {
      btnGenerate.addEventListener('click', () => {
        this.generate(this.state.manualEdits);
      });
    }
  }

  /**
   * Helper to synchronize an <input type="range"> and <input type="number"> two-way
   */
  syncRangeNumber(rangeId, numId, onReset) {
    const range = document.getElementById(rangeId);
    const num = document.getElementById(numId);
    if (!range || !num) return;

    range.addEventListener('input', () => {
      num.value = range.value;
      if (onReset) onReset();
      this.scheduleAutoUpdate();
    });

    num.addEventListener('input', () => {
      range.value = num.value;
      if (onReset) onReset();
      this.scheduleAutoUpdate();
    });
  }

  /**
   * Update the estimated cell count hint under cell-size slider
   * @param {number} [adaptedCellSize] - Optional adapted cell size from backend for seamless tiling
   */
  updateCellSizeHint(adaptedCellSize) {
    const hint = document.getElementById('cell-size-hint');
    if (!hint) return;
    const cellSize = parseFloat(document.getElementById('input-cell-size')?.value) || 15;
    let totalArea = 0;
    if (this.state.boundaries && this.state.boundaries.length > 0) {
      totalArea = this.state.boundaries
        .filter((b) => this.state.selectedBoundaryIds.includes(b.id))
        .reduce((sum, b) => sum + (b.area || 0), 0);
    }
    if (totalArea <= 0) totalArea = 10000; // default 100x100 mm

    const effSize = adaptedCellSize || cellSize;
    const approxCount = Math.max(4, Math.round(totalArea / (0.866 * effSize * effSize)));

    const isSeamless = document.getElementById('toggle-seamless')?.checked || false;
    const patternType = document.querySelector('input[name="pattern_type"]:checked')?.value || 'voronoi';

    if (isSeamless && adaptedCellSize && patternType !== 'voronoi') {
      hint.textContent = `예상 약 ${approxCount}개 (타일링 보정: ${adaptedCellSize.toFixed(1)}mm)`;
    } else {
      hint.textContent = `예상 약 ${approxCount}개`;
    }
  }

  /**
   * Called when cell edge style changes (Line vs Spline)
   * @param {string} style - 'line' | 'spline'
   */
  onCellStyleChange(style) {
    const groupSmoothness = document.getElementById('group-smoothness');
    const groupSplineType = document.getElementById('group-spline-type');
    if (groupSplineType) {
      groupSplineType.style.display = (style === 'spline') ? 'block' : 'none';
    }
    if (groupSmoothness) {
      if (style === 'spline') {
        groupSmoothness.style.display = 'block';
        // If smoothness is currently 0, initialize to 50 so user immediately sees smooth curves
        const smInput = document.getElementById('input-smoothness');
        const smNum = document.getElementById('input-smoothness-num');
        if (smInput && parseFloat(smInput.value) === 0) {
          smInput.value = '50';
          if (smNum) smNum.value = '50';
        }
      } else {
        groupSmoothness.style.display = 'none';
      }
    }
    this.scheduleAutoUpdate();
  }

  /**
   * Called when pattern type changes
   * @param {string} type - 'voronoi' | 'hexagon' | 'triangle' | 'square'
   */
  onPatternTypeChange(type) {
    const groupJitter = document.getElementById('group-jitter');
    const groupCellSize = document.getElementById('group-cell-size');
    const groupLloyd = document.getElementById('group-lloyd');
    const groupSeed = document.getElementById('group-seed');
    const toolbarGroupSeeds = document.getElementById('toolbar-group-seeds');
    const toolbarDividerSeeds = document.getElementById('toolbar-divider-seeds');
    const toggleSeeds = document.getElementById('toggle-seeds');

    if (groupCellSize) groupCellSize.style.display = 'flex';

    if (type === 'voronoi') {
      if (groupJitter) groupJitter.style.display = 'flex';
      if (groupLloyd) groupLloyd.style.display = 'flex';
      if (groupSeed) groupSeed.style.display = 'flex';
      if (toolbarGroupSeeds) toolbarGroupSeeds.style.display = 'flex';
      if (toolbarDividerSeeds) toolbarDividerSeeds.style.display = 'block';
      if (toggleSeeds) {
        this.canvas.toggleSeedVisibility(toggleSeeds.checked);
      }
    } else {
      // Regular parametric grids: hexagon, triangle, square
      if (groupJitter) groupJitter.style.display = 'none';
      if (groupLloyd) groupLloyd.style.display = 'none';
      if (groupSeed) groupSeed.style.display = 'none';
      if (toolbarGroupSeeds) toolbarGroupSeeds.style.display = 'none';
      if (toolbarDividerSeeds) toolbarDividerSeeds.style.display = 'none';
      this.canvas.clearSeeds();
      this.canvas.toggleSeedVisibility(false);
    }

    this.state.patternOffsetX = 0;
    this.state.patternOffsetY = 0;
    this.canvas.setPatternType(type);

    // Toggle shortcut guidance for Voronoi vs regular patterns
    const voronoiShortcuts = document.querySelectorAll('.shortcut-voronoi');
    const regularShortcuts = document.querySelectorAll('.shortcut-regular');
    voronoiShortcuts.forEach((el) => {
      el.style.display = type === 'voronoi' ? 'flex' : 'none';
    });
    regularShortcuts.forEach((el) => {
      el.style.display = type !== 'voronoi' ? 'flex' : 'none';
    });

    this.updateCellSizeHint();
    this.resetManualEdits();
    this.scheduleAutoUpdate();
  }

  /**
   * Reset manual edits flag when generative parameters change
   */
  resetManualEdits() {
    this.state.manualEdits = false;
    this.state.seedPoints = null;
  }

  /* ------------------------------------------------------------------------
     4. Canvas Toolbar Controls & Callbacks
     ------------------------------------------------------------------------ */
  setupToolbarControls() {
    // Listen for add seed event ('+' or '=' key at mouse cursor)
    this.canvas.onAddSeed((wx, wy) => {
      this._addSeedPoint(wx, wy);
    });

    // Toggle Seed Points Visibility
    const toggleSeeds = document.getElementById('toggle-seeds');
    if (toggleSeeds) {
      toggleSeeds.addEventListener('change', (e) => {
        this.canvas.toggleSeedVisibility(e.target.checked);
      });
    }

    // Zoom Controls
    const btnZoomFit = document.getElementById('btn-zoom-fit');
    const btnZoomIn = document.getElementById('btn-zoom-in');
    const btnZoomOut = document.getElementById('btn-zoom-out');
    const btnUndo = document.getElementById('btn-undo');

    if (btnZoomFit) btnZoomFit.addEventListener('click', () => this.canvas.fitToContent());
    if (btnZoomIn) btnZoomIn.addEventListener('click', () => this.canvas.zoomTo(1.25));
    if (btnZoomOut) btnZoomOut.addEventListener('click', () => this.canvas.zoomTo(0.8));
    if (btnUndo) btnUndo.addEventListener('click', () => this.undo());
  }

  /**
   * Wire CanvasManager callbacks to VoronoiApp handlers
   */
  setupCanvasCallbacks() {
    // Seed dragged
    this.canvas.onSeedMoved((idx, newPos) => {
      this.onSeedMoved(idx, newPos);
    });

    // Cell deleted via contextmenu or Delete key
    this.canvas.onCellDeleted((cellIds, seedIndices) => {
      this.onCellDeleted(cellIds, seedIndices);
    });

    // Cursor coordinates update
    this.canvas.onCursorMove((wx, wy) => {
      const el = document.getElementById('status-coords');
      if (el) {
        el.textContent = `X: ${wx.toFixed(2)} mm | Y: ${wy.toFixed(2)} mm`;
      }
    });

    // Zoom level update
    this.canvas.onZoomChange((scale) => {
      const zoomText = `${Math.round(scale * 25)}%`; // normalized percentage
      const zoomDisplay = document.getElementById('zoom-display');
      const statusZoom = document.getElementById('status-zoom');
      if (zoomDisplay) zoomDisplay.textContent = zoomText;
      if (statusZoom) statusZoom.textContent = zoomText;
    });

    // Selection count update
    this.canvas.onSelectionChange((count) => {
      const el = document.getElementById('status-selected');
      if (el) {
        el.textContent = `선택: ${count}개`;
      }
    });

    // Pattern drag callback (Hexagon, Triangle, Square)
    this.canvas.onPatternDragEnd((dxMm, dyMm) => {
      this.state.patternOffsetX = (this.state.patternOffsetX || 0) + dxMm;
      this.state.patternOffsetY = (this.state.patternOffsetY || 0) + dyMm;
      this.generate(false);
    });
  }

  /* ------------------------------------------------------------------------
     5. Export Controls
     ------------------------------------------------------------------------ */
  setupExportControls() {
    const btnExport = document.getElementById('btn-export-dxf');
    if (btnExport) {
      btnExport.addEventListener('click', () => {
        this.exportDxf();
      });
    }
  }

  /**
   * Export generated pattern to DXF file
   */
  async exportDxf() {
    if (!this.state.cells || this.state.cells.length === 0) {
      this.showToast('내보낼 생성된 셀이 없습니다.', 'error');
      return;
    }

    const includeBoundary = document.getElementById('export-include-boundary').checked;
    const filenameInput = document.getElementById('export-filename');
    const filename = filenameInput ? filenameInput.value.trim() : 'voronoi_pattern';

    const selected = this.state.boundaries.filter((b) =>
      this.state.selectedBoundaryIds.includes(b.id)
    );
    const boundaryCoords = selected.length === 1 ? selected[0].coords : selected.map((b) => b.coords);

    const cornerRadius = parseFloat(document.getElementById('input-corner-radius')?.value) || 0;
    const cellStyle = document.querySelector('input[name="cell_style"]:checked')?.value || 'line';
    const splineType = document.querySelector('input[name="spline_type"]:checked')?.value || 'pebble';

    const payload = {
      cells: this.state.cells,
      boundary: boundaryCoords,
      include_boundary: includeBoundary,
      filename: filename,
      corner_radius: cornerRadius,
      cell_style: cellStyle,
      spline_type: splineType,
    };

    this.showLoading(true, 'DXF 파일 내보내는 중...');

    try {
      const result = await API.exportDxf(payload);
      this.showToast(`DXF 파일 다운로드 완료: ${result.filename}`, 'success');
    } catch (err) {
      this.showToast(err.message, 'error');
    } finally {
      this.showLoading(false);
    }
  }

  /* ------------------------------------------------------------------------
     6. Pattern Generation Engine
     ------------------------------------------------------------------------ */

  /**
   * Extract all generation parameters from UI controls
   * @returns {Object} params
   */
  getParams() {
    const patternTypeEl = document.querySelector('input[name="pattern_type"]:checked');
    const patternType = patternTypeEl ? patternTypeEl.value : 'voronoi';

    const cellStyleEl = document.querySelector('input[name="cell_style"]:checked');
    const cellStyle = cellStyleEl ? cellStyleEl.value : 'line';

    const splineTypeEl = document.querySelector('input[name="spline_type"]:checked');
    const splineType = splineTypeEl ? splineTypeEl.value : 'pebble';

    const density = parseFloat(document.getElementById('input-density-num')?.value ?? document.getElementById('input-density')?.value) || 0.5;
    const cellSize = parseFloat(document.getElementById('input-cell-size-num')?.value ?? document.getElementById('input-cell-size')?.value) || 15;
    const seed = parseInt(document.getElementById('input-seed')?.value, 10) || 42;
    const rawJitter = parseFloat(document.getElementById('input-jitter')?.value);
    const jitter = isNaN(rawJitter) ? 0.7 : Math.max(0, Math.min(1, rawJitter));
    const lloydIterations = parseInt(document.getElementById('input-lloyd-num')?.value ?? document.getElementById('input-lloyd')?.value, 10) || 0;
    const rotation = parseFloat(document.getElementById('input-rotation-num')?.value ?? document.getElementById('input-rotation')?.value) || 0;
    const boundaryOffset = parseFloat(document.getElementById('input-boundary-offset-num')?.value ?? document.getElementById('input-boundary-offset')?.value) || 0;
    const rawGap = parseFloat(document.getElementById('input-cell-gap-num')?.value ?? document.getElementById('input-cell-gap')?.value);
    const cellGap = isNaN(rawGap) ? 0.5 : Math.max(0, rawGap);
    const cornerRadius = parseFloat(document.getElementById('input-corner-radius-num')?.value ?? document.getElementById('input-corner-radius')?.value) || 0;
    const smoothness = parseFloat(document.getElementById('input-smoothness-num')?.value ?? document.getElementById('input-smoothness')?.value) || 0;

    const selected = this.state.boundaries.filter((b) =>
      this.state.selectedBoundaryIds.includes(b.id)
    );
    const boundaryCoords = selected.length === 1 ? selected[0].coords : selected.map((b) => b.coords);

    const params = {
      boundaries: selected,
      boundary: boundaryCoords,
      regions: selected,
      pattern_type: patternType,
      cell_style: cellStyle,
      spline_type: splineType,
      density: density,
      cell_size: cellSize,
      seed: seed,
      jitter: jitter,
      lloyd_iterations: lloydIterations,
      rotation: rotation,
      boundary_offset: boundaryOffset,
      cell_gap: cellGap,
      corner_radius: cornerRadius,
      smoothness: smoothness,
      pattern_offset_x: this.state.patternOffsetX || 0,
      pattern_offset_y: this.state.patternOffsetY || 0,
      seamless: document.getElementById('toggle-seamless')?.checked || false,
    };

    if (this.state.manualEdits && this.state.seedPoints && this.state.seedPoints.length > 0) {
      params.seed_points = this.state.seedPoints;
    }

    return params;
  }

  /**
   * Request pattern generation from backend and render results
   * @param {boolean} useSeedPoints - Whether to reuse current seed points
   */
  async generate(useSeedPoints = false) {
    if (useSeedPoints && this.state.seedPoints) {
      this.state.manualEdits = true;
    }

    const params = this.getParams();
    this.showLoading(true, '패턴 생성 중...');

    try {
      const res = await API.generate(params);

      if (!res.cells || !Array.isArray(res.cells)) {
        throw new Error('생성된 셀 데이터가 올바르지 않습니다.');
      }

      // Record snapshot to undo history
      this.pushHistory();

      // Update state
      this.state.cells = res.cells;
      this.state.seedPoints = res.seed_points || this.state.seedPoints || [];

      // Render to SVG Canvas
      this.canvas.renderCells(this.state.cells, params.pattern_type);
      this.canvas.renderSeeds(this.state.seedPoints);

      // Update boundary for live drag preview
      if (this.state.boundaries.length > 0) {
        this.canvas.setLiveBoundary(this.state.boundaries[0].coords);
      }
      // Refresh tile preview if active
      const toggleTilePreview = document.getElementById('toggle-tile-preview');
      if (toggleTilePreview && toggleTilePreview.checked) {
        const bounds = this.canvas.worldBounds || (this.state.boundaries.length > 0 ? this.state.boundaries[0].bounds : null);
        this.canvas.renderTilePreview(this.state.cells, bounds, true);
      }

      // Update status bar
      this.updateStatus();
      this.updateCellSizeHint(res.adapted_cell_size);
    } catch (err) {
      this.showToast(err.message, 'error');
    } finally {
      this.showLoading(false);
    }
  }

  /**
   * Debounced auto-update (400ms delay) triggered on parameter change
   */
  scheduleAutoUpdate() {
    const autoToggle = document.getElementById('toggle-auto-update');
    if (!autoToggle || !autoToggle.checked) return;

    if (this.autoUpdateTimer) {
      clearTimeout(this.autoUpdateTimer);
    }

    this.autoUpdateTimer = setTimeout(() => {
      this.generate(this.state.manualEdits);
    }, 400);
  }

  /* ------------------------------------------------------------------------
     7. Interactive Editing (Seed Drag & Cell Delete)
     ------------------------------------------------------------------------ */

  /**
   * Handle seed point drag completion
   * @param {number} idx - Index of dragged seed
   * @param {Array<number>} newPos - [x, y] in mm
   */
  onSeedMoved(idx, newPos) {
    if (!this.state.seedPoints) return;

    this.state.seedPoints[idx] = newPos;
    this.state.manualEdits = true;

    // Trigger re-generation with updated seed points
    this.scheduleAutoUpdate();
  }

  /**
   * Handle cell deletion (right-click or Delete key)
   * @param {Array<string>} cellIds
   * @param {Array<number>} seedIndices
   */
  onCellDeleted(cellIds, seedIndices) {
    this.pushHistory();

    // Fallback: If seedPoints array is empty, try to populate from cell seed_points
    if (!this.state.seedPoints || this.state.seedPoints.length === 0) {
      if (this.state.cells && this.state.cells.length > 0) {
        this.state.seedPoints = this.state.cells.map(c => c.seed_point).filter(Boolean);
      }
    }

    if (this.state.seedPoints && seedIndices && seedIndices.length > 0) {
      const deleteSet = new Set(seedIndices);
      this.state.seedPoints = this.state.seedPoints.filter((_, idx) => !deleteSet.has(idx));
      this.state.manualEdits = true;

      // Update points count input in UI
      const nPointsRange = document.getElementById('input-n-points');
      const nPointsNum = document.getElementById('input-n-points-num');
      if (nPointsRange) nPointsRange.value = this.state.seedPoints.length;
      if (nPointsNum) nPointsNum.value = this.state.seedPoints.length;

      // Re-generate using remaining seeds
      this.generate(true);
      this.showToast(`${cellIds.length}개 셀이 삭제되었습니다.`, 'info');
    }
  }

  /* ------------------------------------------------------------------------
     8. Undo History (Ctrl+Z)
     ------------------------------------------------------------------------ */
  pushHistory() {
    if (this.state.cells && this.state.cells.length > 0) {
      this.state.history.push({
        cells: JSON.parse(JSON.stringify(this.state.cells)),
        seedPoints: this.state.seedPoints ? JSON.parse(JSON.stringify(this.state.seedPoints)) : null,
        manualEdits: this.state.manualEdits,
      });

      // Keep max 30 history states
      if (this.state.history.length > 30) {
        this.state.history.shift();
      }
    }
  }

  undo() {
    if (this.state.history.length === 0) {
      this.showToast('실행 취소할 이전 기록이 없습니다.', 'info');
      return;
    }

    const prevState = this.state.history.pop();
    this.state.cells = prevState.cells;
    this.state.seedPoints = prevState.seedPoints;
    this.state.manualEdits = prevState.manualEdits;

    this.canvas.renderCells(this.state.cells);
    this.canvas.renderSeeds(this.state.seedPoints);

    // Sync UI points input if changed
    if (this.state.seedPoints) {
      const nPointsRange = document.getElementById('input-n-points');
      const nPointsNum = document.getElementById('input-n-points-num');
      if (nPointsRange) nPointsRange.value = this.state.seedPoints.length;
      if (nPointsNum) nPointsNum.value = this.state.seedPoints.length;
    }

    this.updateStatus();
    this.showToast('이전 작업으로 실행 취소되었습니다.', 'info');
  }

  setupKeyboardShortcuts() {
    window.addEventListener('keydown', (e) => {
      // Ctrl+Z or Cmd+Z for Undo
      if ((e.ctrlKey || e.metaKey) && (e.key === 'z' || e.key === 'Z')) {
        e.preventDefault();
        this.undo();
      }
    });
  }

  /* ------------------------------------------------------------------------
     9. UI Helpers (Toast & Loading)
     ------------------------------------------------------------------------ */
  showLoading(show, message = '처리 중...') {
    const overlay = document.getElementById('loading-overlay');
    const textEl = document.getElementById('loading-text');

    if (overlay) {
      if (show) {
        if (textEl) textEl.textContent = message;
        overlay.classList.add('active');
      } else {
        overlay.classList.remove('active');
      }
    }
  }

  /**
   * Display slide-in toast notification
   * @param {string} msg - Message to display
   * @param {'success'|'error'|'info'} [type='info']
   */
  showToast(msg, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    let iconSvg = '';
    let title = '알림';

    if (type === 'success') {
      title = '성공';
      iconSvg = `
        <svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
          <polyline points="22 4 12 14.01 9 11.01" />
        </svg>`;
    } else if (type === 'error') {
      title = '오류';
      iconSvg = `
        <svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10" />
          <line x1="15" y1="9" x2="9" y2="15" />
          <line x1="9" y1="9" x2="15" y2="15" />
        </svg>`;
    } else {
      title = '정보';
      iconSvg = `
        <svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="16" x2="12" y2="12" />
          <line x1="12" y1="8" x2="12.01" y2="8" />
        </svg>`;
    }

    toast.innerHTML = `
      ${iconSvg}
      <div class="toast-content">
        <div class="toast-title">${title}</div>
        <div class="toast-msg">${msg}</div>
      </div>
    `;

    container.appendChild(toast);

    // Auto dismiss after 3.8s
    setTimeout(() => {
      toast.classList.add('hiding');
      setTimeout(() => {
        if (toast.parentNode) {
          toast.parentNode.removeChild(toast);
        }
      }, 300);
    }, 3800);
  }

  updateStatus() {
    const el = document.getElementById('status-cells');
    if (el) {
      el.textContent = `셀: ${this.state.cells.length}개`;
    }
  }

  setupNewFeatures() {
    // Reset All button
    const btnReset = document.getElementById('btn-reset-all');
    if (btnReset) btnReset.addEventListener('click', () => this.resetAll());

    // Seamless toggle
    const toggleSeamless = document.getElementById('toggle-seamless');
    if (toggleSeamless) {
      toggleSeamless.addEventListener('change', () => {
        this.scheduleAutoUpdate();
      });
    }

    // Tile preview toggle
    const toggleTilePreview = document.getElementById('toggle-tile-preview');
    if (toggleTilePreview) {
      toggleTilePreview.addEventListener('change', (e) => {
        const bounds = this.canvas.worldBounds || (this.state.boundaries.length > 0 ? this.state.boundaries[0].bounds : null);
        this.canvas.renderTilePreview(this.state.cells, bounds, e.target.checked);
      });
    }
  }

  /**
   * Add a new seed point at given world coordinates
   */
  _addSeedPoint(wx, wy) {
    const patternType = document.querySelector('input[name="pattern_type"]:checked')?.value || 'voronoi';
    if (patternType !== 'voronoi') {
      return; // Seeds only applicable to Voronoi
    }

    if (!this.state.seedPoints) {
      // Initialize from existing cells
      if (this.state.cells && this.state.cells.length > 0) {
        this.state.seedPoints = this.state.cells.map(c => c.seed_point).filter(Boolean);
      } else {
        this.state.seedPoints = [];
      }
    }

    this.pushHistory();
    this.state.seedPoints.push([wx, wy]);
    this.state.manualEdits = true;
    this.generate(true);
    this.showToast(`씨드 포인트 추가: (${wx.toFixed(1)}, ${wy.toFixed(1)}) mm`, 'success');
  }

  /**
   * Full reset: clear everything and return to fresh 100x100mm rectangle state
   */
  async resetAll() {
    // Clear backend memory
    await API.resetState();

    // Reset DXF region list UI and file input
    const fileInput = document.getElementById('dxf-file-input');
    if (fileInput) fileInput.value = '';
    const regionListWrapper = document.getElementById('region-list-wrapper');
    if (regionListWrapper) regionListWrapper.style.display = 'none';
    const regionList = document.getElementById('region-list');
    if (regionList) regionList.innerHTML = '';
    const badge = document.getElementById('region-count-badge');
    if (badge) badge.textContent = '감지된 영역: 0개';

    // Reset to default rect values
    const wInput = document.getElementById('input-rect-width');
    const hInput = document.getElementById('input-rect-height');
    if (wInput) wInput.value = '100';
    if (hInput) hInput.value = '100';

    const smInput = document.getElementById('input-smoothness');
    const smNum = document.getElementById('input-smoothness-num');
    if (smInput) smInput.value = '50';
    if (smNum) smNum.value = '50';

    const lineRadio = document.querySelector('input[name="cell_style"][value="line"]');
    if (lineRadio) lineRadio.checked = true;
    const pebbleRadio = document.querySelector('input[name="spline_type"][value="pebble"]');
    if (pebbleRadio) pebbleRadio.checked = true;
    const groupSmoothness = document.getElementById('group-smoothness');
    if (groupSmoothness) groupSmoothness.style.display = 'none';
    const groupSplineType = document.getElementById('group-spline-type');
    if (groupSplineType) groupSplineType.style.display = 'none';

    // Clear canvas
    this.canvas.clearAll();

    // Apply fresh 100x100 rectangle and generate fresh pattern
    this.applyRectangle(true);

    this.showToast('모든 작업이 초기화되고 기본 사각형으로 새로 시작합니다.', 'info');
  }

  /**
   * Update the boundary mode indicator pills
   */
  _updateModeIndicator(mode) {
    const pillRect = document.getElementById('mode-pill-rect');
    const pillDxf = document.getElementById('mode-pill-dxf');
    if (pillRect) pillRect.classList.toggle('active', mode === 'rect');
    if (pillDxf) pillDxf.classList.toggle('active', mode === 'dxf');
  }
}

// Bootstrap application on DOM ready
window.addEventListener('DOMContentLoaded', () => {
  window.app = new VoronoiApp();
  window.app.init();
});
