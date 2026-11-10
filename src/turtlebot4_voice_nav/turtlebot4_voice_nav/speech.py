"""Offline Vietnamese Whisper/Vosk, with microphone and WAV inputs."""
import json
from pathlib import Path
import queue
import time
import wave

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from .navigator import latched


def main(args=None):
    rclpy.init(args=args)
    node = Node('vietnamese_speech')
    model_path = node.declare_parameter('model_path', '').value
    backend = node.declare_parameter('backend', 'whisper').value
    whisper_path = node.declare_parameter('whisper_path', '').value
    wav_path = node.declare_parameter('wav_file', '').value
    device = int(node.declare_parameter('device', -1).value)
    pub = node.create_publisher(String, '/voice_nav/transcript', 10)
    status = node.create_publisher(String, '/voice_nav/speech_status', latched())

    def state(value, message):
        status.publish(String(data=json.dumps(dict(state=value, message=message), ensure_ascii=False)))
        node.get_logger().info(message)

    def publish(result):
        text = result.get('text', '').strip()
        if text:
            confidence = result.get('confidence', min((float(w['conf']) for w in result.get('result', [])), default=0.))
            data = dict(text=text, confidence=confidence, captured_at=result.get('captured_at', time.time()),
                        source='wav' if wav_path else 'microphone', backend=backend)
            pub.publish(String(data=json.dumps(data, ensure_ascii=False)))
            node.get_logger().info(json.dumps(data, ensure_ascii=False))

    try:
        if backend == 'whisper':
            from .whisper_speech import run
            run(node, whisper_path, wav_path, device, publish, state)
            return
        if backend != 'vosk':
            raise ValueError('backend phải là whisper hoặc vosk')
        from vosk import Model, KaldiRecognizer, SetLogLevel
        SetLogLevel(-1)
        if not Path(model_path, 'am').is_dir():
            raise ValueError('Thiếu mô hình Vosk tiếng Việt. Chạy ./setup_voice_nav.bash')
        state('LOADING', 'Đang nạp Vosk tiếng Việt...')
        model = Model(model_path)

        def recognizer(rate):
            rec = KaldiRecognizer(model, rate)
            # Open vocabulary: no grammar forcing unknown speech into known commands.
            rec.SetWords(True)
            return rec

        if wav_path:
            with wave.open(wav_path, 'rb') as audio:
                if audio.getnchannels() != 1 or audio.getsampwidth() != 2 or audio.getcomptype() != 'NONE':
                    raise ValueError('WAV phải là mono PCM signed 16-bit')
                rec = recognizer(audio.getframerate())
                # Allow DDS discovery before replay; no speech is published latched.
                until = time.monotonic()+1.5
                while rclpy.ok() and time.monotonic() < until:
                    rclpy.spin_once(node, timeout_sec=.1)
                while rclpy.ok():
                    block = audio.readframes(4000)
                    if not block:
                        break
                    if rec.AcceptWaveform(block):
                        publish(json.loads(rec.Result()))
                    rclpy.spin_once(node, timeout_sec=0)
                publish(json.loads(rec.FinalResult()))
                state('REPLAY_COMPLETE', 'Đã nhận dạng xong WAV; không phải kiểm thử microphone.')
                until = time.monotonic()+1
                while rclpy.ok() and time.monotonic() < until:
                    rclpy.spin_once(node, timeout_sec=.1)
            return
        import sounddevice as sd
        selected = None if device < 0 else device
        rate = int(sd.query_devices(selected, 'input')['default_samplerate'])
        rec = recognizer(rate)
        audio_queue = queue.Queue(maxsize=10)
        dropped = [False]

        def callback(data, frames, timing, audio_status):
            if audio_status:
                dropped[0] = True
            try:
                audio_queue.put_nowait((time.monotonic(), bytes(data)))
            except queue.Full:
                dropped[0] = True

        with sd.RawInputStream(samplerate=rate, blocksize=int(rate*.1), device=selected,
                               dtype='int16', channels=1, callback=callback):
            state('LISTENING', 'Microphone sẵn sàng: Đi đến khu vực A / B / C.')
            while rclpy.ok():
                rclpy.spin_once(node, timeout_sec=0)
                if dropped[0]:
                    while True:
                        try:
                            audio_queue.get_nowait()
                        except queue.Empty:
                            break
                    rec.Reset()
                    dropped[0] = False
                    state('AUDIO_DROPPED', 'Mất mẫu âm thanh; bỏ câu đang nghe, hãy nói lại.')
                try:
                    captured, block = audio_queue.get(timeout=.1)
                except queue.Empty:
                    continue
                if time.monotonic()-captured > .8:
                    rec.Reset()
                    continue
                if rec.AcceptWaveform(block):
                    publish(json.loads(rec.Result()))
                else:
                    partial = json.loads(rec.PartialResult()).get('partial', '')
                    if partial in ('dừng', 'dừng lại', 'hủy điều hướng'):
                        # A partial stop only cancels; partial movement is never sent.
                        publish(dict(text=partial, result=[dict(conf=1.)]))
                        rec.Reset()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        state('ERROR', f'Giọng nói chưa hoạt động: {exc}')
        raise SystemExit(1) from exc
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
