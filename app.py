# app.py
import traceback
from PyQt5.QtWidgets import QApplication, QMessageBox, QVBoxLayout, QMainWindow, QWidget, QStackedWidget
from PyQt5.QtCore import QTimer  # Add this import
from PyQt5.QtGui import QIcon
import sys
import os
from datetime import datetime
import time
import threading
import queue
import multiprocessing as mp
from multiprocessing import Process, Value, Event, Queue
# Import modułów

from plc_helper import read_plc_data, connect_plc, write_plc_data
from db_helper import init_database, check_database
from data_processing import FastAcquisitionBuffer
from flaw_detection import FlawDetector
from alarm_manager import AlarmManager

# Import stron
from main_page import MainPage
from settings_page import SettingsPage
from history_page import HistoryPage
from config import OFFLINE_MODE

import numpy as np
from scipy.signal import find_peaks


# PLC connection parameters
PLC_IP = "192.168.50.90"  # Przykładowy adres sterownika
PLC_RACK = 0              # Zwykle 0 przy S7-1200
PLC_SLOT = 1              # Często 1 przy S7-1200

# Database parameters
DB_PARAMS = {
    "host": "localhost",
    "user": "root",
    "password": "root",
    "database": "accuscan_db",
    "port": 3306,
    "raise_on_warnings": True,
    "connect_timeout": 5
}

# Set multiprocessing start method to 'spawn' for better compatibility
if __name__ == "__main__":
    # Use spawn method for Windows compatibility. This should be set before any other multiprocessing code runs
    mp.set_start_method('spawn', force=True)

