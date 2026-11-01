"""Ustawia serwo na kanale 0 i pozostawia je w wybranej pozycji."""

from donkeycar.parts import pins
from donkeycar.parts.actuator import PulseController

POZYCJA_PWM = 400  # Wpisz sprawdzoną pozycję; 410 = koła prosto.

# Podczas poprzedniej próby kanał 0 poruszał serwem.
serwo = PulseController(pins.pwm_pin_by_id("PCA9685.1:40.0"))

serwo.set_pulse(POZYCJA_PWM)
print(f"Serwo: ustawiono PWM = {POZYCJA_PWM}.")
# PCA9685 powtarza ustawiony sygnał również po zakończeniu skryptu.
print("Pozycja pozostaje ustawiona do zmiany sygnału lub wyłączenia zasilania.")
