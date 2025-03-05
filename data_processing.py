"""
Data processing module for AccuScan application.
Handles window calculations and processing of measurement data with multithreading support.
"""

import numpy as np
import time
import threading
from collections import deque
from datetime import datetime


class FastAcquisitionBuffer:
    """
    Fast, thread-safe buffer for measurement data acquisition and processing.
    Uses deques for efficient O(1) operations when adding/removing samples.
    Can replace DataManager with more efficient storage and direct DB functionality.
    """
    
    def __init__(self, max_samples=1024):
        """
        Initialize the FastAcquisitionBuffer.
        
        Args:
            max_samples: Maximum number of samples to keep in history (default: 1024)
        """
        self.max_samples = max_samples
        self.lock = threading.Lock()
        
        # Core measurement data with fixed-size deques
        self.diameters = {
            'D1': deque(maxlen=max_samples),
            'D2': deque(maxlen=max_samples),
            'D3': deque(maxlen=max_samples),
            'D4': deque(maxlen=max_samples)
        }
        
        # Metadata and derived values
        self.lumps = deque(maxlen=max_samples)
        self.necks = deque(maxlen=max_samples)
        self.timestamps = deque(maxlen=max_samples)
        self.x_coords = deque(maxlen=max_samples)
        self.avg_diameters = deque(maxlen=max_samples)
        
        # Store all complete samples for potential DB access
        self.samples = deque(maxlen=max_samples)
        
        # Current position tracking
        self.current_x = 0.0
        self.last_update_time = None
        
        # Performance monitoring
        self.acquisition_time = 0.0
        self.processing_time = 0.0
        
        # Statistics cache
        self.stats_cache = {}
        self.last_stats_update = 0
        self.stats_cache_ttl = 1.0  # 1 second

    def add_sample(self, data, production_speed=None, speed_fluctuation_percent=0.0):
        """
        Thread-safe method to add a new sample to the buffer.
        
        Args:
            data: Dictionary containing measurement data
            production_speed: Base production speed in m/min
            speed_fluctuation_percent: Random speed fluctuation in percent
            
        Returns:
            Dictionary with basic metrics about the operation
        """
        with self.lock:
            start_time = time.perf_counter()
            
            # Extract and store raw measurements
            for i in range(1, 5):
                key = f"D{i}"
                self.diameters[key].append(data.get(key, 0))
            
            # Store defect indicators
            self.lumps.append(data.get("lumps", 0))
            self.necks.append(data.get("necks", 0))
            
            # Calculate and store average diameter
            values = [data.get(f"D{i}", 0) for i in range(1, 5)]
            avg = sum(values) / 4.0 if all(v != 0 for v in values) else 0
            self.avg_diameters.append(avg)
            
            # Calculate x-coordinate based on speed
            current_time = data.get("timestamp", datetime.now())
            self.timestamps.append(current_time)
            
            dt = 0
            if self.last_update_time is not None:
                dt = (current_time - self.last_update_time).total_seconds()
            self.last_update_time = current_time
            
            # Apply fluctuation to speed if specified
            if speed_fluctuation_percent > 0:
                import random
                fluctuation_factor = 1.0 + random.uniform(-speed_fluctuation_percent/100, speed_fluctuation_percent/100)
                current_speed = production_speed * fluctuation_factor
            else:
                current_speed = production_speed
                
            if production_speed is None:
                production_speed = data.get("speed", 50.0)
                
            # Convert from m/min to m/s for calculation
            speed_mps = production_speed / 60.0
            self.current_x += dt * speed_mps
            self.x_coords.append(self.current_x)
            
            # Store complete sample with additional computed values
            sample_copy = data.copy()
            sample_copy['xCoord'] = self.current_x
            sample_copy['speed'] = current_speed
            sample_copy['avg_diameter'] = avg
            self.samples.append(sample_copy)
            
            # Invalidate statistics cache
            self.stats_cache = {}
            
            self.acquisition_time = time.perf_counter() - start_time
            
            return {
                'acquisition_time': self.acquisition_time,
                'samples_count': len(self.timestamps)
            }
    
    def get_latest_data(self):
        """Get the most recent data point (thread-safe)"""
        with self.lock:
            if not self.samples:
                return {}
                
            # Return the latest complete sample directly
            return self.samples[-1]
            
            
    def get_statistics(self, last_n=100):
        """Calculate statistics from recent samples (with caching)"""
        now = time.time()
        
        # Check if we can use cached stats
        if self.stats_cache and now - self.last_stats_update < self.stats_cache_ttl:
            return self.stats_cache
            
        with self.lock:
            if not self.samples:
                return {}
                
            # Get the last N samples
            recent_samples = list(self.samples)[-min(last_n, len(self.samples)):]
            
            # Initialize stats dictionary
            stats = {}
            
            # Calculate diameter statistics
            for i in range(1, 5):
                key = f"D{i}"
                values = [sample.get(key, 0) for sample in recent_samples]
                if values:
                    import numpy as np
                    stats[f"{key}_mean"] = np.mean(values)
                    stats[f"{key}_std"] = np.std(values)
                    stats[f"{key}_min"] = np.min(values)
                    stats[f"{key}_max"] = np.max(values)
            
            # Calculate overall statistics
            diameter_values = [sample.get('avg_diameter', 0) for sample in recent_samples]
            if diameter_values:
                import numpy as np
                stats["mean_diameter"] = np.mean(diameter_values)
                stats["std_diameter"] = np.std(diameter_values)
            
            # Cache the results
            self.stats_cache = stats
            self.last_stats_update = now
            
            return stats
    
    def get_window_data(self, interpolate_gaps=False):
        """
        Get all data for visualization (thread-safe copy)
        
        Args:
            interpolate_gaps: If True, attempts to fill small gaps in the data
                              by interpolating missing values for continuity
        """
        with self.lock:
            start_time = time.perf_counter()
            
            # Return copies of all data for thread safety
            window_data = {
                'D1': list(self.diameters['D1']),
                'D2': list(self.diameters['D2']),
                'D3': list(self.diameters['D3']),
                'D4': list(self.diameters['D4']),
                'lumps_history': list(self.lumps),
                'necks_history': list(self.necks),
                'timestamp_history': list(self.timestamps),
                'x_history': list(self.x_coords),
                'diameter_history': list(self.avg_diameters),
                'diameter_x': list(self.x_coords),
                'current_x': self.current_x,
                'acquisition_time': self.acquisition_time
            }
            
            # Fill gaps in diameter data if requested
            if interpolate_gaps and len(self.x_coords) > 2:
                try:
                    # Import here to avoid initial overhead
                    import numpy as np
                    
                    # Convert to numpy arrays for vectorized operations
                    x_arr = np.array(self.x_coords)
                    diameter_arr = np.array(self.avg_diameters)
                    
                    # Check for discontinuities in x-coordinates
                    # A discontinuity is when the distance between points is much larger than average
                    diffs = np.diff(x_arr)
                    mean_diff = np.mean(diffs)
                    std_diff = np.std(diffs)
                    threshold = mean_diff + 2 * std_diff  # 2 standard deviations above mean
                    
                    # Find gaps larger than threshold
                    gap_indices = np.where(diffs > threshold)[0]
                    
                    if len(gap_indices) > 0:
                        # Create a new x-axis with more points to fill gaps
                        new_x = list(x_arr)
                        new_diameters = list(diameter_arr)
                        
                        # Insert interpolated points at each gap
                        added_points = 0
                        for idx in gap_indices:
                            # Adjust index for points we've already added
                            adj_idx = idx + added_points
                            
                            # Calculate how many points to insert in this gap
                            gap_size = diffs[idx]
                            num_points = int(gap_size / mean_diff) - 1
                            
                            if num_points > 0 and num_points < 30:  # Avoid filling huge gaps
                                # Calculate interpolated x values
                                start_x = new_x[adj_idx]
                                end_x = new_x[adj_idx + 1]
                                step = (end_x - start_x) / (num_points + 1)
                                
                                # Calculate interpolated diameter values
                                start_diam = new_diameters[adj_idx]
                                end_diam = new_diameters[adj_idx + 1]
                                diam_step = (end_diam - start_diam) / (num_points + 1)
                                
                                # Insert interpolated points
                                for i in range(1, num_points + 1):
                                    insert_idx = adj_idx + i
                                    new_x.insert(insert_idx, start_x + i * step)
                                    new_diameters.insert(insert_idx, start_diam + i * diam_step)
                                    
                                added_points += num_points
                        
                        # Update window data with interpolated values
                        if added_points > 0:
                            print(f"[Interpolation] Added {added_points} points to fill {len(gap_indices)} gaps")
                            window_data['diameter_history'] = new_diameters
                            window_data['diameter_x'] = new_x
                
                except Exception as e:
                    print(f"[Interpolation] Error: {e}")
            
            self.processing_time = time.perf_counter() - start_time
            window_data['processing_time'] = self.processing_time
            
            return window_data


# Keep WindowProcessor for backwards compatibility
class WindowProcessor(FastAcquisitionBuffer):
    """
    Legacy adapter class for backward compatibility.
    Delegates to FastAcquisitionBuffer.
    """
    
    def process_sample(self, data, production_speed=50.0, speed_fluctuation_percent=0.0):
        """
        Process a new data sample, update histories, and calculate x-coordinate.
        
        Args:
            data: Dictionary containing measurement data
            production_speed: Base production speed in m/min
            speed_fluctuation_percent: Random speed fluctuation in percent
        
        Returns:
            Dictionary with processed data including window counters
        """
        self.add_sample(data, production_speed, speed_fluctuation_percent)
        return self.get_window_data()