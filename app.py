# app.py

import customtkinter as ctk
from datetime import datetime
import time
import threading
import queue
import multiprocessing
from multiprocessing import Process, Value, Event, Queue
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

# Set multiprocessing start method to 'spawn' for better compatibility
if __name__ == "__main__":
    # Use spawn method for Windows compatibility
    # This should be set before any other multiprocessing code runs
    multiprocessing.set_start_method('spawn', force=True)

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
        # Smaller queue size to prevent memory buildup - we'll implement throttling instead
        self.data_queue = mp.Queue(maxsize=250)  # Queue for sending acquisition data to UI
        
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
        speed_cache = 50.0
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
                
                # Critical overflow - need to drop samples to catch up
                if current_queue_size > QUEUE_CRITICAL_THRESHOLD:
                    print(f"[Data Receiver] CRITICAL: Queue size {current_queue_size} exceeds threshold, dropping samples to catch up")
                    # Drop samples to catch up, keeping only the most recent samples
                    samples_to_drop = current_queue_size - QUEUE_WARNING_THRESHOLD
                    for _ in range(samples_to_drop):
                        try:
                            # Get and discard samples - multiprocessing Queue doesn't have task_done
                            _ = self.data_queue.get_nowait()
                            # Note: multiprocessing.Queue doesn't have task_done method
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
                        time.sleep(0.01)
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
                                    
                                speed_cache = getattr(self.main_page, 'production_speed', 50.0)
                        except Exception as e:
                            print(f"[Data Receiver] UI access error: {e}")
                
                # Minimal processing for each sample
                data["batch"] = batch_cache
                data["product"] = product_cache
                data["speed"] = speed_cache
                
                # Add to buffer but skip some unnecessary processing steps for bulk items
                self.acquisition_buffer.add_sample(data)
                self.logic.poll_plc_data(data)
                self.latest_data = data
                
                # Note: multiprocessing.Queue doesn't have task_done method
                samples_processed += 1
                
                # Database saving criteria - only for the first sample in the batch
                # or for samples with flaws to avoid database overload
                save_to_db = False
                
                # Only check flaw detector for first sample in batch for efficiency
                if samples_processed % 10 == 0 and self.db_connected and hasattr(self, 'main_page'):
                    if hasattr(self.main_page, 'flaw_detector'):
                        # Check thresholds only periodically to reduce overhead
                        window_lumps = getattr(self.main_page.flaw_detector, 'window_lumps_count', 0)
                        window_necks = getattr(self.main_page.flaw_detector, 'window_necks_count', 0)
                        
                        # Get current window flaw counts from the detector
                        max_lumps = getattr(self.main_page, 'get_max_lumps', lambda: 30)()
                        max_necks = getattr(self.main_page, 'get_max_necks', lambda: 7)()
                        
                        # Save if thresholds are exceeded
                        if window_lumps >= max_lumps or window_necks >= max_necks:
                            save_to_db = True
                
                # Always check immediate flaws
                current_lumps = data.get("lumps", 0)
                current_necks = data.get("necks", 0)
                
                # Save when we detect immediate flaws
                if current_lumps > 0 or current_necks > 0:
                    save_to_db = True
                
                # If we decide to save, add to DB queue
                if save_to_db and self.db_connected:
                    try:
                        self.db_queue.put_nowait((self.db_params, data))
                    except queue.Full:
                        # Log but don't block
                        pass
                
                # Then process remaining items in the batch - more efficiently
                for _ in range(batch_size - 1):
                    try:
                        data = self.data_queue.get_nowait()
                        
                        # Use cached UI values - minimal processing
                        data["batch"] = batch_cache
                        data["product"] = product_cache
                        data["speed"] = speed_cache
                        
                        # Add to buffer - minimal processing
                        self.acquisition_buffer.add_sample(data)
                        
                        # Update latest data
                        self.latest_data = data
                        
                        # Note: multiprocessing.Queue doesn't have task_done method
                        samples_processed += 1
                        
                        # Only save flaws to database
                        if self.db_connected and (data.get("lumps", 0) > 0 or data.get("necks", 0) > 0):
                            try:
                                self.db_queue.put_nowait((self.db_params, data))
                            except queue.Full:
                                pass
                                
                    except queue.Empty:
                        break
                
                # Log performance only periodically or when queue is large
                current_queue_size = self.data_queue.qsize()
                now = time.time()
                
                if (now - last_perf_log > 5.0) or (current_queue_size > QUEUE_WARNING_THRESHOLD):
                    elapsed = now - last_perf_log
                    rate = samples_processed / elapsed if elapsed > 0 else 0
                    
                    # Log more information if queue size is concerning
                    if current_queue_size > QUEUE_WARNING_THRESHOLD:
                        print(f"[Data Receiver] WARNING - Queue size: {current_queue_size}, " 
                              f"Processing rate: {rate:.1f} samples/sec, "
                              f"Batch time: {time.perf_counter() - batch_start:.4f}s for {batch_size} samples")
                    else:
                        print(f"[Data Receiver] Processing rate: {rate:.1f} samples/sec, Queue size: {current_queue_size}")
                    
                    last_perf_log = now
                    samples_processed = 0
                        
            except Exception as e:
                print(f"[Data Receiver] Error: {e}")
                # Sleep a tiny bit to avoid CPU spinning on repeated errors
                time.sleep(0.01)
    
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
        import queue
        
        print(f"[ACQ Process] Starting acquisition process worker")
        
        # Connect to the PLC
        plc_client = None
        try:
            plc_client = connect_plc(plc_ip, plc_rack, plc_slot)
            print(f"[ACQ Process] Connected to PLC at {plc_ip}")
            
            # Immediately perform initial reset to clear any lingering values
            if plc_client and plc_client.get_connected():
                # First reset that immediately clears all counters
                print("[ACQ Process] Performing initial PLC reset")
                write_accuscan_out_settings(
                    plc_client, db_number=2,
                    # Set all reset bits
                    zl=True, zn=True, zf=True, zt=False
                )
                
                # Short sleep to let reset complete
                time.sleep(0.05)
                
                # Clear the reset bits
                write_accuscan_out_settings(
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
            if not (plc_client and plc_client.get_connected()) and not use_simulation.value:
                try:
                    plc_client = connect_plc(plc_ip, plc_rack, plc_slot, max_attempts=1)
                    print(f"[ACQ Process] Reconnected to PLC at {plc_ip}")
                    initial_reset_needed = True  # Need to reset after reconnection
                except Exception as e:
                    print(f"[ACQ Process] PLC reconnection failed: {e}")
                    time.sleep(0.5)  # Wait before retrying
                    continue
            
            # Perform initial reset when starting measurements
            if initial_reset_needed and plc_client and plc_client.get_connected() and not use_simulation.value:
                try:
                    print("[ACQ Process] Performing initial reset after measurement start")
                    # First reset with all reset bits set
                    write_accuscan_out_settings(
                        plc_client, db_number=2,
                        zl=True, zn=True, zf=True, zt=False
                    )
                    time.sleep(0.05)  # Short delay to ensure reset is processed
                    
                    # Then clear reset bits
                    write_accuscan_out_settings(
                        plc_client, db_number=2,
                        zl=False, zn=False, zf=False, zt=False
                    )
                    
                    # Do an initial read and discard to clear any pending data
                    _ = read_accuscan_data(plc_client, db_number=2)
                    
                    initial_reset_needed = False
                    print("[ACQ Process] Initial reset completed")
                except Exception as e:
                    print(f"[ACQ Process] Error during initial reset: {e}")
                
            try:
                # READ-RESET CYCLE: Critical to reset counters in the same 32ms cycle
                plc_start = time.perf_counter()
                
                # Simulation or real data based on flag
                if use_simulation.value:
                    from accuscan_simulator import AccuScanSimulator
                    simulator = AccuScanSimulator()
                    data = simulator.read_data()
                else:
                    data = read_accuscan_data(plc_client, db_number=2)
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
                if (has_flaws or lumps > 100 or necks > 100) and not use_simulation.value:
                    try:
                        # For performance optimization on frequent resets, do reset with separate writes
                        # First set bits to clear counters
                        write_accuscan_out_settings(
                            plc_client, db_number=2,
                            # Set all reset bits
                            zl=True, zn=True, zf=True, zt=False
                        )
                        
                        # Immediately clear bits in a second write
                        if has_flaws:  # Only do second write if we actually had flaws
                            write_accuscan_out_settings(
                                plc_client, db_number=2,
                                # Clear all reset bits
                                zl=False, zn=False, zf=False, zt=False
                            )
                        
                        # Log reset performance issues
                        now = time.time()
                        reset_count += 1
                        
                        # Track high frequency of resets
                        if now - last_reset_time < 0.05:  # Resets happening very close together
                            print(f"[ACQ Process] WARNING: Rapid resets detected! This may impact performance.")
                            
                            # If we see this is becoming a problem, slow down the acquisition cycle slightly
                            # to give PLC more time to process
                            time.sleep(0.01)  # Add a tiny delay to give PLC breathing room
                        
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
                    # Check queue size and implement dynamic throttling
                    current_size = data_queue.qsize()
                    
                    # Define throttling thresholds
                    LOW_THRESHOLD = 20      # Normal operation
                    WARNING_THRESHOLD = 50  # Begin throttling
                    HIGH_THRESHOLD = 200    # Aggressive throttling
                    CRITICAL_THRESHOLD = 500 # Drop samples
                    
                    # Normal operation - queue is handling the load
                    if current_size < LOW_THRESHOLD:
                        data_queue.put(data, block=False)
                        # Only log occasionally during normal operation
                        if cycle_count % 20 == 0:
                            print(f"[ACQ Process] Queue size: {current_size}")
                            
                    # Warning level - begin throttling by adding delay proportional to queue size
                    elif current_size < HIGH_THRESHOLD:
                        data_queue.put(data, block=False)
                        # Log warning
                        if cycle_count % 5 == 0:
                            print(f"[ACQ Process] WARNING: Queue growing - size: {current_size}")
                        # Add small delay proportional to queue size
                        delay_factor = (current_size - LOW_THRESHOLD) / (HIGH_THRESHOLD - LOW_THRESHOLD)
                        throttle_delay = 0.005 * delay_factor  # max ~5ms delay
                        time.sleep(throttle_delay)
                        
                    # High level - aggressive throttling and selective sampling
                    elif current_size < CRITICAL_THRESHOLD:
                        # Only add data with flaws or every 3rd sample
                        if data.get("lumps", 0) > 0 or data.get("necks", 0) > 0 or cycle_count % 3 == 0:
                            data_queue.put(data, block=False)
                        # Always log high threshold warnings
                        if cycle_count % 2 == 0:
                            print(f"[ACQ Process] HIGH LOAD: Queue size {current_size} - throttling and selective sampling")
                        # Add larger delay to let receiver catch up
                        time.sleep(0.010)  # 10ms delay
                        
                    # Critical level - drop samples and let receiver catch up
                    else:
                        # Only keep samples with flaws
                        if data.get("lumps", 0) > 0 or data.get("necks", 0) > 0:
                            data_queue.put(data, block=False)
                        # Always log critical warnings
                        print(f"[ACQ Process] CRITICAL: Queue size at {current_size} - dropping samples, adding delay")
                        # Add significant delay to allow receiver to catch up
                        time.sleep(0.050)  # 50ms delay
                        
                except queue.Full:
                    print("[ACQ Process] Data queue is full. Could not enqueue data.")
                    time.sleep(0.050)  # Add delay when queue is completely full
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
                
                # Log and handle cycle time issues
                if elapsed > 0.032:
                    # Check if we've recently had lump/neck resets
                    current_time = time.time()
                    time_since_reset = current_time - last_reset_time
                    
                    if time_since_reset < 0.1 and has_flaws:
                        # The overrun is likely due to a recent lump/neck reset
                        print(f"[ACQ Process] Cycle time exceeded due to lump/neck reset: {elapsed:.4f}s, Lumps={lumps}, Necks={necks}")
                    elif elapsed > 0.1:
                        # Severe delay - this might indicate something more serious
                        print(f"[ACQ Process] SEVERE DELAY: Cycle time {elapsed:.4f}s is significantly over budget!")
                    else:
                        # Regular overrun - just log it
                        print(f"[ACQ Process] Cycle time exceeded: {elapsed:.4f}s")
                    
                    # For severe delays, try sleeping a tiny bit to let system recover
                    if elapsed > 0.2:
                        time.sleep(0.01)
                else:
                    # Normal case - sleep to maintain timing
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
        
        # Clean up plot process if it exists in main_page
        if hasattr(self, 'main_page') and hasattr(self.main_page, 'plot_manager'):
            try:
                self.main_page.plot_manager.stop_plot_process()
                print("[App] Plot process stopped")
            except Exception as e:
                print(f"[App] Error stopping plot process: {e}")
        
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
    # Initialize multiprocessing with 'spawn' method for cross-platform compatibility
    multiprocessing.freeze_support()  # Needed for Windows executable support
    
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()