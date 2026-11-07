/**
 * api.js - Backend communication module for Voronoi Pattern Studio
 * Communicates with Flask backend at http://localhost:5000
 */

// Dynamically determine API base URL (supports local file, dev servers, or served from Flask directly)
const API_BASE = (window.location.protocol === 'file:' || (window.location.port && window.location.port !== '5000'))
  ? 'http://localhost:5000'
  : '';

const API = {
  /**
   * Reset backend in-memory state
   */
  async resetState() {
    try {
      await fetch(`${API_BASE}/api/reset`, { method: 'POST' });
    } catch (_) {}
  },

  /**
   * Parse a DXF file and extract closed boundary regions
   * @param {File|Blob} file - The DXF file to parse
   * @returns {Promise<{regions: Array<{id: string|number, coords: number[][], area: number, bounds: {minx: number, miny: number, maxx: number, maxy: number}}>}>}
   */
  async parseDxf(file) {
    if (!file) {
      throw new Error('파싱할 DXF 파일을 선택해주세요.');
    }

    const formData = new FormData();
    formData.append('file', file);

    let res;
    try {
      res = await fetch(`${API_BASE}/api/parse-dxf`, {
        method: 'POST',
        body: formData,
      });
    } catch (networkErr) {
      throw new Error(`백엔드 서버에 연결할 수 없습니다 (${networkErr.message}). http://localhost:5000 상태를 확인하세요.`);
    }

    if (!res.ok) {
      let errMsg = `DXF 파일 파싱 실패 (${res.status} ${res.statusText})`;
      try {
        const errData = await res.json();
        if (errData && (errData.error || errData.message)) {
          errMsg = errData.error || errData.message;
        }
      } catch (_) {
        const text = await res.text().catch(() => '');
        if (text) errMsg = text;
      }
      throw new Error(errMsg);
    }

    return await res.json();
  },

  /**
   * Generate Voronoi / parametric pattern cells
   * @param {Object} params - Generation parameters
   * @returns {Promise<{cells: Array<{coords: number[][], seed_idx: number, seed_point: number[]}>, seed_points: number[][]}>}
   */
  async generate(params) {
    let res;
    try {
      res = await fetch(`${API_BASE}/api/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify(params),
      });
    } catch (networkErr) {
      throw new Error(`패턴 생성 서버 통신 실패 (${networkErr.message}). 백엔드가 실행 중인지 확인하세요.`);
    }

    if (!res.ok) {
      let errMsg = `패턴 생성 오류 (${res.status} ${res.statusText})`;
      try {
        const errData = await res.json();
        if (errData && (errData.error || errData.message)) {
          errMsg = errData.error || errData.message;
        }
      } catch (_) {
        const text = await res.text().catch(() => '');
        if (text) errMsg = text;
      }
      throw new Error(errMsg);
    }

    return await res.json();
  },

  /**
   * Export generated pattern to a DXF file and trigger browser download
   * @param {Object} data - Export parameters and cell geometries
   * @returns {Promise<{success: boolean, filename: string}>}
   */
  async exportDxf(data) {
    let res;
    try {
      res = await fetch(`${API_BASE}/api/export-dxf`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
      });
    } catch (networkErr) {
      throw new Error(`내보내기 통신 실패 (${networkErr.message}). 백엔드 서버 상태를 확인하세요.`);
    }

    if (!res.ok) {
      let errMsg = `DXF 내보내기 실패 (${res.status} ${res.statusText})`;
      try {
        const errData = await res.json();
        if (errData && (errData.error || errData.message)) {
          errMsg = errData.error || errData.message;
        }
      } catch (_) {
        const text = await res.text().catch(() => '');
        if (text) errMsg = text;
      }
      throw new Error(errMsg);
    }

    // Determine target filename
    let downloadFilename = data.filename ? data.filename.trim() : 'voronoi_pattern';
    if (!downloadFilename.toLowerCase().endsWith('.dxf')) {
      downloadFilename += '.dxf';
    }

    // Try reading filename from Content-Disposition header if provided by server
    const disposition = res.headers.get('content-disposition');
    if (disposition && disposition.includes('filename=')) {
      const match = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
      if (match && match[1]) {
        downloadFilename = match[1].replace(/['"]/g, '').trim();
      }
    }

    // Read response as Blob and trigger browser download
    const blob = await res.blob();
    const objectUrl = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = downloadFilename;
    document.body.appendChild(link);
    link.click();

    // Clean up
    setTimeout(() => {
      document.body.removeChild(link);
      window.URL.revokeObjectURL(objectUrl);
    }, 200);

    return {
      success: true,
      filename: downloadFilename,
    };
  },
};

// Export to window
window.API = API;
