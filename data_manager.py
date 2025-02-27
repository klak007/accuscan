# data_manager.py
import pandas as pd
import time

class DataManager:
    def __init__(self, max_samples=1000):
        self.max_samples = max_samples
        # Inicjalnie pusty DataFrame z ustaloną strukturą kolumn
        self.df = pd.DataFrame(columns=["timestamp","D1","D2","D3","D4","lumps","necks","xCoord","speed"])
        # Cache for latest data
        self.latest_sample = None
        self.last_optimized = time.time()
        self.optimize_interval = 60  # seconds
    
    def add_sample(self, sample: dict):
        """
        Dodaje pojedynczy słownik z danymi (sample) do DataFrame.
        """
        # Store latest sample
        self.latest_sample = sample.copy()
        
        # OPTIMIZATION: Create new DataFrame with explicit dtypes matching the columns
        # This prevents DataFrame from trying to infer types which can be slow
        new_df = pd.DataFrame([sample], columns=self.df.columns)
        
        # If DataFrame is empty, set dtypes based on first sample
        if self.df.empty:
            self.df = new_df
        else:
            # OPTIMIZATION: Append rather than concat for single rows
            self.df = pd.concat([self.df, new_df], ignore_index=True)
        
        # Limit the number of samples
        if len(self.df) > self.max_samples:
            # OPTIMIZATION: Drop in batches when exceeding by a significant amount
            # to avoid doing too many small drops
            if len(self.df) > self.max_samples * 1.1:  # 10% over max
                self.df = self.df.iloc[len(self.df) - self.max_samples:]
                self.df.reset_index(drop=True, inplace=True)
        
        # Periodically optimize the DataFrame to reduce memory usage
        now = time.time()
        if now - self.last_optimized > self.optimize_interval:
            self._optimize_dataframe()
            self.last_optimized = now
    
    def _optimize_dataframe(self):
        """Optimize the DataFrame to reduce memory usage"""
        # Convert numeric columns to appropriate dtypes
        numeric_cols = ["D1", "D2", "D3", "D4", "lumps", "necks"]
        for col in numeric_cols:
            if col in self.df.columns:
                if self.df[col].dtype == 'object':
                    # Try to convert to numeric
                    self.df[col] = pd.to_numeric(self.df[col], errors='ignore')
        
        # Explicitly copy to consolidate memory
        self.df = self.df.copy()
    
    def get_current_data(self):
        """
        Zwraca aktualny DataFrame (opcjonalnie można zwrócić kopię).
        """
        return self.df
    
    def get_latest_sample(self):
        """Return the latest sample as a dict without accessing the DataFrame"""
        return self.latest_sample if self.latest_sample else {}
    
    def get_statistics(self, last_n=100):
        """Calculate statistics from recent samples"""
        if self.df.empty or len(self.df) == 0:
            return {}
        
        # Get the last N rows
        recent = self.df.iloc[-min(last_n, len(self.df)):]
        
        stats = {}
        for col in ["D1", "D2", "D3", "D4"]:
            if col in recent.columns:
                stats[f"{col}_mean"] = recent[col].mean()
                stats[f"{col}_std"] = recent[col].std()
                stats[f"{col}_min"] = recent[col].min()
                stats[f"{col}_max"] = recent[col].max()
        
        # Calculate overall statistics
        if all(col in recent.columns for col in ["D1", "D2", "D3", "D4"]):
            diameters = recent[["D1", "D2", "D3", "D4"]].mean(axis=1)
            stats["mean_diameter"] = diameters.mean()
            stats["std_diameter"] = diameters.std()
        
        return stats
