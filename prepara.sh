#!/bin/bash
# tallat · prepara aquest Mac per fer servir tallat.
#
#   ./prepara.sh                 instal·la el que falti (es pot tornar a executar: només fa el que cal)
#   ./prepara.sh --amb-whisper   també baixa el model de transcripció (3 GB), per si no fas servir Descript
#
# Tot va a dins de la teva carpeta d'usuari (~/.tallat) i no demana mai la contrasenya:
#   ~/.tallat/bin      micromamba i uv (els instal·ladors)
#   ~/.tallat/eines    ffmpeg i Node.js (de conda-forge)
#   ~/.tallat/python   Python 3.11
#   ~/.tallat/venv     l'entorn de Python de tallat (WhisperX i companyia); .venv n'és un enllaç
# A més, HyperFrames hi baixa el navegador amb què dibuixa els subtítols, i WhisperX el model de veu català.
set -euo pipefail

CARPETA="$(cd "$(dirname "$0")" && pwd)"
TALLAT="$HOME/.tallat"
BIN="$TALLAT/bin"
EINES="$TALLAT/eines"
PY="$CARPETA/.venv/bin/python"

VERSIO_MICROMAMBA="2.8.1-1"
VERSIO_UV="0.13.1"
VERSIO_HYPERFRAMES="0.8.154"
AMB_WHISPER=0
[ "${1:-}" = "--amb-whisper" ] && AMB_WHISPER=1

pas() { printf '\n▸ %s\n' "$1"; }
fet() { printf '  ✓ %s\n' "$1"; }
falla() { printf '\n✗ %s\n' "$1" >&2; exit 1; }

case "$(uname -s)-$(uname -m)" in
  Darwin-x86_64) MAMBA_ARQ="osx-64"; UV_ARQ="x86_64-apple-darwin" ;;
  Darwin-arm64) MAMBA_ARQ="osx-arm64"; UV_ARQ="aarch64-apple-darwin" ;;
  *) falla "tallat de moment només funciona en Mac (aquest ordinador és $(uname -s) $(uname -m))." ;;
esac

# Baixa un fitxer i en comprova la suma (sha256) amb la que publica qui el fa.
baixa_i_comprova() {
  local url="$1" desti="$2"
  curl -fsSL --retry 3 -o "$desti" "$url" || falla "No he pogut baixar $url. Hi ha connexió a internet?"
  curl -fsSL --retry 3 -o "$desti.sha256" "$url.sha256" || falla "No he pogut baixar la suma de $url."
  local esperat obtingut
  esperat="$(cut -c1-64 "$desti.sha256")"
  obtingut="$(shasum -a 256 "$desti" | cut -c1-64)"
  rm -f "$desti.sha256"
  [ "$esperat" = "$obtingut" ] || { rm -f "$desti"; falla "La baixada de $url no és correcta (la suma no coincideix)."; }
}

mkdir -p "$BIN"
echo "Preparant tallat a $CARPETA"
echo "(la primera vegada baixa uns 2-3 GB i pot trigar 10-20 minuts)"

pas "1/6 · Instal·lador de paquets (micromamba)"
if [ ! -x "$BIN/micromamba" ]; then
  baixa_i_comprova "https://github.com/mamba-org/micromamba-releases/releases/download/$VERSIO_MICROMAMBA/micromamba-$MAMBA_ARQ" "$BIN/micromamba"
  chmod +x "$BIN/micromamba"
fi
fet "micromamba $("$BIN/micromamba" --version)"

pas "2/6 · ffmpeg i Node.js"
if [ ! -x "$EINES/bin/ffmpeg" ] || [ ! -x "$EINES/bin/ffprobe" ] || [ ! -x "$EINES/bin/node" ]; then
  MAMBA_ROOT_PREFIX="$TALLAT/mamba" "$BIN/micromamba" create -y -q -p "$EINES" -c conda-forge --override-channels \
    "ffmpeg=7.1.*=*gpl*" "nodejs=22.*" || falla "No he pogut instal·lar ffmpeg i Node.js."
fi
fet "$("$EINES/bin/ffmpeg" -hide_banner -version | head -1 | cut -d' ' -f1-3) · Node.js $("$EINES/bin/node" --version)"
export PATH="$EINES/bin:$BIN:$PATH"

pas "3/6 · Python 3.11 (uv)"
if [ ! -x "$BIN/uv" ]; then
  baixa_i_comprova "https://github.com/astral-sh/uv/releases/download/$VERSIO_UV/uv-$UV_ARQ.tar.gz" "$BIN/uv.tar.gz"
  tar -xzf "$BIN/uv.tar.gz" -C "$BIN" --strip-components 1
  rm -f "$BIN/uv.tar.gz"
