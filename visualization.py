"""
Visualization module for AccuScan application.
Handles plotting functionality separated from the main UI using a separate process.
"""

import matplotlib.pyplot as plt
import time
import numpy as np
import multiprocessing as mp
from multiprocessing import Process, Queue, Event, Value, cpu_count
from window_fft_analysis import analyze_window_fft
import psutil
import copy


class PlotManager:
    """
    Manages plot updates for AccuScan application.
    Handles throttling of plot updates to improve performance.
    """
    
    def __init__(self, figures_dict, min_update_interval=0.5):
        """
        Initialize the PlotManager with figures and axes.
        
        Args:
            figures_dict: Dictionary with structure:
                {'status': (fig, ax), 'diameter': (fig, ax), 'fft': (fig, ax)}
            min_update_interval: Minimum time between plot updates in seconds
        """
        # Store figure/axes references from main_page
        self.figures = figures_dict
        self.min_update_interval = min_update_interval
        self.last_update_time = None
        self.plot_dirty = False
        
        # Performance monitoring
        self.plot_update_count = 0
        self.throttle_level = 1  # 1=normal (all plots), 2=skip FFT, 3=essential only
        self.last_high_cpu_time = 0  # Last time we detected high CPU usage
        self.adaptive_mode = True  # Enable adaptive throttling
        
        # Create multiprocessing queues and events
        self.plot_data_queue = Queue(maxsize=5)  # Queue for sending data to plot process
        self.plot_request_queue = Queue(maxsize=5)  # Queue for requesting specific plot updates
        self.plot_complete_event = Event()  # Event to signal when plotting is complete
        self.plot_process_active = Value('i', 0)  # Shared flag to indicate if process is running
        
        # Initialize the plotting process
        self.start_plot_process()
    
    def start_plot_process(self):
        """Start a dedicated process for generating plot data"""
        try:
            # Get available CPU cores for potentially pinning the process
            available_cores = cpu_count()
            target_core = max(0, available_cores - 1)  # Use last core by default
            
            # Create and start the process
            self.plot_process = Process(
                target=self._plot_process_worker,
                args=(
                    self.plot_data_queue,
                    self.plot_request_queue,
                    self.plot_complete_event,
                    self.plot_process_active,
                    target_core
                ),
                daemon=True
            )
            self.plot_process.start()
            self.plot_process_active.value = 1
            print(f"[PlotManager] Started plot process (PID: {self.plot_process.pid}) on CPU core {target_core}")
        except Exception as e:
            print(f"[PlotManager] Error starting plot process: {e}")
            # Fall back to local plotting without process
            self.plot_process = None
    
    def stop_plot_process(self):
        """Gracefully stop the plotting process"""
        if hasattr(self, 'plot_process') and self.plot_process and self.plot_process.is_alive():
            self.plot_process_active.value = 0
            self.plot_process.join(timeout=2.0)
            if self.plot_process.is_alive():
                print("[PlotManager] Force terminating plot process")
                self.plot_process.terminate()
                self.plot_process.join(timeout=1.0)
            print("[PlotManager] Plot process stopped")
    
    @staticmethod
    def _plot_process_worker(data_queue, request_queue, complete_event, active_flag, target_core):
        """
        Worker function for the plot data processing process.
        
        Args:
            data_queue: Queue for receiving plot data
            request_queue: Queue for receiving plot requests
            complete_event: Event to signal when plotting is complete
            active_flag: Shared Value to indicate if process should continue running
            target_core: CPU core to run on (if possible)
        """
        print(f"[Plot Process] Starting on core {target_core}")
        
        # Try to pin process to specific CPU core
        try:
            proc = psutil.Process()
            proc.cpu_affinity([target_core])
            print(f"[Plot Process] Pinned to CPU core {target_core}")
        except Exception as e:
            print(f"[Plot Process] Could not pin to core {target_core}: {e}")
        
        # Initialize local plot data cache
        plot_cache = {}
        
        # Main loop
        while active_flag.value == 1:
            try:
                # Check if there's a plot request
                try:
                    request_type = request_queue.get_nowait()
                    print(f"[Plot Process] Got request for {request_type} plot")
                    # Process specific plot request here if needed
                except Exception:
                    # No request, continue normal processing
                    pass
                
                # Get plot data with timeout
                try:
                    plot_data = data_queue.get(timeout=0.1)
                    
                    # Process the data and generate plot data
                    start_time = time.perf_counter()
                    processed_data = {}
                    
                    # Status plot processing
                    if 'x_history' in plot_data and 'lumps_history' in plot_data and 'necks_history' in plot_data:
                        processed_data['status_plot'] = {
                            'x_vals': plot_data['x_history'],
                            'lumps_vals': plot_data['lumps_history'],
                            'necks_vals': plot_data['necks_history'],
                            'batch_name': plot_data.get('batch_name', 'Unknown'),
                            'current_x': plot_data.get('current_x', 0),
                            'plc_sample_time': plot_data.get('plc_sample_time', 0)
                        }
                    
                    # Diameter plot processing
                    if 'diameter_history' in plot_data and 'diameter_x' in plot_data:
                        # No heavy processing needed for diameter, just pass through
                        processed_data['diameter_plot'] = {
                            'x': plot_data['diameter_x'],
                            'y': plot_data['diameter_history'],
                            'current_x': plot_data.get('current_x', 0),
                            'diameter_preset': plot_data.get('diameter_preset', 0),
                            'plc_sample_time': plot_data.get('plc_sample_time', 0)
                        }
                    
                    # FFT plot processing - most computationally expensive
                    if 'diameter_history' in plot_data and len(plot_data['diameter_history']) > 0:
                        # Convert to numpy array for FFT analysis
                        fft_buffer_size = plot_data.get('fft_buffer_size', 64)
                        diameter_array = np.array(
                            plot_data['diameter_history'][-fft_buffer_size:], 
                            dtype=np.float32
                        )
                        
                        if len(diameter_array) > 0:
                            # Calculate FFT
                            diameter_fft = analyze_window_fft(diameter_array)
                            processed_data['fft_plot'] = {
                                'fft_data': np.abs(diameter_fft).tolist(),  # Convert to list for Queue
                                'fft_buffer_size': fft_buffer_size
                            }
                    
                    # Store total processing time
                    processing_time = time.perf_counter() - start_time
                    processed_data['processing_time'] = processing_time
                    
                    # Update the local cache
                    plot_cache.update(processed_data)
                    
                    # Put processed data back in the queue
                    try:
                        # Return the plotting data to main thread
                        # Use a separate queue to avoid blocking
                        # (Implementation detail: in actual code, we'd use a separate return queue)
                        complete_event.set()
                        
                        # Log performance
                        if processing_time > 0.05:  # Only log if significant
                            print(f"[Plot Process] Generated plot data in {processing_time:.4f}s")
                    except Exception as e:
                        print(f"[Plot Process] Error returning data: {e}")
                    
                except Exception:
                    # No data to process (Queue.Empty or other exception)
                    time.sleep(0.01)
            
            except Exception as e:
                print(f"[Plot Process] Error: {e}")
                time.sleep(0.1)
        
        print("[Plot Process] Exiting")
    
    def update_status_plot(self, x_history, lumps_history, necks_history, current_x, batch_name, plc_sample_time=0):
        """
        Update the status plot (lumps/necks over x-coordinate).
        
        Args:
            x_history: List of x-coordinates
            lumps_history: List of lump values
            necks_history: List of neck values
            current_x: Current x position
            batch_name: Name of the current batch
            plc_sample_time: Time taken for PLC sample in seconds
        """
        if 'status' not in self.figures:
            return
            
        fig, ax = self.figures['status']
        ax.clear()
        
        # Set title and labels
        sample_time_ms = plc_sample_time * 1000  # Convert to milliseconds
        ax.set_title(f"Last {len(x_history)} samples - Batch: {batch_name} - PLC: {sample_time_ms:.1f}ms")
        ax.set_xlabel("X-Coord [m]")
        ax.set_ylabel("Błędy w cyklu")
        
        # Set x-axis limits
        if x_history:
            x_min = x_history[0]
            x_max = current_x
            ax.set_xlim(x_min, x_max)
        
        # Use all collected data points for plotting
        filtered_indices = list(range(len(x_history)))
        
        if filtered_indices:
            # Only plot visible data
            x_vals = [x_history[i] for i in filtered_indices]
            lumps_vals = [lumps_history[i] for i in filtered_indices]
            necks_vals = [necks_history[i] for i in filtered_indices]
            
            # Use numpy for bar plotting 
            x_vals = np.array(x_vals)
            width = 0.1  # Width of bars in x units (meters)
            
            # Plot bars for lumps and necks
            ax.bar(x_vals - width/2, lumps_vals, width=width, color="red", label="Lumps")
            ax.bar(x_vals + width/2, necks_vals, width=width, color="blue", label="Necks")
            
            ax.legend()
            
    def update_diameter_plot(self, diameter_x, diameter_history, current_x, diameter_preset=0, plc_sample_time=0):
        """
        Update the diameter plot showing diameter values over distance.
        
        Args:
            diameter_x: List of x-coordinates for diameter values
            diameter_history: List of diameter values
            current_x: Current x position
            diameter_preset: Target diameter value
            plc_sample_time: Time taken for PLC sample in seconds
        """
        if 'diameter' not in self.figures:
            return
            
        fig, ax = self.figures['diameter']
        ax.clear()
        
        if diameter_history:
            # Plot all diameter points directly - no downsampling
            ax.plot(diameter_x, diameter_history, 'g-', label='Actual')
            
            # Horizontal target line for preset diameter
            if diameter_preset > 0:
                ax.axhline(y=diameter_preset, color='r', linestyle='--', label='Preset')
            
            ax.set_xlabel("X-Coord [m]")
            ax.set_ylabel("Diameter [mm]")
            
            # Optimize y-axis limits
            y_min = min(min(diameter_history), diameter_preset) if diameter_preset > 0 else min(diameter_history)
            y_max = max(max(diameter_history), diameter_preset) if diameter_preset > 0 else max(diameter_history)
            margin = (y_max - y_min) * 0.2
            lower_bound = max(y_min - margin, 0)
            upper_bound = y_max + margin
            ax.set_ylim(lower_bound, upper_bound)
            
            # Set x-axis limits to match the data window
            if diameter_x:
                x_min = diameter_x[0]
                x_max = current_x
                ax.set_xlim(x_min, x_max)
                
                # Update the title to show sample count and coverage
                sample_count = len(diameter_history)
                sample_time_ms = plc_sample_time * 1000
                meters_covered = x_max - x_min
                ax.set_title(f"Avg Diameter - {sample_count} samples, {meters_covered:.1f}m - PLC: {sample_time_ms:.1f}ms")
            
            ax.grid(True)
            ax.legend()
    
    def update_fft_plot(self, diameter_history, fft_buffer_size=64):
        """
        Update the FFT analysis plot.
        
        Args:
            diameter_history: List of diameter values
            fft_buffer_size: Number of samples to use for FFT calculation
        """
        if 'fft' not in self.figures:
            return
            
        fig, ax = self.figures['fft']
        ax.clear()
        
        # Only proceed if we have enough data
        if len(diameter_history) > 0:
            # Convert to numpy array for FFT analysis
            import numpy as np
            diameter_array = np.array(diameter_history[-fft_buffer_size:], dtype=np.float32)
            
            if len(diameter_array) > 0:
                # Calculate FFT
                from window_fft_analysis import analyze_window_fft
                diameter_fft = analyze_window_fft(diameter_array)
                
                # Plot FFT results
                ax.set_title("Diameter FFT Analysis")
                ax.plot(np.abs(diameter_fft), label="FFT", color="green")
                ax.set_xlabel("Frequency")
                ax.set_ylabel("Magnitude")
                ax.grid(True)
                ax.legend()
    
    def update_all_plots(self, data_dict):
        """
        Main entry point for plot updates with throttling.
        
        Args:
            data_dict: Dictionary containing all data needed for plotting
        """
        now = time.time()
        # Check if it's time to update the plots
        if (self.last_update_time is None or 
            (now - self.last_update_time) >= self.min_update_interval) and self.plot_dirty:
            
            # First, send the data to the plotting process
            try:
                # Check if the plot process exists and is active
                if hasattr(self, 'plot_process') and self.plot_process and self.plot_process.is_alive():
                    # Make a deep copy to avoid shared memory issues
                    plot_data = copy.deepcopy(data_dict)
                    
                    # Send data to the plot process queue in non-blocking mode
                    # Only queue if we aren't behind
                    if self.plot_data_queue.qsize() < 2:
                        self.plot_data_queue.put_nowait(plot_data)
                        self.plot_complete_event.clear()  # Clear the completion event
                    else:
                        # Skip this update if we're falling behind
                        print("[PlotManager] Skipping plot update, process is falling behind")
                    
                    # If we're running in separate process mode, we don't need to update in main thread
                    # Just mark the plots as updated and return
                    if self.plot_process_active.value == 1:
                        self.plot_dirty = False
                        self.last_update_time = now
                        return
                        
                # If we get here, either:
                # 1. There is no plot process 
                # 2. The plot process has died
                # 3. We chose to still update in the main thread
                # So we fall back to updating plots in the main thread
                    plot_start = time.perf_counter()
                    self.plot_update_count += 1
                    
                    # Update each plot
                    status_time = 0
                    diameter_time = 0
                    fft_time = 0
                    
                    # Get PLC sample time from data dictionary
                    plc_sample_time = data_dict.get('plc_sample_time', 0)
                    
                    # Always update essential plots at any throttle level
                    if 'diameter' in self.figures:
                        start = time.perf_counter()
                        self.update_diameter_plot(
                            data_dict['diameter_x'],
                            data_dict['diameter_history'],
                            data_dict['current_x'],
                            data_dict.get('diameter_preset', 0),
                            plc_sample_time
                        )
                        diameter_time = time.perf_counter() - start
                    
                    # For status plot, update less frequently at high throttle level
                    if 'status' in self.figures and (self.throttle_level < 3 or self.plot_update_count % 2 == 0):
                        start = time.perf_counter()
                        self.update_status_plot(
                            data_dict['x_history'], 
                            data_dict['lumps_history'], 
                            data_dict['necks_history'],
                            data_dict['current_x'],
                            data_dict['batch_name'],
                            plc_sample_time
                        )
                        status_time = time.perf_counter() - start
                    
                    # For FFT plot, skip at higher throttle levels
                    if 'fft' in self.figures and self.throttle_level == 1:  # Only update at lowest throttle level
                        start = time.perf_counter()
                        self.update_fft_plot(
                            data_dict['diameter_history'],
                            data_dict.get('fft_buffer_size', 64)
                        )
                        fft_time = time.perf_counter() - start
                    
                    # Draw only the canvases that were updated
                    draw_start = time.perf_counter()
                    for key, (fig, _) in self.figures.items():
                        # Only draw updated plots based on throttle level
                        if (key == 'diameter' or 
                            (key == 'status' and (self.throttle_level < 3 or self.plot_update_count % 2 == 0)) or
                            (key == 'fft' and self.throttle_level == 1)):
                            fig.canvas.draw()
                    draw_time = time.perf_counter() - draw_start
                
                self.plot_dirty = False
                self.last_update_time = now
            
            except Exception as e:
                print(f"[PlotManager] Error updating plots: {e}")