class App(QMainWindow):
    """
    Główne okno aplikacji, dawniej dziedziczące po ctk.CTk,
    teraz po QMainWindow (PyQt5).
    """
    def __init__(self):
        super().__init__()
        self.plc_connected_flag = Value('i', 0)         #Inicjalizacja flagi PLC
        print("[App] Inicjalizacja aplikacji...")
        

        self.setWindowTitle("AccuScan Controller")
        self.setGeometry(0, 0, 1920, 1080)
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo2.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))
        else:
            print(f"[App] Warning: Logo file not found at: {logo_path}")
        
        
        # Flagi i parametry sterujące
        self.run_measurement = False
        self.current_page = "MainPage"
        self.db_connected = False
        self.log_counter = 0
        self.log_frequency = 10
        self.last_log_time = time.time()
        self.last_plc_retry = 0
        self._closing = False   
        self.processing_time = 0.0  # Czas przetwarzania danych
        self.last_fft_time = time.perf_counter()

        
        # Kolejki, wątki/procesy
        self.acquisition_thread_running = False
        self.acquisition_thread = None
        self.db_queue = queue.Queue(maxsize=100)
        self.analysis_queue = queue.Queue(maxsize=100)
        self.plc_write_queue = queue.Queue(maxsize=20)
        
        if not OFFLINE_MODE:
            self.plc_client = connect_plc(PLC_IP, PLC_RACK, PLC_SLOT)
            if self.plc_client and self.plc_client.get_connected():
                print("[Main] PLC connected in main process.")
            else:
                print("[Main] Failed to connect to PLC in main process.")
        
        # Start PLC writer thread
        self.start_plc_writer()
        
        # Używamy mp.Queue dla między-procesowego przesyłu danych
        self.data_queue = mp.Queue(maxsize=250)
        
        # Parametry bazy danycH
        self.db_params = DB_PARAMS
        self.init_database_connection()

        # Bufor akwizycji
        self.acquisition_buffer = FastAcquisitionBuffer(max_samples=1024)
        self.flaw_detector = FlawDetector()
        self.alarm_manager = AlarmManager(db_params=self.db_params, plc_client=self.plc_client)
        self.plc_client = None
        if not OFFLINE_MODE:
            self.plc_client = connect_plc(PLC_IP, PLC_RACK, PLC_SLOT)
            if self.plc_client and self.plc_client.get_connected():
                print("[Main] PLC connected in main process.")
            else:
                print("[Main] Failed to connect to PLC in main process.")

        
        # Kontener na strony (MainPage, SettingsPage)
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        self.layout = QVBoxLayout(central_widget)
        self.stacked_widget = QStackedWidget(central_widget)
        
        # Inicjalizacja stron
        self.main_page = MainPage(parent=central_widget, controller=self)
        self.settings_page = SettingsPage(parent=central_widget, controller=self)
        self.history_page = HistoryPage(parent=central_widget, controller=self)
        
        self.stacked_widget.addWidget(self.main_page)
        self.stacked_widget.addWidget(self.settings_page)
        self.stacked_widget.addWidget(self.history_page)
        self.layout.addWidget(self.stacked_widget)
        self.settings_page.hide()
        self.history_page.hide()
        
        # Start workerów
        self.start_analysis_worker()
        self.start_acquisition_process()
        
        self.update_timer = QTimer(self)
        # print("[App] Timer aktualizacji utworzony.", flush=True)
        self.update_timer.timeout.connect(self.update_plc_status)
        # print("[App] Metoda update_plc_status przypisana do timera.", flush=True)
        self.update_timer.start(1000)  # check every 1 second

        self.start_update_loop()

    def update_plc_status(self):
        if self.plc_connected_flag.value == 1:
            self.main_page.plc_status_label.setText("Połączono z PLC")
            self.main_page.plc_status_label.setStyleSheet("color: green;")
            self.settings_page.plc_status_label.setText("Połączono z PLC")
            self.settings_page.plc_status_label.setStyleSheet("color: green;")
            self.history_page.plc_status_label.setText("Połączono z PLC")
            self.history_page.plc_status_label.setStyleSheet("color: green;")
        else:
            self.main_page.plc_status_label.setText("Rozłączono z PLC")
            self.main_page.plc_status_label.setStyleSheet("color: red;")
            self.settings_page.plc_status_label.setText("Rozłączono z PLC")
            self.settings_page.plc_status_label.setStyleSheet("color: red;")
            self.history_page.plc_status_label.setText("Rozłączono z PLC")
            self.history_page.plc_status_label.setStyleSheet("color: red;")

    def closeEvent(self, event):
        self._on_closing()
        event.accept()  # lub event.ignore(), zależnie od Twojej logiki
    
    def init_database_connection(self):
        try:
            # print("[App] Inicjalizacja połączenia z bazą...")
            if OFFLINE_MODE:
                self.db_connected = True
                print("[App] Offline mode: Skipped DB initialization.")
                return
            # Próba połączenia z bazą
            if init_database(self.db_params):
                self.db_connected = True
                print("[App] Połączenie z bazą nawiązane.")
            else:
                self.db_connected = False
                print("[App] Brak połączenia z bazą. Aplikacja działa w trybie ograniczonym.")
                QMessageBox.warning(self, "Brak połączenia z bazą",
                                    "Nie można nawiązać połączenia z bazą danych. Aplikacja będzie działać w trybie ograniczonym.")
        except Exception as e:
            self.db_connected = False
            print("[App] Błąd przy inicjalizacji połączenia z bazą:", e)
            QMessageBox.warning(self, "Błąd połączenia",
                                f"Wystąpił błąd przy łączeniu z bazą danych: {str(e)}\nAplikacja będzie działać w trybie ograniczonym.")


    def toggle_page(self, page_name):
        """Przełącza widoczność stron."""
        if page_name == "MainPage":
            self.stacked_widget.setCurrentWidget(self.main_page)
            self.current_page = "MainPage"
        elif page_name == "SettingsPage":
            # Sprawdź połączenie z bazą przed przejściem do strony ustawień
            if not self.db_connected and not check_database(self.db_params):
                QMessageBox.warning(self, "Brak dostępu do bazy danych", 
                                    "Dostęp do strony ustawień jest ograniczony bez połączenia z bazą danych.")
                return
            self.stacked_widget.setCurrentWidget(self.settings_page)
            self.current_page = "SettingsPage"
        elif page_name == "HistoryPage":
            # Sprawdź połączenie z bazą przed przejściem do historii
            if not self.db_connected and not check_database(self.db_params):
                QMessageBox.warning(self, "Brak dostępu do bazy danych", 
                                    "Dostęp do historii jest ograniczony bez połączenia z bazą danych.")
                return
            self.stacked_widget.setCurrentWidget(self.history_page)
            self.current_page = "HistoryPage"
    
    def start_acquisition_process(self):
        """Start dedicated process for high-speed data acquisition from PLC"""
        if OFFLINE_MODE:
            print("[App] Offline mode: Skipped acquisition process.")
            return
        import multiprocessing as mp
        from multiprocessing import Process, Value, Array, Event
        
        # Shared control variables between processes
        self.run_measurement_flag = Value('i', 0)  # 0 = False, 1 = True
        
        self.process_running_flag = Value('i', 1)  # 1 = True, 0 = False
        self.plc_connected_flag = Value('i', 0)
        
        # Create a separate process for data acquisition
        self.acquisition_process = Process(
            target=self._acquisition_process_worker,
            args=(
                self.process_running_flag,
                self.run_measurement_flag,
                self.data_queue,
                PLC_IP,
                PLC_RACK,
                PLC_SLOT,
                self.plc_connected_flag
            ),
            daemon=True
        )
        
        # Set a flag to force an initial reset of the PLC counters when we start measuring
        self.initial_reset_needed = True
        
        # Start the acquisition process and a thread to receive data from the acquisition process
        self.acquisition_process.start()
        print(f"[App] Data acquisition process started with PID: {self.acquisition_process.pid}")
        self.start_data_receiver_thread()
    
    def start_data_receiver_thread(self):
        """Start a thread to receive data from the acquisition process and update the buffer"""
        self.data_receiver_running = True
        self.data_receiver_thread = threading.Thread(target=self._data_receiver_worker, daemon=True)
        self.data_receiver_thread.start()
        print("[App] Data receiver thread started")
        

    def _data_receiver_worker(self):
        """
        Worker thread that receives data from the acquisition process and updates the buffer.

        Dodatkowo mierzymy czas pobrania próbki z kolejki (queue_get_time) oraz czas jej przetworzenia 
        (processing_time). Co 500 próbek wypisujemy średnie wartości obu czasów.
        """


        ui_refresh_counter = 0
        batch_cache = "XABC1566"
        product_cache = "18X0600"
        last_perf_log = time.time()
        samples_processed = 0

        # Listy do akumulacji czasów dla obliczeń średnich.
        # queue_get_times     – mierzy czas potrzebny na pobranie danej z kolejki.
        # processing_times    – mierzy czas przetwarzania danej (dodanie do bufora, itp.).
        queue_get_times = []
        processing_times = []
        samples_since_last_log = 0  # licznik próbek od ostatniego logu 500

        MAX_BATCH_SIZE = 100
        QUEUE_WARNING_THRESHOLD = 50
        QUEUE_CRITICAL_THRESHOLD = 200

        while self.data_receiver_running:
            try:
                current_queue_size = self.data_queue.qsize()
                if current_queue_size > 10:
                    print(f"[Data Receiver] Current queue size: {current_queue_size}")

                # Jeśli kolejka za duża – część odrzucamy.
                if current_queue_size > QUEUE_CRITICAL_THRESHOLD:
                    print(f"[Data Receiver] CRITICAL: Queue size {current_queue_size} exceeds threshold, dropping samples to catch up")
                    samples_to_drop = current_queue_size - QUEUE_WARNING_THRESHOLD
                    for _ in range(samples_to_drop):
                        try:
                            _ = self.data_queue.get_nowait()
                        except queue.Empty:
                            break
                    print(f"[Data Receiver] Dropped {samples_to_drop} samples, new queue size: {self.data_queue.qsize()}")

                # Ustalamy rozmiar partii
                batch_size = min(MAX_BATCH_SIZE, self.data_queue.qsize())
                if batch_size == 0:
                    # Jeśli w kolejce może być 0 elementów – pobieramy pojedynczy z timeoutem
                    try:
                        # Pomiar czasu pobrania z kolejki
                        queue_start = time.perf_counter()
                        data = self.data_queue.get(timeout=0.01)
                        queue_end = time.perf_counter()
                        queue_time = queue_end - queue_start
                        queue_get_times.append(queue_time)

                        batch_size = 1
                    except queue.Empty:
                        continue
                else:
                    # Pobieramy pierwszą próbkę partii
                    queue_start = time.perf_counter()
                    data = self.data_queue.get(timeout=0.01)
                    queue_end = time.perf_counter()
                    queue_time = queue_end - queue_start
                    queue_get_times.append(queue_time)

                batch_start = time.perf_counter()  # start przetwarzania pierwszej próbki w batchu
                ui_refresh_counter += 1

                # Co pewien czas odświeżamy nazwy w UI (o ile nie jest "busy")
                if ui_refresh_counter >= 10:
                    ui_refresh_counter = 0
                    if hasattr(self, 'main_page'):
                        try:
                            if not getattr(self.main_page, 'ui_busy', False):
                                batch_cache = getattr(self.main_page, 'get_batch_name', lambda: batch_cache)()
                                product_cache = getattr(self.main_page, 'get_product_name', lambda: product_cache)()
                        except Exception as e:
                            print(f"[Data Receiver] UI access error: {e}")

                data["batch"] = batch_cache
                data["product"] = product_cache

                # Pobieramy parametry z interfejsu (o ile istnieje)
                if hasattr(self, 'main_page'):
                    try:
                        data["max_lumps"] = self.main_page.get_max_lumps()
                    except Exception:
                        data["max_lumps"] = 3
                    try:
                        data["max_necks"] = self.main_page.get_max_necks()
                    except Exception:
                        data["max_necks"] = 3
                    try:
                        data["upper_tol"] = float(self.main_page.entry_tolerance_plus.text() or "0.5")
                    except ValueError:
                        data["upper_tol"] = 0.5
                    try:
                        data["lower_tol"] = float(self.main_page.entry_tolerance_minus.text() or "0.5")
                    except ValueError:
                        data["lower_tol"] = 0.5
                    try:
                        data["pulsation_threshold"] = float(self.main_page.entry_pulsation_threshold.text() or "500.0")
                    except ValueError:
                        data["pulsation_threshold"] = 500.0

                # Próbujemy wstawić do kolejki analizy
                try:
                    self.analysis_queue.put_nowait(data)
                except queue.Full:
                    print("[Data Receiver] Analysis queue is full, dropping sample")

                # Dodajemy próbkę do bufora
                self.acquisition_buffer.add_sample(data)
                x_coord = self.acquisition_buffer.current_x
                data["xCoord"] = x_coord
                self.latest_data = data
                samples_processed += 1

                # Pomiar czasu przetwarzania tej jednej próbki
                batch_end = time.perf_counter()
                processing_time = batch_end - batch_start
                processing_times.append(processing_time)

                samples_since_last_log += 1

                # Sprawdzamy, czy przekroczyliśmy 500 próbek od ostatniego logu.
                if samples_since_last_log >= 500:
                    avg_queue_get = sum(queue_get_times) / len(queue_get_times)
                    avg_processing = sum(processing_times) / len(processing_times)
                    print(f"[Data Receiver][Performance] Last 500 samples => "
                        f"Avg queue get time: {avg_queue_get:.6f} s/sample, "
                        f"Avg processing time: {avg_processing:.6f} s/sample")
                    queue_get_times.clear()
                    processing_times.clear()
                    samples_since_last_log = 0

                # Jeżeli w partii jest więcej próbek – pobieramy je i przetwarzamy w pętli
                for _ in range(batch_size - 1):
                    try:
                        queue_start = time.perf_counter()
                        data = self.data_queue.get_nowait()
                        queue_end = time.perf_counter()
                        queue_time = queue_end - queue_start
                        queue_get_times.append(queue_time)

                        batch_start = time.perf_counter()

                        data["batch"] = batch_cache
                        data["product"] = product_cache
                        self.acquisition_buffer.add_sample(data)
                        self.latest_data = data
                        x_coord = data.get("xCoord", 0.0)
                        print(f"[Data Receiver] Processing data at x={x_coord:.2f} m")
                        samples_processed += 1

                        batch_end = time.perf_counter()
                        processing_time = batch_end - batch_start
                        processing_times.append(processing_time)

                        samples_since_last_log += 1
                        if samples_since_last_log >= 500:
                            avg_queue_get = sum(queue_get_times) / len(queue_get_times)
                            avg_processing = sum(processing_times) / len(processing_times)
                            print(f"[Data Receiver][Performance] Last 500 samples => "
                                f"Avg queue get time: {avg_queue_get:.6f} s/sample, "
                                f"Avg processing time: {avg_processing:.6f} s/sample")
                            queue_get_times.clear()
                            processing_times.clear()
                            samples_since_last_log = 0

                    except queue.Empty:
                        break

                # Kontrola rozmiaru kolejki i logi wydajności
                current_queue_size = self.data_queue.qsize()
                now = time.time()
                if (now - last_perf_log > 5.0) or (current_queue_size > QUEUE_WARNING_THRESHOLD):
                    elapsed = now - last_perf_log
                    avg_time = elapsed / samples_processed if samples_processed > 0 else 0
                    if current_queue_size > QUEUE_WARNING_THRESHOLD:
                        print(f"[Data Receiver] WARNING - Queue size: {current_queue_size}, "
                            f"Average processing time: {avg_time:.4f} s/sample, "
                            f"Batch time (this cycle): {time.perf_counter() - batch_start:.4f}s "
                            f"for {batch_size} samples")
                    elif samples_processed % 1000 == 0:
                        print(f"[Data Receiver] Average processing time: {avg_time:.4f} s/sample, Queue size: {current_queue_size}")

                    self.processing_time = avg_time
                    last_perf_log = now
                    samples_processed = 0

            except queue.Empty:
                # kolejka pusta — normalne, nic nie logujemy
                continue
            except Exception as e:
                print(f"[Data Receiver] Unexpected Error: {e!r}")
                time.sleep(0.01)




    
    @staticmethod
    def _acquisition_process_worker(process_running, run_measurement, data_queue, plc_ip, plc_rack, plc_slot, plc_connected_flag):
        """
        Worker function for high-speed data acquisition process.
        This runs in a separate process to avoid GIL limitations.
        
        Args:
            process_running: Shared Value flag indicating if process should continue running
            run_measurement: Shared Value flag indicating if measurements should be taken
            
            data_queue: Multiprocessing Queue for sending data back to main process
        """
        
        print(f"[ACQ Process] Starting acquisition process worker")
        # Inicjalizacja zmiennych do akumulacji defektów
        lumps_prev = 0
        necks_prev = 0
        lumps_total = 0
        necks_total = 0
        stable_count = 0  # licznik cykli bez przyrostu
        # Connect to the PLC
        plc_client = None
        try:
            plc_client = connect_plc(plc_ip, plc_rack, plc_slot)
            if plc_client and plc_client.get_connected():
                plc_connected_flag.value = 1
                print(f"[ACQ Process] Connected to PLC at {plc_ip}")
            
            # Immediately perform initial reset to clear any lingering values
            if plc_client and plc_client.get_connected():
                # First reset that immediately clears all counters
                print("[ACQ Process] Performing initial PLC reset")
                write_plc_data(
                    plc_client, db_number=2,
                    # Set all reset bits
                    zl=True, zn=True, zf=True, zt=False
                )
                
                # Clear the reset bits
                write_plc_data(
                    plc_client, db_number=2,
                    # Clear reset bits
                    zl=False, zn=False, zf=False, zt=False
                )
        except Exception as e:
            print(f"[ACQ Process] Initial PLC connection failed: {e}")
        
        cycle_count = 0
        log_frequency = 10
        
        # Flag to track if we need to perform an initial reset
        initial_reset_needed = True
        
        # Performance tracking for lump/neck resets
        last_reset_time = 0
        reset_count = 0
        reset_log_time = time.time()
        
        # Main acquisition loop
        while process_running.value:
            cycle_start = time.perf_counter()
            
            if not run_measurement.value:
                # Reset the initial reset flag when measurement is off
                initial_reset_needed = True
                # If not measuring, just sleep and continue
                time.sleep(0.01)
                continue
                
            # Check PLC connection and retry if needed
            if not (plc_client and plc_client.get_connected()):
                plc_connected_flag.value = 0
                print("[ACQ Process] PLC not connected, attempting to reconnect...")
                try:
                    plc_client = connect_plc(plc_ip, plc_rack, plc_slot, max_attempts=1)
                    if plc_client and plc_client.get_connected():
                        plc_connected_flag.value = 1
                        print(f"[ACQ Process] Reconnected to PLC at {plc_ip}")
                        initial_reset_needed = True  # Need to reset after reconnection
                    else:
                        plc_connected_flag.value = 0
                        time.sleep(0.5)  # Wait before retrying
                        continue
                except Exception as e:
                    plc_connected_flag.value = 0
                    print(f"[ACQ Process] PLC reconnection failed: {e}")
                    time.sleep(0.5)  # Wait before retrying
                    continue
            
            # Perform initial reset when starting measurements
            if initial_reset_needed and plc_client and plc_client.get_connected():
                try:
                    print("[ACQ Process] Performing initial reset after measurement start")
                    # First reset with all reset bits set
                    write_plc_data(
                        plc_client, db_number=2,
                        zl=True, zn=True, zf=True, zt=False
                    )
                    # time.sleep(0.05)  # Short delay to ensure reset is processed
                    
                    # Then clear reset bits
                    write_plc_data(
                        plc_client, db_number=2,
                        zl=False, zn=False, zf=False, zt=False
                    )
                    
                    # Do an initial read and discard to clear any pending data
                    _ = read_plc_data(plc_client, db_number=2)
                    
                    initial_reset_needed = False
                    print("[ACQ Process] Initial reset completed")
                except Exception as e:
                    print(f"[ACQ Process] Error during initial reset: {e}")
                
            try:
                plc_start = time.perf_counter()
                data = read_plc_data(plc_client, db_number=2)
                read_time = time.perf_counter() - plc_start

                # Pobierz bieżące wartości z PLC
                current_lumps = data.get("lumps", 0)
                current_necks = data.get("necks", 0)

                # Debug: wypis wartości odczytanych z PLC oraz poprzednich
                # print(f"[ACQ Process] Odczyt z PLC: "
                #     f"current_lumps={current_lumps}, current_necks={current_necks}, "
                #     f"lumps_prev={lumps_prev}, necks_prev={necks_prev}")

                # Oblicz przyrosty (delta) na podstawie poprzednich odczytów
                if current_lumps >= lumps_prev:
                    delta_lumps = current_lumps - lumps_prev
                else:
                    # Jeśli current_lumps jest mniejsze, licznik w PLC został zresetowany lub przepełniony
                    delta_lumps = current_lumps

                if current_necks >= necks_prev:
                    delta_necks = current_necks - necks_prev
                else:
                    delta_necks = current_necks

                # Debug: wypis przyrostów
                # print(f"[ACQ Process] Delta: delta_lumps={delta_lumps}, delta_necks={delta_necks}")

                # Aktualizacja sumarycznych liczników defektów (opcjonalnie)
                lumps_total += delta_lumps
                necks_total += delta_necks

                # Debug: wypis sumarycznych liczników
                # print(f"[ACQ Process] Po sumowaniu: lumps_total={lumps_total}, necks_total={necks_total}")

                # Zapisz wyniki do danych przekazywanych dalej
                data["lumps_software"] = lumps_total
                data["necks_software"] = necks_total
                data["lumps_delta"] = delta_lumps
                data["necks_delta"] = delta_necks

                # Uaktualnij zmienne poprzednich odczytów
                lumps_prev = current_lumps
                necks_prev = current_necks

                # Debug: wypis nowo ustawionych poprzednich wartości
                # print(f"[ACQ Process] Zaktualizowano lumps_prev i necks_prev: "
                #     f"lumps_prev={lumps_prev}, necks_prev={necks_prev}")

                # Aktualizacja licznika stabilności – jeśli przyrosty są zerowe, zwiększamy licznik cykli bez zmian
                if delta_lumps == 0 and delta_necks == 0:
                    stable_count += 1
                else:
                    stable_count = 0

                # Debug: wypis licznika stabilności
                # print(f"[ACQ Process] stable_count={stable_count}")

                reset_start = time.perf_counter()
                # Warunki resetu: duża wartość w licznikach lub długi brak przyrostu
                if current_lumps > 9000 or current_necks > 9000 or stable_count >= 128:
                    # print("[ACQ Process] Warunki resetu osiągnięte, wykonuję reset PLC")
                    # Maksymalna liczba prób resetu
                    max_reset_attempts = 3
                    reset_attempt = 0
                    reset_successful = False

                    while reset_attempt < max_reset_attempts:
                        # print(f"[ACQ Process] Próba resetu nr {reset_attempt + 1}")
                        try:
                            # Wykonaj reset w PLC
                            write_plc_data(plc_client, db_number=2, zl=True, zn=True, zf=True, zt=False)
                            write_plc_data(plc_client, db_number=2, zl=False, zn=False, zf=False, zt=False)
                        except Exception as e:
                            print(f"[ACQ Process] Reset error: {e}")
                        
                        # Daj PLC chwilę na wykonanie resetu – np. 50 ms
                        time.sleep(0.05)
                        
                        # Odczytaj ponownie dane z PLC
                        data_after_reset = read_plc_data(plc_client, db_number=2)
                        post_reset_lumps = data_after_reset.get("lumps", 0)
                        post_reset_necks = data_after_reset.get("necks", 0)
                        # print(f"[ACQ Process] Po resecie: lumps={post_reset_lumps}, necks={post_reset_necks}")
                        
                        # Jeśli oba liczniki są zerowe, reset się powiódł
                        if post_reset_lumps == 0 and post_reset_necks == 0:
                            reset_successful = True
                            break
                        reset_attempt += 1

                    if reset_successful:
                        # print("[ACQ Process] Reset udany po próbie nr", reset_attempt + 1)
                        # Ustaw zmienne poprzednich odczytów na 0
                        lumps_prev = 0
                        necks_prev = 0
                        stable_count = 0
                    else:
                        print("[ACQ Process] Reset nie udany po maksymalnej liczbie prób")
                        # Jeśli reset nie zadziałał, możesz ustawić zmienne poprzednich odczytów na wartość odczytaną po ostatniej próbie
                        lumps_prev = post_reset_lumps
                        necks_prev = post_reset_necks
                        stable_count = 0

                reset_time = time.perf_counter() - reset_start
                
                # Add timing information to the data
                data["timestamp"] = datetime.now()
                data["plc_read_time"] = read_time
                data["plc_reset_time"] = reset_time
                
                # Send the data to the main process via the queue with adaptive throttling
                try:
                    data_queue.put(data, block=False)
                except queue.Full:
                    print("[ACQ Process] Data queue is full. Could not enqueue data.")

                
                # Periodically log performance info
                cycle_count += 1
                if cycle_count >= log_frequency:
                    cycle_count = 0
                    total_time = time.perf_counter() - cycle_start
                    #print once every 100 cycles
                    # if cycle_count % 100 == 0:
                    #     print(f"[ACQ Process] Total: {total_time:.4f}s | Read: {read_time:.4f}s | Reset: {reset_time:.4f}s")
                
                # Calculate sleep time to maintain 32ms cycle
                elapsed = time.perf_counter() - cycle_start
                # print(f"[ACQ Process] Elapsed time: {elapsed:.4f}s")
                sleep_time = 0.001 # max(0, 0.014 - elapsed)
                
                
                # Log and handle cycle time issues
                if elapsed > 0.032:
                    # Check if we've recently had lump/neck resets
                    current_time = time.time()
                    time_since_reset = current_time - last_reset_time
                    
                    if time_since_reset < 0.1:
                        print(f"[ACQ Process] Cycle time exceeded due to lump/neck reset: {elapsed:.4f}s, Read: {read_time:.4f}s, Reset: {reset_time:.4f}s, Lumps={current_lumps}, Necks={current_necks}")
                    # elif elapsed > 0.1:
                    #     print(f"[ACQ Process] SEVERE DELAY: Cycle time {elapsed:.4f}s, Read: {read_time:.4f}s, Reset: {reset_time:.4f}s is significantly over budget!")
                    # else:
                    #     print(f"[ACQ Process] Cycle time exceeded: {elapsed:.4f}s, Read: {read_time:.4f}s, Reset: {reset_time:.4f}s")
                    
                    # # For severe delays, try sleeping a tiny bit to let system recover
                    # if elapsed > 0.2:
                    #     time.sleep(0.01)
                else:
                    # Normal case - sleep to maintain timing
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                        # print(f"[ACQ Process] Sleeping for {sleep_time:.4f}s to maintain cycle time")
                
            except Exception as e:
                print(f"[ACQ Process] Error during acquisition: {e}")
                # If it's a PLC connection issue, clean up and try to reconnect next cycle
                
                try:
                    if plc_client:
                        plc_client.disconnect()
                        plc_client = None
                except:
                    pass
                time.sleep(0.1)  # Small delay before next attempt
            
            if plc_client and plc_client.get_connected():
                try:
                    # Force a small read to ensure the connection is still valid
                    _ = read_plc_data(plc_client, db_number=2)
                except:
                    plc_connected_flag.value = 0
                    plc_client = None
                    print("[ACQ Process] PLC connection lost during forced read, setting flag to 0.")
        
        print("[ACQ Process] Acquisition process worker exiting")
        # Clean up PLC connection before exiting
        plc_connected_flag.value = 0
        if plc_client:
            try:
                plc_client.disconnect()
            except:
                pass

    def start_plc_writer(self):
        """Start worker thread for PLC write operations."""
        if OFFLINE_MODE:
            print("[App] Offline mode: Skipped PLC writer.")
            return
        self.plc_writer_running = True
        self.plc_writer_thread = threading.Thread(target=self._plc_writer, daemon=True)
        self.plc_writer_thread.start()
        print("[App] PLC writer thread started")

    
    def _plc_writer(self):
        """Worker function for PLC write operations."""
        while self.plc_writer_running:
            try:
                write_cmd = self.plc_write_queue.get(timeout=0.5)
                if write_cmd.get("command") == "write_plc_settings":
                    from plc_helper import write_plc_data
                    # Użyj obiektu PLC, który masz – np. self.plc_client,
                    # lub jeśli korzystasz z innego mechanizmu, przekaż odpowiedni obiekt.
                    if hasattr(self, "plc_client") and self.plc_client and self.plc_client.get_connected():
                        write_plc_data(
                            self.plc_client,
                            db_number=write_cmd.get("db_number", 2),
                            lump_threshold=write_cmd.get("lump_threshold"),
                            neck_threshold=write_cmd.get("neck_threshold"),
                            flaw_preset_diameter=write_cmd.get("flaw_preset_diameter"),
                            upper_tol=write_cmd.get("upper_tol"),
                            under_tol=write_cmd.get("under_tol"),
                        )
                    else:
                        print("[PLC Writer] PLC not connected. Command skipped.")
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[PLC Writer] Error: {e}")


    def start_analysis_worker(self):
        """Uruchamia wątek do analizy danych i wywoływania alarmów."""
        if OFFLINE_MODE:
            print("[App] Offline mode: Skipped analysis worker.")
            return
        self.analysis_worker_running = True
        self.analysis_thread = threading.Thread(target=self._analysis_worker, daemon=True)
        self.analysis_thread.start()
        print("[App] Analysis worker thread started.")
        
    def _analysis_worker(self):
        """
        Worker thread for analyzing measurement data and triggering alarms.
        """

        print("[Analysis Worker] Worker started.")
        while self.analysis_worker_running:
            try:
                measurement_data = self.analysis_queue.get(timeout=0.01)
                x_coord = measurement_data.get("xCoord", 0.0)

                # --- Główna logika: analiza defektów ---
                # measure time taken by process flaws in ms
                start = time.perf_counter()
                self.flaw_detector.process_flaws(measurement_data, x_coord)
                end = time.perf_counter()
                process_time = end - start
                # print in ms not s
                # print(f"[Analysis Worker] Processing flaws took {process_time*1000:.6f} ms")
                lumps_in_window = self.flaw_detector.flaw_lumps_count
                necks_in_window = self.flaw_detector.flaw_necks_count

                max_lumps = measurement_data.get("max_lumps", 3)
                max_necks = measurement_data.get("max_necks", 3)
                upper_tol = measurement_data.get("upper_tol", 0.5)
                lower_tol = measurement_data.get("lower_tol", 0.5)

                # Znacznik czasowy przed i po check_and_update_defects_alarm
                start_alarm = time.perf_counter()
                self.alarm_manager.check_and_update_defects_alarm(
                    lumps_in_window,
                    necks_in_window,
                    measurement_data,
                    max_lumps,
                    max_necks
                )
                end_alarm = time.perf_counter()
                # print(f"[Analysis Worker] check_and_update_defects_alarm took {(end_alarm - start_alarm)*1000:.6f} ms")

                # Znacznik czasowy przed i po check_and_update_diameter_alarm
                start_alarm = time.perf_counter()
                self.alarm_manager.check_and_update_diameter_alarm(
                    measurement_data,
                    upper_tol,
                    lower_tol
                )
                end_alarm = time.perf_counter()
                # print(f"[Analysis Worker] check_and_update_diameter_alarm took {(end_alarm - start_alarm)*1000:.6f} ms")

                pulsation_threshold = measurement_data.get("pulsation_threshold", 500.0)
                fft_buffer_size = 64  # Rozmiar bufora do FFT

                # Pobieramy dane okna z bufora akwizycji
                window_data = self.acquisition_buffer.get_window_data()
                diameter_history = window_data.get("diameter_history", [])

                # Sprawdzamy, czy mamy wystarczającą liczbę próbek do przeprowadzenia FFT
                if len(diameter_history) >= fft_buffer_size:
                    current_time = time.perf_counter()
                    fft_start = time.perf_counter()

                    processing_time = window_data.get("processing_time", 0.01)
                    sample_rate = 1 / processing_time if processing_time > 0 else 83.123

                    # Pobierz ostatnie fft_buffer_size próbek
                    diameter_array = np.array(diameter_history[-fft_buffer_size:], dtype=np.float32)
                    diameter_mean = np.mean(diameter_array)
                    diameter_array -= diameter_mean  # Sygnał centrowany wokół zera

                    if len(diameter_array) > 1:
                        fft_magnitude = np.abs(np.fft.rfft(diameter_array))
                        fft_freqs = np.fft.rfftfreq(len(diameter_array), d=1.0 / sample_rate)
                        peak_idxs, _ = find_peaks(fft_magnitude, prominence=100, distance=5)

                        pulsation_vals = [
                            (float(fft_freqs[i]), float(fft_magnitude[i]))
                            for i in peak_idxs if fft_magnitude[i] > pulsation_threshold
                        ]

                        # Dodaj klucze do measurement_data
                        measurement_data["pulsation_vals"] = pulsation_vals
                        measurement_data["fft_freqs"] = fft_freqs
                        measurement_data["fft_magnitude"] = fft_magnitude

                        self.fft_data = {
                            "fft_freqs": fft_freqs,
                            "fft_magnitude": fft_magnitude,
                            "pulsation_vals": pulsation_vals
                        }

                    fft_end = time.perf_counter()
                    fft_time = fft_end - fft_start
                    # print(f"[Analysis Worker] FFT computation took {fft_time:.6f} s")
                    self.last_fft_time = current_time

                # Znacznik czasowy przed i po check_and_update_pulsation_alarm
                start_alarm = time.perf_counter()
                self.alarm_manager.check_and_update_pulsation_alarm(
                    measurement_data, pulsation_threshold
                )
                end_alarm = time.perf_counter()
                # print(f"[Analysis Worker] check_and_update_pulsation_alarm took {(end_alarm - start_alarm)*1000:.6f} ms")

                self.analysis_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                print(f"[Analysis Worker] Error: {e}")



    
    def _on_closing(self):
        if self._closing:
            return  # Already closing, avoid recursion
        self._closing = True
        print("[App] Zamykanie aplikacji...")
        
        # Stop acquisition process
        if hasattr(self, 'process_running_flag'):
            self.process_running_flag.value = 0
            
        # Stop threads
        self.acquisition_thread_running = False
        if hasattr(self, 'data_receiver_running'):
            self.data_receiver_running = False
        self.db_worker_running = False
        self.plc_writer_running = False
        
        # Stop the update timer
        if hasattr(self, 'update_timer'):
            self.update_timer.stop()
        
        # Wait for threads to finish (with timeout)
        if hasattr(self, 'acquisition_thread') and self.acquisition_thread and self.acquisition_thread.is_alive():
            self.acquisition_thread.join(timeout=1.0)
            
        if hasattr(self, 'data_receiver_thread') and self.data_receiver_thread and self.data_receiver_thread.is_alive():
            self.data_receiver_thread.join(timeout=1.0)
            
        # wait to finish analysis thread
        if hasattr(self, 'analysis_thread') and self.analysis_thread and self.analysis_thread.is_alive():
            self.analysis_thread.join(timeout=1.0)
            
        if hasattr(self, 'plc_writer_thread') and self.plc_writer_thread and self.plc_writer_thread.is_alive():
            self.plc_writer_thread.join(timeout=1.0)
            
        # Wait for acquisition process to finish (with timeout)
        if hasattr(self, 'acquisition_process') and self.acquisition_process and self.acquisition_process.is_alive():
            self.acquisition_process.join(timeout=2.0)
            # If the process is still running after timeout, terminate it
            if self.acquisition_process.is_alive():
                print("[App] Forcing acquisition process termination...")
                self.acquisition_process.terminate()
                self.acquisition_process.join(timeout=1.0)
        
        # Destroy window
        self.destroy()
    
    def destroy(self):
        """Safe method to exit the application"""
        # Instead of calling _on_closing again, just close the window.
        try:
            self.close()  # This will trigger closeEvent only once since _closing is already True
        except Exception as e:
            print(f"[App] Error while closing: {e}")
            # Force close as last resort
            import sys
            sys.exit(0)

    def start_update_loop(self):
        """Start a separate update loop for UI with lower frequency than data collection"""
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_ui)
        
        # Set initial update delay - will be adjusted in the update method
        # Main page with plots needs less frequent updates
        if self.current_page == "MainPage":
            update_delay = 100  # plot-heavy main page
        else:
            update_delay = 50   # for other pages
            
        self.update_timer.start(update_delay)
    
    def update_ui(self):
        now = time.time()
        if hasattr(self, 'latest_data'):
            ui_start = time.perf_counter()

            # Pobierz kopię najnowszych danych z odbiornika
            data_dict = self.latest_data.copy()
            # print("[update_ui] Latest data keys:", list(data_dict.keys()))
            # Scal z danymi FFT, jeśli są dostępne
            if hasattr(self, "fft_data"):
                # print("[update_ui] FFT data keys:", list(self.fft_data.keys()))
                data_dict.update(self.fft_data)

            # Dodaj czas przetwarzania
            data_dict["processing_time"] = self.processing_time
            # print("[update_ui] Merged data keys:", list(data_dict.keys()))
            # Aktualizuj UI strony
            current_page = self.get_current_page()
            if hasattr(current_page, 'update_data'):
                current_page.update_data()

            ui_time = time.perf_counter() - ui_start

            # Log UI update time jeśli przekroczy 100 ms, ale nie częściej niż co 5 sekund
            if ui_time > 0.1 and (now - getattr(self, 'last_log_time', 0)) > 5:
                print(f"[PERF] UI Update time: {ui_time:.4f}s")
                self.last_log_time = now

        # Adjust timer interval based on current page
        if getattr(self, 'current_page', None) == "MainPage":
            self.update_timer.setInterval(100)  # plot-heavy main page
        else:
            self.update_timer.setInterval(50)   # for other pages

        
        
    
    def get_current_page(self):
        if self.current_page == "MainPage":
            return self.main_page
        elif self.current_page == "SettingsPage":
            return self.settings_page
        elif self.current_page == "HistoryPage":
            return self.history_page
        else:
            return None

if __name__ == "__main__":
    mp.freeze_support()  
    print("[App] Uruchamianie aplikacji")

    app = QApplication(sys.argv)
    app.setStyle("fusion")
    main_window = App() 
    main_window.showFullScreen()

    sys.exit(app.exec_())
    print("[App] Aplikacja zakończona")
