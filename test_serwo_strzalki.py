"""Sterowanie WWW: python test_serwo_strzalki.py, potem http://IP_RASPBERRY:8000."""

import json
import secrets
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from donkeycar.parts import pins
from donkeycar.parts.actuator import PulseController

MIN_PWM = 300
MAX_PWM = 490
SRODEK_PWM = 410
KROK = 20
KIERUNEK_LEWO = 1  # Zmień na -1, jeżeli strzałki skręcają w odwrotne strony.
STOP_PWM = 370
JAZDA_PWM = 400

PORT = 8000
BRAK_POLACZENIA_STOP_S = 0.7  # Przeglądarka sama wysyła stan co 0,1 s.


STRONA = """<!doctype html>
<html lang="pl">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PiRacer — sterowanie</title>
<style>
  body { font: 18px system-ui, sans-serif; max-width: 620px; margin: 40px auto;
         padding: 0 20px; background: #f2f5f8; color: #17212b; }
  h1 { font-size: 28px; }
  button { font: inherit; padding: 20px; border: 0; border-radius: 12px;
           cursor: pointer; touch-action: none; user-select: none; }
  button:active, #gaz.aktywny { background: #c6e2ff; }
  .przyciski { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  #gaz { grid-column: 1 / -1; background: #cae9d4; }
  #stop { grid-column: 1 / -1; background: #f5c9c9; }
  #polacz { margin-top: 16px; }
  #stan { padding: 16px; background: white; border-radius: 12px; }
  small { display: block; line-height: 1.6; margin-top: 20px; }
</style>
<h1>PiRacer — sterowanie</h1>
<p>Trzymaj <b>W</b>, aby jechać. Puść W, aby zatrzymać silnik.</p>
<p><b>← / →</b>: skręt o 20 jednostek. Serwo zachowuje ustawiony skręt.</p>
<p id="stan" role="status">Łączenie…</p>
<div class="przyciski">
  <button id="gaz" type="button">W — trzymaj, aby jechać</button>
  <button id="lewo" type="button">← Lewo</button>
  <button id="prawo" type="button">Prawo →</button>
  <button id="stop" type="button">STOP — spacja / Q</button>
</div>
<button id="polacz" type="button" hidden onclick="location.reload()">Połącz ponownie</button>
<small>Możesz też używać przycisków na ekranie. Puszczenie gazu lub opuszczenie
okna zatrzymuje silnik. Utrata połączenia: STOP po około 0,7 s od ostatniej
wiadomości. Po przerwaniu połączenia kliknij „Połącz ponownie”.</small>
<script>
const sesja = __SESJA__;
const ustawienia = __USTAWIENIA__;
const stan = document.getElementById('stan');
const gazPrzycisk = document.getElementById('gaz');
let serwoPWM = ustawienia.srodek;
let klawiszW = false;
let dotykW = false;
let polaczenie = true;
let wysylanie = false;
let numer = 0;
let ostatniaOdpowiedz = 0;

function jedzie() { return klawiszW || dotykW; }

function wyczyscGaz() {
  klawiszW = false;
  dotykW = false;
  gazPrzycisk.classList.remove('aktywny');
}

function trescPolecenia() {
  return JSON.stringify({sesja, numer: ++numer, gaz: jedzie(), serwo_pwm: serwoPWM});
}

function ostatniStop() {
  // keepalive pozwala wysłać STOP również podczas zamykania strony.
  fetch('/steruj', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: trescPolecenia(), keepalive: true}).catch(() => {});
}

async function wyslij() {
  if (!polaczenie) return;
  const body = trescPolecenia();
  const mojNumer = numer;
  const kontroler = new AbortController();
  const limit = setTimeout(() => kontroler.abort(), 600);
  try {
    const odpowiedz = await fetch('/steruj', {method: 'POST',
      headers: {'Content-Type': 'application/json'}, body,
      signal: kontroler.signal, keepalive: !jedzie()});
    const dane = await odpowiedz.json();
    if (!odpowiedz.ok) throw new Error(dane.blad || 'Błąd sterowania.');
    if (polaczenie && mojNumer >= ostatniaOdpowiedz) {
      ostatniaOdpowiedz = mojNumer;
      stan.textContent = `Serwo PWM: ${dane.serwo_pwm} | Silnik PWM: ${dane.silnik_pwm}`;
    }
  } catch (blad) {
    if (!polaczenie) return;
    polaczenie = false;
    wyczyscGaz();
    ostatniStop();
    stan.textContent = 'STOP. ' + (blad.name === 'AbortError'
      ? 'Brak odpowiedzi samochodu.' : blad.message);
    document.getElementById('polacz').hidden = false;
    for (const przycisk of document.querySelectorAll('.przyciski button')) {
      przycisk.disabled = true;
    }
  } finally {
    clearTimeout(limit);
  }
}

async function odswiez() {
  if (wysylanie || !polaczenie || document.hidden) return;
  wysylanie = true;
  try { await wyslij(); } finally { wysylanie = false; }
}

function zmienGaz() {
  gazPrzycisk.classList.toggle('aktywny', jedzie());
  if (jedzie()) odswiez();
  else wyslij();  // STOP od razu, także gdy poprzednia wiadomość jeszcze trwa.
}

function stop() {
  wyczyscGaz();
  wyslij();
}

function skrec(kierunek) {
  if (!polaczenie) return;
  serwoPWM = Math.max(ustawienia.min, Math.min(ustawienia.max,
    serwoPWM + kierunek * ustawienia.krok * ustawienia.kierunek_lewo));
  odswiez();
}

document.addEventListener('keydown', event => {
  if (event.ctrlKey || event.altKey || event.metaKey) return;
  if (!['KeyW', 'ArrowLeft', 'ArrowRight', 'Space', 'KeyQ'].includes(event.code)) return;
  event.preventDefault();
  if (!polaczenie) return;
  if (event.code === 'KeyW' && !event.repeat) { klawiszW = true; zmienGaz(); }
  if (event.code === 'ArrowLeft') skrec(1);
  if (event.code === 'ArrowRight') skrec(-1);
  if (event.code === 'Space' || event.code === 'KeyQ') stop();
});
document.addEventListener('keyup', event => {
  if (event.code === 'KeyW') {
    event.preventDefault();
    klawiszW = false;
    zmienGaz();
  }
});

gazPrzycisk.addEventListener('pointerdown', event => {
  if (!polaczenie || event.button !== 0) return;
  event.preventDefault();
  gazPrzycisk.setPointerCapture(event.pointerId);
  dotykW = true;
  zmienGaz();
});
for (const zdarzenie of ['pointerup', 'pointercancel', 'lostpointercapture']) {
  gazPrzycisk.addEventListener(zdarzenie, () => { dotykW = false; zmienGaz(); });
}
document.getElementById('lewo').addEventListener('click', () => skrec(1));
document.getElementById('prawo').addEventListener('click', () => skrec(-1));
document.getElementById('stop').addEventListener('click', stop);
window.addEventListener('blur', stop);
window.addEventListener('pagehide', () => { wyczyscGaz(); ostatniStop(); });
document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });
setInterval(odswiez, 100);  // Stan trzymanego W, niezależny od powtarzania klawiszy.
odswiez();
</script>
</html>
"""


