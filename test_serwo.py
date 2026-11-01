"""Krótki ruch serwa na kanale 0, potem powrót do środka."""

import time

from donkeycar.parts import pins
from donkeycar.parts.actuator import PulseController

SRODEK_PWM = 375  # Przybliżony środek według granic skrętu w config.py.
SKRET_PWM = 400  # Niewielkie wychylenie; kierunek do sprawdzenia.

# Podczas poprzedniej próby kanał 0 poruszał serwem.
serwo = PulseController(pins.pwm_pin_by_id("PCA9685.1:40.0"))

try:
    print(f"Serwo: środek, PWM = {SRODEK_PWM}.")
    serwo.set_pulse(SRODEK_PWM)
    time.sleep(1)

    print(f"Serwo: skręt przez 1 sekundę, PWM = {SKRET_PWM}.")
    serwo.set_pulse(SKRET_PWM)
    time.sleep(1)
finally:
    serwo.set_pulse(SRODEK_PWM)  # Powrót również po Ctrl+C.
    print("Serwo: powrót do środka.")
