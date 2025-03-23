"""
Visualization module for AccuScan application.
Handles plotting functionality separated from the main UI using a separate process.
"""

import pyqtgraph as pg
import time
import numpy as np
import multiprocessing as mp
from multiprocessing import Process, Queue, Event, Value, cpu_count
from window_fft_analysis import analyze_window_fft
from scipy.signal import find_peaks
from PyQt5.QtCore import Qt

class PlotManager:
    """
    Manages plot updates for AccuScan application using PyQtGraph.
    Handles throttling of plot updates to improve performance.
    """
    
    def __init__(self, plot_widgets=None, min_update_interval=0.2, analysis_queue=None):
        """
        Initialize the PlotManager with pyqtgraph plot widgets.
        
        Args:
            plot_widgets: Dictionary with structure:
                {'status': status_plot_widget, 'diameter': diameter_plot_widget, 'fft': fft_plot_widget}
            min_update_interval: Minimum time between plot updates in seconds.
        """
        pg.setConfigOptions(background=(240, 240, 240), foreground='k')
        # Store plot widget references (instead of matplotlib figures/axes)
        self.plot_widgets = {}
        self.plot_widgets['status'] = pg.PlotWidget()
        self.plot_widgets['status'].setTitle("Defekty na dystansie")
        self.plot_widgets['diameter'] = pg.PlotWidget()
        self.plot_widgets['fft'] = pg.PlotWidget()
        self.min_update_interval = min_update_interval
        self.last_update_time = None
        self.plot_dirty = False
        self.fft_threshold = 500.0
        self.current_pulsation_val = 0.0
        
        self.analysis_queue = analysis_queue
        # Performance monitoring
        self.plot_update_count = 0
        self.throttle_level = 1  # 1 = normal (update all plots), 2 = skip FFT, 3 = essential only
        self.last_high_cpu_time = 0  # Last time high CPU usage was detected
        self.adaptive_mode = True  # Enable adaptive throttling
        
        # For PyQtGraph we update in the main thread; no separate process is needed.
        self.using_main_thread = True
        
        # If desired, you can still set up queues for decoupling heavy calculations,
        # but here we assume that plot updates occur directly in the UI.
        print("[PlotManager] Initialized for PyQtGraph; using main thread for updates.")
    

    def apply_pulsation(self, diameter_history, sample_rate=100, modulation_frequency=1, modulation_depth=0.05):
        """
        Modyfikuje dane diameter_history, mnożąc je przez współczynnik pulsacji.
        
        Args:
            diameter_history: Lista oryginalnych próbek średnicy.
            sample_rate: Częstotliwość próbkowania (ilość próbek na sekundę).
            modulation_frequency: Częstotliwość pulsacji (Hz).
            modulation_depth: Głębokość modulacji (np. 0.05 to 5% zmiany).
        
        Returns:
            Nowa lista próbek po nałożeniu modulacji.
        """
        modulated = []
        for i, d in enumerate(diameter_history):
            t = i / sample_rate
            mod_factor = 1 + modulation_depth * np.sin(2 * np.pi * modulation_frequency * t)
            modulated.append(d * mod_factor)
        return modulated
    


    def update_status_plot(self, x_history, lumps_history, necks_history, current_x, batch_name, plc_sample_time=0):
        """
        Aktualizuje wykres statusu (lumps/necks względem współrzędnych X) przy użyciu PyQtGraph.
        
        Args:
            x_history: Lista współrzędnych X
            lumps_history: Lista wartości lumps
            necks_history: Lista wartości necks
            current_x: Aktualna pozycja X
            batch_name: Nazwa bieżącej partii
            plc_sample_time: Czas pobierania próbki z PLC (w sekundach)
        """
        plot_widget = self.plot_widgets.get('status')
        if plot_widget is not None:
            plot_widget.clear()
        
            # sample_time_ms = plc_sample_time * 1000  # konwersja do ms
            plot_widget.setTitle(f"Defekty na dystansie - ostatnie {len(x_history)} próbek - Batch: {batch_name}")
            plot_widget.setLabel('bottom', "Dystans [m]")
            plot_widget.setLabel('left', "Defekty w cyklu")
            
            if x_history:
                x_min = x_history[0]
                x_max = current_x
                plot_widget.setXRange(x_min, x_max)
            
            # Używamy BarGraphItem, aby narysować słupki dla lumps i necks
            if x_history:
                x_vals = np.array(x_history)
                width = 0.1  # Szerokość słupka w metrach
                lumps_vals = np.array(lumps_history)
                necks_vals = np.array(necks_history)
                
                lumps_bar = pg.BarGraphItem(x=x_vals - width/2, height=lumps_vals, width=width, brush='r')
                necks_bar = pg.BarGraphItem(x=x_vals + width/2, height=necks_vals, width=width, brush='b')
                
                plot_widget.addItem(lumps_bar)
                plot_widget.addItem(necks_bar)

            
    def update_diameter_plot(self, diameter_x, diameter_history, current_x, diameter_preset=0, plc_sample_time=0):
        """
        Aktualizuje wykres średnicy (wartości średnicy w zależności od odległości) przy użyciu PyQtGraph.
        
        Args:
            diameter_x: Lista współrzędnych X dla średnic
            diameter_history: Lista wartości średnicy
            current_x: Aktualna pozycja X
            diameter_preset: Docelowa wartość średnicy
            plc_sample_time: Czas pobierania próbki z PLC (w sekundach)
        """
        if 'diameter' not in self.plot_widgets:
            return
        plot_widget = self.plot_widgets['diameter']
        plot_widget.clear()
        
        if diameter_history:
            # Rysujemy linię – używamy domyślnego pen'a zielonego
            plot_widget.plot(diameter_x, diameter_history, pen='b', name='Actual')
            
            # Dodajemy poziomą linię docelową, jeśli zadana jest wartość średnicy docelowej
            if diameter_preset > 0:
                preset_line = pg.InfiniteLine(angle=0, pos=diameter_preset,
                                            pen=pg.mkPen('r', style=pg.QtCore.Qt.DashLine))
                plot_widget.addItem(preset_line)
            
            plot_widget.setLabel('bottom', "X-Coord [m]")
            plot_widget.setLabel('left', "Diameter [mm]")
            
            # Ustalanie granic osi Y z marginesem 20%
            y_min = min(min(diameter_history), diameter_preset) if diameter_preset > 0 else min(diameter_history)
            y_max = max(max(diameter_history), diameter_preset) if diameter_preset > 0 else max(diameter_history)
            margin = (y_max - y_min) * 0.2
            lower_bound = max(y_min - margin, 0)
            upper_bound = y_max + margin
            plot_widget.setYRange(lower_bound, upper_bound)
            
            if diameter_x:
                x_min = diameter_x[0]
                x_max = current_x
                plot_widget.setXRange(x_min, x_max)
                sample_count = len(diameter_history)
                sample_time_ms = plc_sample_time * 1000
                meters_covered = x_max - x_min
                plot_widget.setTitle(f"Uśredniona średnica na dystansie - {sample_count} samples, {meters_covered:.1f}m")
            


    def detect_peaks(self, freqs, amplitudes, threshold=None):
        """
        Wyszukuje lokalne maksima (piki) w wektorze amplitudes,
        zwraca listę indeksów tych pików, które przekraczają zadany próg.
        """
        if threshold is None:
            threshold = self.fft_threshold
        peak_indices, properties = find_peaks(amplitudes, prominence=100, distance=5)
        peak_indices_above_thresh = [i for i in peak_indices if amplitudes[i] > threshold]
        return peak_indices_above_thresh

    def update_fft_plot(self, diameter_history, fft_buffer_size=256, processing_time=0, measurement_data=None):
        if 'fft' not in self.plot_widgets:
            return

        plot_widget = self.plot_widgets['fft']
        plot_widget.clear()

        if len(diameter_history) > 0:
            # Ustal dynamiczny sample rate na podstawie processing_time, używając 74 Hz jako domyślnej wartości
            sample_rate = 1 / processing_time if processing_time > 0 else 83.123
                
            diameter_array = np.array(diameter_history[-fft_buffer_size:], dtype=np.float32)
            diameter_mean = np.mean(diameter_array)
            diameter_array -= diameter_mean

            if len(diameter_array) > 1:
                diameter_fft = np.abs(np.fft.rfft(diameter_array))
                freqs = np.fft.rfftfreq(len(diameter_array), d=1.0 / sample_rate)
                peak_idxs = self.detect_peaks(freqs, diameter_fft, threshold=self.fft_threshold)

                if len(peak_idxs) > 0:
                    max_amp = max(diameter_fft[i] for i in peak_idxs)
                else:
                    max_amp = 0.0
                self.current_pulsation_val = max_amp

                if measurement_data is not None:
                    measurement_data['pulsation_val'] = max_amp 
                print(f"[PlotManager] Detected pulsation amplitude: {max_amp:.2f}")

                # Uaktualnij tytuł wykresu, dodając sample rate i processing time
                title_text = f"Diameter FFT Analysis (Sample rate: {sample_rate:.2f} Hz, Proc time: {processing_time:.4f} s)"
                plot_widget.setTitle(title_text)
                
                plot_widget.plot(freqs, diameter_fft, pen='m', name="FFT")
                plot_widget.setLabel('bottom', "Frequency [Hz]")
                plot_widget.setLabel('left', "Magnitude")
                
                threshold_line = pg.InfiniteLine(pos=self.fft_threshold, angle=0, pen='r')
                plot_widget.addItem(threshold_line)
                
                for idx in peak_idxs:
                    vertical_line = pg.InfiniteLine(
                        pos=freqs[idx],
                        angle=90,
                        pen=pg.mkPen(color='b', style=pg.QtCore.Qt.DashLine)
                    )
                    plot_widget.addItem(vertical_line)

    

    def check_plot_process(self):
        """Since we're updating plots in the main thread, no separate plot process is used."""
        print("[PlotManager] Using main thread for plotting; no plot process to check or restart.")
        return False

       
    def initialize_plots(self):
        # Configure each plot widget
        if self.plot_widgets['status']:
            self.plot_widgets['status'].setTitle("Liczba defektów na dystansie")
        if self.plot_widgets['diameter']:
            self.plot_widgets['diameter'].setTitle("Uśredniona średnica na dystansie")
        if self.plot_widgets['fft']:
            self.plot_widgets['fft'].setTitle("FFT Plot")

    def stop_plot_process(self):
        """
        Clean method to stop any plotting processes.
        This is called during application shutdown.
        """
        # For PyQtGraph we're using the main thread, so this is a no-op
        print("[PlotManager] No separate process to stop in PyQtGraph mode")
        return True