class Sterowanie:
    """Jeden wspólny dostęp do PWM dla strony i kontroli połączenia."""

    def __init__(self, silnik, serwo):
        self.silnik = silnik
        self.serwo = serwo
        self.pozycja = SRODEK_PWM
        self.gaz = STOP_PWM
        self.blokada = threading.Lock()
        self.sesja = None
        self.numer = -1
        self.ostatnia_wiadomosc = 0
        self.zamkniete = False

    def _gaz(self, wartosc):
        if wartosc != self.gaz:
            self.silnik.set_pulse(wartosc)
            self.gaz = wartosc

    def _sprawdz_czas(self):
        if self.sesja and time.monotonic() - self.ostatnia_wiadomosc >= BRAK_POLACZENIA_STOP_S:
            self.sesja = None  # Stare wiadomości nie uruchomią ponownie silnika.
            self._gaz(STOP_PWM)

    def nowa_sesja(self):
        with self.blokada:
            if self.zamkniete:
                raise RuntimeError('Sterowanie wyłączone. Uruchom skrypt ponownie.')
            self.silnik.set_pulse(STOP_PWM)
            self.gaz = STOP_PWM
            self.sesja = secrets.token_urlsafe(24)
            self.numer = -1
            self.ostatnia_wiadomosc = time.monotonic()
            return self.sesja, self.pozycja

    def polecenie(self, dane):
        with self.blokada:
            if self.zamkniete:
                raise RuntimeError('Sterowanie wyłączone. Uruchom skrypt ponownie.')
            self._sprawdz_czas()
            if not self.sesja or dane['sesja'] != self.sesja:
                raise ValueError('Sesja wygasła lub otwarto inną kartę. Połącz ponownie.')
            if dane['numer'] > self.numer:
                # Numery chronią przed opóźnionym gazem, który dotarłby po STOP.
                self.numer = dane['numer']
                pozycja = max(MIN_PWM, min(MAX_PWM, dane['serwo_pwm']))
                if pozycja != self.pozycja:
                    self.serwo.set_pulse(pozycja)
                    self.pozycja = pozycja
                self._gaz(JAZDA_PWM if dane['gaz'] else STOP_PWM)
                self.ostatnia_wiadomosc = time.monotonic()
            return {'serwo_pwm': self.pozycja, 'silnik_pwm': self.gaz}

    def sprawdz_polaczenie(self):
        with self.blokada:
            self._sprawdz_czas()

    def zamknij(self):
        with self.blokada:
            self.zamkniete = True
            self.sesja = None
            self.silnik.set_pulse(STOP_PWM)
            self.gaz = STOP_PWM


