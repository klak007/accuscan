# plc_helper.py
import snap7
import subprocess
from time import sleep
from snap7.util import (
    get_bool, get_byte, get_word, get_real,
    set_bool, set_word, set_real
)
from config import OFFLINE_MODE

class PLCConnectionError(Exception):
    """Wyjątek rzucany, gdy nie uda się nawiązać lub utrzymać połączenia z PLC."""
    pass

# Global connection cache to avoid multiple connections to the same PLC
_plc_connections = {}
_plc_last_used = {}
_connection_locks = {}  # For thread safety on connection level
import threading

def connect_plc(ip: str, rack: int = 0, slot: int = 1, delay: int = 2, max_attempts: int = 10) -> snap7.client.Client:
    """
    Łączy się z PLC za pomocą Snap7.
    Tries to establish a connection, waiting 'delay' seconds between attempts.
    Uses connection caching to avoid multiple connections to the same PLC.
    
    Args:
        ip: IP address of the PLC
        rack: Rack number (default 0)
        slot: Slot number (default 1)
        delay: Delay between connection attempts in seconds (default 2)
        max_attempts: Maximum number of connection attempts (default 3, set to -1 for infinite)
    
    Returns:
        snap7.client.Client: Connected PLC client
        
    Raises:
        PLCConnectionError: If connection cannot be established after max_attempts
    """
    if OFFLINE_MODE:
        print("[PLC Helper] Offline mode: Skipped PLC connection.")
        return None

    global _plc_connections, _plc_last_used, _connection_locks
    import time
    
    # Create connection key
    conn_key = f"{ip}:{rack}:{slot}"
    
    # Create lock for this connection if it doesn't exist
    if conn_key not in _connection_locks:
        _connection_locks[conn_key] = threading.Lock()
    
    # Acquire lock for this connection
    with _connection_locks[conn_key]:
        # Check if we already have a connection to this PLC
        if conn_key in _plc_connections:
            client = _plc_connections[conn_key]
            # Update last used timestamp
            _plc_last_used[conn_key] = time.time()
            
            # Check if the connection is still valid
            if client.get_connected():
                print(f"[PLC Helper] Using existing connection to {ip}")
                return client
            else:
                # Connection is no longer valid, remove it
                print(f"[PLC Helper] Existing connection to {ip} is broken, creating new")
                try:
                    client.destroy()
                except:
                    pass
                del _plc_connections[conn_key]
    
        # Create a new connection
        attempt = 1
        while max_attempts < 0 or attempt <= max_attempts:
            try:
                # Try to ping first
                ping_cmd = ["ping", "-c", "1", ip] if subprocess.os.name == "posix" else ["ping", "-n", "1", ip]
                subprocess.run(ping_cmd, timeout=3, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                # Create and configure the client
                client = snap7.client.Client()
                
                # Connect
                client.connect(ip, rack, slot)
                
                if not client.get_connected():
                    raise PLCConnectionError(f"Nie udało się połączyć z PLC o IP {ip} (próba {attempt})")
                    
                # Store the connection in cache
                _plc_connections[conn_key] = client
                _plc_last_used[conn_key] = time.time()
                
                print(f"[PLC Helper] Successfully connected to PLC at {ip}")
                return client

            except Exception as e:
                print(f"[PLC Helper] Connection attempt {attempt} failed: {e}. Retrying in {delay} seconds...")
                attempt += 1
                if max_attempts < 0 or attempt <= max_attempts:
                    sleep(delay)
                else:
                    raise PLCConnectionError(f"Failed to connect to PLC at {ip} after {max_attempts} attempts")

def disconnect_plc(client_or_ip):
    """
    Properly disconnects and cleans up a PLC connection.
    
    Args:
        client_or_ip: Either a PLC client object or an IP address
    """
    global _plc_connections, _plc_last_used, _connection_locks
    
    if isinstance(client_or_ip, str):
        # We were given an IP address
        ip = client_or_ip
        # Find all connections to this IP
        for conn_key in list(_plc_connections.keys()):
            if conn_key.startswith(f"{ip}:"):
                disconnect_key = conn_key
                break
        else:
            print(f"[PLC Helper] No connection found for IP {ip}")
            return
    else:
        # We were given a client object
        client = client_or_ip
        # Find the connection key for this client
        for key, value in _plc_connections.items():
            if value is client:
                disconnect_key = key
                break
        else:
            # Client not in our cache, just disconnect it
            try:
                client.disconnect()
                client.destroy()
            except:
                pass
            return
    
    # We found a connection to disconnect
    if disconnect_key in _connection_locks:
        with _connection_locks[disconnect_key]:
            if disconnect_key in _plc_connections:
                client = _plc_connections[disconnect_key]
                try:
                    client.disconnect()
                    client.destroy()
                except:
                    pass
                del _plc_connections[disconnect_key]
                if disconnect_key in _plc_last_used:
                    del _plc_last_used[disconnect_key]
                print(f"[PLC Helper] Disconnected from {disconnect_key}")
    else:
        print(f"[PLC Helper] No lock found for {disconnect_key}, can't disconnect safely")

def read_plc_data(client: snap7.client.Client, db_number: int = 2) -> dict:
    """
    Odczytuje strukturę danych z DB sterownika (np. DB2) i zwraca wyniki
    jako słownik z nazwami kluczowymi (np. 'D1', 'D2', 'lumps').
    
    Handles "Job pending" errors with retries.
    """
    if OFFLINE_MODE or not client:
        return {"D1": 0, "D2": 0, "D3": 0, "D4": 0, "lumps": 0, "necks": 0}

    size = 56  # Rozmiar w bajtach, wymagany do odczytu offsetu (bylo 48)
    start = 0
    
    # Try with retries for job pending errors
    retry_count = 0
    max_retries = 3
    read_success = False
    
    while not read_success and retry_count < max_retries:
        try:
            raw_data = client.db_read(db_number, start, size)
            read_success = True
        except Exception as e:
            if "CLI: Job pending" in str(e):
                # Wait a bit and retry
                import time
                time.sleep(0.01 * (retry_count + 1))  # Exponential backoff
                retry_count += 1
                print(f"[PLC Helper] Job pending on read_plc_data, retrying {retry_count}/{max_retries}")
            else:
                # Re-raise other exceptions
                raise
    
    if not read_success:
        raise RuntimeError("[PLC Helper] Failed to read data from PLC after multiple retries")

    # Przykładowe odczyty (offsety dopasowane do struktury w PLC):
    status_byte = get_byte(raw_data, 0)
    d1 = get_real(raw_data, 2)
    d2 = get_real(raw_data, 6)
    d3 = get_real(raw_data, 10)
    d4 = get_real(raw_data, 14)
    lumps_count = get_word(raw_data, 18)
    necks_count = get_word(raw_data, 20)
    speed = get_real(raw_data, 22)  
    # print(f"[PLC Helper] Speed: {speed} m/min")
    status_plc = get_word(raw_data, 26)  

    # Przykładowe bity z obszaru 'Out' (offsety i bitmaski wg definicji w DB):
    zl_zero_lump_alarm = get_bool(raw_data, 28, 0)
    zn_zero_neck_alarm = get_bool(raw_data, 28, 1)
    zf_zero_lump_neck_alarm = get_bool(raw_data, 28, 2)
    zt_zero_diameter_tolerance_alarm = get_bool(raw_data, 28, 4)

    num_scans_averaging = get_word(raw_data, 30)
    flaw_preset_diameter = get_real(raw_data, 32)
    lump_threshold = get_real(raw_data, 36)
    neck_threshold = get_real(raw_data, 40)
    flaw_mode_word = get_word(raw_data, 44)
    upper_tol_preset = get_real(raw_data, 46)
    under_tol_preset = get_real(raw_data, 50)
    lamp_control= get_bool(raw_data, 55, 0)

    return {
        "status_byte": status_byte,
        "D1": d1, "D2": d2, "D3": d3, "D4": d4,
        "lumps": lumps_count,
        "necks": necks_count,
        "speed": speed,
        "status_plc": status_plc,
        "zl_zero_lump_alarm": zl_zero_lump_alarm,
        "zn_zero_neck_alarm": zn_zero_neck_alarm,
        "zf_zero_lump_neck_alarm": zf_zero_lump_neck_alarm,
        "zt_zero_diameter_tolerance_alarm": zt_zero_diameter_tolerance_alarm,
        #...
        "num_scans": num_scans_averaging,
        "flaw_preset_diameter": flaw_preset_diameter,
        "lump_threshold": lump_threshold,
        "neck_threshold": neck_threshold,
        "flaw_mode_word": flaw_mode_word,
        "upper_tolerance": upper_tol_preset,
        "under_tolerance": under_tol_preset,
        "lamp_control": lamp_control,
    }

def write_plc_data(
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
    under_tol: float=None,
    lamp_on: bool=False,
    lamp_off: bool=False

) -> None:
    """
    Zapisuje wybrane ustawienia 'Out' w DB2 (np. offset od 28 w górę).
    Jeśli użytkownik nie poda wartości dla średnicy lub progów, pozostaną one niezmienione.
    """
    size = 28  # Zakładany rozmiar (bajty) do zapisu od offsetu 28
    retry_count = 0
    max_retries = 3
    read_success = False
    
    while not read_success and retry_count < max_retries:
        try:
            read_success = True
        except Exception as e:
            if "CLI: Job pending" in str(e):
                # Wait a bit and retry
                import time
                time.sleep(0.01 * (retry_count + 1))  # Exponential backoff
                retry_count += 1
                print(f"[PLC Helper] Job pending on read, retrying {retry_count}/{max_retries}")
            else:
                # Re-raise other exceptions
                raise

    # Przygotowanie danych do zapisu
    write_data = bytearray(size)
    # print(f"[PLC Helper] Preparing data for write: {write_data.hex()}")
    # Ustawienie bitów w bajtach 0-1
    set_bool(write_data, 0, 0, zl if zl is not None else False)  # ZL
    set_bool(write_data, 0, 1, zn if zn is not None else False)  # ZN
    set_bool(write_data, 0, 2, zf if zf is not None else False)  # ZF
    set_bool(write_data, 0, 3, th if th is not None else False)  # TH
    set_bool(write_data, 0, 4, zt if zt is not None else False)  # ZT
    set_bool(write_data, 0, 5, et if et is not None else True)  # ET
    set_bool(write_data, 0, 6, el if el is not None else True)  # EL
    set_bool(write_data, 0, 7, en if en is not None else True)  # EN
    set_bool(write_data, 1, 0, eo if eo is not None else True)  # EO
    set_bool(write_data, 1, 1, zo if zo is not None else False)  # ZO

    # WORD num_scans
    set_word(write_data, 2, num_scans if num_scans is not None else 128)
    # REAL flaw_preset_diameter
    set_real(write_data, 4, flaw_preset_diameter if flaw_preset_diameter is not None else 18.0)
    set_real(write_data, 8, lump_threshold if lump_threshold is not None else 0.1)
    set_real(write_data, 12, neck_threshold if neck_threshold is not None else 0.1)
    # WORD flaw_mode
    set_word(write_data, 16, flaw_mode if flaw_mode is not None else 16386)
    # REAL upper_tol, under_tol
    set_real(write_data, 18, upper_tol if upper_tol is not None else 0.3)
    set_real(write_data, 22, under_tol if under_tol is not None else 0.3)
    set_bool(write_data, 27, 0, lamp_on if lamp_on else False)
    set_bool(write_data, 27, 1, lamp_off if lamp_off else False)
    # print(f"[PLC Helper] Data prepared for write: {write_data.hex()}")    

    # Zapis do DB (offset 22 w pamięci PLC) with error handling and retry
    retry_count = 0
    max_retries = 3
    write_success = False
    
    while not write_success and retry_count < max_retries:
        try:
            client.db_write(db_number, 28, write_data)
            write_success = True
        except Exception as e:
            if "CLI: Job pending" in str(e):
                # Wait a bit and retry
                import time
                time.sleep(0.02 * (retry_count + 1))  # Exponential backoff
                retry_count += 1
                print(f"[PLC Helper] Job pending on write, retrying {retry_count}/{max_retries}")
            else:
                # Re-raise other exceptions
                raise
    
    if not write_success:
        raise RuntimeError("[PLC Helper] Failed to write settings to PLC after multiple retries")

