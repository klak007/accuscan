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
    
    
    def process_flaws(self, data, current_x):
        """
        Process flaw data and update counters.
        
        Args:
            data: Dictionary containing measurement data
            current_x: Current x-coordinate position
            
        Returns:
            Dictionary with flaw detection results
        """
        # Extract flaw indicators from data
        lumps = data.get("lumps_delta", 0)
        necks = data.get("necks_delta", 0)
        
        # -----------------------------
        # 1) Obsługa dodawania defektów
        # -----------------------------
        
        # Track total counts
        if lumps > 0:
            self.total_lumps_count += lumps
        if necks > 0:
            self.total_necks_count += necks
        
        # Track flaws in window
        if lumps > 0:
            self.flaw_lumps_coords.append((current_x, lumps))
            self.flaw_lumps_count += lumps

        if necks > 0:
            self.flaw_necks_coords.append((current_x, necks))
            self.flaw_necks_count += necks

        # -----------------------------
        # 2) Obsługa usuwania defektów poza oknem
        # -----------------------------

        
        window_start = current_x - self.flaw_window_size
        
        # Usuwanie lumps poza oknem
        if self.flaw_lumps_coords and self.flaw_lumps_coords[0][0] < window_start:
            drop_idx = None
            for i, (x, cnt) in enumerate(self.flaw_lumps_coords):
                if x >= window_start:
                    drop_idx = i
                    break
            if drop_idx is None:
                drop_idx = len(self.flaw_lumps_coords)
            if drop_idx > 0:
                removed = sum(cnt for (_, cnt) in self.flaw_lumps_coords[:drop_idx])
                self.flaw_lumps_coords = self.flaw_lumps_coords[drop_idx:]
                self.flaw_lumps_count -= removed

        
        # Usuwanie necks poza oknem

        if self.flaw_necks_coords and self.flaw_necks_coords[0][0] < window_start:
            drop_idx = None
            for i, (x, cnt) in enumerate(self.flaw_necks_coords):
                if x >= window_start:
                    drop_idx = i
                    break
            if drop_idx is None:
                drop_idx = len(self.flaw_necks_coords)
            if drop_idx > 0:
                removed = sum(cnt for (_, cnt) in self.flaw_necks_coords[:drop_idx])
                self.flaw_necks_coords = self.flaw_necks_coords[drop_idx:]
                self.flaw_necks_count -= removed
        
        # -----------------------------
        # 3) Podsumowanie czasu
        # -----------------------------

        # Log (opcjonalny) – jeśli chcesz w konsoli zobaczyć czasy szczegółowe:
        # print(
        #     "[FlawDetector.process_flaws] "
        #     f"Lumps Add Time: {lumps_add_time:.6f}s, "
        #     f"Necks Add Time: {necks_add_time:.6f}s, "
        #     f"Total Add Time: {add_time_total:.6f}s, "
        #     f"Lumps Removal Time: {lumps_removal_time:.6f}s, "
        #     f"Necks Removal Time: {necks_removal_time:.6f}s, "
        #     f"Total Removal Time: {removal_time_total:.6f}s, "
        #     f"Overall Processing Time: {self.processing_time:.6f}s"
        # )
        
        # Zwracamy wyniki
        return {
            'lumps_count': self.total_lumps_count,
            'necks_count': self.total_necks_count,
            'window_lumps_count': self.flaw_lumps_count,
            'window_necks_count': self.flaw_necks_count,
            'processing_time': self.processing_time,
            
        }
