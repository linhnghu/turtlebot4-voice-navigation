"""Physical microphone -> offline Vosk transcription -> ROS speech input."""
import json
from pathlib import Path
import queue
import signal
import time

import numpy as np
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String

from .voice_core import transcript


def main(args=None):
    rclpy.init(args=args)
    node = Node('reference_microphone')
    model_path = str(node.declare_parameter('model_path', '').value)
    device = int(node.declare_parameter('device', -1).value)
    sample_rate = int(node.declare_parameter('sample_rate', 16000).value)
    minimum = float(node.declare_parameter('confidence', .6).value)
    speech = node.create_publisher(String, '/reference/speech', 10)
    transcripts = node.create_publisher(String, '/reference/transcript', 10)
    health = node.create_publisher(String, '/reference/mic_status', 1)
    blocks = queue.Queue(maxsize=8)
    overrun = False
    try:
        import sounddevice as sd
        from vosk import KaldiRecognizer, Model
        if not Path(model_path, 'am').is_dir():
            raise ValueError('Vosk model missing: run scripts/setup_live.bash')
        if not 0 <= minimum <= 1 or sample_rate < 8000:
            raise ValueError('invalid confidence or sample_rate')
        recognizer = KaldiRecognizer(Model(model_path), sample_rate)
        recognizer.SetWords(True)

        def callback(data, frames, timing, status):
            nonlocal overrun
            if status:
                overrun = True
            try:
                blocks.put_nowait((time.monotonic(), bytes(data)))
            except queue.Full:
                overrun = True

        chosen = None if device < 0 else device
        info = sd.query_devices(chosen, 'input')
        sd.check_input_settings(device=chosen, channels=1, dtype='int16', samplerate=sample_rate)
        # A 200 ms capture buffer avoids ALSA overflow at the very small
        # default latency while MediaPipe and the decoder are both running.
        with sd.RawInputStream(samplerate=sample_rate, blocksize=sample_rate // 5, device=chosen,
                               latency=.2, channels=1, dtype='int16', callback=callback):
            node.get_logger().info(f'Microphone ready: {info["name"]}; model={Path(model_path).name}')
            node.get_logger().info('Nói: Lấy vật này / Gắp vật màu đỏ. Giữ ngón trỏ tới khi hiện câu nói.')
            count, last_health, last_partial = 0, 0., ''
            while rclpy.ok():
                rclpy.spin_once(node, timeout_sec=0)
                try:
                    stamp, block = blocks.get(timeout=.1)
                except queue.Empty:
                    if time.monotonic() - last_health > .7:
                        health.publish(String(data=json.dumps(dict(healthy=False, reason='audio_stream_timeout'))))
                    continue
                if overrun or time.monotonic() - stamp > .8:
                    overrun = False
                    while not blocks.empty():
                        try:
                            blocks.get_nowait()
                        except queue.Empty:
                            break
                    recognizer.Reset()
                    transcripts.publish(String(data=json.dumps(dict(text='', accepted=False, reason='audio_overrun'))))
                    continue
                count += 1
                samples = np.frombuffer(block, dtype=np.int16).astype(float)
                rms = float(np.sqrt(np.mean(samples ** 2)))
                clipping = float(np.mean(np.abs(samples) >= 32000))
                if recognizer.AcceptWaveform(block):
                    data = transcript(json.loads(recognizer.Result()), minimum)
                    if data['text']:
                        transcripts.publish(String(data=json.dumps(data, ensure_ascii=False)))
                        if data['accepted']:
                            speech.publish(String(data=json.dumps(data, ensure_ascii=False)))
                        node.get_logger().info(f"STT {data['confidence']:.2f}: {data['text']} (accepted={data['accepted']})")
                    last_partial = ''
                else:
                    partial = json.loads(recognizer.PartialResult()).get('partial', '')
                    if partial != last_partial:
                        transcripts.publish(String(data=json.dumps(dict(text=partial, partial=True,
                                                                         accepted=False), ensure_ascii=False)))
                        last_partial = partial
                if time.monotonic() - last_health >= .2:
                    health.publish(String(data=json.dumps(dict(healthy=True, blocks=count, rms=round(rms, 1),
                        clip_fraction=round(clipping, 4), device=info['name'], model=Path(model_path).name))))
                    last_health = time.monotonic()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    except (ImportError, ValueError, OSError, RuntimeError) as exc:
        node.get_logger().error(f'Microphone unavailable: {exc}')
        raise
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        if rclpy.ok():
            health.publish(String(data=json.dumps(dict(healthy=False, reason='microphone_shutdown'))))
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
