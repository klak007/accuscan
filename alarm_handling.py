import datetime
import db_helper    

class AlarmHandler: 
    """ Klasa do obsługi alarmów defektów (wybrzuszenia i zagłębień). 
    Zdarzenia alarmowe są zapisywane do bazy danych przy użyciu funkcji save_event z modułu db_helper.
    Przykładowe kody błędów:
    - 0   : brak alarmu (norma)
    - 100 : alarm wybrzuszeń (lumps)
    - 20  : alarm zagłębień (necks)
    - 120 : alarm obu defektów jednocześnie
    """
    ERROR_NONE = 0
    ERROR_LUMPS = 100
    ERROR_NECKS = 20
    ERROR_BOTH = 120

    def __init__(self, db_params, id_register_settings, product_nr, batch_nr):
        """
        Inicjalizuje obiekt obsługi alarmów.
        
        :param db_params: parametry połączenia z bazą danych (słownik)
        :param id_register_settings: identyfikator ustawień rejestru (np. ID z tabeli settings)
        :param product_nr: numer produktu
        :param batch_nr: numer partii
        """
        self.db_params = db_params
        self.id_register_settings = id_register_settings
        self.product_nr = product_nr
        self.batch_nr = batch_nr
        self.current_alarm_code = self.ERROR_NONE

    def update_alarm(self, lumps_count, max_lumps, necks_count, max_necks, x_coordinate, D_values=None, statusword=0):
        """
        Sprawdza bieżące wartości defektów i porównuje je z ustalonymi limitami.
        Jeśli nastąpi zmiana stanu alarmu (aktywacja lub dezaktywacja), loguje zdarzenie do bazy danych.
        
        :param lumps_count: bieżąca liczba wybrzuszeń
        :param max_lumps: maksymalna dozwolona liczba wybrzuszeń
        :param necks_count: bieżąca liczba zagłębień
        :param max_necks: maksymalna dozwolona liczba zagłębień
        :param x_coordinate: współrzędna X, dla której rejestrowane jest zdarzenie
        :param D_values: lista wartości D1, D2, D3, D4 (opcjonalnie)
        :param statusword: dodatkowy status (opcjonalnie)
        """
        # Określ nowy kod alarmu na podstawie warunków
        if lumps_count > max_lumps and necks_count > max_necks:
            new_alarm_code = self.ERROR_BOTH
        elif lumps_count > max_lumps:
            new_alarm_code = self.ERROR_LUMPS
        elif necks_count > max_necks:
            new_alarm_code = self.ERROR_NECKS
        else:
            new_alarm_code = self.ERROR_NONE

        # Jeśli stan alarmu uległ zmianie, wyślij zdarzenie do bazy danych
        if new_alarm_code != self.current_alarm_code:
            self.current_alarm_code = new_alarm_code
            self.log_event(x_coordinate, new_alarm_code, lumps_count, necks_count, D_values, statusword)

    def log_event(self, x_coordinate, alarm_statusword, lumps_count, necks_count, D_values, statusword):
        """
        Zapisuje zdarzenie alarmowe do bazy danych przy użyciu funkcji save_event z db_helper.
        
        :param x_coordinate: współrzędna X
        :param alarm_statusword: kod alarmu (np. 100, 20, 120 lub 0)
        :param lumps_count: liczba wybrzuszeń
        :param necks_count: liczba zagłębień
        :param D_values: lista wartości D1, D2, D3, D4 (opcjonalnie)
        :param statusword: dodatkowy status (opcjonalnie)
        """
        event_data = {
            "id_register_settings": self.id_register_settings,
            "date_time": datetime.now(),
            "x_coordinate": x_coordinate,
            "product_nr": self.product_nr,
            "batch_nr": self.batch_nr,
            "alarm_statusword": alarm_statusword,
            "D1": D_values[0] if D_values and len(D_values) > 0 else 0.0,
            "D2": D_values[1] if D_values and len(D_values) > 1 else 0.0,
            "D3": D_values[2] if D_values and len(D_values) > 2 else 0.0,
            "D4": D_values[3] if D_values and len(D_values) > 3 else 0.0,
            "lumps": lumps_count,
            "necks": necks_count
        }
        if db_helper.save_event(self.db_params, event_data):
            print(f"[AlarmHandler] Zdarzenie zapisane: kod alarmu {alarm_statusword}, x = {x_coordinate}")
        else:
            print(f"[AlarmHandler] Błąd przy zapisie zdarzenia: kod alarmu {alarm_statusword}, x = {x_coordinate}")