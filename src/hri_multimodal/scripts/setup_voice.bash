#!/usr/bin/env bash
set -euo pipefail
_hri_ws="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
/usr/bin/python3 -m venv --system-site-packages "${_hri_ws}/.venv-hri"
"${_hri_ws}/.venv-hri/bin/python" -m pip install -r "${_hri_ws}/src/hri_multimodal/requirements-voice.txt"
if ! /usr/bin/python3 -c 'from ctypes.util import find_library; assert find_library("portaudio")' 2>/dev/null; then
    mkdir -p "${_hri_ws}/.hri-runtime/debs"
    (
        cd "${_hri_ws}/.hri-runtime/debs"
        apt-get download libportaudio2
        for package in libportaudio2_*.deb; do
            dpkg-deb -x "$package" "${_hri_ws}/.hri-runtime"
        done
    )
    _hri_lib="${_hri_ws}/.hri-runtime/usr/lib/$(dpkg-architecture -qDEB_HOST_MULTIARCH)"
    ln -sfn libportaudio.so.2 "${_hri_lib}/libportaudio.so"
fi
mkdir -p "${_hri_ws}/.models/hri"
"${_hri_ws}/.venv-hri/bin/python" - "${_hri_ws}/.models/hri" <<'PY'
from pathlib import Path
import sys
import urllib.request
import zipfile

folder = Path(sys.argv[1])
name = 'vosk-model-small-en-us-0.15'
if not (folder / name / 'am').is_dir():
    archive = folder / f'{name}.zip'
    urllib.request.urlretrieve(f'https://alphacephei.com/vosk/models/{name}.zip', archive)
    with zipfile.ZipFile(archive) as source:
        root = folder.resolve()
        if any(not (root / item.filename).resolve().is_relative_to(root) for item in source.infolist()):
            raise RuntimeError('Unexpected path in model archive')
        source.extractall(folder)
    archive.unlink()
print('Model:', folder / name)
PY