fi
# L'entorn va a ~/.tallat/venv i .venv n'és un enllaç: si tallat s'actualitza (o és un connector de
# Claude, que es reinstal·la a cada versió), només cal refer l'enllaç. Si ja hi havia un .venv de
# debò (instal·lacions d'abans), es queda on és.
VENV="$TALLAT/venv"
if [ -d "$CARPETA/.venv" ] && [ ! -L "$CARPETA/.venv" ]; then
  VENV="$CARPETA/.venv"
fi
if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 11) else 1)' 2>/dev/null; then
  # Un entorn a mitges (una instal·lació interrompuda) o d'una altra versió: s'aparta i se'n fa un de
  # nou (uv no en fa cap en una carpeta que no sigui buida). L'apartat s'esborra quan el nou funciona.
  if [ -e "$VENV" ] || [ -L "$VENV" ]; then
    rm -rf "$VENV.vell"
    mv "$VENV" "$VENV.vell" || falla "No he pogut apartar l'entorn de Python d'abans ($VENV)."
  fi
  UV_PYTHON_INSTALL_DIR="$TALLAT/python" "$BIN/uv" venv --quiet --python 3.11 "$VENV" \
    || falla "No he pogut crear l'entorn de Python."
  "$VENV/bin/python" -c 'import sys' 2>/dev/null || falla "L'entorn de Python nou no funciona."
  rm -rf "$VENV.vell"
fi
[ "$VENV" = "$CARPETA/.venv" ] || ln -sfn "$VENV" "$CARPETA/.venv"
fet "$("$PY" --version) a $VENV"

pas "4/6 · WhisperX i la resta de paquets de Python (la part més llarga)"
"$BIN/uv" pip install --quiet --python "$PY" -r "$CARPETA/requirements.txt" || falla "No he pogut instal·lar els paquets de Python."
if [ "$(uname -m)" = "x86_64" ]; then
  # Mac Intel: ctranslate2 i torch porten cadascun la seva còpia d'OpenMP i xoquen (el programa peta).
  # Fem que totes facin servir la de torch.
  SP="$("$PY" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
  OMP="$SP/torch/lib/libiomp5.dylib"
  for copia in "$SP/ctranslate2/.dylibs/libiomp5.dylib" "$SP/functorch/.dylibs/libiomp5.dylib"; do
    if [ -f "$OMP" ] && [ -f "$copia" ] && [ ! -L "$copia" ]; then
      mv "$copia" "$copia.original"
      ln -s "$OMP" "$copia"
    fi
  done
fi
# Abans de WhisperX, la llista de lletres del Mac que fa servir matplotlib (vegeu motor/entorn.py).
(cd "$CARPETA" && "$PY" -c 'from motor import entorn; entorn.llista_de_lletres(); import ctranslate2, torch, whisperx') 2>/dev/null \
  || falla "WhisperX no arrenca. Executa «.venv/bin/python tallat.py comprova» per veure-hi més."
fet "WhisperX $("$PY" -c 'import importlib.metadata as m; print(m.version("whisperx"))') · torch $("$PY" -c 'import importlib.metadata as m; print(m.version("torch"))')"

pas "5/6 · HyperFrames i el seu navegador (per dibuixar els subtítols)"
npx --yes "hyperframes@$VERSIO_HYPERFRAMES" browser ensure >/dev/null 2>&1 \
  || falla "No he pogut preparar HyperFrames. Torna-ho a provar d'aquí a una estona."
# El primer cop que s'obre un programa acabat de baixar, el Mac el revisa uns segons i HyperFrames no
# l'espera prou (el primer esborrany fallaria): l'obrim ara un cop, sense pressa.
NAVEGADOR="$(npx --yes "hyperframes@$VERSIO_HYPERFRAMES" browser path 2>/dev/null | tail -n 1)"
if [ -x "$NAVEGADOR" ]; then "$NAVEGADOR" --version >/dev/null 2>&1 || true; fi
fet "HyperFrames $VERSIO_HYPERFRAMES"

pas "6/6 · Model de veu català (per saber quan es diu cada paraula)"
(cd "$CARPETA" && HF_HUB_VERBOSITY=error TRANSFORMERS_VERBOSITY=error "$PY" -) <<'PYTHON' || falla "No he pogut baixar el model de veu català."
import warnings
warnings.filterwarnings("ignore")
from motor import transcripcio
transcripcio._whisperx().load_align_model(language_code="ca", device="cpu")
PYTHON
fet "model de Softcatalà"
if [ "$AMB_WHISPER" = 1 ]; then
  (cd "$CARPETA" && "$PY" -c 'from motor import transcripcio; transcripcio._whisperx().load_model("large-v3", "cpu", compute_type="int8", language="ca")') \
    || falla "No he pogut baixar el model de transcripció."
  fet "model de transcripció (large-v3)"
fi

printf '\nComprovació final:\n'
"$PY" "$CARPETA/tallat.py" comprova
