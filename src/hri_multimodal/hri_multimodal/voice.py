"""Optional offline microphone adapter using Vosk and sounddevice.

Run with the package's optional venv, which inherits system ROS packages.
No constrained grammar: unknown speech must stay unknown rather than being
forced into one of the movement commands.
"""
import json
from pathlib import Path
import queue

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from .fusion import voice_intent


def main(args=None):
    rclpy.init(args=args)
    node = Node('hri_voice')
    model_path = str(node.declare_parameter('model_path', '').value)
    device = int(node.declare_parameter('device', -1).value)
    pub = node.create_publisher(String, '/hri/voice', 10)
    try:
        import sounddevice as sd
        from vosk import KaldiRecognizer, Model
        if not Path(model_path, 'am').is_dir():
            raise ValueError('Set model_path to an extracted Vosk model; see README.md')
        model = Model(model_path)
        recognizer = KaldiRecognizer(model, 16000)
        recognizer.SetWords(True)
        audio = queue.Queue(maxsize=20)

        def callback(data, frames, timing, status):
            if status:
                node.get_logger().warning(str(status))
            try:
                audio.put_nowait(bytes(data))
            except queue.Full:
                # Drop queued audio instead of executing delayed commands.
                while not audio.empty():
                    try:
                        audio.get_nowait()
                    except queue.Empty:
                        break

        with sd.RawInputStream(samplerate=16000, blocksize=1600,
                               device=None if device < 0 else device,
                               dtype='int16', channels=1, callback=callback):
            node.get_logger().info('Microphone ready: Come here / Move forward / Stop')
            partial_stopped = False
            while rclpy.ok():
                rclpy.spin_once(node, timeout_sec=0)
                try:
                    block = audio.get(timeout=.1)
                except queue.Empty:
                    continue
                if recognizer.AcceptWaveform(block):
                    result = json.loads(recognizer.Result())
                    text = result.get('text', '')
                    words = result.get('result', [])
                    confidence = min((w['conf'] for w in words), default=0.)
                    if text:
                        pub.publish(String(data=json.dumps(dict(text=text, confidence=confidence))))
                        node.get_logger().info(f'{text!r} confidence={confidence:.2f}')
                    partial_stopped = False
                else:
                    partial = json.loads(recognizer.PartialResult()).get('partial', '')
                    if voice_intent(partial) == 'stop' and not partial_stopped:
                        # STOP need not wait for the utterance endpoint.
                        pub.publish(String(data=json.dumps(dict(text='Stop', confidence=1.0))))
                        partial_stopped = True
    except KeyboardInterrupt:
        pass
    except (ImportError, ValueError, OSError, RuntimeError) as exc:
        node.get_logger().error(f'Voice adapter unavailable: {exc}')
        raise SystemExit(1) from exc
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
