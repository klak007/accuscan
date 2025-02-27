"""
FFT analysis module for processing diameter data.
This is optimized for performance.
"""

import numpy as np
import time

# Cache for FFT results to avoid recalculation
_fft_cache = {}
_fft_cache_max_size = 50
_last_fft_calc = 0  # timestamp

def analyze_window_fft(data_array, cache_ttl=5):
    """
    Analyze data with FFT, with caching for performance optimization.
    
    Args:
        data_array: Numpy array containing the data
        cache_ttl: Time to live for cache entries in seconds
    
    Returns:
        Numpy array with FFT results
    """
    global _last_fft_calc, _fft_cache
    
    # Don't run FFT too often - if called within 200ms, use previous result
    now = time.time()
    if now - _last_fft_calc < 0.2 and _fft_cache:
        # Return most recent result from cache
        return list(_fft_cache.values())[-1]
    
    # Check if we already calculated this exact data recently
    data_hash = hash(data_array.tobytes())
    
    if data_hash in _fft_cache:
        cache_entry = _fft_cache[data_hash]
        if now - cache_entry['time'] < cache_ttl:
            return cache_entry['result']
    
    # Compute FFT if not in cache or cache expired
    if len(data_array) <= 1:
        result = np.zeros(32, dtype=np.float32)
    else:
        # Optimization: use real FFT for real data (faster)
        result = np.abs(np.fft.rfft(data_array))
        
        # Scale to expected range
        if len(result) > 0:
            result = result / np.max(result) if np.max(result) > 0 else result
    
    # Store in cache
    _fft_cache[data_hash] = {'result': result, 'time': now}
    
    # Limit cache size
    if len(_fft_cache) > _fft_cache_max_size:
        # Remove oldest entries
        oldest_keys = sorted(_fft_cache.keys(), 
                          key=lambda k: _fft_cache[k]['time'])[:len(_fft_cache) // 2]
        for key in oldest_keys:
            del _fft_cache[key]
    
    _last_fft_calc = now
    return result
