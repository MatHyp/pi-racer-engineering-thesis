"""Etap B1: kamera CSI/Picamera2, RGB i klatki zapisane w images/<sesja>/.

python camera.py                     # test przez 10 sekund
python camera.py --seconds 30        # test przez 30 sekund
python camera.py --seconds 0         # do Ctrl+C

Wymaga Picamera2 na Raspberry Pi OS: sudo apt install python3-picamera2
Dokumentacja: https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import signal
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image

IMAGES_PATH = Path(__file__).with_name('images')


@dataclass(frozen=True)
class Frame:
    frame_id: int
    timestamp_ns: int  # Surowy SensorTimestamp kamery; zegar CLOCK_BOOTTIME.
    image_rgb: Image  # Obraz Pillow w RGB, gotowy także do np.asarray(...).


class Camera:
    """Jedyny właściciel kamery; read() zwraca obraz i metadane tej samej klatki."""

    def __init__(self, width=640, height=480, fps=10.0, warmup_seconds=2.0):
        if type(width) is not int or type(height) is not int or min(width, height) <= 0:
            raise ValueError('Szerokość i wysokość muszą być dodatnimi liczbami całkowitymi.')
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError('FPS musi być dodatnią, skończoną liczbą.')
        if not math.isfinite(warmup_seconds) or warmup_seconds < 0:
            raise ValueError('Czas rozgrzewania nie może być ujemny.')
        self.width, self.height = width, height
        self.fps = fps
        self.warmup_seconds = warmup_seconds
        self._camera = None
        self._started = False
        self._frame_id = 0
        self._last_timestamp_ns = 0

    def start(self):
        if self._camera is not None:
            raise RuntimeError('Ta kamera jest już uruchomiona.')
        try:
            from picamera2 import Picamera2
        except ImportError as error:
            raise RuntimeError('Brak Picamera2. Na Raspberry Pi: sudo apt install python3-picamera2. '
                               'Użyj Pythona z dostępem do pakietów systemowych '
                               '(venv: --system-site-packages).') from error
        try:
            self._camera = Picamera2()
            config = self._camera.create_video_configuration(
                # W Picamera2 BGR888 oznacza bajty [R, G, B]. make_image zwraca Pillow RGB.
                main={'size': (self.width, self.height), 'format': 'BGR888'},
                raw=None, controls={'FrameRate': self.fps}, buffer_count=4, queue=False,
            )
            self._camera.configure(config)
            actual = self._camera.camera_configuration()['main']
            self.width, self.height = actual['size']
            self._camera.start()
            self._started = True
            self._frame_id = 0
            self._last_timestamp_ns = 0
            time.sleep(self.warmup_seconds)  # Daj automatyce ekspozycji czas na ustawienie obrazu.
        except BaseException:
            self.close()
            raise
        return self

    def read(self):
        if not self._started:
            raise RuntimeError('Najpierw uruchom kamerę przez start() albo with Camera().')
        request = self._camera.capture_request()
        try:
            metadata = request.get_metadata()
            timestamp_ns = metadata.get('SensorTimestamp')
            if timestamp_ns is None or int(timestamp_ns) <= self._last_timestamp_ns:
                raise RuntimeError('Brak poprawnego, rosnącego SensorTimestamp dla klatki.')
            # Kopia jest niezależna od bufora, który za chwilę oddajemy kamerze.
            image_rgb = request.make_image('main').copy()
            if image_rgb.mode != 'RGB':
                image_rgb = image_rgb.convert('RGB')
            self._frame_id += 1
            self._last_timestamp_ns = int(timestamp_ns)
            return Frame(self._frame_id, self._last_timestamp_ns, image_rgb)
        finally:
            request.release()

    def close(self):
        camera, self._camera = self._camera, None
        started, self._started = self._started, False
        if camera is not None:
            try:
                if started:
                    camera.stop()
            finally:
                camera.close()

    def __enter__(self):
        return self.start()

    def __exit__(self, _type, _value, _traceback):
        self.close()


def record_frames(camera, output=IMAGES_PATH, seconds=10.0):
    """Osobny test zapisu; w przyszłym rejestratorze użyjemy bezpośrednio Camera.read()."""
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError('Czas nagrania musi być nieujemny; 0 oznacza zapis do Ctrl+C.')
    now = datetime.now(timezone.utc)
    folder = Path(output) / now.strftime('%Y%m%dT%H%M%S_%fZ')
    folder.mkdir(parents=True, exist_ok=False)
    metadata = {
        'created_utc': now.isoformat(),
        'width': camera.width, 'height': camera.height,
        'fps_requested': camera.fps,
        'picamera2_format': 'BGR888', 'image_color_order': 'RGB',
        'timestamp_source': 'SensorTimestamp', 'timestamp_clock': 'CLOCK_BOOTTIME',
        'timestamp_unit': 'ns', 'jpeg_quality': 90,
        'seconds_requested': seconds,
    }
    metadata_path = folder / 'metadata.json'
    metadata_path.write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    count = 0
    start = time.monotonic()
    print(f'Zapis do: {folder.resolve()}\nCtrl+C kończy zapis.')
    try:
        with (folder / 'frames.csv').open('w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['frame_id', 'timestamp_ns', 'image'])
            file.flush()
            while seconds == 0 or time.monotonic() - start < seconds:
                frame = camera.read()
                filename = f'{frame.frame_id:06d}.jpg'
                frame.image_rgb.save(folder / filename, format='JPEG', quality=90)
                writer.writerow([frame.frame_id, frame.timestamp_ns, filename])
                file.flush()
                count += 1
                print(f'Klatka {frame.frame_id:06d} | timestamp_ns={frame.timestamp_ns} | {filename}')
    finally:
        metadata['frames_saved'] = count
        metadata['elapsed_seconds'] = round(time.monotonic() - start, 3)
        metadata_path.write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
        print(f'Zapisano {count} klatek. Folder: {folder.resolve()}')
    return folder


def _stop(_signal, _frame):
    raise KeyboardInterrupt


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path, default=IMAGES_PATH, help='Katalog sesji testowych.')
    parser.add_argument('--seconds', type=float, default=10.0, help='Czas zapisu; 0 = do Ctrl+C.')
    parser.add_argument('--fps', type=float, default=10.0, help='Żądana liczba klatek/s; domyślnie 10.')
    parser.add_argument('--width', type=int, default=640)
    parser.add_argument('--height', type=int, default=480)
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds < 0:
        parser.error('--seconds musi być nieujemną, skończoną liczbą.')
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, _stop)
    try:
        with Camera(args.width, args.height, args.fps) as camera:
            record_frames(camera, args.output, args.seconds)
    except KeyboardInterrupt:
        print('\nZakończono test kamery.')
    except (ImportError, OSError, RuntimeError, ValueError, IndexError) as error:
        parser.exit(1, f'Błąd kamery: {error}\n')


if __name__ == '__main__':
    main()
