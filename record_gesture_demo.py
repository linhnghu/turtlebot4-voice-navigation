#!/usr/bin/env python3
"""Record Gazebo and the real gesture webcam side by side on X11/XWayland."""
import argparse
import os
from pathlib import Path
import re
import signal
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=float, default=180,
                        help='Recording time in seconds; start before performing gestures')
    args = parser.parse_args()
    if args.duration <= 0:
        parser.error('--duration must be positive')
    workspace = Path(__file__).resolve().parent
    pointer = workspace/'artifacts/latest_gesture_run.txt'
    deadline = time.monotonic()+90
    while time.monotonic() < deadline:
        tree = subprocess.check_output(['xwininfo','-root','-tree'], text=True)
        gazebo = re.search(r'(0x[0-9a-f]+) "Gazebo":', tree)
        webcam = re.search(r'(0x[0-9a-f]+) "TurtleBot 4 - Hand Gesture Webcam"', tree)
        if gazebo and webcam and pointer.exists():
            break
        time.sleep(.5)
    else:
        raise SystemExit('Start ./run_gesture_demo.bash with its webcam window visible first.')
    video = Path(pointer.read_text().strip())/'demo_gazebo_gestures.mp4'
    command = ['ffmpeg','-hide_banner','-loglevel','warning','-y']
    for window in (gazebo, webcam):
        command += ['-thread_queue_size','128','-f','x11grab','-framerate','15',
                    '-draw_mouse','0','-window_id',str(int(window.group(1),16)),
                    '-i',os.environ.get('DISPLAY',':0')]
    command += ['-filter_complex',
                '[0:v]scale=960:720:force_original_aspect_ratio=decrease,'
                'pad=960:720:(ow-iw)/2:(oh-ih)/2[a];'
                '[1:v]scale=800:720:force_original_aspect_ratio=decrease,'
                'pad=800:720:(ow-iw)/2:(oh-ih)/2[b];[a][b]hstack=inputs=2[v]',
                '-map','[v]','-c:v','libx264','-threads','2','-preset','veryfast',
                '-crf','23','-pix_fmt','yuv420p','-t',str(args.duration),str(video)]
    print(f'Recording Gazebo + webcam: {video}', flush=True)
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL)
    try:
        code = process.wait()
    except KeyboardInterrupt:
        process.send_signal(signal.SIGINT)
        code = process.wait(timeout=15)
    if code not in (0,255):
        raise SystemExit(f'ffmpeg failed ({code}); check X11/XWayland window capture.')
    print(f'Saved: {video}', flush=True)


if __name__ == '__main__':
    main()
