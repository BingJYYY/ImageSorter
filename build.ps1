.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean build.spec
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Build complete. Output: dist\ImageSort\ImageSort.exe" -ForegroundColor Green
    Write-Host "Copy the dist\ImageSort folder to any Win10/11 PC and double-click ImageSort.exe to run." -ForegroundColor Green
}
