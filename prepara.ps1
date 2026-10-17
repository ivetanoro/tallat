# tallat · prepara aquest Windows per fer servir tallat (el que fa prepara.sh al Mac).
#
#   powershell -ExecutionPolicy Bypass -File prepara.ps1                instal·la el que falti (es pot tornar a executar)
#   powershell -ExecutionPolicy Bypass -File prepara.ps1 -AmbWhisper    també el model de transcripció (3 GB)
#
# Tot va a dins de la teva carpeta d'usuari (%USERPROFILE%\.tallat) i no demana permisos d'administrador:
#   .tallat\bin      micromamba i uv (els instal·ladors)
#   .tallat\eines    ffmpeg i Node.js (de conda-forge)
#   .tallat\python   Python 3.11
#   .tallat\venv     l'entorn de Python de tallat (WhisperX i companyia); .venv n'és un enllaç (junction)
# A més, HyperFrames hi baixa el navegador amb què dibuixa els subtítols, i WhisperX el model de veu català.
param([switch]$AmbWhisper)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # sense la barra de progrés, Invoke-WebRequest va molt més de pressa
[Console]::OutputEncoding = [Text.Encoding]::UTF8
# GitHub només accepta TLS 1.2 o més nou, i el PowerShell de Windows 10 de vegades encara comença pel 1.0.
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$CARPETA = $PSScriptRoot
$TALLAT = Join-Path $env:USERPROFILE ".tallat"
$BIN = Join-Path $TALLAT "bin"
$EINES = Join-Path $TALLAT "eines"
$PY = Join-Path $CARPETA ".venv\Scripts\python.exe"

$VERSIO_MICROMAMBA = "2.8.1-1"
$VERSIO_UV = "0.13.1"
$VERSIO_HYPERFRAMES = "0.8.154"

function Pas($text) { Write-Host ""; Write-Host "▸ $text" }
function Fet($text) { Write-Host "  ✓ $text" }
function Falla($text) { Write-Host ""; Write-Host "✗ $text"; exit 1 }

if (-not [Environment]::Is64BitOperatingSystem) { Falla "tallat necessita un Windows de 64 bits." }

# Els camins, sempre literals (-LiteralPath): amb -Path, una carpeta com «Pau[1]» es llegiria com un patró.
function Hi-Es($cami) { return Test-Path -LiteralPath $cami }
function Esborra($cami) { if (Hi-Es $cami) { Remove-Item -LiteralPath $cami -Recurse -Force } }

# Baixa un fitxer i en comprova la suma (sha256) amb la que publica qui el fa. Es baixa a «.part» i només
# quan la suma coincideix pren el nom de debò: si es talla internet a mitges, la vegada següent es torna a baixar.
function Baixa-I-Comprova($url, $desti) {
  $part = "$desti.part"; $suma = "$desti.sha256"
  Esborra $part; Esborra $suma
  try {
    $web = New-Object Net.WebClient
    $web.DownloadFile($url, $part)
    $web.DownloadFile("$url.sha256", $suma)
  } catch { Esborra $part; Esborra $suma; Falla "No he pogut baixar $url. Hi ha connexió a internet?" }
  $esperat = (([IO.File]::ReadAllText($suma)).Trim() -split "\s+")[0].ToLower()
  $obtingut = (Get-FileHash -Algorithm SHA256 -LiteralPath $part).Hash.ToLower()
  Esborra $suma
  if ($esperat -ne $obtingut) { Esborra $part; Falla "La baixada de $url no és correcta (la suma no coincideix)." }
  Esborra $desti
  Move-Item -LiteralPath $part -Destination $desti
}

