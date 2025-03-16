"""
FFT analysis module for processing diameter data.
"""

import numpy as np

def analyze_window_fft(data_array, cache_ttl=5):
    if len(data_array) <= 1:
        return np.zeros(32, dtype=np.float32)
    result = np.abs(np.fft.rfft(data_array))
    return result