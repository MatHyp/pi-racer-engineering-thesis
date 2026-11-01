"""Próba napędu na kanale 1. Unieś koła przed uruchomieniem."""

import time

from donkeycar.parts import pins
from donkeycar.parts.actuator import PulseController

STOP_PWM = 370  # Wartość STOP zapisana w config.py.
JAZDA_PWM = 390  # Małe odchylenie od STOP; kierunek i próg ruszania do sprawdzenia.

# Kanał 0 poruszał serwem, więc napęd sprawdzamy na kanale 1.
silnik = PulseController(pins.pwm_pin_by_id("PCA9685.1:40.1"))

try:
    print(f"Silnik: STOP, PWM = {STOP_PWM}. Czekam 2 sekundy.")
    silnik.set_pulse(STOP_PWM)
    time.sleep(2)

    print(f"Silnik: gaz przez 1 sekundę, PWM = {JAZDA_PWM}.")
    silnik.set_pulse(JAZDA_PWM)
    time.sleep(1)
finally:
    silnik.set_pulse(STOP_PWM)  # STOP również po Ctrl+C.
    print("Silnik: STOP.")