# Executa un programa i diu si ha anat bé (sense que els seus missatges d'error aturin l'script). El que
# ha escrit queda a $script:Sortida, per mostrar-ne el final si falla (Falla-Amb).
$script:Sortida = ""
function Prova($programa, [string[]]$arguments) {
  $ErrorActionPreference = "Continue"
  # Cada línia com a text: si no, PowerShell hi afegeix el seu propi embolcall d'error a cada línia d'stderr.
  $script:Sortida = (& $programa @arguments 2>&1 | ForEach-Object { "$_" } | Out-String)
  return $LASTEXITCODE -eq 0
}
function Falla-Amb($text) {
  $linies = ($script:Sortida -split "`r?`n" | Where-Object { $_.Trim() }) | Select-Object -Last 15
  if ($linies) { Write-Host ""; Write-Host "Les últimes línies del que ha passat:"; $linies | ForEach-Object { Write-Host "    $_" } }
  Falla $text
}

[IO.Directory]::CreateDirectory($BIN) | Out-Null
Write-Host "Preparant tallat a $CARPETA"
Write-Host "(la primera vegada baixa uns 2-3 GB i pot trigar 10-20 minuts)"

Pas "1/6 · Instal·lador de paquets (micromamba)"
$MAMBA = Join-Path $BIN "micromamba.exe"
if (-not (Hi-Es $MAMBA)) {
  Baixa-I-Comprova "https://github.com/mamba-org/micromamba-releases/releases/download/$VERSIO_MICROMAMBA/micromamba-win-64" $MAMBA
}
Fet "micromamba $(& $MAMBA --version)"

Pas "2/6 · ffmpeg i Node.js"
# Els paquets de conda-forge per a Windows deixen ffmpeg a Library\bin i Node.js a l'arrel de l'entorn.
$FFMPEG = Join-Path $EINES "Library\bin\ffmpeg.exe"
$NODE = Join-Path $EINES "node.exe"
if (-not (Hi-Es $FFMPEG) -or -not (Hi-Es (Join-Path $EINES "Library\bin\ffprobe.exe")) -or -not (Hi-Es $NODE)) {
  $env:MAMBA_ROOT_PREFIX = Join-Path $TALLAT "mamba"
  if (-not (Prova $MAMBA @("create", "-y", "-q", "-p", $EINES, "-c", "conda-forge", "--override-channels",
                            "ffmpeg=7.1.*=*gpl*", "nodejs=22.*"))) { Falla-Amb "No he pogut instal·lar ffmpeg i Node.js." }
}
$env:PATH = "$(Join-Path $EINES 'Library\bin');$EINES;$BIN;$env:PATH"
Fet "$((& $FFMPEG -hide_banner -version | Select-Object -First 1) -replace '^(ffmpeg version \S+).*', '$1') · Node.js $(& $NODE --version)"

Pas "3/6 · Python 3.11 (uv)"
$UV = Join-Path $BIN "uv.exe"
if (-not (Hi-Es $UV)) {
  $zip = Join-Path $BIN "uv.zip"
  Baixa-I-Comprova "https://github.com/astral-sh/uv/releases/download/$VERSIO_UV/uv-x86_64-pc-windows-msvc.zip" $zip
  $dins = Join-Path $BIN "uv-baixat"
  Esborra $dins
  Expand-Archive -Force -LiteralPath $zip -DestinationPath $dins
  Get-ChildItem -LiteralPath $dins -Recurse -Filter "uv*.exe" | ForEach-Object {
    Move-Item -Force -LiteralPath $_.FullName -Destination (Join-Path $BIN $_.Name)
  }
  Esborra $dins; Esborra $zip
}
# L'entorn va a .tallat\venv i .venv n'és un enllaç (una «junction», que a Windows no demana permisos): si
# tallat s'actualitza, només cal refer l'enllaç. Si ja hi havia un .venv de debò, es queda on és.
$VENV = Join-Path $TALLAT "venv"
$enllac = Get-Item -Force -ErrorAction SilentlyContinue -LiteralPath (Join-Path $CARPETA ".venv")
if ($enllac -and -not $enllac.LinkType) { $VENV = $enllac.FullName }
$PYVENV = Join-Path $VENV "Scripts\python.exe"
if (-not (Hi-Es $PYVENV) -or -not (Prova $PYVENV @("-c", "import sys; sys.exit(0 if sys.version_info[:2] == (3, 11) else 1)"))) {
  # Un entorn a mitges (una instal·lació interrompuda) o d'una altra versió: s'aparta i se'n fa un de nou.
  if (Hi-Es $VENV) {
    Esborra "$VENV.vell"
    Rename-Item -LiteralPath $VENV -NewName (Split-Path -Leaf "$VENV.vell")
  }
  $env:UV_PYTHON_INSTALL_DIR = Join-Path $TALLAT "python"
  if (-not (Prova $UV @("venv", "--quiet", "--python", "3.11", $VENV))) { Falla-Amb "No he pogut crear l'entorn de Python." }
  if (-not (Prova $PYVENV @("-c", "import sys"))) { Falla "L'entorn de Python nou no funciona." }
  Esborra "$VENV.vell"
}
if ($VENV -ne (Join-Path $CARPETA ".venv")) {
  if ($enllac) { $enllac.Delete() }  # només l'enllaç, no el que hi ha a dins
  # mklink /J: una «junction» (no demana administrador); amb cmd, els camins van literals.
  cmd /c mklink /J "$(Join-Path $CARPETA '.venv')" "$VENV" | Out-Null
  if (-not (Hi-Es (Join-Path $CARPETA ".venv\Scripts\python.exe"))) { Falla "No he pogut enllaçar .venv amb $VENV." }
}
Fet "$(& $PY --version) a $VENV"

