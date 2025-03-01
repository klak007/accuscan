"""
Data processing module for AccuScan application.
Handles window calculations and processing of measurement data.
"""

import numpy as np
import time
from datetime import datetime


class WindowProcessor:
    """
    Processes measurement data samples and manages data window.
    Keeps track of sample history and calculates derived data.
    """
    
    def __init__(self, max_samples=32):
        """
        Initialize the WindowProcessor.
        
        Args:
            max_samples: Maximum number of samples to keep in history (default: 1024)
        """
        # Windows for tracking various data types
        self.max_samples = max_samples
        self.lumps_history = []
        self.necks_history = []
        self.x_history = []
        self.diameter_history = []  # Average diameter values
        self.diameter_x = []        # X-coordinates for diameter values
        
        # Current position tracking
        self.current_x = 0.0
        self.last_update_time = None
        
        # Performance monitoring
        self.processing_time = 0.0

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
        start_time = time.perf_counter()
        
        # Extract values from data dictionary
        lumps = data.get("lumps", 0)
        necks = data.get("necks", 0)
        
        # Calculate average diameter from D1-D4
        d1 = data.get("D1", 0)
        d2 = data.get("D2", 0)
        d3 = data.get("D3", 0)
        d4 = data.get("D4", 0)
        diameters = [d1, d2, d3, d4]
        davg = sum(diameters) / 4.0 if all(d != 0 for d in diameters) else 0
        
        # Calculate x-coordinate based on speed
        current_time = data.get("timestamp", datetime.now())
        dt = 0 if self.last_update_time is None else (current_time - self.last_update_time).total_seconds()
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
        
        # Update histories
        self.lumps_history.append(lumps)
        self.necks_history.append(necks)
        self.x_history.append(self.current_x)
        self.diameter_history.append(davg)
        self.diameter_x.append(self.current_x)
        
        # Enforce history limits
        while len(self.lumps_history) > self.max_samples:
            self.lumps_history.pop(0)
            if len(self.x_history) > self.max_samples:
                self.x_history.pop(0)
        
        while len(self.necks_history) > self.max_samples:
            self.necks_history.pop(0)
            
        while len(self.diameter_history) > self.max_samples:
            self.diameter_x.pop(0)
            self.diameter_history.pop(0)
        
        # Calculate processing time
        self.processing_time = time.perf_counter() - start_time
        
        # Return processed data
        processed_data = {
            'lumps_history': self.lumps_history,
            'necks_history': self.necks_history,
            'x_history': self.x_history,
            'diameter_history': self.diameter_history,
            'diameter_x': self.diameter_x,
            'current_x': self.current_x,
            'processing_time': self.processing_time
        }
        
        return processed_data