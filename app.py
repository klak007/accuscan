# app.py

import customtkinter as ctk
from datetime import datetime
import time
import threading
import queue
from tkinter import messagebox
# Import modułów
import config
from plc_helper import read_accuscan_data, connect_plc
from db_helper import init_database, save_measurement_sample, check_database
from data_manager import DataManager
from data_processing import FastAcquisitionBuffer
from logic import MeasurementLogic
from user_manager import UserManager
# Import stron
from main_page import MainPage
from settings_page import SettingsPage
from accuscan_simulator import AccuScanSimulator

class App(ctk.CTk):
    """
    Główne okno aplikacji CustomTkinter.
    """
    def __init__(self):
        super().__init__()
        self.title("AccuScan GUI")
        self.geometry("1920x1080")
        
        # Flagi sterujące
        self.run_measurement = False
        self.use_simulation = False
        self.current_page = "MainPage"
        self.db_connected = False
        
        # Performance monitoring
        self.log_counter = 0
        self.log_frequency = 10  # Log every 10 cycles
        self.last_log_time = time.time()
        
        # Thread control
        self.acquisition_thread_running = False
        self.acquisition_thread = None
        self.db_queue = queue.Queue(maxsize=100)  # Queue for database operations
        
        # Zapisanie parametrów bazy danych jako atrybut
        self.db_params = config.DB_PARAMS
        
        # Inicjalizacja bazy danych
        self.init_database_connection()
        
        # Inicjalizacja logiki
        self.logic = MeasurementLogic()
        self.logic.init_logic()
        
        # UserManager i DataManager (keep for DB operations)
        self.user_manager = UserManager()
        self.data_mgr = DataManager(max_samples=1000)
        
        # New FastAcquisitionBuffer for high-speed acquisition
        self.acquisition_buffer = FastAcquisitionBuffer(max_samples=1024)
        
        # Symulator AccuScan
        self.simulator = AccuScanSimulator()
        
        # --- Tworzymy kontener na strony ---
        self.container = ctk.CTkFrame(self)
        self.container.pack(fill="both", expand=True)
        
        # Inicjalizacja stron
        self.main_page = MainPage(self.container, self)
        self.settings_page = SettingsPage(self.container, self)
        
        # Pokazujemy domyślnie MainPage
        self.main_page.pack(fill="both", expand=True)
        self.settings_page.pack_forget()
        
        # Obsługa zamknięcia okna
        self.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        # Start database worker thread
        self.start_db_worker()
        
        # Start data acquisition thread
        self.start_acquisition_thread()
        
        # Startujemy pętlę aktualizacyjną z niższą częstotliwością odświeżania UI
        self.start_update_loop()

        self.last_plc_retry = 0  # Track last retry attempt for PLC
    
    def init_database_connection(self):
        """Inicjalizuje połączenie z bazą danych, wyświetla ostrzeżenie jeśli jest problem."""
        self.db_connected = init_database(self.db_params)
        if not self.db_connected:
            message = "Nie można połączyć się z bazą danych. Program będzie działać w trybie ograniczonym.\n\n"
            message += "Funkcje zapisu i odczytu danych z bazy nie będą dostępne."
            messagebox.showwarning("Problem z bazą danych", message)
            print("[App] Program działa w trybie ograniczonym - brak dostępu do bazy danych.")
    
    def toggle_page(self, page_name):
        """Przełącza widoczność stron."""
        if page_name == "MainPage":
            self.main_page.pack(fill="both", expand=True)
            self.settings_page.pack_forget()
            self.current_page = "MainPage"
        elif page_name == "SettingsPage":
            # Sprawdź połączenie z bazą przed przejściem do strony ustawień
            if not self.db_connected and not check_database(self.db_params):
                messagebox.showwarning("Brak dostępu do bazy danych", 
                                      "Dostęp do strony ustawień jest ograniczony bez połączenia z bazą danych.")
                return
            self.main_page.pack_forget()
            self.settings_page.pack(fill="both", expand=True)
            self.current_page = "SettingsPage"
    
    def start_acquisition_thread(self):
        """Start dedicated thread for high-speed data acquisition from PLC"""
        if self.acquisition_thread is not None and self.acquisition_thread.is_alive():
            return  # Thread already running
            
        self.acquisition_thread_running = True
        self.acquisition_thread = threading.Thread(target=self._acquisition_worker, daemon=True)
        self.acquisition_thread.start()
        print("[App] Data acquisition thread started")
        
    def _acquisition_worker(self):
        """Worker function for high-speed data acquisition thread"""
        cycle_count = 0
        while self.acquisition_thread_running:
            cycle_start = time.perf_counter()
            
            if not self.run_measurement:
                # If not measuring, just sleep and continue
                time.sleep(0.01)
                continue
                
            # Check PLC connection and retry if needed
            if not (hasattr(self.logic, "plc_client") and self.logic.plc_client.get_connected()):
                self._try_reconnect_plc()
                time.sleep(0.5)  # Wait before retrying
                continue
                
            try:
                # READ PHASE: Fast, minimal processing
                plc_start = time.perf_counter()
                data = self.simulator.read_data() if self.use_simulation else read_accuscan_data(self.logic.plc_client, db_number=2)
                plc_time = time.perf_counter() - plc_start
                
                data["timestamp"] = datetime.now()
                data["batch"] = self.main_page.entry_batch.get() or "XABC1566"
                data["product"] = self.main_page.entry_product.get() or "18X0600"
                
                # Add to fast acquisition buffer - minimal processing, just store the data
                acquisition_start = time.perf_counter()
                acquisition_result = self.acquisition_buffer.add_sample(data)
                acquisition_time = time.perf_counter() - acquisition_start
                
                # Store in DataManager for eventual database saving
                self.data_mgr.add_sample(data)
                
                # Queue for database writing (non-blocking)
                if self.db_connected:
                    try:
                        self.db_queue.put_nowait((self.db_params, data))
                    except queue.Full:
                        # Queue full, skip this sample for database
                        pass
                
                # Logic processing can remain in the acquisition thread
                # since it's time-sensitive for alarms
                logic_start = time.perf_counter()
                self.logic.poll_plc_data(data)
                logic_time = time.perf_counter() - logic_start
                
                # Store latest data for UI thread
                self.latest_data = data
                
                # Periodically log performance info
                cycle_count += 1
                if cycle_count >= self.log_frequency:
                    cycle_count = 0
                    total_time = time.perf_counter() - cycle_start
                    if total_time > 0.025:  # Log if taking >25ms (over 75% of our budget)
                        print(f"[ACQ] Total: {total_time:.4f}s | PLC: {plc_time:.4f}s | Buffer: {acquisition_time:.4f}s | Logic: {logic_time:.4f}s")
                
                # Calculate sleep time to maintain 32ms cycle
                elapsed = time.perf_counter() - cycle_start
                sleep_time = max(0, 0.032 - elapsed)
                
                if sleep_time > 0:
                    time.sleep(sleep_time)
                
            except RuntimeError as exc:
                print(f"[ACQ] PLC read failed: {exc}")
                # Mark PLC as disconnected so retry logic can kick in
                if hasattr(self.logic, "plc_client"):
                    self.logic.plc_client.disconnect()
                time.sleep(0.5)  # Wait before retrying
    
    def start_db_worker(self):
        """Start worker thread for database operations"""
        # Start database worker thread
        self.db_worker_running = True
        self.db_worker_thread = threading.Thread(target=self._db_worker, daemon=True)
        self.db_worker_thread.start()
        print("[App] Database worker thread started")
        
    def _db_worker(self):
        """Worker function for database operations thread"""
        while self.db_worker_running:
            try:
                # Get item from queue with timeout
                params, data = self.db_queue.get(timeout=0.5)
                
                # Save to database
                success = save_measurement_sample(params, data)
                if not success:
                    self.db_connected = False
                    
                # Mark task as done
                self.db_queue.task_done()
            except queue.Empty:
                # No items in queue, just continue
                continue
            except Exception as e:
                print(f"[DB Worker] Error: {e}")
                # Mark task as done if we got one
                try:
                    self.db_queue.task_done()
                except:
                    pass
    
    def _try_reconnect_plc(self):
        """Try to reconnect to the PLC"""
        current_time = time.time()
        if current_time - self.last_plc_retry < 5:  # Don't retry too often
            return
            
        self.last_plc_retry = current_time
        print("[App] Recreating PLC connection...")
        if hasattr(self.logic, "plc_client"):
            try:
                self.logic.plc_client.disconnect()
            except:
                pass
        try:
            self.logic.plc_client = connect_plc("192.168.50.90")
            print("[App] PLC Reconnection successful.")
        except Exception as e:
            print(f"[App] PLC Reconnection failed: {e}")
    
    def _on_closing(self):
        """Zamykanie aplikacji – rozłączenie z PLC, zamknięcie okna."""
        print("[App] Zamykanie aplikacji...")
        
        # Stop threads
        self.acquisition_thread_running = False
        self.db_worker_running = False
        
        # Wait for threads to finish (with timeout)
        if self.acquisition_thread and self.acquisition_thread.is_alive():
            self.acquisition_thread.join(timeout=1.0)
            
        if hasattr(self, 'db_worker_thread') and self.db_worker_thread.is_alive():
            self.db_worker_thread.join(timeout=1.0)
            
        # Close logic connections
        self.logic.close_logic()
        
        # Destroy window
        self.destroy()
    
    def start_update_loop(self):
        """Start a separate update loop for UI with lower frequency than data collection"""
        def update_loop():
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
            
            # Use variable delay based on current page
            # Main page with plots needs less frequent updates
            if self.current_page == "MainPage":
                update_delay = 500  # 500ms (2 FPS) for plot-heavy main page
            else:
                update_delay = 250  # 250ms (4 FPS) for other pages
                
            self.after(update_delay, update_loop)
        
        update_loop()
    
    def get_current_page(self):
        if self.current_page == "MainPage":
            return self.main_page
        elif self.current_page == "SettingsPage":
            return self.settings_page
        else:
            return None

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()