Pas "4/6 · WhisperX i la resta de paquets de Python (la part més llarga)"
if (-not (Prova $UV @("pip", "install", "--quiet", "--python", $PY, "-r", (Join-Path $CARPETA "requirements.txt")))) {
  Falla-Amb "No he pogut instal·lar els paquets de Python."
}
# torch i ctranslate2 porten cadascun la seva còpia d'OpenMP (vegeu motor/entorn.py).
$env:KMP_DUPLICATE_LIB_OK = "TRUE"
Push-Location $CARPETA
$arrenca = Prova $PY @("-c", "from motor import entorn; entorn.prepara(); entorn.llista_de_lletres(); import ctranslate2, torch, whisperx")
Pop-Location
if (-not $arrenca) { Falla-Amb "WhisperX no arrenca. Executa «.venv\Scripts\python tallat.py comprova» per veure-hi més." }
$versions = & $PY -c "import importlib.metadata as m; print(m.version('whisperx') + ' · torch ' + m.version('torch'))"
Fet "WhisperX $versions"

Pas "5/6 · HyperFrames i el seu navegador (per dibuixar els subtítols)"
$NPX = Join-Path $EINES "npx.cmd"
if (-not (Prova $NPX @("--yes", "hyperframes@$VERSIO_HYPERFRAMES", "browser", "ensure"))) {
  Falla-Amb "No he pogut preparar HyperFrames. Torna-ho a provar d'aquí a una estona."
}
Fet "HyperFrames $VERSIO_HYPERFRAMES"

Pas "6/6 · Model de veu català (per saber quan es diu cada paraula)"
$env:HF_HUB_VERBOSITY = "error"
$env:TRANSFORMERS_VERBOSITY = "error"
Push-Location $CARPETA
$model = Prova $PY @("-c", "import warnings; warnings.filterwarnings('ignore'); from motor import entorn, transcripcio; entorn.prepara(); transcripcio._whisperx().load_align_model(language_code='ca', device='cpu')")
Pop-Location
if (-not $model) { Falla-Amb "No he pogut baixar el model de veu català." }
Fet "model de Softcatalà"
if ($AmbWhisper) {
  Push-Location $CARPETA
  $whisper = Prova $PY @("-c", "from motor import entorn, transcripcio; entorn.prepara(); transcripcio._whisperx().load_model('large-v3', 'cpu', compute_type='int8', language='ca')")
  Pop-Location
  if (-not $whisper) { Falla-Amb "No he pogut baixar el model de transcripció." }
  Fet "model de transcripció (large-v3)"
}

Write-Host ""
Write-Host "Comprovació final:"
& $PY (Join-Path $CARPETA "tallat.py") comprova
exit $LASTEXITCODE
