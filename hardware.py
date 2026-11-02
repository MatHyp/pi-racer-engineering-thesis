"""Etap B1: wspólna kalibracja i przeliczanie skrętu, bez zapisu do sprzętu.

python hardware.py
python hardware.py --steer -1 -0.5 0 0.5 1
python hardware.py --pwm 300 355 410 450 490
python hardware.py --interactive
"""

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

CALIBRATION_PATH = Path(__file__).with_name('calibration.json')


@dataclass(frozen=True)
class Calibration:
    steering_pin: str
    motor_pin: str
    min_pwm: int
    max_pwm: int
    center_pwm: int
    step_pwm: int
    left_direction: int
    stop_pwm: int
    drive_pwm: int

    def __post_init__(self):
        for name in ('min_pwm', 'max_pwm', 'center_pwm', 'stop_pwm', 'drive_pwm'):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= 4095:
                raise ValueError(f'{name} musi być liczbą całkowitą od 0 do 4095.')
        if not self.min_pwm < self.center_pwm < self.max_pwm:
            raise ValueError('Wymagane: min_pwm < center_pwm < max_pwm.')
        if type(self.step_pwm) is not int or self.step_pwm <= 0:
            raise ValueError('step_pwm musi być dodatnią liczbą całkowitą.')
        if type(self.left_direction) is not int or self.left_direction not in (-1, 1):
            raise ValueError('left_direction musi wynosić 1 albo -1.')
        if self.stop_pwm == self.drive_pwm:
            raise ValueError('STOP i jazda muszą mieć różne PWM.')
        for name in ('steering_pin', 'motor_pin'):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f'{name} musi zawierać identyfikator pinu.')
        if self.steering_pin == self.motor_pin:
            raise ValueError('Serwo i silnik muszą używać osobnych pinów.')

    @property
    def left_pwm(self):
        return self.max_pwm if self.left_direction == 1 else self.min_pwm

    @property
    def right_pwm(self):
        return self.min_pwm if self.left_direction == 1 else self.max_pwm


def load_calibration(path=CALIBRATION_PATH):
    with Path(path).open(encoding='utf-8') as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError('Kalibracja musi być obiektem JSON.')
    try:
        return Calibration(**data)
    except TypeError as error:
        raise ValueError(f'Nieprawidłowe pola kalibracji: {error}') from error


def _finite(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('Wartość musi być skończoną liczbą, bez NaN i inf.')
    return value


def steer_to_pwm(steer_u, calibration):
    """-1 = lewo, 0 = prosto, +1 = prawo; wynik to całkowite PWM.

    Każda strona ma własny zakres. Wartości spoza [-1, 1] są ograniczane.
    """
    steer_u = max(-1.0, min(1.0, _finite(steer_u)))
    endpoint = calibration.left_pwm if steer_u < 0 else calibration.right_pwm
    pwm = round(calibration.center_pwm + abs(steer_u) * (endpoint - calibration.center_pwm))
    return max(calibration.min_pwm, min(calibration.max_pwm, pwm))


def pwm_to_steer(pwm, calibration):
    """Odwrotne przeliczenie, przydatne do etykiet faktycznie wysłanego PWM."""
    pwm = max(calibration.min_pwm, min(calibration.max_pwm, _finite(pwm)))
    delta = pwm - calibration.center_pwm
    if delta == 0:
        return 0.0
    if delta * calibration.left_direction > 0:
        return -delta / (calibration.left_pwm - calibration.center_pwm)
    return delta / (calibration.right_pwm - calibration.center_pwm)


def throttle_to_pwm(driving, calibration):
    """Na tym etapie tylko dwie komendy: ustalona jazda albo STOP."""
    if type(driving) is not bool:
        raise ValueError('driving musi być True albo False.')
    return calibration.drive_pwm if driving else calibration.stop_pwm


def print_conversion(steer_u, calibration):
    pwm = steer_to_pwm(steer_u, calibration)
    applied_u = pwm_to_steer(pwm, calibration)
    direction = 'lewo' if applied_u < 0 else 'prawo' if applied_u > 0 else 'prosto'
    print(f'{steer_u:>10.4f} -> {pwm:>3} PWM -> {applied_u:>8.4f}  {direction}')


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--calibration', type=Path, default=CALIBRATION_PATH)
    parser.add_argument('--steer', type=float, nargs='+', help='Wartości steer_u do przeliczenia.')
    parser.add_argument('--pwm', type=int, nargs='+', help='PWM do przeliczenia na steer_u.')
    parser.add_argument('--interactive', action='store_true', help='Wpisuj steer_u w konsoli; q kończy.')
    args = parser.parse_args()
    try:
        calibration = load_calibration(args.calibration)
        print(f'Kalibracja: {args.calibration.resolve()}')
        print(f'Serwo: {calibration.steering_pin}; lewo {calibration.left_pwm}, '
              f'środek {calibration.center_pwm}, prawo {calibration.right_pwm}')
        print(f'Silnik: {calibration.motor_pin}; STOP {throttle_to_pwm(False, calibration)}, '
              f'jazda {throttle_to_pwm(True, calibration)}')
        print('Test przeliczeń w konsoli. Nie wysyłam sygnałów PWM.\n')
        print('  żądane u -> PWM     -> faktyczne u (po zaokrągleniu)')
        if args.steer is not None:
            values = args.steer
        elif args.pwm is None:
            values = [-1.0, -0.5, 0.0, 0.5, 1.0]
        else:
            values = []
        for value in values:
            print_conversion(value, calibration)
        if args.pwm is not None:
            for pwm in args.pwm:
                steer_u = pwm_to_steer(pwm, calibration)
                print(f'{pwm:>3} PWM -> steer_u {steer_u:>8.4f} '
                      f'(ograniczone PWM: {steer_to_pwm(steer_u, calibration)})')
        if args.interactive:
            print('\nWpisuj skręt od -1 do 1; np. -0.5, 0, 0.5. q kończy.')
            while True:
                text = input('steer_u> ').strip()
                if text.lower() in ('q', 'quit', 'exit'):
                    break
                try:
                    print_conversion(float(text.replace(',', '.')), calibration)
                except ValueError as error:
                    print(f'Błąd: {error}')
    except (KeyboardInterrupt, EOFError):
        print('\nKoniec testu.')
    except (OSError, ValueError) as error:
        parser.exit(1, f'Błąd: {error}\n')


if __name__ == '__main__':
    main()
