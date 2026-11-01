"""Sterowanie serwem strzałkami w terminalu, bez powrotu do środka na końcu."""

import curses

from donkeycar.parts import pins
from donkeycar.parts.actuator import PulseController

MIN_PWM = 300
MAX_PWM = 460
SRODEK_PWM = 410
KROK = 10
KIERUNEK_LEWO = 1  # Zmień na -1, jeżeli strzałki skręcają w odwrotne strony.


def steruj(ekran):
    ekran.keypad(True)  # Odczyt strzałek bez naciskania Enter.
    ekran.clear()
    ekran.addstr(0, 0, "Strzałki lewo/prawo: skręt o 10 jednostek.")
    ekran.addstr(1, 0, f"Zakres: {MIN_PWM}–{MAX_PWM}. Środek: {SRODEK_PWM}.")
    ekran.addstr(5, 0, "Q / Ctrl+C: wyjście z zachowaniem pozycji.")

    serwo = PulseController(pins.pwm_pin_by_id("PCA9685.1:40.0"))
    pozycja = SRODEK_PWM
    serwo.set_pulse(pozycja)

    while True:
        ekran.addstr(3, 0, f"Aktualne PWM: {pozycja:3d}")
        ekran.refresh()
        klawisz = ekran.getch()

        if klawisz in (ord("q"), ord("Q")):
            break
        if klawisz == curses.KEY_LEFT:
            zmiana = KROK * KIERUNEK_LEWO
        elif klawisz == curses.KEY_RIGHT:
            zmiana = -KROK * KIERUNEK_LEWO
        else:
            continue

        nowa_pozycja = max(MIN_PWM, min(MAX_PWM, pozycja + zmiana))
        if nowa_pozycja != pozycja:
            serwo.set_pulse(nowa_pozycja)
            pozycja = nowa_pozycja


if __name__ == "__main__":
    try:
        curses.wrapper(steruj)  # Przywraca terminal również po Ctrl+C.
    except KeyboardInterrupt:
        pass
    print("Koniec. Serwo pozostaje w ostatniej ustawionej pozycji.")
