"""Offline Whisper with an explicit silence endpoint and no queued commands."""
import audioop
from collections import deque
import math
from pathlib import Path
import queue
import time

import numpy as np
import rclpy


class WhisperRecognizer:
    def __init__(self, model_path, region_names=None):
        from faster_whisper import WhisperModel
        if not Path(model_path, 'model.bin').is_file():
            raise ValueError('Thiếu mô hình Whisper; chạy ./setup_voice_nav.bash')
        self.model = WhisperModel(model_path, device='cpu', compute_type='int8',
                                  cpu_threads=2, local_files_only=True)
        self.context = 'Tên địa điểm: ' + '; '.join(region_names or [
            'phòng học', 'phòng thí nghiệm', 'hành lang']) + '.'

    def recognize(self, audio):
        segments, _ = self.model.transcribe(
            audio, language='vi', beam_size=5, temperature=0,
            condition_on_previous_text=False, vad_filter=True,
            initial_prompt=self.context, word_timestamps=False)
        segments = [s for s in segments if s.no_speech_prob < .6]
        return dict(text=' '.join(s.text.strip() for s in segments),
                    confidence=min((math.exp(s.avg_logprob) for s in segments), default=0.))


def run(node, model_path, wav_path, device, publish, state):
    state('LOADING', 'Đang nạp Whisper tiếng Việt offline...')
    region_file = node.declare_parameter('regions_file', '').value
    names = None
    if region_file:
        import yaml
        names = [r['name'] for r in yaml.safe_load(Path(region_file).read_text())['regions']]
    rec = WhisperRecognizer(model_path, names)
    if wav_path:
        # Wait for the command subscriber before publishing a non-latched replay.
        until = time.monotonic()+2
        while rclpy.ok() and time.monotonic() < until:
            rclpy.spin_once(node, timeout_sec=.1)
        publish(rec.recognize(wav_path))
        state('REPLAY_COMPLETE', 'Đã nhận dạng WAV bằng Whisper; không phải microphone.')
        until = time.monotonic()+1
        while rclpy.ok() and time.monotonic() < until:
            rclpy.spin_once(node, timeout_sec=.1)
        return
    import sounddevice as sd
    selected = None if device < 0 else device
    rate = int(sd.query_devices(selected, 'input')['default_samplerate'])
    threshold = float(node.declare_parameter('energy_threshold', 300.).value)
    audio_queue = queue.Queue(maxsize=15)
    overflow = [False]

    def callback(data, frames, timing, status):
        if status:
            overflow[0] = True
        try:
            audio_queue.put_nowait((time.monotonic(), bytes(data)))
        except queue.Full:
            overflow[0] = True

    def flush():
        while True:
            try:
                audio_queue.get_nowait()
            except queue.Empty:
                break
        overflow[0] = False

    with sd.RawInputStream(samplerate=rate, blocksize=int(rate*.1), device=selected,
                           channels=1, dtype='int16', callback=callback):
        state('LISTENING', 'Whisper sẵn sàng. Nói một câu rồi nghỉ 0.8 giây.')
        pre_roll, phrase = deque(maxlen=3), []
        silence, voiced = 0, 0
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0)
            if overflow[0]:
                flush()
                phrase, silence, voiced = [], 0, 0
                pre_roll.clear()
                state('AUDIO_DROPPED', 'Bỏ câu có âm thanh bị mất; hãy nói lại.')
            try:
                captured, block = audio_queue.get(timeout=.1)
            except queue.Empty:
                continue
            if time.monotonic()-captured > .8:
                phrase, silence, voiced = [], 0, 0
                pre_roll.clear()
                continue
            is_voice = audioop.rms(block, 2) >= threshold
            if not phrase:
                pre_roll.append(block)
                if is_voice:
                    phrase = list(pre_roll)
                    voiced = 1
                    silence = 0
                continue
            phrase.append(block)
            silence = 0 if is_voice else silence+1
            voiced += int(is_voice)
            if len(phrase) >= 100:
                # Never execute a truncated long utterance that may omit negation.
                phrase, silence, voiced = [], 0, 0
                pre_roll.clear()
                state('TOO_LONG', 'Câu dài hơn 10 giây; hãy nói lại ngắn hơn.')
                continue
            if silence < 8:
                continue
            if voiced >= 3:
                pcm = b''.join(phrase)
                if rate != 16000:
                    pcm, _ = audioop.ratecv(pcm, 2, 1, rate, 16000, None)
                audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)/32768.
                state('PROCESSING', 'Đang nhận dạng Whisper...')
                ended = time.time()
                result = rec.recognize(audio)
                result['captured_at'] = ended
                publish(result)
                # Audio spoken during inference is discarded, never queued.
                flush()
                state('LISTENING', 'Whisper sẵn sàng nhận câu tiếp theo.')
            phrase, silence, voiced = [], 0, 0
            pre_roll.clear()
