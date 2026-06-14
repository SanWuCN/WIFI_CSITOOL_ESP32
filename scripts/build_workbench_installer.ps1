$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$AppName = "SwCSI"
$DisplayName = "SwCSI"
$Version = "V1.0.2"
$PythonLauncher = "py"
$PythonVersionArg = "-3.9"

$DistDir = Join-Path $Root "dist"
$PyInstallerWorkDir = Join-Path $Root "build\pyinstaller"
$InstallerWorkDir = Join-Path $Root "build\workbench_installer"
$InstallerOutDir = Join-Path $Root "dist_installer"
$PyInstallerAppDir = Join-Path $DistDir $AppName
$StageDir = Join-Path $InstallerWorkDir "stage"
$StageAppDir = Join-Path $StageDir $AppName
$AppZip = Join-Path $InstallerWorkDir "app.zip"
$SedFile = Join-Path $InstallerWorkDir "installer.sed"
$InstallerExe = Join-Path $InstallerOutDir ($AppName + "_" + $Version + "_Setup.exe")

Write-Host "Root: $Root"
Write-Host "Building $DisplayName $Version installer..."

Remove-Item -LiteralPath $InstallerWorkDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $InstallerWorkDir, $InstallerOutDir | Out-Null

& $PythonLauncher $PythonVersionArg -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --windowed `
    --name $AppName `
    --icon (Join-Path $Root "assets\swcsi_icon.ico") `
    --paths (Join-Path $Root "tools") `
    --distpath $DistDir `
    --workpath $PyInstallerWorkDir `
    (Join-Path $Root "tools\csi_workbench.py")

if (-not (Test-Path (Join-Path $PyInstallerAppDir ($AppName + ".exe")))) {
    throw "PyInstaller output exe was not created."
}

New-Item -ItemType Directory -Force -Path (Join-Path $PyInstallerAppDir "data\raw") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $PyInstallerAppDir "docs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $PyInstallerAppDir "assets") | Out-Null
Copy-Item -LiteralPath (Join-Path $Root "docs\CSI-workbench.md") -Destination (Join-Path $PyInstallerAppDir "docs\CSI-workbench.md") -Force
Copy-Item -LiteralPath (Join-Path $Root "requirements.txt") -Destination (Join-Path $PyInstallerAppDir "requirements.txt") -Force
Copy-Item -LiteralPath (Join-Path $Root "assets\swcsi_icon.png") -Destination (Join-Path $PyInstallerAppDir "assets\swcsi_icon.png") -Force
Copy-Item -LiteralPath (Join-Path $Root "assets\swcsi_icon.ico") -Destination (Join-Path $PyInstallerAppDir "assets\swcsi_icon.ico") -Force

$UninstallPs1 = @'
$ErrorActionPreference = "Stop"
$InstallDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Desktop = [Environment]::GetFolderPath("DesktopDirectory")
$Programs = [Environment]::GetFolderPath("Programs")
$Shortcut1 = Join-Path $Desktop "SwCSI.lnk"
$Shortcut2 = Join-Path $Programs "SwCSI.lnk"
$UninstallShortcut = Join-Path $Programs "Uninstall SwCSI.lnk"
Remove-Item -LiteralPath $Shortcut1 -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $Shortcut2 -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $UninstallShortcut -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 300
Remove-Item -LiteralPath $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "SwCSI has been removed."
'@
$UninstallCmd = @'
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1"
'@
Set-Content -LiteralPath (Join-Path $PyInstallerAppDir "uninstall.ps1") -Value $UninstallPs1 -Encoding UTF8
Set-Content -LiteralPath (Join-Path $PyInstallerAppDir "uninstall.cmd") -Value $UninstallCmd -Encoding ASCII

Remove-Item -LiteralPath $StageDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $StageDir | Out-Null
Copy-Item -LiteralPath $PyInstallerAppDir -Destination $StageAppDir -Recurse -Force
Remove-Item -LiteralPath $AppZip -Force -ErrorAction SilentlyContinue
Compress-Archive -LiteralPath $StageAppDir -DestinationPath $AppZip -Force

$InstallPs1 = @'
$ErrorActionPreference = "Stop"
$AppName = "SwCSI"
$DisplayName = "SwCSI"
$InstallRoot = Join-Path $env:LOCALAPPDATA "Programs"
$InstallDir = Join-Path $InstallRoot $AppName
$SourceZip = Join-Path $PSScriptRoot "app.zip"

if (-not (Test-Path -LiteralPath $SourceZip)) {
    throw "Missing app.zip beside installer script."
}

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
$BackupDir = $null
if (Test-Path -LiteralPath $InstallDir) {
    $BackupDir = $InstallDir + ".old_" + (Get-Date -Format "yyyyMMddHHmmss")
    Move-Item -LiteralPath $InstallDir -Destination $BackupDir -Force
}

