# Voronoi & Parametric Pattern Studio for CAD / 3D Printing
> **Parametric 2D CAD Pattern Generator** optimized for CNC machining, laser cutting, 3D printing, and CAD workflows (Siemens NX, SolidWorks, Rhino, Fusion 360).

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/flask-2.3+-green.svg)](https://flask.palletsprojects.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CAD: True ARCs](https://img.shields.io/badge/DXF%20Export-True%20Circular%20Arcs-orange.svg)](#dxf-export)

---

[📖 English](#-english) | [📖 한국어](#-한국어)

---

## 🌐 English

### Overview
**Voronoi Pattern Studio** generates mathematical, aesthetic, and functional 2D patterns (Voronoi, Hexagon, Triangle, Square) with CAD-accurate dimensions (millimeters). It exports clean DXF files containing true circular arc fillets (`LINE` + `ARC` entities) that import seamlessly into 3D CAD sketch environments (e.g. Siemens NX, SolidWorks, Autodesk Fusion 360, Rhino) for extruding, pocketing, and lightweight infill design.

```
[CAD Sketch (NX / SolidWorks)] 
       │  Export 2D Boundary (.dxf)
       ▼
[Voronoi Pattern Studio] ──► Tune Cell Size, Rib Gap, Fillets & Seamless Tiling
       │  Export Pattern (.dxf with true ARCs)
       ▼
[Re-import to CAD Sketch] ──► Extrude / Cut / 3D Print / CNC Milling
```

---

### Key Features
1. **4 Pattern Types**:
   - **Voronoi**: Organic cellular structures with adjustable randomness (jitter) and centroidal smoothing (Lloyd's relaxation).
   - **Hexagon**: Regular pointy-topped honeycombs with zero geometric distortion.
   - **Triangle**: Equilateral triangular lattices.
   - **Square**: Orthogonal square grid patterns.
2. **Flexible Boundary Definition**:
   - **Parametric Rectangle**: Instant $W \times H$ mm bounding box.
   - **DXF Sketch Import**: Drag & drop any `.dxf` sketch to extract closed polygon loops with multi-region selection.
3. **Seamless Infinite Tiling**:
   - Boundary-seam clipping for continuous, tileable surface textures.
   - **Integer Period Quantization**: Automatically adjusts grid dimensions to boundary edges while strictly preserving regular geometric aspect ratios (0% square distortion, <1% hex/tri distortion).
   - **3×3 Tile Preview**: Real-time visual confirmation of edge continuity.
4. **Interactive SVG Canvas**:
   - **Pan & Zoom**: Smooth CAD navigation (wheel zoom, right-drag or middle-drag pan).
   - **Voronoi Point Control**: Real-time draggable seed points with instant Delaunay preview; add seed with `+` key at cursor.
   - **Regular Pattern Shift**: Click and drag on canvas to translate the pattern grid in real-time.
   - **Cell Management**: Select individual cells, toggle selection, delete with `Del` or right-click.
5. **CAD-Engineered DXF Export**:
   - Exports true CAD `ARC` entities (inward circular fillets) and `LINE` segments instead of faceted polylines, ensuring smooth toolpaths and clean CAD sketch surfaces.
   - Layer segregation: `VORONOI_PATTERN` (color red) and `BOUNDARY` (color green).

---

### Interactive Canvas Shortcuts

| Mode | Shortcut | Action |
|---|---|---|
| **All Modes** | `Wheel` | Zoom In / Out |
| **All Modes** | `Right-Drag` or `Middle-Drag` | Pan Canvas View |
| **All Modes** | `Ctrl + Z` | Undo last operation |
| **Voronoi** | `+` or `=` | Add seed point at cursor position |
| **Voronoi** | `Left-Click` on cell | Select / Deselect cell (toggle highlight) |
| **Voronoi** | `Shift + Click` | Multi-select cells |
| **Voronoi** | `Del` or `Backspace` | Delete selected cell(s) |
| **Voronoi** | `Right-Click` on cell | Delete cell immediately |
| **Voronoi** | `Drag Cyan Point` | Move seed point with live preview |
| **Hex / Tri / Square** | `Left-Drag` on canvas | Shift entire pattern position interactively |

---

### Parameters Guide

- **Cell Size (`cell_size`, mm)**: The nominal diameter or pitch of each cell.
- **Rib Width / Cell Gap (`cell_gap`, mm)**: Distance between adjacent cells (thickness of structural ribs).
- **Corner Fillet Radius (`corner_radius`, mm)**: Fillet radius applied to all internal cell vertices (exported as true CAD `ARC`s).
- **Boundary Inset (`boundary_offset`, mm)**: Margin inward from boundary outline.
- **Pattern Rotation (`rotation`, deg)**: Angle of pattern orientation (-90° to +90°).
- **Jitter (`jitter`, 0.0 ~ 1.0, Voronoi only)**: Randomness of initial seed distribution.
- **Lloyd's Relaxation (`lloyd_iterations`, Voronoi only)**: Number of Centroidal Voronoi Tessellation iterations for uniform cell sizes.
- **Seamless Tiling (`seamless`)**: Closes periodic boundaries across borders for infinite surface continuity.

---

### Local Installation & Running

#### Prerequisites
- Python 3.10 or higher
- Git

#### Quick Start
```bash
# 1. Clone repository
git clone https://github.com/your-username/voronoi-pattern-generator.git
cd voronoi-pattern-generator

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start application
python app.py
```
Open your browser and navigate to **`http://localhost:5000`**.

---

### Free Cloud Deployment (24/7 Always Active)

Deploy this app online for free on **Render.com** with **UptimeRobot** keep-alive (zero cold-start delay):

1. **Deploy to Render.com**:
   - Push this repo to GitHub.
   - Go to [Render.com](https://render.com/) → **New Web Service** → Connect your GitHub repository.
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
   - Instance Type: **Free** (Region: Singapore recommended for Asia)
   - Click **Create Web Service**.
2. **Prevent Sleep Mode (UptimeRobot)**:
   - Go to [UptimeRobot.com](https://uptimerobot.com/) (free tier).
   - Add New Monitor → Type: `HTTP(s)` → URL: `https://your-service.onrender.com/health`.
   - Set interval to **10 minutes**.
   - Your Render instance will stay awake 24/7 at zero cost!

---
---

## 📖 한국어

### 개요
**보로노이 패턴 스튜디오 (Voronoi & Parametric Pattern Studio)**는 3D 프린팅, CNC 가공, 레이저 커팅 및 3D CAD(Siemens NX, SolidWorks, Rhino, Fusion 360 등) 워크플로우에 최적화된 파라메트릭 2D 패턴 생성기입니다.

곡면 분할선이 각진 다각형(Polyline)으로 쪼개지지 않고 **CAD 전용 원호(`LINE` + `ARC` 엔티티)** 형태로 내보내지므로, 모델링 프로그램 스케치로 재가져오기 시 가볍고 매끄러운 돌출(Extrude) 및 포켓(Pocket) 모델링이 가능합니다.

```
[CAD 스케치 (Siemens NX / SolidWorks)] 
       │  경계선 2D 스케치 내보내기 (.dxf)
       ▼
[보로노이 패턴 스튜디오] ──► 셀 크기, 리브 간격, 라운드 반경 & 무한 반복 타일링 조절
       │  CAD 전용 DXF 내보내기 (진성 원호 ARC 포함)
       ▼
[CAD 스케치로 재가져오기] ──► 3D 돌출 / 컷팅 / 3D 프린팅 메쉬 생성
```

---

### 주요 기능
1. **4가지 패턴 유형 지원**:
   - **보로노이 (Voronoi)**: 자연스러운 유기적 격자 구조, 지터(Jitter) 및 로이드 완화(Lloyd Relaxation) 지원.
   - **육각형 (Hexagon)**: 정육각형 벌집(Honeycomb) 구조.
   - **삼각형 (Triangle)**: 정삼각형 격자 패턴.
   - **사각형 (Square)**: 직교 정사각형 격자 패턴.
2. **유연한 경계 설정**:
   - **파라메트릭 사각형**: 가로($W$) × 세로($H$) mm 수치 입력으로 즉시 경계 생성.
   - **DXF 스케치 불러오기**: 복잡한 폐곡선(Closed Loop) 영역을 자동 분할 인식하여 원하는 영역만 다중 선택 가능.
3. **무한 반복 타일링 (Seamless Tiling)**:
   - 타일과 타일이 맞닿는 경계선을 개방 연결하여 3D 텍스처나 무한 반복 패널 제작 가능.
   - **정수 주기 양자화 (Integer Period Quantization)**: 경계 크기에 맞춰 셀 크기를 자동 보정하되, 정사각형은 100% 비율 유지, 정육각형/정삼각형은 1% 이내 오차로 정다각형 형태를 완벽 유지.
   - **3×3 타일 미리보기**: 경계 외곽 8개 인접 타일을 함께 렌더링하여 이음매 연결성 실시간 검증.
4. **대화형 SVG 캔버스 조작**:
   - **자유로운 뷰포트 탐색**: 휠 줌(Zoom), 마우스 우클릭 드래그 화면 이동(Pan).
   - **보로노이 씨드 포인트 조작**: 씨드 드래그 시 실시간 실루엣 프리뷰, 마우스 커서 위치에서 `+` 키로 즉시 씨드 추가.
   - **규칙 패턴(육각형/삼각형/사각형) 드래그 이동**: 캔버스 좌클릭 드래그로 전체 패턴 그리드 위치를 실시간 이동.
   - **셀 선택 및 삭제**: 셀 클릭 시 토글 선택(붉은 하이라이트), `Del` 또는 우클릭으로 즉시 개별 삭제.
5. **CAD 친화적 정밀 DXF 내보내기**:
   - 코너 라운드 적용 시 각진 폴리라인이 아닌 실제 CAD 호(`ARC`) 엔티티로 정확한 내부 필렛 생성.
   - 레이어 자동 분리: 패턴 레이어(`VORONOI_PATTERN`, 빨간색) 및 경계선 레이어(`BOUNDARY`, 초록색).

---

### 캔버스 단축키 안내

| 적용 모드 | 단축키 | 동작 설명 |
|---|---|---|
| **공통** | `마우스 휠` | 화면 확대 / 축소 (Zoom) |
| **공통** | `마우스 우클릭 드래그` 또는 `휠 클릭 드래그` | 화면 이동 (Pan) |
| **공통** | `Ctrl + Z` | 실행 취소 (Undo) |
| **보로노이** | `+` 또는 `=` | 마우스 커서 위치에 새 씨드 포인트 즉시 추가 |
| **보로노이** | `마우스 좌클릭` | 셀 선택 / 선택 해제 토글 |
| **보로노이** | `Shift + 좌클릭` | 셀 다중 선택 |
| **보로노이** | `Del` 또는 `Backspace` | 선택된 셀 삭제 |
| **보로노이** | `마우스 우클릭` (셀 위) | 해당 셀 즉시 삭제 |
| **보로노이** | `씨드 원형 드래그` | 씨드 좌표 실시간 이동 |
| **육각형 / 삼각형 / 사각형** | `마우스 좌클릭 드래그` | 패턴 그리드 전체 위치 이동 |

---

### 주요 파라미터 설명

- **셀 크기 (`cell_size`, mm)**: 패턴을 구성하는 각 셀의 기준 지름/한 변의 크기.
- **셀 간격 / 리브 폭 (`cell_gap`, mm)**: 셀과 셀 사이의 살 두께 (3D 프린팅 벽 두께).
- **모따기 반경 (`corner_radius`, mm)**: 셀 내부 각진 모서리에 들어갈 필렛 반경 (CAD의 `ARC` 원호로 내보내짐).
- **경계 오프셋 (`boundary_offset`, mm)**: 외곽 경계선으로부터 안쪽으로 띄울 여백 거리.
- **패턴 회전 (`rotation`, °)**: 패턴의 배치 각도 (-90° ~ +90°).
- **지터 (`jitter`, 0.0 ~ 1.0, 보로노이 전용)**: 씨드 배치의 무작위성 (0=정규 격자, 1=불규칙 자연 형상).
- **로이드 완화 (`lloyd_iterations`, 보로노이 전용)**: 보로노이 셀 크기를 균등하게 정돈하는 최적화 패스 수.
- **무한 반복 타일링 (`seamless`)**: 경계 끝부분을 열어 인접 타일과 100% 매끄럽게 연결되는 패턴 생성.

---

### 로컬 환경 설치 및 실행

#### 요구 사항
- Python 3.10 이상
- Git

#### 실행 단계
```bash
# 1. 저장소 클론
git clone https://github.com/your-username/voronoi-pattern-generator.git
cd voronoi-pattern-generator

# 2. 필수 라이브러리 설치
pip install -r requirements.txt

# 3. 서버 실행
python app.py
```
실행 후 웹 브라우저에서 **`http://localhost:5000`**에 접속합니다.

---

### 무료 클라우드 배포 (24시간 절전 없이 상시 가동)

GitHub와 **Render.com** 무료 티어 및 **UptimeRobot**을 결합하여 무료로 웹사이트를 상시 호스팅할 수 있습니다:

1. **Render.com 배포**:
   - 본 코드를 GitHub 개인 저장소에 Push합니다.
   - [Render.com](https://render.com/) 가입 후 **[New +] → [Web Service]**에서 GitHub 저장소를 선택합니다.
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
   - Instance Type: **Free** (Region: Singapore 선택 권장)
   - **[Create Web Service]**를 클릭하면 2~3분 뒤 웹 주소(`https://내서비스.onrender.com`)가 발급됩니다.
2. **24시간 절전 방지 설정 (UptimeRobot)**:
   - [UptimeRobot.com](https://uptimerobot.com/) 무료 가입 후 **[+ Add New Monitor]** 클릭.
   - Monitor Type: `HTTP(s)` / URL: `https://내서비스.onrender.com/health` 입력.
   - 모니터링 주기: **10분 (10 minutes)** 설정 후 저장.
   - UptimeRobot이 10분마다 헬스체크 신호를 보내므로 Render 무료 서버가 절전 모드로 들어가지 않고 24시간 즉시 접속 가능한 상태로 유지됩니다.

---

### Tech Stack
- **Backend**: Python 3, Flask, SciPy, Shapely, NumPy, ezdxf, Gunicorn
- **Frontend**: Vanilla JavaScript (ES6+), SVG Canvas, HTML5, CSS3 (No Framework dependencies)

### License
This project is open-source and licensed under the [MIT License](LICENSE).
