"""
Visualization module for AccuScan application.
Handles plotting functionality separated from the main UI.
"""

import matplotlib.pyplot as plt
import time
import numpy as np
from window_fft_analysis import analyze_window_fft


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
        if (self.last_update_time is None or 
            (now - self.last_update_time) >= self.min_update_interval) and self.plot_dirty:
            
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
            
            total_plot_time = time.perf_counter() - plot_start
            
            # Adaptive throttling based on performance
            if self.adaptive_mode:
                if total_plot_time > 0.2:  # Slow plotting detected
                    # Increase throttling level (up to maximum of 3)
                    old_level = self.throttle_level
                    self.throttle_level = min(self.throttle_level + 1, 3)
                    if old_level != self.throttle_level:
                        print(f"[Plot] Increasing throttle level to {self.throttle_level} due to slow updates")
                    self.last_high_cpu_time = now
                elif total_plot_time < 0.05 and (now - self.last_high_cpu_time) > 5.0:
                    # Decrease throttling if performance is good for a while
                    old_level = self.throttle_level
                    self.throttle_level = max(self.throttle_level - 1, 1)
                    if old_level != self.throttle_level:
                        print(f"[Plot] Decreasing throttle level to {self.throttle_level} due to good performance")
            
            # Log performance data but only if it's significant
            if total_plot_time > 0.1:
                print(f"[Plot] Total: {total_plot_time:.4f}s | Status: {status_time:.4f}s | "
                      f"Diameter: {diameter_time:.4f}s | FFT: {fft_time:.4f}s | Draw: {draw_time:.4f}s | "
                      f"Throttle: {self.throttle_level}")