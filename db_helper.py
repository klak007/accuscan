# db_helper.py
import mysql.connector
from mysql.connector import Error
from datetime import datetime

def check_database(db_params: dict) -> bool:
    """
    Sprawdza czy można połączyć się z bazą danych.
    Zwraca True jeśli połączenie jest możliwe, False w przeciwnym przypadku.
    """
    connection = None
    try:
        connection = mysql.connector.connect(**db_params)
        if connection.is_connected():
            return True
    except Error as e:
        print(f"check_database() - Błąd MySQL: {e}")
        return False
    finally:
        if connection is not None and connection.is_connected():
            connection.close()
    return False

def init_database(db_params: dict) -> bool:
    """
    Inicjuje bazę danych: łączy się z MySQL 
    Zwraca True jeśli inicjalizacja się powiodła, False w przeciwnym przypadku.
    """
    print("init_database()")
    connection = None
    try:
        # Uwaga: klucz w db_params powinien nazywać się "database" zamiast "db"
        # jeśli stosujemy standardowe argumenty MySQL Connector
        print("db_params:", db_params)
        connection = mysql.connector.connect(**db_params)
        print("Połączono z bazą danych.")
        cursor = connection.cursor()
        
        # Zatwierdź zmiany
        connection.commit()
        print("init_database() - Inicjalizacja bazy danych zakończona sukcesem.")
        return True

    except Error as e:
        print(f"init_database() - Błąd MySQL: {e}")
        return False
    finally:
        if connection is not None and connection.is_connected():
            connection.close()