class ObslugaWWW(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(2)

    def odpowiedz(self, kod, tresc, typ='application/json; charset=utf-8'):
        zawartosc = tresc.encode('utf-8')
        self.send_response(kod)
        self.send_header('Content-Type', typ)
        self.send_header('Content-Length', str(len(zawartosc)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        try:
            self.wfile.write(zawartosc)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Osobny wątek zatrzyma silnik, jeśli przeglądarka zniknęła.

    def blad_sprzetu(self, blad):
        print(f'Błąd sterowania: {blad}', file=sys.stderr)
        try:
            self.server.sterowanie.zamknij()
        except Exception as blad_stop:
            print(f'Nie udało się wysłać STOP: {blad_stop}', file=sys.stderr)
        self.odpowiedz(503, json.dumps({'blad': 'Błąd PWM. Uruchom skrypt ponownie.'}))

    def do_GET(self):
        if self.path != '/':
            self.odpowiedz(404, '{}')
            return
        try:
            sesja, pozycja = self.server.sterowanie.nowa_sesja()
        except Exception as blad:
            self.blad_sprzetu(blad)
            return
        ustawienia = {'min': MIN_PWM, 'max': MAX_PWM, 'srodek': pozycja,
                      'krok': KROK, 'kierunek_lewo': KIERUNEK_LEWO}
        strona = STRONA.replace('__SESJA__', json.dumps(sesja))
        strona = strona.replace('__USTAWIENIA__', json.dumps(ustawienia))
        self.odpowiedz(200, strona, 'text/html; charset=utf-8')

    def do_POST(self):
        if self.path != '/steruj':
            self.odpowiedz(404, '{}')
            return
        # Przyjmuj polecenia tylko od strony otwartej na tym serwerze.
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.headers.get('Host', ''):
            self.odpowiedz(403, json.dumps({'blad': 'Niedozwolona strona.'}))
            return
        try:
            rozmiar = int(self.headers.get('Content-Length', '0'))
            if not 0 < rozmiar <= 1024:
                raise ValueError('Nieprawidłowy rozmiar polecenia.')
            dane = json.loads(self.rfile.read(rozmiar))
            if (not isinstance(dane, dict)
                    or not isinstance(dane.get('sesja'), str)
                    or type(dane.get('numer')) is not int or dane['numer'] < 0
                    or type(dane.get('gaz')) is not bool
                    or type(dane.get('serwo_pwm')) is not int):
                raise ValueError('Nieprawidłowe polecenie.')
        except (ValueError, OSError) as blad:
            self.odpowiedz(400, json.dumps({'blad': str(blad)}))
            return
        try:
            wynik = self.server.sterowanie.polecenie(dane)
        except ValueError as blad:
            self.odpowiedz(409, json.dumps({'blad': str(blad)}))
        except Exception as blad:
            self.blad_sprzetu(blad)
        else:
            self.odpowiedz(200, json.dumps(wynik))

    def log_message(self, _format, *args):
        pass  # Nie wypisuj każdej wiadomości wysyłanej co 0,1 s.


def pilnuj_polaczenia(sterowanie, koniec):
    while not koniec.wait(0.05):
        try:
            sterowanie.sprawdz_polaczenie()
        except Exception as blad:
            print(f'Błąd kontroli połączenia: {blad}', file=sys.stderr)
            sterowanie.zamknij()
            return


def zakoncz(_sygnal, _ramka):
    raise KeyboardInterrupt


def main():
    for sygnal in (signal.SIGHUP, signal.SIGTERM, signal.SIGTSTP):
        signal.signal(sygnal, zakoncz)
    silnik = PulseController(pins.pwm_pin_by_id('PCA9685.1:40.1'))
    sterowanie = None
    koniec = threading.Event()
    watek = None
    try:
        silnik.set_pulse(STOP_PWM)
        serwo = PulseController(pins.pwm_pin_by_id('PCA9685.1:40.0'))
        serwo.set_pulse(SRODEK_PWM)
        print('Silnik: STOP. Czekam 2 sekundy na regulator.')
        time.sleep(2)
        sterowanie = Sterowanie(silnik, serwo)
        with ThreadingHTTPServer(('0.0.0.0', PORT), ObslugaWWW) as serwer:
            serwer.sterowanie = sterowanie
            watek = threading.Thread(target=pilnuj_polaczenia,
                                     args=(sterowanie, koniec), daemon=True)
            watek.start()
            print(f'Otwórz na komputerze: http://IP_RASPBERRY:{PORT}')
            print('W: gaz; strzałki: skręt; spacja / Q: STOP. Ctrl+C zamyka serwer.')
            serwer.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if sterowanie is not None:
                sterowanie.zamknij()
            else:
                silnik.set_pulse(STOP_PWM)
        finally:
            koniec.set()
            if watek is not None:
                watek.join(timeout=1)
        print('Silnik: STOP. Serwo pozostaje w ostatniej ustawionej pozycji.')


if __name__ == '__main__':
    main()
