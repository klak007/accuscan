import datetime
from db_helper import save_event, check_database
from config import OFFLINE_MODE
import plc_helper


class AlarmManager:
    """
    Klasa AlarmManager obsługuje alarm defektów.

    Alarm defektów jest aktywowany, gdy jednocześnie przekroczone zostaną limity wybrzuszeń
    oraz zagłębień w oknie. Przejście ze stanu nieaktywnego na aktywny (oraz odwrotnie)
    rejestrowane jest w bazie danych za pomocą funkcji save_event, a zmiana stanu common fault
    aktualizowana jest w PLC przy pomocy funkcji lamp_control.
    """

    def __init__(self, db_params: dict, plc_client):
        """
        Inicjalizuje AlarmManager.
        
        :param db_params: Parametry połączenia z bazą danych.
        :param plc_client: Połączenie z PLC, wykorzystywane do sterowania lampką.
        """
        self.db_params = db_params
        self.plc_client = plc_client
        self.alarm_active = False  # Bieżący stan alarmu defektów (False - nieaktywny, True - aktywny)

    def update_alarm(self, lumps_in_window: int, necks_in_window: int,
                    max_lumps: int, max_necks: int,
                    measurement_data: dict) -> str:
        """
        Aktualizuje stan alarmu defektów.
        Zwraca:
        "entered"  - jeśli alarm właśnie się uaktywnił,
        "exited"   - jeśli alarm właśnie się wyłączył,
        "no_change" - jeśli stan alarmu nie uległ zmianie.
        """
        # 1) Obliczamy nowy stan (dla przykładu: alarm, jeśli lumps>max_lumps AND necks>max_necks)
        new_state = (lumps_in_window > max_lumps) and (necks_in_window > max_necks)
        
        # 2) Domyślnie brak zmiany
        state_change = "no_change"

        if new_state != self.alarm_active:
            # event_type = 0 => wejście, 1 => zejście
            event_type = 0 if new_state else 1
            self._save_event(measurement_data, event_type)
            self._update_common_fault(new_state)

            # Ustal, czy weszliśmy w alarm, czy z niego wyszliśmy
            if new_state:
                state_change = "entered"
            else:
                state_change = "exited"

        # 3) Zapisujemy nowy stan
        self.alarm_active = new_state
        
        return state_change

    def _save_event(self, measurement_data: dict, event_type: int):
        """
        Rejestruje zdarzenie w bazie danych za pomocą funkcji save_event z db_helper.

        :param measurement_data: Słownik zawierający dane pomiarowe.
        :param event_type: Typ zdarzenia: 0 - wejście w alarm, 1 - zejście z alarmu.
        """
        event_data = {
            "id_register_settings": measurement_data.get("id_register_settings"),
            "date_time": measurement_data.get("timestamp", datetime.datetime.now()),
            "x_coordinate": measurement_data.get("xCoord", 0.0),
            "product_nr": measurement_data.get("product", ""),
            "batch_nr": measurement_data.get("batch", ""),
            "alarm_statusword": measurement_data.get("statusword", 0),
            "D1": measurement_data.get("D1", 0.0),
            "D2": measurement_data.get("D2", 0.0),
            "D3": measurement_data.get("D3", 0.0),
            "D4": measurement_data.get("D4", 0.0),
            "lumps": measurement_data.get("lumps", 0),
            "necks": measurement_data.get("necks", 0),
            "alarm_type": "defects_alarm",
            "event_type": event_type,
            "comment": "Wejście w alarm defektów" if event_type == 0 else "Zejście z alarmu defektów"
        }

        if OFFLINE_MODE or not check_database(self.db_params):
            return

        if not save_event(self.db_params, event_data):
            print("Błąd zapisu zdarzenia w bazie dla alarmu defektów.")


    def _update_common_fault(self, is_active: bool):
        """
        Aktualizuje common fault w PLC. W zależności od stanu alarmu:
        - Jeśli is_active = True → ustawia się bit 55.0 (LampON = True) i bit 55.1 (LampOFF = False).
        - Jeśli is_active = False → ustawia się bit 55.0 (LampON = False) i bit 55.1 (LampOFF = True).
        """
        try:
            if self.plc_client:
                if is_active:
                    plc_helper.write_plc_data(self.plc_client, lamp_on=True, lamp_off=False)
                else:
                    plc_helper.write_plc_data(self.plc_client, lamp_on=False, lamp_off=True)
        except Exception as e:
            print("Błąd podczas aktualizacji common fault w PLC:", e)
