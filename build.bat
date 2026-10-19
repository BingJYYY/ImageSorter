@echo off
setlocal
cd /d "%~dp0"
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean build.spec
if errorlevel 1 goto :err
echo.
echo Build complete. Output: dist\ImageSort\ImageSort.exe
echo Copy the dist\ImageSort folder to any Win10/11 PC and run ImageSort.exe.
goto :eof
:err
echo Build failed with exit code %errorlevel%
exit /b %errorlevel%