try {
    Expand-Archive -LiteralPath $SourceZip -DestinationPath $InstallRoot -Force
    $Exe = Join-Path $InstallDir ($AppName + ".exe")
    if (-not (Test-Path -LiteralPath $Exe)) {
        throw "Installed exe was not found: $Exe"
    }

    $Shell = New-Object -ComObject WScript.Shell
    $Desktop = [Environment]::GetFolderPath("DesktopDirectory")
    $Programs = [Environment]::GetFolderPath("Programs")

    $DesktopShortcut = $Shell.CreateShortcut((Join-Path $Desktop ($DisplayName + ".lnk")))
    $DesktopShortcut.TargetPath = $Exe
    $DesktopShortcut.WorkingDirectory = $InstallDir
    $DesktopShortcut.Description = $DisplayName
    $DesktopShortcut.Save()

    $StartShortcut = $Shell.CreateShortcut((Join-Path $Programs ($DisplayName + ".lnk")))
    $StartShortcut.TargetPath = $Exe
    $StartShortcut.WorkingDirectory = $InstallDir
    $StartShortcut.Description = $DisplayName
    $StartShortcut.Save()

    $UninstallCmd = Join-Path $InstallDir "uninstall.cmd"
    if (Test-Path -LiteralPath $UninstallCmd) {
        $UninstallShortcut = $Shell.CreateShortcut((Join-Path $Programs ("Uninstall " + $DisplayName + ".lnk")))
        $UninstallShortcut.TargetPath = $UninstallCmd
        $UninstallShortcut.WorkingDirectory = $InstallDir
        $UninstallShortcut.Description = "Uninstall " + $DisplayName
        $UninstallShortcut.Save()
    }

    if ($BackupDir -and (Test-Path -LiteralPath $BackupDir)) {
        Remove-Item -LiteralPath $BackupDir -Recurse -Force -ErrorAction SilentlyContinue
    }

    Write-Host "$DisplayName installed to $InstallDir"
} catch {
    if ((-not (Test-Path -LiteralPath $InstallDir)) -and $BackupDir -and (Test-Path -LiteralPath $BackupDir)) {
        Move-Item -LiteralPath $BackupDir -Destination $InstallDir -Force
    }
    throw
}
'@
$InstallCmd = @'
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 (
  echo.
  echo Installation failed.
  pause
)
'@
Set-Content -LiteralPath (Join-Path $InstallerWorkDir "install.ps1") -Value $InstallPs1 -Encoding UTF8
Set-Content -LiteralPath (Join-Path $InstallerWorkDir "install.cmd") -Value $InstallCmd -Encoding ASCII

$Sed = @"
[Version]
Class=IEXPRESS
SEDVersion=3

[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=1
HideExtractAnimation=0
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=%InstallPrompt%
DisplayLicense=%DisplayLicense%
FinishMessage=%FinishMessage%
TargetName=%TargetName%
FriendlyName=%FriendlyName%
AppLaunched=%AppLaunched%
PostInstallCmd=%PostInstallCmd%
AdminQuietInstCmd=%AdminQuietInstCmd%
UserQuietInstCmd=%UserQuietInstCmd%
SourceFiles=SourceFiles

[Strings]
InstallPrompt=
DisplayLicense=
FinishMessage=Install complete.
TargetName=$InstallerExe
FriendlyName=$DisplayName $Version Installer
AppLaunched=install.cmd
PostInstallCmd=<None>
AdminQuietInstCmd=
UserQuietInstCmd=
FILE0="install.cmd"
FILE1="install.ps1"
FILE2="app.zip"

[SourceFiles]
SourceFiles0=$InstallerWorkDir

[SourceFiles0]
%FILE0%=
%FILE1%=
%FILE2%=
"@
Set-Content -LiteralPath $SedFile -Value $Sed -Encoding ASCII

$IExpress = Join-Path $env:WINDIR "System32\iexpress.exe"
if (-not (Test-Path -LiteralPath $IExpress)) {
    throw "IExpress was not found: $IExpress"
}

& $IExpress /N /Q $SedFile

if (-not (Test-Path -LiteralPath $InstallerExe)) {
    throw "Installer exe was not created: $InstallerExe"
}

$PortableZip = Join-Path $InstallerOutDir ($AppName + "_" + $Version + "_Portable.zip")
Compress-Archive -LiteralPath $StageAppDir -DestinationPath $PortableZip -Force

Write-Host "Installer: $InstallerExe"
Write-Host "Portable zip: $PortableZip"
