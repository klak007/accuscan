# app.py

import customtkinter as ctk
from datetime import datetime
import time
from tkinter import messagebox
# Import modułów
import config
from plc_helper import read_accuscan_data
from db_helper import init_database, save_measurement_sample, check_database
from data_manager import DataManager
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
        
        # Zapisanie parametrów bazy danych jako atrybut
        self.db_params = config.DB_PARAMS
        
        # Inicjalizacja bazy danych
        self.init_database_connection()
        
        # Inicjalizacja logiki
        self.logic = MeasurementLogic()
        self.logic.init_logic()
        
        # UserManager i DataManager
        self.user_manager = UserManager()
        self.data_mgr = DataManager(max_samples=1000)
        
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
        
        # Startujemy cykliczne odczyty
        self._update_data()
        
        # Obsługa zamknięcia okna
        self.protocol("WM_DELETE_WINDOW", self._on_closing)
        
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
    
    def _update_data(self):
        cycle_start = time.perf_counter()
        current_time = time.time()
        if self.run_measurement:
            # Check PLC connection and retry if needed:
            if not (hasattr(self.logic, "plc_client") and self.logic.plc_client.get_connected()):
                # ...existing retry logic...
                pass

            # Only read if PLC is connected:
            if hasattr(self.logic, "plc_client") and self.logic.plc_client.get_connected():
                try:
                    plc_start = time.perf_counter()
                    data = self.simulator.read_data() if self.use_simulation else read_accuscan_data(self.logic.plc_client, db_number=2)
                    plc_time = time.perf_counter() - plc_start
                    data["timestamp"] = datetime.now()
                    data["batch"] = self.main_page.entry_batch.get() or "XABC1566"
                    data["product"] = self.main_page.entry_product.get() or "18X0600"
                    
                    dm_start = time.perf_counter()
                    self.data_mgr.add_sample(data)
                    dm_time = time.perf_counter() - dm_start
                    
                    db_start = time.perf_counter()
                    if self.db_connected:
                        success = save_measurement_sample(self.db_params, data)
                        if not success:
                            self.db_connected = False
                    db_time = time.perf_counter() - db_start
                    
                    logic_start = time.perf_counter()
                    self.logic.poll_plc_data(data)
                    logic_time = time.perf_counter() - logic_start
                    
                    self.latest_data = data
                    
                    self.log_counter += 1
                    if self.log_counter >= self.log_frequency:
                        self.log_counter = 0
                        total_time = time.perf_counter() - cycle_start
                        if total_time > 0.1:
                            print(f"[PERF] Total: {total_time:.4f}s | PLC: {plc_time:.4f}s | DB: {db_time:.4f}s | Logic: {logic_time:.4f}s | DM: {dm_time:.4f}s")
                except RuntimeError as exc:
                    print(f"[App] PLC read failed: {exc}")
                    # Mark PLC as disconnected so retry logic can kick in
                    self.logic.plc_client.disconnect()
        # Schedule the next update exactly after 32 ms
        self.after(32, self._update_data)
    
    def _on_closing(self):
        """Zamykanie aplikacji – rozłączenie z PLC, zamknięcie okna."""
        print("[App] Zamykanie aplikacji...")
        self.logic.close_logic()
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