"""Próba napędu: sekunda gazu, potem STOP. Unieś koła przed uruchomieniem."""

import time

from donkeycar.parts import pins
from donkeycar.parts.actuator import PulseController

STOP_PWM = 370  # Zatrzymanie potwierdzone na samochodzie.
JAZDA_PWM = 400  # Wartość jazdy wybrana podczas próby na samochodzie.

# W sprawdzonym połączeniu silnik jest na kanale 1.
silnik = PulseController(pins.pwm_pin_by_id("PCA9685.1:40.1"))

try:
    print(f"Kanał 1: ustawiam STOP, PWM = {STOP_PWM}.")
    silnik.set_pulse(STOP_PWM)
    print("STOP — czekam 2 sekundy na uruchomienie regulatora.")
    time.sleep(2)

    print(f"Kanał 1: próba jazdy przez 1 sekundę, PWM = {JAZDA_PWM}.")
    silnik.set_pulse(JAZDA_PWM)
    time.sleep(1)
finally:
    silnik.set_pulse(STOP_PWM)  # STOP również po Ctrl+C.
    print(f"Kanał 1: STOP, PWM = {STOP_PWM}.")
