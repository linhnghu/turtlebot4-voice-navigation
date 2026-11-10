#!/usr/bin/env bash
set -euo pipefail
_reference_ws="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
/usr/bin/python3 -m venv --system-site-packages "${_reference_ws}/.venv-gesture"
"${_reference_ws}/.venv-gesture/bin/python" -m pip install -r "${_reference_ws}/src/hri_object_reference/requirements-camera.txt"
/usr/bin/python3 -m venv --system-site-packages "${_reference_ws}/.venv-hri"
"${_reference_ws}/.venv-hri/bin/python" -m pip install -r "${_reference_ws}/src/hri_object_reference/requirements-voice.txt"
if ! /usr/bin/python3 -c 'from ctypes.util import find_library; assert find_library("portaudio")' 2>/dev/null; then
    mkdir -p "${_reference_ws}/.hri-runtime/debs"
    (
        cd "${_reference_ws}/.hri-runtime/debs"
        apt-get download libportaudio2
        for package in libportaudio2_*.deb; do
            dpkg-deb -x "$package" "${_reference_ws}/.hri-runtime"
        done
    )
    _reference_lib="${_reference_ws}/.hri-runtime/usr/lib/$(dpkg-architecture -qDEB_HOST_MULTIARCH)"
    ln -sfn libportaudio.so.2 "${_reference_lib}/libportaudio.so"
fi
"${_reference_ws}/.venv-hri/bin/python" - "${_reference_ws}/.models/hri" <<'PY'
from pathlib import Path
import sys
import urllib.request
import zipfile
folder = Path(sys.argv[1]).resolve()
folder.mkdir(parents=True, exist_ok=True)
name = 'vosk-model-small-vn-0.4'
if not (folder / name / 'am').is_dir():
    archive = folder / f'{name}.zip'
    urllib.request.urlretrieve(f'https://alphacephei.com/vosk/models/{name}.zip', archive)
    with zipfile.ZipFile(archive) as source:
        for item in source.infolist():
            if not (folder / item.filename).resolve().is_relative_to(folder):
                raise ValueError('Unexpected model archive path')
        source.extractall(folder)
    archive.unlink()
print('Vietnamese offline model ready:', folder / name)
PY
