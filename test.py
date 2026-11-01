"""Próba napędu: sekunda gazu, potem STOP. Unieś koła przed uruchomieniem."""

import time

from donkeycar.parts import pins
from donkeycar.parts.actuator import PulseController

STOP_PWM = 370  # Wartość STOP zapisana w config.py.
JAZDA_PWM = 390  # Niewielki gaz do przodu; może nie wystarczyć do ruszenia.

# Według config.py: silnik na kanale 0, serwo na kanale 1.
silnik = PulseController(pins.pwm_pin_by_id("PCA9685.1:40.0"))
serwo = PulseController(pins.pwm_pin_by_id("PCA9685.1:40.1"))

try:
    silnik.set_pulse(STOP_PWM)
    serwo.set_pulse(375)  # Środek między zapisanymi granicami skrętu.
    print("STOP — czekam 2 sekundy na uruchomienie regulatora.")
    time.sleep(2)

    print(f"Jazda przez 1 sekundę, PWM = {JAZDA_PWM}.")
    silnik.set_pulse(JAZDA_PWM)
    time.sleep(1)
finally:
    silnik.set_pulse(STOP_PWM)  # STOP również po Ctrl+C.
    print("STOP")
