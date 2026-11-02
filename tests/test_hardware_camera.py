"""Testy B1 bez Raspberry Pi: python3 -B -m unittest discover -s tests -v."""

import contextlib
import csv
import io
import json
import tempfile
import types
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import camera
import hardware

try:
    from PIL import Image
except ImportError:
    Image = None


class HardwareTests(unittest.TestCase):
    def setUp(self):
        self.calibration = hardware.load_calibration()

    def test_confirmed_calibration(self):
        c = self.calibration
        self.assertEqual((c.min_pwm, c.center_pwm, c.max_pwm), (300, 410, 490))
        self.assertEqual((c.step_pwm, c.left_direction, c.stop_pwm, c.drive_pwm), (20, 1, 370, 394))
        self.assertEqual((c.steering_pin, c.motor_pin), ('PCA9685.1:40.0', 'PCA9685.1:40.1'))

    def test_asymmetric_endpoints_and_midpoints(self):
        for steer_u, pwm in [(-1, 490), (-0.5, 450), (0, 410), (0.5, 355), (1, 300)]:
            with self.subTest(steer_u=steer_u):
                self.assertEqual(hardware.steer_to_pwm(steer_u, self.calibration), pwm)
                self.assertEqual(hardware.pwm_to_steer(pwm, self.calibration), steer_u)

    def test_every_pwm_round_trips_with_both_directions(self):
        for direction in (-1, 1):
            c = replace(self.calibration, left_direction=direction)
            for pwm in range(c.min_pwm, c.max_pwm + 1):
                steer_u = hardware.pwm_to_steer(pwm, c)
                self.assertTrue(-1 <= steer_u <= 1)
                self.assertEqual(hardware.steer_to_pwm(steer_u, c), pwm)

    def test_reversed_direction(self):
        c = replace(self.calibration, left_direction=-1)
        self.assertEqual(hardware.steer_to_pwm(-1, c), 300)
        self.assertEqual(hardware.steer_to_pwm(1, c), 490)
        self.assertEqual(hardware.steer_to_pwm(0, c), 410)

    def test_limits_and_rounding(self):
        c = self.calibration
        self.assertEqual(hardware.steer_to_pwm(-7, c), 490)
        self.assertEqual(hardware.steer_to_pwm(7, c), 300)
        self.assertEqual(hardware.pwm_to_steer(700, c), -1)
        self.assertEqual(hardware.pwm_to_steer(100, c), 1)
        self.assertEqual(hardware.steer_to_pwm(-0.123, c), 420)
        self.assertEqual(hardware.pwm_to_steer(420, c), -0.125)

    def test_nan_and_infinity_rejected(self):
        for value in (float('nan'), float('inf'), -float('inf')):
            for function in (hardware.steer_to_pwm, hardware.pwm_to_steer):
                with self.subTest(value=value, function=function.__name__), self.assertRaises(ValueError):
                    function(value, self.calibration)

    def test_invalid_calibration_rejected(self):
        for change in ({'center_pwm': 300}, {'left_direction': 0}, {'min_pwm': True},
                       {'drive_pwm': 370}, {'step_pwm': 0}, {'motor_pin': 'PCA9685.1:40.0'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(self.calibration, **change)

    def test_motor_has_only_drive_and_stop(self):
        self.assertEqual(hardware.throttle_to_pwm(True, self.calibration), 394)
        self.assertEqual(hardware.throttle_to_pwm(False, self.calibration), 370)
        with self.assertRaises(ValueError):
            hardware.throttle_to_pwm('False', self.calibration)

    def test_cli_interactive_and_reverse_conversion(self):
        output = io.StringIO()
        with patch('sys.argv', ['hardware.py', '--pwm', '355', '--interactive']), \
                patch('builtins.input', side_effect=['-0,5', 'nan', 'q']), \
                contextlib.redirect_stdout(output):
            hardware.main()
        text = output.getvalue()
        self.assertIn('jazda 394', text)
        self.assertIn('355 PWM -> steer_u   0.5000', text)
        self.assertIn('450 PWM', text)
        self.assertIn('Błąd:', text)


@unittest.skipIf(Image is None, 'Testy obrazu wymagają Pillow, dostarczanego z Picamera2.')
class CameraTests(unittest.TestCase):
    def setUp(self):
        test = self
        self.clock = 0.0
        self.devices = []

        class Request:
            def __init__(self, device):
                self.device = device
                self.released = False

            def get_metadata(self):
                return self.device.metadata

            def make_image(self, stream):
                test.assertEqual(stream, 'main')
                width, height = self.device.config['main']['size']
                image = Image.new('RGB', (width, height), (255, 0, 0))
                image.paste((0, 0, 255), (width // 2, 0, width, height))
                return image

            def release(self):
                self.released = True

        class Device:
            def __init__(self):
                test.devices.append(self)
                self.requests = []
                self.metadata = {'SensorTimestamp': 1_000_000_000}
                self.closed = False
                self.stopped = False

            def create_video_configuration(self, **config):
                return config

            def configure(self, config):
                self.config = config

            def camera_configuration(self):
                return self.config

            def start(self):
                pass

            def capture_request(self):
                test.clock += 0.1
                request = Request(self)
                self.requests.append(request)
                return request

            def stop(self):
                self.stopped = True

            def close(self):
                self.closed = True

        self.device_class = Device
        self.modules = patch.dict('sys.modules', {'picamera2': types.SimpleNamespace(Picamera2=Device)})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.time = patch.object(camera, 'time', types.SimpleNamespace(
            monotonic=lambda: self.clock, sleep=lambda _seconds: None))
        self.time.start()
        self.addCleanup(self.time.stop)

    def test_frame_uses_capture_metadata_and_correct_rgb(self):
        with camera.Camera(width=32, height=16) as stream:
            first = stream.read()
            device = self.devices[0]
            device.metadata = {'SensorTimestamp': 1_100_000_000}
            second = stream.read()
            self.assertEqual((first.frame_id, first.timestamp_ns), (1, 1_000_000_000))
            self.assertEqual((second.frame_id, second.timestamp_ns), (2, 1_100_000_000))
            self.assertEqual(first.image_rgb.mode, 'RGB')
            self.assertEqual(first.image_rgb.getpixel((0, 0)), (255, 0, 0))
            self.assertEqual(first.image_rgb.getpixel((31, 0)), (0, 0, 255))
            self.assertTrue(all(request.released for request in device.requests))
            self.assertEqual(device.config['main']['format'], 'BGR888')
            self.assertFalse(device.config['queue'])
        self.assertTrue(device.closed)
        self.assertTrue(device.stopped)

    def test_missing_or_stale_timestamp_releases_buffer(self):
        for metadata in ({}, {'SensorTimestamp': 0}, {'SensorTimestamp': 1_000_000_000}):
            with self.subTest(metadata=metadata), camera.Camera() as stream:
                stream.read()
                device = self.devices[-1]
                device.metadata = metadata
                with self.assertRaises(RuntimeError):
                    stream.read()
                self.assertTrue(device.requests[-1].released)

    def test_record_jpegs_csv_metadata_and_separate_sessions(self):
        original_capture = self.device_class.capture_request

        def capture(device):
            device.metadata = {'SensorTimestamp': 1_000_000_000 + len(device.requests) * 100_000_000}
            return original_capture(device)

        with tempfile.TemporaryDirectory() as temp, \
                patch.object(self.device_class, 'capture_request', capture), \
                contextlib.redirect_stdout(io.StringIO()), \
                camera.Camera(width=32, height=16) as stream:
            folder = camera.record_frames(stream, temp, 0.25)
            with (folder / 'frames.csv').open(newline='') as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 3)
            self.assertEqual([row['frame_id'] for row in rows], ['1', '2', '3'])
            self.assertEqual([row['timestamp_ns'] for row in rows],
                             ['1000000000', '1100000000', '1200000000'])
            for row in rows:
                with Image.open(folder / row['image']) as image:
                    self.assertEqual((image.size, image.mode), ((32, 16), 'RGB'))
                    self.assertGreater(image.getpixel((4, 4))[0], 200)
                    self.assertGreater(image.getpixel((28, 4))[2], 200)
            metadata = json.loads((folder / 'metadata.json').read_text())
            self.assertEqual(metadata['frames_saved'], 3)
            self.assertEqual(metadata['timestamp_clock'], 'CLOCK_BOOTTIME')
            self.assertEqual(metadata['image_color_order'], 'RGB')
            second_folder = camera.record_frames(stream, temp, 0.05)
            self.assertNotEqual(folder, second_folder)
            self.assertTrue((folder / '000001.jpg').exists())

    def test_record_failure_closes_camera_and_keeps_csv_consistent(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(OSError), camera.Camera() as stream, \
                    patch.object(Image.Image, 'save', side_effect=OSError('Disk full')):
                camera.record_frames(stream, temp, 1)
            folder = next(Path(temp).iterdir())
            with (folder / 'frames.csv').open() as file:
                self.assertEqual(len(list(csv.DictReader(file))), 0)
            self.assertEqual(json.loads((folder / 'metadata.json').read_text())['frames_saved'], 0)
            self.assertTrue(self.devices[-1].closed)

    def test_keyboard_interrupt_closes_camera(self):
        with self.assertRaises(KeyboardInterrupt), camera.Camera():
            raise KeyboardInterrupt
        self.assertTrue(self.devices[-1].closed)

    def test_configuration_failure_still_closes_camera(self):
        with patch.object(self.device_class, 'configure', side_effect=RuntimeError('Bad config')):
            with self.assertRaises(RuntimeError):
                camera.Camera().start()
        self.assertTrue(self.devices[-1].closed)

    def test_stop_failure_still_closes_device(self):
        with patch.object(self.device_class, 'stop', side_effect=RuntimeError('Stop failed')):
            with self.assertRaises(RuntimeError), camera.Camera():
                pass
        self.assertTrue(self.devices[-1].closed)

    def test_read_requires_started_camera(self):
        with self.assertRaises(RuntimeError):
            camera.Camera().read()

    def test_invalid_capture_settings(self):
        for settings in ({'fps': 0}, {'fps': float('nan')}, {'width': 0}, {'warmup_seconds': -1}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                camera.Camera(**settings)


if __name__ == '__main__':
    unittest.main()
