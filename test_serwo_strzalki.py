"""Strzałki sterują serwem, a powtarzane W podaje gaz w terminalu SSH."""

import curses
import signal
import time

from donkeycar.parts import pins
from donkeycar.parts.actuator import PulseController

MIN_PWM = 300
MAX_PWM = 490
SRODEK_PWM = 410
KROK = 20
KIERUNEK_LEWO = 1  # Zmień na -1, jeżeli strzałki skręcają w odwrotne strony.
STOP_PWM = 370
JAZDA_PWM = 400
BRAK_W_STOP_S = 0.7  # SSH nie przekazuje puszczenia klawisza.


def steruj(ekran):
    ekran.keypad(True)  # Odczyt strzałek bez naciskania Enter.
    ekran.timeout(50)  # Sprawdzaj czas także wtedy, gdy nie ma nowych klawiszy.
    ekran.clear()
    ekran.addstr(0, 0, f"Strzałki lewo/prawo: skręt o {KROK} jednostek.")
    ekran.addstr(1, 0, f"Zakres: {MIN_PWM}–{MAX_PWM}. Środek: {SRODEK_PWM}.")
    ekran.addstr(2, 0, f"W: gaz {JAZDA_PWM}. Brak W przez {BRAK_W_STOP_S} s: STOP.")
    ekran.addstr(6, 0, "Q / Ctrl+C: STOP i wyjście. Serwo zachowuje pozycję.")

    silnik = PulseController(pins.pwm_pin_by_id("PCA9685.1:40.1"))
    try:
        silnik.set_pulse(STOP_PWM)
        serwo = PulseController(pins.pwm_pin_by_id("PCA9685.1:40.0"))
        pozycja = SRODEK_PWM
        serwo.set_pulse(pozycja)
        gaz = STOP_PWM
        ostatnie_w = None

        ekran.addstr(4, 0, "Silnik: STOP. Czekam 2 sekundy na regulator.")
        ekran.refresh()
        time.sleep(2)
        curses.flushinp()  # Pomiń klawisze naciśnięte podczas uruchamiania.
        ekran.move(4, 0)
        ekran.clrtoeol()

        while True:
            ekran.addstr(3, 0, f"Serwo PWM: {pozycja:3d}")
            ekran.addstr(4, 0, f"Silnik PWM: {gaz:3d}")
            ekran.refresh()
            klawisz = ekran.getch()
            teraz = time.monotonic()

            if klawisz in (ord("q"), ord("Q")):
                break
            if klawisz in (ord("w"), ord("W")):
                ostatnie_w = teraz
            elif klawisz in (curses.KEY_LEFT, curses.KEY_RIGHT):
                zmiana = KROK * KIERUNEK_LEWO
                if klawisz == curses.KEY_RIGHT:
                    zmiana = -zmiana
                nowa_pozycja = max(MIN_PWM, min(MAX_PWM, pozycja + zmiana))
                if nowa_pozycja != pozycja:
                    serwo.set_pulse(nowa_pozycja)
                    pozycja = nowa_pozycja

            nowy_gaz = STOP_PWM
            if ostatnie_w is not None and teraz - ostatnie_w < BRAK_W_STOP_S:
                nowy_gaz = JAZDA_PWM
            if nowy_gaz != gaz:
                silnik.set_pulse(nowy_gaz)
                gaz = nowy_gaz
    finally:
        silnik.set_pulse(STOP_PWM)  # STOP po Q, Ctrl+C, błędzie lub sygnale zamknięcia.


def zakoncz(_sygnal, _ramka):
    raise KeyboardInterrupt


if __name__ == "__main__":
    for sygnal in (signal.SIGHUP, signal.SIGTERM, signal.SIGTSTP):
        signal.signal(sygnal, zakoncz)
    try:
        curses.wrapper(steruj)  # Przywraca terminal również po Ctrl+C.
    except KeyboardInterrupt:
        pass
    print("Silnik: STOP. Serwo pozostaje w ostatniej ustawionej pozycji.")
