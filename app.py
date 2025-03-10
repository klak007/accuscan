# app.py
from PyQt5.QtWidgets import QApplication, QMessageBox, QVBoxLayout, QMainWindow, QWidget, QStackedWidget
from PyQt5.QtCore import QTimer  # Add this import
from PyQt5.QtGui import QIcon
import sys
from datetime import datetime
import time
import threading
import queue
import multiprocessing as mp
from multiprocessing import Process, Value, Event, Queue
# Import modułów
from plc_helper import read_plc_data, connect_plc
from plc_helper import read_plc_data, connect_plc, write_plc_data
from db_helper import init_database, save_measurement_sample, check_database
from data_processing import FastAcquisitionBuffer
from flaw_detection import FlawDetector
# Import stron
from main_page import MainPage
from settings_page import SettingsPage
from config import OFFLINE_MODE
import os


# Configuration settings (originally from config.py)
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
    # Use spawn method for Windows compatibility
    # This should be set before any other multiprocessing code runs
    mp.set_start_method('spawn', force=True)

class App(QMainWindow):
    """
    Główne okno aplikacji, dawniej dziedziczące po ctk.CTk,
    teraz po QMainWindow (PyQt5).
    """
    def __init__(self):
        # Inicjalizacja aplikacji    
        super().__init__()
        #Inicjalizacja flagi PLC
        from multiprocessing import Value
        self.plc_connected_flag = Value('i', 0)
        print("[App] Inicjalizacja aplikacji...")
        
        # Ustawienia okna
        self.setWindowTitle("AccuScan Controller")
        self.setGeometry(0, 0, 1920, 700)
        # Add logo as window icon
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo2.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))
            print(f"[App] Logo loaded from: {logo_path}")
        else:
            print(f"[App] Warning: Logo file not found at: {logo_path}")
        
        # -----------------------------------
        # Flagi i parametry sterujące
        # -----------------------------------
        self.run_measurement = False
        self.current_page = "MainPage"
        self.db_connected = False
        self.log_counter = 0
        self.log_frequency = 10
        self.last_log_time = time.time()
        
        
        # -----------------------------------
        # Kolejki, wątki/procesy
        # -----------------------------------
        self.acquisition_thread_running = False
        self.acquisition_thread = None
        self.db_queue = queue.Queue(maxsize=100)
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
        
        
        # -----------------------------------
        # Parametry bazy danych
        # -----------------------------------
        self.db_params = DB_PARAMS
        self.init_database_connection()
        # -----------------------------------
        # Bufor akwizycji
        # -----------------------------------
        self.acquisition_buffer = FastAcquisitionBuffer(max_samples=1024)
        
        self.flaw_detector = FlawDetector()
        
        # -----------------------------------
        # Kontener na strony (MainPage, SettingsPage)
        # -----------------------------------
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        self.layout = QVBoxLayout(central_widget)
        self.stacked_widget = QStackedWidget(central_widget)
        
        
        # Inicjalizacja stron
        self.main_page = MainPage(parent=central_widget, controller=self)
        self.settings_page = SettingsPage(parent=central_widget, controller=self)
        
        
        # Na razie dodajemy tylko main_page do layoutu
        self.stacked_widget.addWidget(self.main_page)
        self.stacked_widget.addWidget(self.settings_page)
        self.layout.addWidget(self.stacked_widget)
        self.settings_page.hide()
        
        
        # -----------------------------------
        # Obsługa zamknięcia okna
        # (Metoda closeEvent zostanie nadpisana, gdy zajdzie potrzeba)
        # -----------------------------------
        
        # Start workerów
        self.start_db_worker()
        
        
        self.start_acquisition_process()
        
        
        self.update_timer = QTimer(self)
        print("[App] Timer aktualizacji utworzony.", flush=True)
        self.update_timer.timeout.connect(self.update_plc_status)
        print("[App] Metoda update_plc_status przypisana do timera.", flush=True)
        self.update_timer.start(1000)  # check every 1 second

        self.start_update_loop()
        
        
        self.last_plc_retry = 0
        
        self._closing = False   # <-- new flag to prevent recursion

    def update_plc_status(self):
        # Debug print to show the current flag value
        # print(f"[PLC CONNECT FLAG] update_plc_status: plc_connected_flag = {self.plc_connected_flag.value}")
        if self.plc_connected_flag.value == 1:
            self.main_page.plc_status_label.setText("Połączono z PLC")
            self.main_page.plc_status_label.setStyleSheet("color: green;")
            # print("[PLC CONNECT FLAG] PLC is connected according to flag")
        else:
            self.main_page.plc_status_label.setText("Rozłączono z PLC")
            self.main_page.plc_status_label.setStyleSheet("color: red;")
            # print("[PLC CONNECT FLAG] PLC is disconnected according to flag")

    def closeEvent(self, event):
        """
        Zamiast self.protocol("WM_DELETE_WINDOW", self._on_closing),
        w PyQt robimy override closeEvent().
        """
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
                # QMessageBox.warning(self, "Brak połączenia z bazą",
                                    # "Nie można nawiązać połączenia z bazą danych. Aplikacja będzie działać w trybie ograniczonym.")
        except Exception as e:
            self.db_connected = False
            print("[App] Błąd przy inicjalizacji połączenia z bazą:", e)
            # QMessageBox.warning(self, "Błąd połączenia",
            #                     f"Wystąpił błąd przy łączeniu z bazą danych: {str(e)}\nAplikacja będzie działać w trybie ograniczonym.")


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
        
        # Start the acquisition process
        self.acquisition_process.start()
        print(f"[App] Data acquisition process started with PID: {self.acquisition_process.pid}")
        
        # Also start a thread to receive data from the acquisition process
        self.start_data_receiver_thread()
    
    def start_data_receiver_thread(self):
        """Start a thread to receive data from the acquisition process and update the buffer"""
        self.data_receiver_running = True
        self.data_receiver_thread = threading.Thread(target=self._data_receiver_worker, daemon=True)
        self.data_receiver_thread.start()
        print("[App] Data receiver thread started")
        
    def _data_receiver_worker(self):
        """Worker thread that receives data from the acquisition process and updates the buffer"""
        # Cache UI values to reduce UI thread interactions
        batch_cache = "XABC1566"
        product_cache = "18X0600"
        
        ui_refresh_counter = 0
        
        # Performance monitoring
        last_perf_log = time.time()
        samples_processed = 0
        
        # Process a larger batch size to keep up with high data rates
        MAX_BATCH_SIZE = 100  # Increased from 20 to 100
        QUEUE_WARNING_THRESHOLD = 50  # Log warnings if queue exceeds this size
        QUEUE_CRITICAL_THRESHOLD = 200  # Start dropping samples if queue exceeds this size
        
        while self.data_receiver_running:
            try:
                # Check if we need to handle queue overflow situation
                current_queue_size = self.data_queue.qsize()
                if current_queue_size > 0:
                    print(f"[Data Receiver] Current queue size: {current_queue_size}")
                
                # Critical overflow - need to drop samples to catch up
                if current_queue_size > QUEUE_CRITICAL_THRESHOLD:
                    print(f"[Data Receiver] CRITICAL: Queue size {current_queue_size} exceeds threshold, dropping samples to catch up")
                    # Drop samples to catch up, keeping only the most recent samples
                    samples_to_drop = current_queue_size - QUEUE_WARNING_THRESHOLD
                    for _ in range(samples_to_drop):
                        try:
                            # Get and discard samples - multiprocessing Queue doesn't have task_done
                            _ = self.data_queue.get_nowait()
                            # Note: mp.Queue doesn't have task_done method
                        except queue.Empty:
                            break
                    print(f"[Data Receiver] Dropped {samples_to_drop} samples, new queue size: {self.data_queue.qsize()}")
                
                # Process in larger batches to avoid falling behind when UI is busy
                batch_size = min(MAX_BATCH_SIZE, self.data_queue.qsize())
                if batch_size == 0:
                    # No data available, try to get at least one sample with timeout
                    try:
                        data = self.data_queue.get(timeout=0.1)
                        batch_size = 1
                    except queue.Empty:
                        # No data to process, sleep and continue
                        # time.sleep(0.01)
                        continue
                else:
                    # Get the first item in the batch
                    data = self.data_queue.get(timeout=0.1)
                
                batch_start = time.perf_counter()
                
                # Only refresh UI values occasionally to reduce overhead
                ui_refresh_counter += 1
                if ui_refresh_counter >= 20:  # Reduced frequency of UI updates from 10 to 20 cycles
                    ui_refresh_counter = 0
                    # Update cached values from UI using the safer methods if available
                    if hasattr(self, 'main_page'):
                        try:
                            # Check if UI is busy - if so, skip refreshing
                            if not hasattr(self.main_page, 'ui_busy') or not self.main_page.ui_busy:
                                # Use safe getter methods if available
                                if hasattr(self.main_page, 'get_batch_name'):
                                    batch_cache = self.main_page.get_batch_name()
                                else:
                                    batch_cache = self.main_page.entry_batch.get() if hasattr(self.main_page, 'entry_batch') else "XABC1566"
                                    
                                if hasattr(self.main_page, 'get_product_name'):
                                    product_cache = self.main_page.get_product_name()
                                else:
                                    product_cache = self.main_page.entry_product.get() if hasattr(self.main_page, 'entry_product') else "18X0600"
                                    
                                
                        except Exception as e:
                            print(f"[Data Receiver] UI access error: {e}")
                
                # Minimal processing for each sample
                data["batch"] = batch_cache
                data["product"] = product_cache
                
                
                # Add to buffer but skip some unnecessary processing steps for bulk items
                self.acquisition_buffer.add_sample(data)
                self.latest_data = data
                
                # Note: mp.Queue doesn't have task_done method
                samples_processed += 1
                
                # Database saving removed - no longer saving measurement samples
                
                # Then process remaining items in the batch - more efficiently
                for _ in range(batch_size - 1):
                    try:
                        data = self.data_queue.get_nowait()
                        
                        # Use cached UI values - minimal processing
                        data["batch"] = batch_cache
                        data["product"] = product_cache
                        
                        
                        # Add to buffer - minimal processing
                        self.acquisition_buffer.add_sample(data)
                        
                        # Update latest data
                        self.latest_data = data
                        
                        self.flaw_detector.process_flaws(data, 0)
                        print(f"[Flaws] Lumps = {self.flaw_detector.total_lumps_count}, "
                              f"Necks = {self.flaw_detector.total_necks_count}, "
                              f"Total = {self.flaw_detector.get_total_flaws_count()}")
                        
                        # Note: mp.Queue doesn't have task_done method
                        samples_processed += 1
                        
                        # Database saving removed - no longer saving measurement samples
                            
                    except queue.Empty:
                        break
                
                # Log performance only periodically or when queue is large
                current_queue_size = self.data_queue.qsize()
                now = time.time()
                
                if (now - last_perf_log > 5.0) or (current_queue_size > QUEUE_WARNING_THRESHOLD):
                    elapsed = now - last_perf_log
                    avg_time = elapsed / samples_processed if samples_processed > 0 else 0
                    # Log more information if queue size is concerning
                    if current_queue_size > QUEUE_WARNING_THRESHOLD:
                        print(f"[Data Receiver] WARNING - Queue size: {current_queue_size}, "
                            f"Average processing time: {avg_time:.4f} s/sample, "
                            f"Batch time: {time.perf_counter() - batch_start:.4f}s for {batch_size} samples")
                    else:
                        print(f"[Data Receiver] Average processing time: {avg_time:.4f} s/sample, Queue size: {current_queue_size}")
                    
                    last_perf_log = now
                    samples_processed = 0  # Reset sample count after logging
                        
            except Exception as e:
                print(f"[Data Receiver] Error: {e}")
                # Sleep a tiny bit to avoid CPU spinning on repeated errors
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
            plc_ip: IP address of the PLC
            plc_rack: Rack number of the PLC
            plc_slot: Slot number of the PLC
        """
        
        print(f"[ACQ Process] Starting acquisition process worker")
        
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
                # READ-RESET CYCLE: Critical to reset counters in the same 32ms cycle
                plc_start = time.perf_counter()
                
                
                data = read_plc_data(plc_client, db_number=2)
                read_time = time.perf_counter() - plc_start
                
                # 2. IMMEDIATELY reset the counters in PLC to avoid cumulative counts
                # This is critical and must happen in the same cycle as the read
                reset_start = time.perf_counter()
                
                # Get lump and neck values to detect potential issues
                lumps = data.get("lumps", 0)
                necks = data.get("necks", 0)
                has_flaws = (lumps > 0 or necks > 0)
                
                # Warning for unusually high values which indicates reset issue
                if lumps > 100 or necks > 100:
                    print(f"[ACQ Process] WARNING: Unusually high values detected: lumps={lumps}, necks={necks}")
                    print("[ACQ Process] Performing emergency reset...")
                
                # Perform reset for ANY flaws or if values are suspiciously high
                if (has_flaws or lumps > 100 or necks > 100):
                    try:
                        # For performance optimization on frequent resets, do reset with separate writes
                        # First set bits to clear counters
                        write_plc_data(
                            plc_client, db_number=2,
                            # Set all reset bits
                            zf=True, zt=True#, zl=True, zn=True, 
                        )
                        
                        # Immediately clear bits in a second write
                        if has_flaws:  # Only do second write if we actually had flaws
                            write_plc_data(
                                plc_client, db_number=2,
                                # Clear all reset bits
                                zf=False, zt=False#,zl=False, zn=False, 
                            )
                        
                        # Log reset performance issues
                        now = time.time()
                        reset_count += 1
                        
                        # Track high frequency of resets
                        # if now - last_reset_time < 0.05:  # Resets happening very close together
                        #     print(f"[ACQ Process] WARNING: Rapid resets detected! This may impact performance.")
                            
                        #     # If we see this is becoming a problem, slow down the acquisition cycle slightly
                        #     # to give PLC more time to process
                        #     time.sleep(0.01)  # Add a tiny delay to give PLC breathing room
                        
                        last_reset_time = now
                        
                        # Log reset counts periodically
                        if now - reset_log_time > 5.0:
                            if reset_count > 0:
                                print(f"[ACQ Process] Reset count: {reset_count} in last 5 seconds")
                            reset_count = 0
                            reset_log_time = now
                    except Exception as e:
                        print(f"[ACQ Process] Reset error: {e}")
                
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
                # cycle_count += 1
                # if cycle_count >= log_frequency:
                #     cycle_count = 0
                #     total_time = time.perf_counter() - cycle_start
                #     if total_time > 0.001:  # Only print if cycle time exceeded 31ms
                #         print(f"[ACQ Process] Total: {total_time:.4f}s | Read: {read_time:.4f}s | Reset: {reset_time:.4f}s")
                
                # Calculate sleep time to maintain 32ms cycle
                elapsed = time.perf_counter() - cycle_start
                sleep_time = max(0, 0.032 - elapsed)
                
                # Log and handle cycle time issues
                if elapsed > 0.032:
                    # Check if we've recently had lump/neck resets
                    current_time = time.time()
                    time_since_reset = current_time - last_reset_time
                    
                    if time_since_reset < 0.1 and has_flaws:
                        print(f"[ACQ Process] Cycle time exceeded due to lump/neck reset: {elapsed:.4f}s, Read: {read_time:.4f}s, Reset: {reset_time:.4f}s, Lumps={lumps}, Necks={necks}")
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

    def start_db_worker(self):
        """Start worker thread for database operations"""
        if OFFLINE_MODE:
            print("[App] Offline mode: Skipped DB worker.")
            return
        # Start database worker thread
        self.db_worker_running = True
        self.db_worker_thread = threading.Thread(target=self._db_worker, daemon=True)
        self.db_worker_thread.start()
        print("[App] Database worker thread started")
        
    def _db_worker(self):
        """Worker function for database operations thread - no longer saves measurement samples"""
        print("[DB Worker] Database worker started (measurement sample saving disabled)")
        
        while self.db_worker_running:
            try:
                # Clear any items from the queue but don't save them
                try:
                    params, data = self.db_queue.get(timeout=0.1)
                    # Just mark as done without saving
                    self.db_queue.task_done()
                except queue.Empty:
                    # No items in queue
                    pass
                    
                # Sleep to avoid CPU spinning
                time.sleep(1.0)
                
            except Exception as e:
                print(f"[DB Worker] Error: {e}")
                # Mark task as done if we got one
                try:
                    self.db_queue.task_done()
                except:
                    pass
    
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
        
        # Clean up plot process if it exists in main_page
        if hasattr(self, 'main_page') and hasattr(self.main_page, 'plot_manager'):
            try:
                self.main_page.plot_manager.stop_plot_process()
                print("[App] Plot process stopped")
            except Exception as e:
                print(f"[App] Error stopping plot process: {e}")
        
        # Stop the update timer
        if hasattr(self, 'update_timer'):
            self.update_timer.stop()
        
        # Wait for threads to finish (with timeout)
        if hasattr(self, 'acquisition_thread') and self.acquisition_thread and self.acquisition_thread.is_alive():
            self.acquisition_thread.join(timeout=1.0)
            
        if hasattr(self, 'data_receiver_thread') and self.data_receiver_thread and self.data_receiver_thread.is_alive():
            self.data_receiver_thread.join(timeout=1.0)
            
        if hasattr(self, 'db_worker_thread') and self.db_worker_thread and self.db_worker_thread.is_alive():
            self.db_worker_thread.join(timeout=1.0)
            
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
        # Limit UI updates to improve performance
        now = time.time()
        if hasattr(self, 'latest_data'):
            current_page = self.get_current_page()
            ui_start = time.perf_counter()
            if hasattr(current_page, 'update_data'):
                current_page.update_data()
            ui_time = time.perf_counter() - ui_start
            
            # Log UI update time if it's slow (>100ms)
            if ui_time > 0.1 and (now - self.last_log_time) > 5:
                print(f"[PERF] UI Update time: {ui_time:.4f}s")
                self.last_log_time = now
        
        # Adjust timer interval based on current page
        if self.current_page == "MainPage":
            self.update_timer.setInterval(100)  # plot-heavy main page
        else:
            self.update_timer.setInterval(50)   # for other pages
        
        
    
    def get_current_page(self):
        if self.current_page == "MainPage":
            return self.main_page
        elif self.current_page == "SettingsPage":
            return self.settings_page
        else:
            return None

if __name__ == "__main__":
    import multiprocessing as mp
    mp.freeze_support()  # Wymagane dla Windows
    print("[App] Uruchamianie aplikacji po freeze ...")
    

    # Inicjalizacja aplikacji PyQt
    app = QApplication(sys.argv)
    print("[App] Inicjalizacja aplikacji PyQt qapplication")
    # Opcjonalnie można ustawić styl, np. "Fusion"
    app.setStyle("fusion")
    # print("[App] Ustawienie stylu aplikacji na Fusion")

    main_window = App()  # App to Twoja klasa dziedzicząca po QMainWindow
    # print("DEBUG: Created main_window, about to show()")
    main_window.show()
    # print("[App] Wyświetlenie głównego okna aplikacji")

    sys.exit(app.exec_())
    print("[App] Aplikacja zakończona")
