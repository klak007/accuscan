# AccuScan Documentation

## Program Architecture

- AccuScan is a tube inspection system GUI using a multi-process/multi-thread architecture
- PLC data acquisition runs in a separate process to avoid blocking the main UI thread
- UI updates and data processing are handled in separate threads
- Plotting operations run in a separate process on a dedicated CPU core for performance 

## Common Commands

### Development Commands
```bash
# Start the application
python app.py
```

### Performance Optimization
- Plot rendering has been moved to a separate process to improve UI responsiveness
- The plotting process is pinned to a specific CPU core (normally the last available core)
- Data is passed between processes using multiprocessing.Queue
- psutil is used to set CPU affinity for performance isolation

## Code Structure
- `app.py` - Main application window and initialization
- `main_page.py` - Main UI page with controls and plots
- `visualization.py` - Plot management including separate process implementation
- `plc_helper.py` - PLC communication functions 
- `data_processing.py` - Data processing and buffer management
- `window_fft_analysis.py` - FFT analysis for diameter data
- `logic.py` - Business logic and core functionality