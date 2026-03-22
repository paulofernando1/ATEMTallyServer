# Run PyInstaller to build a standalone Windows Executable
# --noconsole removes the command prompt window in the background
# --onefile packages everything into a single .exe (fully portable for a flash drive)
# --windowed ensure it runs as a GUI application
# --clean clears the cache before building

python -m PyInstaller --noconfirm --clean --onefile --windowed --name "TallyServerEmulator" "app.py"

Write-Host "Build complete! The PORTABLE executable is located in the 'dist' directory as 'TallyServerEmulator.exe'."
