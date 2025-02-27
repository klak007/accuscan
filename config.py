# config.py

# Adres i parametry połączenia z PLC (S7-1200)
PLC_IP = "192.168.50.90"  # Przykładowy adres sterownika
PLC_RACK = 0            # Zwykle 0 przy S7-1200
PLC_SLOT = 1            # Często 1 przy S7-1200

# Parametry bazy danych MySQL
DB_PARAMS = {
    "host": "localhost",
    "user": "root",
    "password": "root",
    "db": "accuscan_db",
    "port": 3306
}


# Opcjonalnie można zdefiniować interwał odczytu (w sekundach)
# np. co 50 ms => 0.05 s
READ_INTERVAL_S = 0.05

# Maksymalna liczba próbek, którą trzymamy w DataFrame (okno przesuwne)
MAX_SAMPLES = 1000

