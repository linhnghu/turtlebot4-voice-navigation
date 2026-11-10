#!/usr/bin/env python3
"""Vietnamese WAV -> real offline ASR -> parser verification.

Uses existing WAV by default. Google/eSpeak fixture generation is explicit.
This is not a microphone or human-speaker benchmark. Publishes no movement.
"""
import argparse
import ctypes
import ctypes.util
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.parse
import urllib.request
import wave

from vosk import KaldiRecognizer, Model, SetLogLevel
import yaml
from turtlebot4_voice_nav.commands import CommandParser, CommandError


def synthesize(text, output):
    lib = ctypes.CDLL(ctypes.util.find_library('espeak-ng'))
    lib.espeak_Initialize.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    rate = lib.espeak_Initialize(2, 0, None, 0)
    if rate <= 0:
        raise RuntimeError('espeak initialization failed')
    chunks = []
    callback_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int, ctypes.c_void_p)

    @callback_type
    def callback(samples, count, events):
        if samples and count:
            chunks.append(ctypes.string_at(samples, count*2))
        return 0

    lib.espeak_SetSynthCallback(callback)
    lib.espeak_SetVoiceByName.argtypes = [ctypes.c_char_p]
    if lib.espeak_SetVoiceByName(b'vi'):
        raise RuntimeError('Vietnamese espeak voice unavailable')
    lib.espeak_SetParameter(1, 140, 0)  # Words per minute, absolute.
    encoded = text.encode('utf-8') + b'\0'
    lib.espeak_Synth.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_uint,
                                ctypes.c_int, ctypes.c_uint, ctypes.c_uint,
                                ctypes.c_void_p, ctypes.c_void_p]
    lib.espeak_Synth(encoded, len(encoded), 0, 0, 0, 1, None, None)
    lib.espeak_Synchronize()
    raw = output.with_suffix('.raw.wav')
    with wave.open(str(raw), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b''.join(chunks) + b'\0\0'*rate)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(raw),
                    '-ar', '16000', '-ac', '1', str(output)], check=True)
    raw.unlink()


def download_fixture(text, output):
    """Public demo sentence only; requires --engine google and network access."""
    query = urllib.parse.urlencode(dict(ie='UTF-8', client='tw-ob', tl='vi', q=text))
    request = urllib.request.Request('https://translate.google.com/translate_tts?' + query,
                                     headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(request, timeout=30) as response:
        mp3 = output.with_suffix('.mp3')
        mp3.write_bytes(response.read())
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(mp3),
                    '-ar', '16000', '-ac', '1', str(output)], check=True)
    mp3.unlink()


def recognize(model, path):
    with wave.open(str(path), 'rb') as audio:
        rec = KaldiRecognizer(model, audio.getframerate())
        rec.SetWords(True)
        results = []
        while True:
            block = audio.readframes(4000)
            if not block:
                break
            if rec.AcceptWaveform(block):
                results.append(json.loads(rec.Result()))
        results.append(json.loads(rec.FinalResult()))
    text = ' '.join(d.get('text', '') for d in results).strip()
    confidence = min((w['conf'] for d in results for w in d.get('result', [])), default=0.)
    return text, confidence


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', default='.models/faster-whisper-small')
    p.add_argument('--backend', choices=['whisper', 'vosk'], default='whisper')
    p.add_argument('--output', default='artifacts/voice_nav/speech')
    p.add_argument('--engine', choices=['google', 'espeak', 'existing'], default='existing',
                   help='existing uses command_1.wav through command_3.wav; google downloads public demo TTS')
    args = p.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[3]
    parser = CommandParser(yaml.safe_load((root/'src/turtlebot4_voice_nav/config/seeds.yaml').read_text())['regions'])
    SetLogLevel(-1)
    if args.backend == 'whisper':
        from turtlebot4_voice_nav.whisper_speech import WhisperRecognizer
        model = WhisperRecognizer(args.model)
    else:
        model = Model(args.model)
    checks = []
    for index, (sentence, expected) in enumerate([
            ('Đi đến phòng học', ['A']),
            ('Đi đến phòng thí nghiệm', ['B']),
            ('Đi đến hành lang', ['C'])]):
        wav = output / f'command_{index+1}.wav'
        if args.engine == 'google':
            download_fixture(sentence, wav)
        elif args.engine == 'espeak':
            # A fresh process per fixture avoids reinitializing libespeak.
            subprocess.run([sys.executable, '-c',
                            'from pathlib import Path; from check_speech import synthesize; '
                            'import sys; synthesize(sys.argv[1], Path(sys.argv[2]))', sentence, str(wav)],
                           env={**os.environ,
                                'PYTHONPATH': str(Path(__file__).parent) + ':' + os.environ.get('PYTHONPATH', '')},
                           check=True, timeout=30)
        if args.backend == 'whisper':
            recognized = model.recognize(str(wav))
            text, confidence = recognized['text'], recognized['confidence']
        else:
            text, confidence = recognize(model, wav)
        try:
            route = list(parser.parse(text).route)
            error = None
        except CommandError as exc:
            route, error = [], str(exc)
        checks.append(dict(original=sentence, transcript=text, confidence=confidence,
                           expected=expected, route=route, error=error,
                           wav=str(wav), passed=route == expected and confidence >= .65))
        print(json.dumps(checks[-1], ensure_ascii=False), flush=True)
    result = dict(passed=all(c['passed'] for c in checks),
                  input='wav_not_microphone', fixture_engine=args.engine, backend=args.backend,
                  grammar='open_vocabulary', checks=checks)
    (output/'speech_validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
