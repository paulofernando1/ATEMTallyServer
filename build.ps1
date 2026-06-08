# Run PyInstaller to build a standalone Windows Executable
# --noconsole removes the command prompt window in the background
# --onefile packages everything into a single .exe (fully portable for a flash drive)
# --add-data "static;static" includes the localized socket.io assets
# --windowed ensure it runs as a GUI application
# --clean clears the cache before building

python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --icon "Tally.ico" `
    --add-data "static;static" `
    --add-data "Tally.ico;." `
    --add-data "Tally.png;." `
    --add-data "Config.ico;." `
    --add-data "Config.png;." `
    --add-data "Help.ico;." `
    --add-data "Help.png;." `
    --hidden-import "qrcode" `
    --hidden-import "qrcode.image.pil" `
    --hidden-import "PIL._tkinter_finder" `
    --name "TallyServerPro" `
    "app.py"

Write-Host "Build complete! The PORTABLE executable is located in the 'dist' directory as 'TallyServerPro.exe'."
