# AccuScan Documentation

## Program Architecture

- AccuScan is a tube inspection system GUI using a multi-process/multi-thread architecture.
- PLC data acquisition runs in a separate process to avoid blocking the main UI thread.
- UI updates and data processing are handled in separate threads.
- Plotting operations run in a separate process on a dedicated CPU core for performance.

## Code Structure and File Descriptions

- **app.py**  
  Main application window and initialization. It sets up the overall application, instantiates key modules (such as the DataManager and FastAcquisitionBuffer), and manages processes and queues (e.g., for database and PLC interactions).

- **main_page.py**  
  The main UI page providing controls and plots. It arranges the main interface into panels (left, middle, right) for batch/product info, simulation parameters, and plot display. Also handles user interactions such as starting/stopping measurements and saving settings.

- **visualization.py**  
  Responsible for plot management, including updating and throttling plot rendering. It handles plotting in a separate process, updates plots based on incoming data (e.g., diameter values, FFT analysis), and manages inter-process communication via queues.

- **plc_helper.py**  
  Contains functions for PLC communication including connecting, disconnecting, and reading/writing data from/to the PLC. It abstracts low-level PLC interactions so that other parts of the app can use simple function calls.

- **data_processing.py**  
  Manages data acquisition and buffering. Implements the FastAcquisitionBuffer (using deques for efficient sample storage) and legacy WindowProcessor for backwards compatibility. It processes incoming measurement samples and prepares data for plotting and analysis.

- **window_fft_analysis.py**  
  Performs FFT analysis on diameter data. It optimizes FFT computation with caching mechanisms to avoid recalculating results too often, and provides processed data to the visualization components.

- **logic.py**  
  Contains the main business logic of the application. This includes connecting to the PLC, processing measurements (including flaw detection), calculating statistics, and coordinating with the UI via the controller reference.

- **db_helper.py**  
  Provides database functionality. Implements functions to initialize the database, check connectivity, and save various types of data (measurement samples, settings, events) to the database.

- **flaw_detection.py**  
  Implements flaw detection algorithms. It analyzes measurement data to detect and track flaws such as lumps and necks, updating counters for both local window and overall totals.
