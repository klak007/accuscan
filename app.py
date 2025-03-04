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
        self.geometry("1920x700+0+0")
        
        # Flagi sterujące
        self.run_measurement = False
        self.use_simulation = False
        self.current_page = "MainPage"
        self.db_connected = False
        
        # Performance monitoring
        self.log_counter = 0
        self.log_frequency = 10  # Log every 10 cycles
        self.last_log_time = time.time()
        
        # Thread and process control
        self.acquisition_thread_running = False
        self.acquisition_thread = None
        self.db_queue = queue.Queue(maxsize=100)  # Queue for database operations
        self.plc_write_queue = queue.Queue(maxsize=20)  # Queue for PLC write operations
        
        # Use multiprocessing.Queue for sharing data between processes
        # unlike threading.Queue, this is safe for interprocess communication
        import multiprocessing as mp
        self.data_queue = mp.Queue(maxsize=100)  # Queue for sending acquisition data to UI
        
        # Zapisanie parametrów bazy danych jako atrybut
        self.db_params = config.DB_PARAMS
        
        # Inicjalizacja bazy danych
        self.init_database_connection()
        
        # Inicjalizacja logiki
        self.logic = MeasurementLogic(controller=self)
        self.logic.init_logic()
        
        # UserManager for user management
        self.user_manager = UserManager()
        
        # Legacy DataManager - will be phased out
        # Keep temporarily for backwards compatibility
        self.data_mgr = DataManager(max_samples=1000)
        
        # FastAcquisitionBuffer for high-speed acquisition
        # This will eventually replace DataManager completely
        self.acquisition_buffer = FastAcquisitionBuffer(max_samples=1024)
        
        # Make acquisition_buffer available as data_mgr.buffer for transition
        self.data_mgr.buffer = self.acquisition_buffer
        
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
        
        # Start PLC writer thread
        self.start_plc_writer()
        
        # Start data acquisition process (not thread)
        self.start_acquisition_process()
        
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
    
    def start_acquisition_process(self):
        """Start dedicated process for high-speed data acquisition from PLC"""
        import multiprocessing as mp
        from multiprocessing import Process, Value, Array, Event
        
        # Shared control variables between processes
        self.run_measurement_flag = Value('i', 0)  # 0 = False, 1 = True
        self.use_simulation_flag = Value('i', 0)  # 0 = False, 1 = True
        self.process_running_flag = Value('i', 1)  # 1 = True, 0 = False
        
        # Create a separate process for data acquisition
        self.acquisition_process = Process(
            target=self._acquisition_process_worker,
            args=(
                self.process_running_flag,
                self.run_measurement_flag,
                self.use_simulation_flag,
                self.data_queue,
                config.PLC_IP,
                config.PLC_RACK,
                config.PLC_SLOT
            ),
            daemon=True
        )
        
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
        while self.data_receiver_running:
            try:
                # Get data from the queue with a timeout
                data = self.data_queue.get(timeout=0.5)
                
                # Add batch and product info from UI - Use a safe method to access UI
                if hasattr(self, 'main_page'):
                    try:
                        # Copy values locally to avoid UI thread contention
                        data["batch"] = self.main_page.entry_batch.get() if hasattr(self.main_page, 'entry_batch') else "XABC1566"
                        data["product"] = self.main_page.entry_product.get() if hasattr(self.main_page, 'entry_product') else "18X0600"
                        data["speed"] = getattr(self.main_page, 'production_speed', 50.0)
                    except Exception as e:
                        # Fallback to defaults if UI access fails
                        data["batch"] = "XABC1566"
                        data["product"] = "18X0600"
                        data["speed"] = 50.0
                        print(f"[Data Receiver] UI access error: {e}")
                
                # Update the buffer with the received data
                self.acquisition_buffer.add_sample(data)
                
                # Process the data with the logic component
                self.logic.poll_plc_data(data)
                
                # Store latest data for UI
                self.latest_data = data
                
                # Queue for database if connected
                if self.db_connected:
                    try:
                        self.db_queue.put_nowait((self.db_params, data))
                    except queue.Full:
                        pass
                        
            except (queue.Empty, Exception) as e:
                # Just continue if queue is empty or there's an error
                if not isinstance(e, queue.Empty):  # Only log non-empty queue errors
                    print(f"[Data Receiver] Error: {e}")
                continue
    
    @staticmethod
    def _acquisition_process_worker(process_running, run_measurement, use_simulation, data_queue, plc_ip, plc_rack, plc_slot):
        """
        Worker function for high-speed data acquisition process.
        This runs in a separate process to avoid GIL limitations.
        
        Args:
            process_running: Shared Value flag indicating if process should continue running
            run_measurement: Shared Value flag indicating if measurements should be taken
            use_simulation: Shared Value flag indicating if simulation should be used
            data_queue: Multiprocessing Queue for sending data back to main process
            plc_ip: IP address of the PLC
            plc_rack: Rack number of the PLC
            plc_slot: Slot number of the PLC
        """
        # Import needed modules within the process
        import time
        from datetime import datetime
        from plc_helper import read_accuscan_data, connect_plc, write_accuscan_out_settings
        
        
        print(f"[ACQ Process] Starting acquisition process worker")
        
        
        # Connect to the PLC
        plc_client = None
        try:
            plc_client = connect_plc(plc_ip, plc_rack, plc_slot)
            print(f"[ACQ Process] Connected to PLC at {plc_ip}")
        except Exception as e:
            print(f"[ACQ Process] Initial PLC connection failed: {e}")
        
        cycle_count = 0
        log_frequency = 10
        
        # Main acquisition loop
        while process_running.value:
            cycle_start = time.perf_counter()
            
            if not run_measurement.value:
                # If not measuring, just sleep and continue
                time.sleep(0.01)
                continue
                
            # Check PLC connection and retry if needed
            if not (plc_client and plc_client.get_connected()) and not use_simulation.value:
                try:
                    plc_client = connect_plc(plc_ip, plc_rack, plc_slot, max_attempts=1)
                    print(f"[ACQ Process] Reconnected to PLC at {plc_ip}")
                except Exception as e:
                    print(f"[ACQ Process] PLC reconnection failed: {e}")
                    time.sleep(0.5)  # Wait before retrying
                    continue
                
            try:
                # READ-RESET CYCLE: Critical to reset counters in the same 32ms cycle
                plc_start = time.perf_counter()
                
                
                data = read_accuscan_data(plc_client, db_number=2)
                read_time = time.perf_counter() - plc_start
                
                # 2. IMMEDIATELY reset the counters in PLC to avoid cumulative counts
                # This is critical and must happen in the same cycle as the read
                reset_start = time.perf_counter()
                if (data.get("lumps", 0) > 0 or data.get("necks", 0) > 0):
                    # Direct write for critical reset - no queuing
                    write_accuscan_out_settings(
                        plc_client, db_number=2,
                        # Set and immediately clear the reset bits
                        zl=True, zn=True, zf=True, zt=False
                    )
                reset_time = time.perf_counter() - reset_start
                
                # Add timing information to the data
                data["timestamp"] = datetime.now()
                data["plc_read_time"] = read_time
                data["plc_reset_time"] = reset_time
                
                # Send the data to the main process via the queue
                print(f"[ACQ Process] Queue size before put: {data_queue.qsize()}")
                try:
                    data_queue.put(data, block=False)
                    print(f"[ACQ Process] Sent data. Queue size after put: {data_queue.qsize()}")
                except queue.Full:
                    print("[ACQ Process] Data queue is full. Could not enqueue data.")
                except Exception as e:
                    print(f"[ACQ Process] Error sending data to queue: {e}")
                
                # Periodically log performance info
                cycle_count += 1
                if cycle_count >= log_frequency:
                    cycle_count = 0
                    total_time = time.perf_counter() - cycle_start
                    if total_time > 0.025:  # Log if taking >25ms (over 75% of our budget)
                        print(f"[ACQ Process] Total: {total_time:.4f}s | Read: {read_time:.4f}s | Reset: {reset_time:.4f}s")
                
                # Calculate sleep time to maintain 32ms cycle
                elapsed = time.perf_counter() - cycle_start
                sleep_time = max(0, 0.032 - elapsed)
                if elapsed > 0.032:
                    print(f"[ACQ Process] Uwaga! Czas cyklu przekroczył 32 ms: {elapsed:.6f} s")
                if sleep_time > 0:
                    time.sleep(sleep_time)
                
            except Exception as e:
                print(f"[ACQ Process] Error during acquisition: {e}")
                # If it's a PLC connection issue, clean up and try to reconnect next cycle
                if not use_simulation.value:
                    try:
                        if plc_client:
                            plc_client.disconnect()
                            plc_client = None
                    except:
                        pass
                time.sleep(0.1)  # Small delay before next attempt
        
        print("[ACQ Process] Acquisition process worker exiting")
        # Clean up PLC connection before exiting
        if plc_client:
            try:
                plc_client.disconnect()
            except:
                pass
    
    def start_db_worker(self):
        """Start worker thread for database operations"""
        # Start database worker thread
        self.db_worker_running = True
        self.db_worker_thread = threading.Thread(target=self._db_worker, daemon=True)
        self.db_worker_thread.start()
        print("[App] Database worker thread started")
        
    def _db_worker(self):
        """Worker function for database operations thread"""
        last_saved_timestamp = None
        
        while self.db_worker_running:
            try:
                # First try to get items from the queue (newest samples)
                try:
                    params, data = self.db_queue.get(timeout=0.1)
                    
                    # Save to database
                    success = save_measurement_sample(params, data)
                    if not success:
                        self.db_connected = False
                    else:
                        last_saved_timestamp = data.get('timestamp')
                        
                    # Mark task as done
                    self.db_queue.task_done()
                    
                    # Continue to get more items from queue if available
                    continue
                    
                except queue.Empty:
                    # No items in queue, try batch saving from buffer
                    pass
                
                # If queue is empty, we can do periodic batch saves from the buffer
                if self.db_connected and hasattr(self, 'acquisition_buffer'):
                    # Get samples from buffer that haven't been saved yet
                    with self.acquisition_buffer.lock:
                        unsaved_samples = []
                        for sample in self.acquisition_buffer.samples:
                            if last_saved_timestamp is None or sample.get('timestamp') > last_saved_timestamp:
                                unsaved_samples.append(sample)
                        
                        # Save in batches of up to 10 samples
                        if unsaved_samples:
                            batch_size = 10
                            batches = [unsaved_samples[i:i+batch_size] for i in range(0, len(unsaved_samples), batch_size)]
                            
                            for batch in batches:
                                # Save each sample in batch
                                for sample in batch:
                                    success = save_measurement_sample(self.db_params, sample)
                                    if not success:
                                        self.db_connected = False
                                        break
                                    last_saved_timestamp = sample.get('timestamp')
                                
                                if not self.db_connected:
                                    break
                            
                            print(f"[DB Worker] Batch saved {len(unsaved_samples)} samples")
                
                # Sleep if no work was done
                time.sleep(1.0)
                
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
                # Use our improved disconnect function
                from plc_helper import disconnect_plc
                disconnect_plc(self.logic.plc_client)
            except Exception as e:
                print(f"[App] Error during PLC disconnect: {e}")
                # Fallback to direct disconnect
                try:
                    self.logic.plc_client.disconnect()
                except:
                    pass
        
        try:
            # Use proper config values and improved connect function
            from plc_helper import connect_plc
            import config
            self.logic.plc_client = connect_plc(config.PLC_IP, config.PLC_RACK, config.PLC_SLOT, max_attempts=1)
            print("[App] PLC Reconnection successful.")
        except Exception as e:
            print(f"[App] PLC Reconnection failed: {e}")
    
    def start_plc_writer(self):
        """Start worker thread for PLC write operations"""
        self.plc_writer_running = True
        self.plc_writer_thread = threading.Thread(target=self._plc_writer, daemon=True)
        self.plc_writer_thread.start()
        print("[App] PLC writer thread started")
        
    def _plc_writer(self):
        """Worker function for PLC write operations"""
        while self.plc_writer_running:
            try:
                # Get an item from the queue with timeout
                plc_write_args = self.plc_write_queue.get(timeout=0.5)
                
                # Check if PLC is connected
                if not hasattr(self.logic, "plc_client") or not self.logic.plc_client.get_connected():
                    # Skip this write operation
                    self.plc_write_queue.task_done()
                    continue
                    
                # Unpack the arguments - first element is function name, rest are args
                func_name = plc_write_args[0]
                args = plc_write_args[1:]
                
                # Perform the write operation based on function name
                if func_name == "write_accuscan_out_settings":
                    from plc_helper import write_accuscan_out_settings
                    write_start = time.perf_counter()
                    write_accuscan_out_settings(self.logic.plc_client, *args)
                    write_time = time.perf_counter() - write_start
                    if write_time > 0.01:  # Log if it took more than 10ms
                        print(f"[PLC Write] Settings write took {write_time:.4f}s")
                else:
                    print(f"[PLC Write] Unknown function: {func_name}")
                
                # Mark task as done
                self.plc_write_queue.task_done()
                
            except queue.Empty:
                # No items in queue, just continue
                continue
            except Exception as e:
                print(f"[PLC Writer] Error: {e}")
                # Mark task as done if we got one
                try:
                    self.plc_write_queue.task_done()
                except:
                    pass
    
    def _on_closing(self):
        """Zamykanie aplikacji – rozłączenie z PLC, zamknięcie okna."""
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
                update_delay = 100 # plot-heavy main page
            else:
                update_delay = 50  # for other pages
                
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