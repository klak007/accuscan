
# Struktura aplikacji

## 1. app.py
Główna klasa aplikacji (`App`) bazująca na `customtkinter.CTk`. Definiuje rozmiar i tytuł okna, inicjuje:

- Połączenie z PLC (`connect_plc` z `plc_helper.py`).
- Połączenie z bazą danych (`init_database` z `db_helper.py`).
- Komunikację międzyprocesową (`multiprocessing` z metodą `spawn` i `Queue`).
- Bufor do akwizycji danych (`FastAcquisitionBuffer` z `data_processing.py`).
- Obiekty stron (`MainPage`, `SettingsPage`).

### Metody godne uwagi:
- `start_acquisition_process()` – uruchamia proces zbierania danych z PLC.
- `start_data_receiver_thread()` – odbiera dane z `data_queue` i przekazuje do bufora.
- `db_queue`, `plc_write_queue` – kolejki do komunikacji z bazą i PLC.
- `toggle_page()` – przełącza strony UI.
- `init_database_connection()` – nawiązuje połączenie z bazą.

`App` zarządza interfejsem, wieloprocesowością i wielowątkowością.

## 2. data_processing.py
Zawiera `FastAcquisitionBuffer` – szybki, wielowątkowy bufor pomiarowy z `deque`:

- Kontrola rozmiaru (max_samples) i synchronizacja (`threading.Lock`).
- `add_sample()` – zapisuje pomiary, liczy średnią, aktualizuje położenie `xCoord`.
- `get_statistics()` – cache statystyk.
- `get_latest_data()`, `get_current_data()` – zwracają dane w `DataFrame`.

Moduł przechowuje i przetwarza dane w RAM.

## 3. db_helper.py
Obsługa MySQL (`mysql.connector`):

- `check_database()` – weryfikacja połączenia.
- `init_database()` – inicjalizacja bazy.
- `save_measurement_sample()` – zapis danych pomiarowych.
- `save_event()` – zapis zdarzeń.
- `save_settings()`, `save_settings_history()` – zapis i historia ustawień.

Oddziela warstwę danych od UI.

## 4. flaw_detection.py
Klasa `FlawDetector` – wykrywa `lumps` i `necks`:

- `process_flaws()` – aktualizacja detekcji.
- `check_thresholds()` – sprawdza limity.

Analizuje defekty w czasie rzeczywistym.

## 5. plc_helper.py
Komunikacja z PLC (`snap7`):

- `connect_plc()` – łączenie z PLC.
- `disconnect_plc()` – rozłączenie.
- `read_accuscan_data()` – odczyt z DB2.
- `write_accuscan_out_settings()` – zapis ustawień do PLC.

Obsługa warstwy komunikacji.

## 6. settings_page.py
Klasa `SettingsPage` – UI zarządzania recepturami:

- Wyświetlanie, edycja, usuwanie receptur.
- Sprawdzanie statusu bazy.
- Tabela `ttk.Treeview` + kontrolki.

Obsługuje ustawienia i bazę w warstwie UI.

## 7. visualization.py
`PlotManager` – zarządza wykresami:

- `start_plot_process()` – przetwarzanie danych w osobnym procesie.
- `_plot_process_worker()` – odbiera dane z `plot_data_queue`, wykonuje FFT.
- Monitorowanie obciążenia CPU (adaptive throttling).

Mechanizm generowania danych do wykresów.

## 8. window_fft_analysis.py
Funkcja `analyze_window_fft()`:

- Cache wyników.
- Normalizacja FFT.
- Zwraca wynik do wizualizacji.

Odpowiada za analizę sygnału.

## 9. main_page.py
`MainPage` – główny interfejs:

- Górna belka (pomiar, nastawy, historia, AccuScan).
- Lewy panel (batch, produkt, receptury).
- Środkowy panel (dodatkowe info).
- Prawy panel (wykresy: status, średnica, FFT).
- Przyciski `Start/Stop`, `Kwituj`, `Zapisz`.

### Zależności:
- `PlotManager` (wizualizacja).
- `FlawDetector` (analiza defektów).
- `FastAcquisitionBuffer` (przetwarzanie danych).

### Przepływ danych:
1. `App` startuje proces akwizycji (czyta PLC, wrzuca do `data_queue`).
2. `data_receiver_thread` pobiera dane i zapisuje do bufora.
3. `MainPage` pobiera pomiary i:
   - Wyświetla je.
   - Analizuje w `FlawDetector`.
   - Przekazuje do `PlotManager`.
4. `PlotManager` analizuje FFT i sygnalizuje odświeżenie.

## Kluczowe cechy struktury:
- Podział na moduły:
  - PLC (`plc_helper`).
  - Baza danych (`db_helper`).
  - Detekcja defektów (`flaw_detection`).
  - Bufor i obliczenia (`data_processing`).
  - UI (`main_page`, `settings_page`).
  - Koordynacja (`app.py`).
  - Wizualizacja i FFT (`visualization.py`, `window_fft_analysis.py`).
- Wieloprocesowość (`multiprocessing.Process`).
- Kolejki (`multiprocessing.Queue`, `threading.Queue`).
- Cache obliczeń FFT.
- Tryb offline (brak bazy nie blokuje pracy UI).

## Podsumowanie
Struktura aplikacji pozwala na akwizycję i wizualizację danych z AccuScan (PLC Siemens S7 + czujniki D1..D4, lumps, necks). Główne moduły:

- `app.py` – główny kontroler aplikacji.
- `main_page.py`, `settings_page.py` – UI.
- `data_processing.py`, `flaw_detection.py` – przetwarzanie danych.
- `db_helper.py` – komunikacja z MySQL.
- `plc_helper.py` – obsługa PLC (snap7).
- `visualization.py`, `window_fft_analysis.py` – generowanie wykresów i analiza FFT.

Modułowa budowa ułatwia rozwój i konserwację aplikacji