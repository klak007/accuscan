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
        
        # Current position tracking
        self.current_x = 0.0
        self.last_update_time = None
        
        # Performance monitoring
        self.acquisition_time = 0.0
        self.processing_time = 0.0

    def add_sample(self, data, production_speed=50.0, speed_fluctuation_percent=0.0):
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
                
            # Convert from m/min to m/s for calculation
            speed_mps = current_speed / 60.0
            self.current_x += dt * speed_mps
            self.x_coords.append(self.current_x)
            
            self.acquisition_time = time.perf_counter() - start_time
            
            return {
                'acquisition_time': self.acquisition_time,
                'samples_count': len(self.timestamps)
            }
    
    def get_latest_data(self):
        """Get the most recent data point (thread-safe)"""
        with self.lock:
            if not self.timestamps:
                return {}
                
            return {
                'D1': self.diameters['D1'][-1] if self.diameters['D1'] else 0,
                'D2': self.diameters['D2'][-1] if self.diameters['D2'] else 0,
                'D3': self.diameters['D3'][-1] if self.diameters['D3'] else 0,
                'D4': self.diameters['D4'][-1] if self.diameters['D4'] else 0,
                'lumps': self.lumps[-1] if self.lumps else 0,
                'necks': self.necks[-1] if self.necks else 0,
                'avg_diameter': self.avg_diameters[-1] if self.avg_diameters else 0,
                'timestamp': self.timestamps[-1] if self.timestamps else None,
                'x_coord': self.x_coords[-1] if self.x_coords else 0,
            }
    
    def get_window_data(self):
        """Get all data for visualization (thread-safe copy)"""
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