"""
Flaw detection module for AccuScan application.
Handles the detection and counting of lumps and necks.
"""

import time


class FlawDetector:
    """
    Detects and tracks flaws (lumps and necks) based on measurement data.
    Maintains counters for total flaws and flaws within a specified window.
    """
    
    def __init__(self, flaw_window_size=0.5):
        """
        Initialize the FlawDetector.
        
        Args:
            flaw_window_size: Size of the window to track flaws in meters
        """
        self.flaw_window_size = flaw_window_size
        
        # Counters for flaws in the window
        self.flaw_lumps_count = 0
        self.flaw_necks_count = 0
        
        # Coordinates of flaws for window tracking
        self.flaw_lumps_coords = []
        self.flaw_necks_coords = []
        
        # Total counters
        self.total_lumps_count = 0
        self.total_necks_count = 0
        
        # Processing time
        self.processing_time = 0.0
    
    def update_flaw_window_size(self, size):
        """
        Update the size of the flaw window.
        
        Args:
            size: New window size in meters
        """
        self.flaw_window_size = size
    
    def process_flaws(self, data, current_x):
        """
        Process flaw data and update counters.
        
        Args:
            data: Dictionary containing measurement data
            current_x: Current x-coordinate position
            
        Returns:
            Dictionary with flaw detection results
        """
        start_time = time.perf_counter()
        
        # Extract flaw indicators from data
        lumps = data.get("lumps_delta", 0)
        necks = data.get("necks_delta", 0)
        
        # Track total counts
        if lumps > 0:
            self.total_lumps_count += 1
        if necks > 0:
            self.total_necks_count += 1
        
        # Track flaws in window
        if lumps > 0:
            self.flaw_lumps_coords.append(current_x)
            self.flaw_lumps_count += 1
        
        if necks > 0:
            self.flaw_necks_coords.append(current_x)
            self.flaw_necks_count += 1
        
        # Efficiently remove flaws that are outside the window (too old)
        # Use a windowing approach that preserves order and is efficient for sequential removal
        window_start = current_x - self.flaw_window_size
        
        # Optimize lumps removal
        if self.flaw_lumps_coords:
            old_count = len(self.flaw_lumps_coords)
            # Fast path: check if any need to be removed
            if self.flaw_lumps_coords[0] < window_start:
                # Find the index of the first element that's within the window
                # Binary search would be faster for large arrays, but most windows will be small
                drop_idx = 0
                for i, x in enumerate(self.flaw_lumps_coords):
                    if x >= window_start:
                        drop_idx = i
                        break
                
                # Remove all elements before this index
                if drop_idx > 0:
                    self.flaw_lumps_coords = self.flaw_lumps_coords[drop_idx:]
                    removed = old_count - len(self.flaw_lumps_coords)
                    self.flaw_lumps_count -= removed
        
        # Optimize necks removal
        if self.flaw_necks_coords:
            old_count = len(self.flaw_necks_coords)
            # Fast path: check if any need to be removed
            if self.flaw_necks_coords[0] < window_start:
                # Find the index of the first element that's within the window
                drop_idx = 0
                for i, x in enumerate(self.flaw_necks_coords):
                    if x >= window_start:
                        drop_idx = i
                        break
                
                # Remove all elements before this index
                if drop_idx > 0:
                    self.flaw_necks_coords = self.flaw_necks_coords[drop_idx:]
                    removed = old_count - len(self.flaw_necks_coords)
                    self.flaw_necks_count -= removed
        
        # Calculate processing time
        self.processing_time = time.perf_counter() - start_time
        
        # Return detection results
        return {
            'lumps_count': self.total_lumps_count,
            'necks_count': self.total_necks_count,
            'window_lumps_count': self.flaw_lumps_count,
            'window_necks_count': self.flaw_necks_count,
            'processing_time': self.processing_time
        }
    
    def check_thresholds(self, max_lumps=0, max_necks=0):
        """
        Check if flaw counts exceed thresholds.
        
        Args:
            max_lumps: Maximum allowed number of lumps in window
            max_necks: Maximum allowed number of necks in window
            
        Returns:
            Dictionary with threshold violation flags
        """
        return {
            'lumps_exceeded': self.flaw_lumps_count > max_lumps if max_lumps > 0 else False,
            'necks_exceeded': self.flaw_necks_count > max_necks if max_necks > 0 else False
        }
    
    def reset_counters(self):
        """Reset all flaw counters."""
        self.flaw_lumps_count = 0
        self.flaw_necks_count = 0
        self.flaw_lumps_coords.clear()
        self.flaw_necks_coords.clear()
        self.total_lumps_count = 0
        self.total_necks_count = 0

    def get_total_flaws_count(self):
        """
        Return total lumps + necks encountered since the start.
        """
        return self.total_lumps_count + self.total_necks_count