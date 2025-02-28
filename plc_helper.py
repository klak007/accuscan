# plc_helper.py
import snap7
import subprocess
from time import sleep
from snap7.util import (
    get_bool, get_byte, get_word, get_real,
    set_bool, set_word, set_real
)

class PLCConnectionError(Exception):
    """Wyjątek rzucany, gdy nie uda się nawiązać lub utrzymać połączenia z PLC."""
    pass

def connect_plc(ip: str, rack: int = 0, slot: int = 1, delay: int = 2) -> snap7.client.Client:
    """
    Łączy się z PLC za pomocą Snap7.
    Próbujemy nawiązać połączenie w nieskończoność, czekając delay sekund między próbami.
    """
    attempt = 1
    while True:
        try:
            subprocess.run(["ping", "-n", "1", ip], timeout=3)
            sleep(1)
            client = snap7.client.Client()
            client.connect(ip, rack, slot)
            if not client.get_connected():
                raise PLCConnectionError(f"Nie udało się połączyć z PLC o IP {ip} (próba {attempt})")
            return client

        except Exception as e:
            print(f"Attempt {attempt} failed: {e}. Retrying in {delay} seconds...")
            attempt += 1
            sleep(delay)

def read_accuscan_data(client: snap7.client.Client, db_number: int = 2) -> dict:
    """
    Odczytuje strukturę danych z DB sterownika (np. DB2) i zwraca wyniki
    jako słownik z nazwami kluczowymi (np. 'D1', 'D2', 'lumps').
    """
    size = 48  # Rozmiar w bajtach, wymagany do odczytu offsetu 0..47
    start = 0
    raw_data = client.db_read(db_number, start, size)

    # Przykładowe odczyty (offsety dopasowane do struktury w PLC):
    status_byte = get_byte(raw_data, 0)
    d1 = get_real(raw_data, 2)
    d2 = get_real(raw_data, 6)
    d3 = get_real(raw_data, 10)
    d4 = get_real(raw_data, 14)
    lumps_count = get_word(raw_data, 18)
    necks_count = get_word(raw_data, 20)

    # Przykładowe bity z obszaru 'Out' (offsety i bitmaski wg definicji w DB):
    zl_zero_lump_alarm = get_bool(raw_data, 22, 0)
    zn_zero_neck_alarm = get_bool(raw_data, 22, 1)
    # ...

    num_scans_averaging = get_word(raw_data, 24)
    flaw_preset_diameter = get_real(raw_data, 26)
    lump_threshold = get_real(raw_data, 30)
    neck_threshold = get_real(raw_data, 34)
    flaw_mode_word = get_word(raw_data, 38)
    upper_tol_preset = get_real(raw_data, 40)
    under_tol_preset = get_real(raw_data, 44)

    return {
        "status_byte": status_byte,
        "D1": d1, "D2": d2, "D3": d3, "D4": d4,
        "lumps": lumps_count,
        "necks": necks_count,
        "zl_zero_lump_alarm": zl_zero_lump_alarm,
        "zn_zero_neck_alarm": zn_zero_neck_alarm,
        # ...
        "num_scans": num_scans_averaging,
        "flaw_preset_diameter": flaw_preset_diameter,
        "lump_threshold": lump_threshold,
        "neck_threshold": neck_threshold,
        "flaw_mode_word": flaw_mode_word,
        "upper_tolerance": upper_tol_preset,
        "under_tolerance": under_tol_preset
    }

def write_accuscan_out_settings(
    client: snap7.client.Client,
    db_number: int = 2,
    zl: bool=False, zn: bool=False, zf: bool=False, th: bool=False,
    zt: bool=False,
    et: bool=True,  # changed default to True: enable Diameter Tolerance Alarms
    el: bool=True,  # changed default to True: enable Lump Alarms
    en: bool=True,  # changed default to True: enable Neck Alarms
    eo: bool=True,  # changed default to True: enable Ovality Alarms
    zo: bool=False,
    num_scans: int=128,
    flaw_preset_diameter: float=None,
    lump_threshold: float=None,
    neck_threshold: float=None,
    flaw_mode: int=16386,
    upper_tol: float=None,
    under_tol: float=None
) -> None:
    """
    Zapisuje wybrane ustawienia 'Out' w DB2 (np. offset od 22 w górę).
    Jeśli użytkownik nie poda wartości dla średnicy lub progów, pozostaną one niezmienione.
    """
    size = 26  # Zakładany rozmiar (bajty) do zapisu od offsetu 22

    # Odczyt istniejących wartości z PLC
    existing_data = client.db_read(db_number, 22, size)

    # Pobranie aktualnych wartości, jeśli nie podano nowych
    if flaw_preset_diameter is None:
        flaw_preset_diameter = get_real(existing_data, 4)
    if lump_threshold is None:
        lump_threshold = get_real(existing_data, 8)
    if neck_threshold is None:
        neck_threshold = get_real(existing_data, 12)
    if upper_tol is None:
        upper_tol = get_real(existing_data, 18)
    if under_tol is None:
        under_tol = get_real(existing_data, 22)

    # Przygotowanie danych do zapisu
    write_data = bytearray(size)

    # Ustawienie bitów w bajtach 0-1
    set_bool(write_data, 0, 0, zl)
    set_bool(write_data, 0, 1, zn)
    set_bool(write_data, 0, 2, zf)
    set_bool(write_data, 0, 3, th)
    set_bool(write_data, 0, 4, zt)
    set_bool(write_data, 0, 5, et)
    set_bool(write_data, 0, 6, el)
    set_bool(write_data, 0, 7, en)
    set_bool(write_data, 1, 0, eo)
    set_bool(write_data, 1, 1, zo)

    # WORD num_scans
    set_word(write_data, 2, num_scans)
    # REAL flaw_preset_diameter
    set_real(write_data, 4, flaw_preset_diameter)
    set_real(write_data, 8, lump_threshold)
    set_real(write_data, 12, neck_threshold)
    # WORD flaw_mode
    set_word(write_data, 16, flaw_mode)
    # REAL upper_tol, under_tol
    set_real(write_data, 18, upper_tol)
    set_real(write_data, 22, under_tol)

    # Zapis do DB (offset 22 w pamięci PLC)
    client.db_write(db_number, 22, write_data)

