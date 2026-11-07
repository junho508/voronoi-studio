@echo off
echo Installing dependencies...
python -m pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    pip install -r requirements.txt
)
echo.
echo Starting Voronoi Generator Server...
echo Open your browser at: http://localhost:5000
echo.
python app.py
pause
