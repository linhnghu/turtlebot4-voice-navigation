#!/usr/bin/env python3
"""Record only the demo's RViz and YOLO windows, side by side, using ffmpeg."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=float, default=600,
                        help='Maximum real-time recording length in seconds')
    args = parser.parse_args()
    workspace = Path(__file__).resolve().parent
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        tree = subprocess.check_output(['xwininfo', '-root', '-tree'], text=True)
        rviz = re.search(r'(0x[0-9a-f]+) "[^"\n]*vision\.rviz[^"\n]*"', tree)
        yolo = re.search(r'(0x[0-9a-f]+) "TurtleBot 4 - YOLO RGB Camera"', tree)
        pointer = workspace / 'artifacts/latest_vision_run.txt'
        if rviz and yolo and pointer.exists():
            break
        time.sleep(0.5)
    else:
        raise SystemExit('Demo windows missing. Start ./run_vision_demo.bash with show_window:=true.')
    output = Path(pointer.read_text().strip())
    video = output / 'demo_rviz_yolo.mp4'
    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'warning', '-y']
    for window in (rviz, yolo):
        cmd += ['-thread_queue_size', '128', '-f', 'x11grab', '-framerate', '8',
                '-draw_mouse', '0', '-window_id', str(int(window.group(1), 16)),
                '-i', os.environ.get('DISPLAY', ':0')]
    cmd += ['-filter_complex',
            '[0:v]scale=800:850:force_original_aspect_ratio=decrease,'
            'pad=800:850:(ow-iw)/2:(oh-ih)/2[a];'
            '[1:v]scale=800:850:force_original_aspect_ratio=decrease,'
            'pad=800:850:(ow-iw)/2:(oh-ih)/2[b];[a][b]hstack=inputs=2[v]',
            '-map', '[v]', '-c:v', 'libx264', '-threads', '2', '-preset', 'veryfast',
            '-crf', '25', '-pix_fmt', 'yuv420p', '-t', str(args.duration), str(video)]
    print(f'Recording RViz + YOLO to {video}', flush=True)
    process = subprocess.Popen(cmd, stdin=subprocess.DEVNULL)
    completed_at = None
    try:
        while process.poll() is None:
            report = output / 'mission_results.json'
            if report.exists():
                try:
                    result = json.loads(report.read_text())
                except (OSError, ValueError):
                    result = {}
                if 'passed' in result and completed_at is None:
                    completed_at = time.monotonic()
            if completed_at and time.monotonic() - completed_at >= 5:
                process.send_signal(signal.SIGINT)
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
    finally:
        process.wait(timeout=15)
    print(f'Saved {video}', flush=True)


if __name__ == '__main__':
    main()
