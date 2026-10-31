# Builds dist\PoE-Tracker-Setup.exe on Windows (GitHub Actions runs this on every
# release; you can also run it yourself with Python 3.13 and Inno Setup 6).
#   pwsh installer/build.ps1 -Version 0.2.0
param(
    [string]$Version = "0.1.0",
    [string]$Commit = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$build = Join-Path $root "build"
$dist = Join-Path $root "dist"
Remove-Item $build, $dist -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force "$build\python", "$build\app", $dist | Out-Null

# 1. A private copy of Python: the official "embeddable" build of the same version
$pyver = (python -c "import sys; print('%d.%d.%d' % sys.version_info[:3])").Trim()
$tag = (python -c "import sys; print('%d%d' % sys.version_info[:2])").Trim()
Write-Host "Python $pyver"
$zip = Join-Path $env:RUNNER_TEMP "python-embed.zip"
if (-not $env:RUNNER_TEMP) { $zip = Join-Path $env:TEMP "python-embed.zip" }
Invoke-WebRequest "https://www.python.org/ftp/python/$pyver/python-$pyver-embed-amd64.zip" -OutFile $zip
Expand-Archive $zip "$build\python" -Force
# where it looks for modules: its own library, our packages, and the tracker
Set-Content "$build\python\python$tag._pth" -Encoding ascii -Value @(
    "python$tag.zip", ".", "Lib\site-packages", "..\app", "import site")

# 2. The tracker's packages, installed into that Python
python -m pip install --disable-pip-version-check --no-warn-script-location `
    --target "$build\python\Lib\site-packages" -r (Join-Path $root "requirements.txt")
if ($LASTEXITCODE) { throw "pip install failed" }

# 3. The tracker itself
Copy-Item (Join-Path $root "poetracker") "$build\app\poetracker" -Recurse
Get-ChildItem "$build\app" -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Copy-Item (Join-Path $root "requirements.txt") "$build\app\"
if (-not $Commit) { $Commit = (git -C $root rev-parse HEAD).Trim() }
$date = (git -C $root log -1 --format=%cd "--date=format:%b %d, %H:%M" $Commit).Trim()
@{ commit = $Commit; date = $date; installer = $Version } | ConvertTo-Json | Set-Content "$build\app\version.json" -Encoding utf8

# 4. The launcher (PoE Tracker.exe), compiled with the C# compiler that ships with Windows
$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
& $csc /nologo /target:winexe /optimize+ "/win32icon:$root\poetracker\ui\static\icon.ico" `
    /reference:System.Windows.Forms.dll "/out:$build\PoE Tracker.exe" (Join-Path $PSScriptRoot "launcher.cs")
if ($LASTEXITCODE) { throw "launcher build failed" }

# 5. Quick check that the bundled Python can load the tracker
& "$build\python\python.exe" -c "import poetracker, nicegui, webview, yaml; print('bundle ok', poetracker.__version__)"
if ($LASTEXITCODE) { throw "bundle check failed" }

# 6. The installer
$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) { $iscc = "$env:ProgramFiles\Inno Setup 6\ISCC.exe" }
& $iscc "/DAppVersion=$Version" (Join-Path $PSScriptRoot "PoETracker.iss")
if ($LASTEXITCODE) { throw "Inno Setup failed" }
Get-ChildItem $dist
