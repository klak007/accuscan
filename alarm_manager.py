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
        # Stan obecnego alarmu defektów (może być rozwinięte o stany alarmu średnicy i pulsacji)
        self.defects_alarm_active = False
        self.diameter_alarm_active = False
        self.pulsation_alarm_active = False

    def check_and_update_defects_alarm(
        self,
        lumps_in_window: int,
        necks_in_window: int,
        measurement_data: dict,
        max_lumps: int,
        max_necks: int
    ) -> str:
        """
        Sprawdza, czy przekroczono limity defektów (wybrzuszeń i zagłębień).
        Jeśli tak, ustawia/wyłącza alarm defektów. Zwraca "entered", "exited" lub "no_change".
        """
        # Warunek alarmu, gdy lumps>max_lumps ORAZ necks>max_necks (wg Twojej logiki)
        new_state = (lumps_in_window > max_lumps) and (necks_in_window > max_necks)
        old_state = self.defects_alarm_active

        if new_state != old_state:
            # Zmiana stanu
            event_type = 0 if new_state else 1  # 0=wejście, 1=wyjście
            alarm_type = "defects_alarm"
            comment = "Wejście w alarm defektów" if new_state else "Zejście z alarmu defektów"

            self._save_event(measurement_data, event_type, alarm_type, comment)
            self._update_common_fault(new_state)

            self.defects_alarm_active = new_state
            return "entered" if new_state else "exited"
        return "no_change"

    def check_and_update_diameter_alarm(
        self,
        measurement_data: dict,
        upper_tol: float,
        lower_tol: float
    ) -> str:
        """
        Sprawdza, czy którakolwiek z wartości D1, D2, D3, D4
        jest poza zakresem [dAvg - lower_tol, dAvg + upper_tol].
        """
        d1 = measurement_data.get("D1", 0.0)
        d2 = measurement_data.get("D2", 0.0)
        d3 = measurement_data.get("D3", 0.0)
        d4 = measurement_data.get("D4", 0.0)
        diameters = [d1, d2, d3, d4]
        d_avg = sum(diameters) / 4.0

        out_of_range = any(
            (d < d_avg - lower_tol) or (d > d_avg + upper_tol)
            for d in diameters
        )
        new_state = bool(out_of_range)
        old_state = self.diameter_alarm_active

        if new_state != old_state:
            # Zmiana stanu alarmu
            event_type = 0 if new_state else 1
            alarm_type = "diameter_error"
            comment = ("Wejście w alarm średnicy" if new_state
                       else "Zejście z alarmu średnicy")

            self._save_event(measurement_data, event_type, alarm_type, comment)
            self._update_common_fault(new_state)

            self.diameter_alarm_active = new_state
            return "entered" if new_state else "exited"
        return "no_change"

    def check_and_update_pulsation_alarm(
        self,
        measurement_data: dict,
        pulsation_threshold: float
    ) -> str:
        """
        Sprawdza, czy wartość 'pulsation_val' w measurement_data > pulsation_threshold.
        """
        pulsation_val = measurement_data.get("pulsation_val", 1.0)

        print("Pulsation value:", pulsation_val)
        new_state = pulsation_val > pulsation_threshold
        # print pulse threshold val and new state
        print("Pulsation threshold:", pulsation_threshold)
        print("New state:", new_state)
        
        old_state = self.pulsation_alarm_active

        if new_state != old_state:
            event_type = 0 if new_state else 1
            alarm_type = "pulsation_error"
            comment = ("Wejście w alarm pulsacji" if new_state
                       else "Zejście z alarmu pulsacji")

            self._save_event(measurement_data, event_type, alarm_type, comment)
            self._update_common_fault(new_state)

            self.pulsation_alarm_active = new_state
            return "entered" if new_state else "exited"
        return "no_change"

    def _save_event(self, measurement_data: dict, event_type: int,
                    alarm_type: str, comment: str):
        """
        Rejestruje zdarzenie w bazie danych.
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
            "alarm_type": alarm_type,
            "event_type": event_type,
            "comment": comment
        }

        if OFFLINE_MODE or not check_database(self.db_params):
            return

        if not save_event(self.db_params, event_data):
            print(f"[AlarmManager] Błąd zapisu zdarzenia w bazie dla alarmu: {alarm_type}")


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
