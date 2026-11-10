#!/usr/bin/env python3
"""Open input for 1 second; persist only device/level statistics, not audio."""
import json
from pathlib import Path
import numpy as np
import sounddevice as sd

report = dict(passed=False, human_commands_tested=False)
try:
    device = sd.query_devices(kind='input')
    rate = int(device['default_samplerate'])
    audio = sd.rec(rate, samplerate=rate, channels=1, dtype='int16')
    sd.wait()
    report.update(passed=len(audio) == rate, device=str(device['name']),
                  samplerate=rate, frames=len(audio), duration_seconds=1,
                  rms=float(np.sqrt(np.mean(audio.astype(float)**2))))
except Exception as exc:
    report['error'] = str(exc)
Path('artifacts/voice_nav/microphone_validation.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report))
raise SystemExit(0 if report['passed'] else 1)