def save_measurement_sample(db_params: dict, data: dict) -> bool:
    """
    Zapisuje próbkę pomiarową do tabeli measurement:
      ID_Measurement (auto), Statusword, D1..D4, lumps number of, necks number of
    Zwraca True jeśli zapis się powiódł, False w przeciwnym przypadku.
    """
    if not check_database(db_params):
        return False
        
    connection = None
    try:
        connection = mysql.connector.connect(**db_params)
        cursor = connection.cursor()

        sql = """
        INSERT INTO measurement (
            Statusword, D1, D2, D3, D4,
            `lumps number of`, `necks number of`
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(
            sql,
            (
                data.get("statusword", 0),
                data.get("D1", 0.0), data.get("D2", 0.0),
                data.get("D3", 0.0), data.get("D4", 0.0),
                data.get("lumps", 0), data.get("necks", 0),
            )
        )
        connection.commit()
        return True
    except Error as e:
        print(f"save_measurement_sample() - Błąd MySQL: {e}")
        if connection:
            connection.rollback()
        return False
    finally:
        if connection is not None and connection.is_connected():
            connection.close()

def save_event(db_params: dict, event_data: dict) -> bool:
    """
    Zapisuje zdarzenie do tabeli event:
      Id register settings, Date time, X-coordinate, Product nr, Batch nr, 
      Alarm Statusword, D1..D4, lumps number of, necks number of
    Zwraca True jeśli zapis się powiódł, False w przeciwnym przypadku.
    """
    if not check_database(db_params):
        return False

    connection = None
    try:
        connection = mysql.connector.connect(**db_params)
        cursor = connection.cursor()
        sql = """
        INSERT INTO event (
            `Id register settings`,
            `Date time`, `X-coordinate`,
            `Product nr`, `Batch nr`,
            `Alarm Statusword`,
            D1, D2, D3, D4,
            `lumps number of`, `necks number of`
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(
            sql,
            (
                event_data.get("id_register_settings", None),
                event_data.get("date_time"),
                event_data.get("x_coordinate", 0.0),
                event_data.get("product_nr", ""),
                event_data.get("batch_nr", ""),
                event_data.get("alarm_statusword", 0),
                event_data.get("D1", 0.0),
                event_data.get("D2", 0.0),
                event_data.get("D3", 0.0),
                event_data.get("D4", 0.0),
                event_data.get("lumps", 0),
                event_data.get("necks", 0),
            )
        )
        connection.commit()
        return True
    except Error as e:
        print(f"save_event() - Błąd MySQL: {e}")
        if connection:
            connection.rollback()
        return False
    finally:
        if connection is not None and connection.is_connected():
            connection.close()

def save_settings(db_params: dict, settings_data: dict) -> int:
    """
    Zapisuje/aktualizuje rekord w tabeli settings:
      Id Settings, Product nr, Preset Diameter, Diameter Over tolerance, ...
    Zwraca ID rekordu w przypadku powodzenia, None w przeciwnym przypadku.
    """
    if not check_database(db_params):
        return None

    connection = None
    row_id = None
    try:
        connection = mysql.connector.connect(**db_params)
        cursor = connection.cursor()

        if "id_settings" in settings_data:
            sql = """
            UPDATE settings
            SET `Recipe name`=%s, `Product nr`=%s, `Preset Diameter`=%s, `Diameter Over tolerance`=%s,
                `Diameter Under tolerance`=%s, `Diameter window`=%s,
                `Diameter standard deviation`=%s, `Lump threshold`=%s,
                `Neck threshold`=%s, `Flaw Window`=%s,
                `Number of scans for gauge to average`=%s,
                `Diameter histeresis`=%s, `Lump histeresis`=%s,
                `Neck histeresis`=%s, `Max lumps in flaw window`=%s, 
                `Max necks in flaw window`=%s
            WHERE `Id Settings`=%s
            """
            cursor.execute(
                sql,
                (
                    settings_data.get("recipe_name", ""),
                    settings_data.get("product_nr", ""),
                    settings_data.get("preset_diameter", 0.0),
                    settings_data.get("diameter_over_tol", 0.5),
                    settings_data.get("diameter_under_tol", 0.5),
                    settings_data.get("diameter_window", 0.0),
                    settings_data.get("diameter_std_dev", 0.0),
                    settings_data.get("lump_threshold", 0.3),
                    settings_data.get("neck_threshold", 0.3),
                    settings_data.get("flaw_window", 0.0),
                    settings_data.get("num_scans", 128),
                    settings_data.get("diameter_histeresis", 0.0),
                    settings_data.get("lump_histeresis", 0.0),
                    settings_data.get("neck_histeresis", 0.0),
                    settings_data.get("max_lumps_in_flaw_window", 3),
                    settings_data.get("max_necks_in_flaw_window", 3),
                    settings_data["id_settings"]
                )
            )
            row_id = settings_data["id_settings"]
        else:
            sql = """
            INSERT INTO settings (
                `Recipe name`, `Product nr`, `Preset Diameter`, `Diameter Over tolerance`,
                `Diameter Under tolerance`, `Diameter window`,
                `Diameter standard deviation`, `Lump threshold`,
                `Neck threshold`, `Flaw Window`,
                `Number of scans for gauge to average`,
                `Diameter histeresis`, `Lump histeresis`,
                `Neck histeresis`, `Max lumps in flaw window`, 
                `Max necks in flaw window`
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(
                sql,
                (
                    settings_data.get("recipe_name", ""),
                    settings_data.get("product_nr", ""),
                    settings_data.get("preset_diameter", 0.0),
                    settings_data.get("diameter_over_tol", 0.5),
                    settings_data.get("diameter_under_tol", 0.5),
                    settings_data.get("diameter_window", 0.0),
                    settings_data.get("diameter_std_dev", 0.0),
                    settings_data.get("lump_threshold", 0.3),
                    settings_data.get("neck_threshold", 0.3),
                    settings_data.get("flaw_window", 0.0),
                    settings_data.get("num_scans", 128),
                    settings_data.get("diameter_histeresis", 0.0),
                    settings_data.get("lump_histeresis", 0.0),
                    settings_data.get("neck_histeresis", 0.0),
                    settings_data.get("max_lumps_in_flaw_window", 3),
                    settings_data.get("max_necks_in_flaw_window", 3),
                )
            )
            row_id = cursor.lastrowid
        
        connection.commit()
        # Zapisz do tabeli settings_register
        from datetime import datetime
        history_data = {
            "datetime": datetime.now(),
            "recipe_name": settings_data.get("recipe_name", ""),
            "product_nr": settings_data.get("product_nr", ""),
            "preset_diameter": settings_data.get("preset_diameter", 0.0),
            "diameter_over_tol": settings_data.get("diameter_over_tol", 0.5),
            "diameter_under_tol": settings_data.get("diameter_under_tol", 0.5),
            "diameter_window": settings_data.get("diameter_window", 0.0),
            "diameter_std_dev": settings_data.get("diameter_std_dev", 0.0),
            "lump_threshold": settings_data.get("lump_threshold", 0.3),
            "neck_threshold": settings_data.get("neck_threshold", 0.3),
            "flaw_window": settings_data.get("flaw_window", 0.0),
            "num_scans": settings_data.get("num_scans", 128),
            "diameter_histeresis": settings_data.get("diameter_histeresis", 0.0),
            "lump_histeresis": settings_data.get("lump_histeresis", 0.0),
            "neck_histeresis": settings_data.get("neck_histeresis", 0.0),
            "max_lumps_in_flaw_window": settings_data.get("max_lumps_in_flaw_window", 3),
            "max_necks_in_flaw_window": settings_data.get("max_necks_in_flaw_window", 3),
        }
        save_settings_history(db_params, history_data)
        return row_id
    except Error as e:
        print(f"save_settings() - Błąd MySQL: {e}")
        if connection:
            connection.rollback()
        return None
    finally:
        if connection is not None and connection.is_connected():
            connection.close()

def save_settings_history(db_params: dict, settings_data: dict) -> bool:
    """
    Dodaje historyczny zapis do settings_register:
      Id register Settings, Date time, Product nr, Preset Diameter, ...
    Zwraca True jeśli zapis się powiódł, False w przeciwnym przypadku.
    """
    if not check_database(db_params):
        return False

    connection = None
    try:
        connection = mysql.connector.connect(**db_params)
        cursor = connection.cursor()
        sql = """
        INSERT INTO settings_register (
            `Date time`, `Recipe name`, `Product nr`, `Preset Diameter`,
            `Diameter Over tolerance`, `Diameter Under tolerance`,
            `Diameter window`, `Diameter standard deviation`,
            `Lump threshold`, `Neck threshold`, `Flaw Window`,
            `Number of scans for gauge to average`,
            `Diameter histeresis`, `Lump histeresis`,
            `Neck histeresis`, `Max lumps in flaw window`,
            `Max necks in flaw window`
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(
            sql,
            (
                settings_data.get("datetime"),
                settings_data.get("recipe_name", ""),
                settings_data.get("product_nr", ""),
                settings_data.get("preset_diameter", 0.0),
                settings_data.get("diameter_over_tol", 0.5),
                settings_data.get("diameter_under_tol", 0.5),
                settings_data.get("diameter_window", 0.0),
                settings_data.get("diameter_std_dev", 0.0),
                settings_data.get("lump_threshold", 0.3),
                settings_data.get("neck_threshold", 0.3),
                settings_data.get("flaw_window", 0.0),
                settings_data.get("num_scans", 128),
                settings_data.get("diameter_histeresis", 0.0),
                settings_data.get("lump_histeresis", 0.0),
                settings_data.get("neck_histeresis", 0.0),
                settings_data.get("max_lumps_in_flaw_window", 3),
                settings_data.get("max_necks_in_flaw_window", 3),
            )
        )
        connection.commit()
        return True
    except Error as e:
        print(f"save_settings_history() - Błąd MySQL: {e}")
        if connection:
            connection.rollback()
        return False
    finally:
        if connection is not None and connection.is_connected():
            connection.close()

def load_settings(db_params: dict, settings_id: int) -> dict:
    """
    Odczytuje jeden rekord z tabeli settings.
    """
    if not check_database(db_params):
        return {}

    connection = None
    try:
        connection = mysql.connector.connect(**db_params)
        cursor = connection.cursor(dictionary=True)
        sql = "SELECT * FROM settings WHERE id=%s"
        cursor.execute(sql, (settings_id,))
        row = cursor.fetchone()
        if row is None:
            return {}
        return row
    except Error as e:
        print(f"load_settings() - Błąd MySQL: {e}")
        return {}
    finally:
        if connection is not None and connection.is_connected():
            connection.close()

def save_detection_event(db_params: dict, event_data: dict) -> bool:
    """
    Zapisuje zdarzenie lumps/necks do tabeli 'events'.
    Wykorzystuje klucze w event_data: 
    id_register_settings, date_time, x_coordinate, distance,
    product, batch, alarm_status_word, D1, D2, D3, D4, lumps, necks, result.
    Zwraca True jeśli zapis się powiódł, False w przeciwnym przypadku.
    """
    if not check_database(db_params):
        return False

    connection = None
    try:
        connection = mysql.connector.connect(**db_params)
        cursor = connection.cursor()
        sql = """
        INSERT INTO events (
            id_register_settings, date_time, x_coordinate, distance,
            product_nr, batch_nr, alarm_status_word,
            D1, D2, D3, D4, lumps, necks, result
        )
        VALUES (
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s
        )
        """
        cursor.execute(sql, (
            event_data.get("id_register_settings", None),
            event_data.get("date_time"),
            event_data.get("x_coordinate", 0.0),
            event_data.get("distance", 0.0),
            event_data.get("product_nr", ""),
            event_data.get("batch_nr", ""),
            event_data.get("alarm_status_word", 0),
            event_data.get("D1", 0.0),
            event_data.get("D2", 0.0),
            event_data.get("D3", 0.0),
            event_data.get("D4", 0.0),
            event_data.get("lumps", 0),
            event_data.get("necks", 0),
            event_data.get("result", ""),
        ))
        connection.commit()
        return True
    except Error as e:
        print(f"save_detection_event() - Błąd MySQL: {e}")
        if connection:
            connection.rollback()
        return False
    finally:
        if connection is not None and connection.is_connected():
            connection.close()
