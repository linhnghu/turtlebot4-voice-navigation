#!/usr/bin/env bash
set -euo pipefail
_vn_ws="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
/usr/bin/python3 -m venv --system-site-packages "${_vn_ws}/.venv-voice-nav"
"${_vn_ws}/.venv-voice-nav/bin/python" -m pip install -r "${_vn_ws}/src/turtlebot4_voice_nav/requirements-voice.txt"
if ! /usr/bin/python3 -c 'from ctypes.util import find_library; assert find_library("portaudio")' 2>/dev/null; then
    mkdir -p "${_vn_ws}/.voice-nav-runtime/debs"
    (
        cd "${_vn_ws}/.voice-nav-runtime/debs"
        apt-get download libportaudio2
        for package in libportaudio2_*.deb; do
            dpkg-deb -x "$package" "${_vn_ws}/.voice-nav-runtime"
        done
    )
    _vn_lib="${_vn_ws}/.voice-nav-runtime/usr/lib/$(dpkg-architecture -qDEB_HOST_MULTIARCH)"
    ln -sfn libportaudio.so.2 "${_vn_lib}/libportaudio.so"
fi
mkdir -p "${_vn_ws}/.models/hri"
"${_vn_ws}/.venv-voice-nav/bin/python" - "${_vn_ws}/.models/hri" <<'PY'
from pathlib import Path
import sys
import urllib.request
import zipfile
folder = Path(sys.argv[1])
name = 'vosk-model-small-vn-0.4'
if not (folder / name / 'am').is_dir():
    archive = folder / f'{name}.zip'
    urllib.request.urlretrieve(f'https://alphacephei.com/vosk/models/{name}.zip', archive)
    with zipfile.ZipFile(archive) as source:
        root = folder.resolve()
        if any(not (root / item.filename).resolve().is_relative_to(root) for item in source.infolist()):
            raise RuntimeError('Unexpected model archive path')
        source.extractall(folder)
    archive.unlink()
print('Vietnamese model ready:', folder / name)
PY
HF_HUB_DISABLE_XET=1 "${_vn_ws}/.venv-voice-nav/bin/python" - "${_vn_ws}/.models" <<'PY'
from pathlib import Path
import sys
from faster_whisper.utils import download_model
folder = Path(sys.argv[1])
model = folder / 'faster-whisper-small'
if not (model / 'model.bin').is_file():
    download_model('small', output_dir=str(model), cache_dir=str(folder / 'huggingface'))
print('Whisper model ready:', model)
PY
echo 'Setup complete. Build turtlebot4_lab and turtlebot4_voice_nav, then run ./run_voice_nav.bash'
