import datetime
import queue
import threading
import time
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
        self.active_pulsation_alarms = {}  

        self.db_event_queue = queue.Queue()
        self.db_event_thread_running = True
        self.db_event_thread = threading.Thread(target=self._process_db_events, daemon=True)
        self.db_event_thread.start()

    def _process_db_events(self):
        """
        Oddzielny wątek, który pobiera zdarzenia z kolejki i zapisuje je do bazy.
        """
        while self.db_event_thread_running:
            try:
                # Próba pobrania zdarzenia z kolejki (timeout 1 s, aby móc sprawdzić flagę wyłączenia)
                event_data = self.db_event_queue.get(timeout=1)
            except queue.Empty:
                continue
            start_time = time.perf_counter()
            # Warunki: jeśli aplikacja nie działa w trybie offline oraz baza jest dostępna
            if not (OFFLINE_MODE or not check_database(self.db_params)):
                if not save_event(self.db_params, event_data):
                    print(f"[AlarmManager] Błąd zapisu zdarzenia dla alarmu: {event_data.get('alarm_type')}")
            elapsed = time.perf_counter() - start_time
            # print(f"Zdarzenie zapisane w bazie danych w czasie: {elapsed:.3f} s")
            self.db_event_queue.task_done()
    
    def enqueue_event(self, event_data: dict):
        """
        Umieszcza zdarzenie do zapisu w kolejce.
        """
        self.db_event_queue.put(event_data)

    def shutdown_db_event_thread(self):
        """
        Zatrzymuje wątek zapisu zdarzeń.
        """
        self.db_event_thread_running = False
        self.db_event_thread.join(timeout=1)

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

    # def check_and_update_pulsation_alarm(self, measurement_data: dict, pulsation_threshold: float) -> str:
    #     """
    #     Sprawdza, ile pików (elementów) znajduje się w measurement_data pod kluczem 'pulsation_vals'
    #     (przy czym same wartości amplitudy nie mają znaczenia, liczy się tylko ich liczba).
    #     Jeśli liczba pików jest różna od poprzednio zarejestrowanej, loguje wejście/aktualizację alarmu,
    #     lub zejście z alarmu, jeśli pików już nie ma.
    #     Zwraca "changed", jeśli stan alarmu uległ zmianie, w przeciwnym razie "no_change".
    #     """
        
    #     # Pobierz listę pików
    #     current_pulsation_peaks = measurement_data.get("pulsation_vals", [])
    #     peak_count = len(current_pulsation_peaks)

    #     # Jeśli nie ma wcześniej śledzonej liczby, inicjujemy ją
    #     if not hasattr(self, "active_pulsation_alarm_count"):
    #         self.active_pulsation_alarm_count = 0

    #     old_peak_count = self.active_pulsation_alarm_count

    #     # Przy zmianie liczby wykrytych pików logujemy zdarzenie
    #     if peak_count != old_peak_count:
    #         if peak_count > 0 and old_peak_count == 0:
    #             event_type = 0  # wejście w alarm
    #             comment = f"Wejście alarmu pulsacji: {peak_count} peaków"
    #         elif peak_count == 0 and old_peak_count > 0:
    #             event_type = 1  # zejście z alarmu
    #             comment = "Zejście z alarmu pulsacji"
    #         else:
    #             # Zmiana liczby pików (np. aktualizacja liczby alarmów)
    #             event_type = 0
    #             comment = f"Aktualizacja alarmu pulsacji: {peak_count} peaków"

    #         self.active_pulsation_alarm_count = peak_count

    #         # Aktualizujemy stan common fault – alarm aktywny, jeśli wykryto choć jeden pik
    #         overall_active = (peak_count > 0)
    #         self._update_common_fault(overall_active)

    #         self._save_event(measurement_data, event_type, "pulsation_error", comment)
    #         return "changed"

    #     # Jeśli liczba pików się nie zmieniła, nadal ustawiamy stan common fault
    #     overall_active = (peak_count > 0)
    #     self._update_common_fault(overall_active)
    #     return "no_change"

    def check_and_update_pulsation_alarm(self, measurement_data: dict, pulsation_threshold: float) -> str:
        """
        Sprawdza, czy wykryto choć jedną pulsację (czyli czy lista 'pulsation_vals' zawiera jakiekolwiek elementy).
        Jeśli tak, alarm jest aktywowany, w przeciwnym razie alarm zostaje wyłączony.
        Zmiana stanu alarmu (wejście lub zejście) jest rejestrowana jako zdarzenie.
        """
        # Pobierz listę pików
        current_pulsation_peaks = measurement_data.get("pulsation_vals", [])
        peak_count = len(current_pulsation_peaks)

        # Ustalamy nowy stan – alarm jest aktywny, gdy wykryto choć jeden pik
        new_state = peak_count > 0

        # Inicjalizacja stanu alarmu, jeśli jeszcze nie istnieje
        if not hasattr(self, "pulsation_alarm_active"):
            self.pulsation_alarm_active = False

        old_state = self.pulsation_alarm_active

        if new_state != old_state:
            event_type = 0 if new_state else 1  # 0 = wejście w alarm, 1 = zejście z alarmu
            if new_state:
                comment = "Wejście w alarm pulsacji: wykryto pulsację"
            else:
                comment = "Zejście z alarmu pulsacji: brak wykrytych pulsacji"

            self._save_event(measurement_data, event_type, "pulsation_error", comment)
            self._update_common_fault(new_state)
            self.pulsation_alarm_active = new_state

            return "entered" if new_state else "exited"

        # Aktualizacja stanu common fault, nawet jeśli stan alarmu nie uległ zmianie
        self._update_common_fault(new_state)
        return "no_change"


    def check_and_update_ovality_alarm(self, measurement_data: dict, max_ovality_threshold: float) -> str:
        """
        Sprawdza, czy mierzona owalność (obliczana jako (dMax - dMin)/dAvg*100)
        jest mniejsza niż zadany próg max_ovality_threshold.
        Jeśli tak, aktywowany zostaje alarm 'Wysoka owalność'.
        """
        d1 = measurement_data.get("D1", 0.0)
        d2 = measurement_data.get("D2", 0.0)
        d3 = measurement_data.get("D3", 0.0)
        d4 = measurement_data.get("D4", 0.0)

        diameters = [d1, d2, d3, d4]
        davg = sum(diameters) / 4.0 if sum(diameters) != 0 else 0.0
        dmin = min(diameters)
        dmax = max(diameters)
        ovality = ((dmax - dmin) / davg * 100) if davg != 0 else 0.0

        new_state = (ovality < max_ovality_threshold)

        if not hasattr(self, "ovality_alarm_active"):
            self.ovality_alarm_active = False
        old_state = self.ovality_alarm_active

        if new_state != old_state:
            event_type = 0 if new_state else 1  # 0 = wejście w alarm, 1 = zejście z alarmu
            alarm_type = "ovality_high"
            comment = "Wejście w alarm wysokiej owalności" if new_state else "Zejście z alarmu wysokiej owalności"
            self._save_event(measurement_data, event_type, alarm_type, comment)
            self._update_common_fault(new_state)
            self.ovality_alarm_active = new_state
            return "entered" if new_state else "exited"

        return "no_change"


    # def check_and_update_std_dev_alarm(self, measurement_data: dict, max_std_dev_threshold: float) -> dict:
    #     """
    #     Sprawdza osobno odchylenie standardowe dla każdej średnicy (D1, D2, D3, D4).
    #     Jeśli wartość std dev dla danej średnicy przekracza max_std_dev_threshold,
    #     alarm jest aktywowany, a odpowiednie zdarzenie rejestrowane w bazie danych.

    #     Zwraca słownik, w którym kluczami są nazwy średnic,
    #     a wartości to status zmiany alarmu: "entered", "exited" lub "no_change".
    #     """
    #     results = {}
    #     diameters = ["D1", "D2", "D3", "D4"]

    #     # Inicjalizacja stanu alarmów przy pierwszym użyciu
    #     if not hasattr(self, "std_dev_alarm_states"):
    #         self.std_dev_alarm_states = {d: False for d in diameters}

    #     for d in diameters:
    #         key = f"{d}_std"
    #         std_value = measurement_data.get(key, 0.0)
    #         new_state = (std_value > max_std_dev_threshold)
    #         old_state = self.std_dev_alarm_states.get(d, False)

    #         if new_state != old_state:
    #             event_type = 0 if new_state else 1  # 0 = wejście w alarm, 1 = zejście
    #             alarm_type = f"std_dev_high_{d}"
    #             comment = (
    #                 f"Wejście w alarm wysokiego odchylenia standardowego średnicy {d}"
    #                 if new_state else
    #                 f"Zejście z alarmu wysokiego odchylenia standardowego średnicy {d}"
    #             )

    #             self._save_event(measurement_data, event_type, alarm_type, comment)
    #             self._update_common_fault(new_state)
    #             self.std_dev_alarm_states[d] = new_state

    #             results[d] = "entered" if new_state else "exited"
    #         else:
    #             results[d] = "no_change"

    #     return results

    def check_and_update_std_dev_alarm(self, measurement_data: dict, max_std_dev_threshold: float) -> str:
        """
        Sprawdza odchylenie standardowe dla średnic D1, D2, D3 i D4.
        Jeśli którakolwiek z wartości przekracza max_std_dev_threshold, alarm jest aktywowany.
        Alarm schodzi wtedy, gdy wszystkie średnice mają odchylenie standardowe poniżej tego progu.

        Zwraca "entered", "exited" lub "no_change" w zależności od zmiany stanu alarmu.
        """
        diameters = ["D1", "D2", "D3", "D4"]
        new_state = False
        exceeded = []

        for d in diameters:
            key = f"{d}_std"
            std_value = measurement_data.get(key, 0.0)
            if std_value > max_std_dev_threshold:
                new_state = True
                exceeded.append(d)

        if not hasattr(self, "std_dev_alarm_active"):
            self.std_dev_alarm_active = False
        old_state = self.std_dev_alarm_active

        if new_state != old_state:
            event_type = 0 if new_state else 1  # 0 = wejście w alarm, 1 = zejście z alarmu
            alarm_type = "std_dev_high"

            if new_state:
                comment = (
                    "Wejście w alarm wysokiego odchylenia standardowego dla średnic: "
                    + ", ".join(exceeded)
                )
            else:
                comment = "Zejście z alarmu wysokiego odchylenia standardowego dla średnic"

            self._save_event(measurement_data, event_type, alarm_type, comment)
            self._update_common_fault(new_state)
            self.std_dev_alarm_active = new_state

            return "entered" if new_state else "exited"

        return "no_change"



    def _save_event(self, measurement_data: dict, event_type: int,
                    alarm_type: str, comment: str):
        """
        Rejestruje zdarzenie w bazie danych.
        """
        start_time = time.time()
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

        end_time = time.time()
        # print(f"Zdarzenie zapisane w bazie danych w czasie: {end_time - start_time} s")


    def _update_common_fault(self, is_active: bool):
        try:

            # if hasattr(self, 'last_common_fault_state') and self.last_common_fault_state == is_active:
            #     return  
            # self.last_common_fault_state = is_active  

            if self.plc_client:
                if is_active:
                    plc_helper.write_plc_data(self.plc_client, lamp_on=True, lamp_off=False)
                else:
                    plc_helper.write_plc_data(self.plc_client, lamp_on=False, lamp_off=True)
        except Exception as e:
            print("Błąd podczas aktualizacji common fault w PLC:", e)

