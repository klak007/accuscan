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
import psutil
import copy


class PlotManager:
    """
    Manages plot updates for AccuScan application using PyQtGraph.
    Handles throttling of plot updates to improve performance.
    """
    
    def __init__(self, plot_widgets=None, min_update_interval=0.2):
        """
        Initialize the PlotManager with pyqtgraph plot widgets.
        
        Args:
            plot_widgets: Dictionary with structure:
                {'status': status_plot_widget, 'diameter': diameter_plot_widget, 'fft': fft_plot_widget}
            min_update_interval: Minimum time between plot updates in seconds.
        """
        # Store plot widget references (instead of matplotlib figures/axes)
        self.plot_widgets = {}
        self.plot_widgets['status'] = pg.PlotWidget()
        self.plot_widgets['status'].setTitle("Status Plot")
        self.plot_widgets['diameter'] = pg.PlotWidget()
        self.plot_widgets['fft'] = pg.PlotWidget()
        self.min_update_interval = min_update_interval
        self.last_update_time = None
        self.plot_dirty = False
        
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
    
    def process_plot_data(plot_data, fft_buffer_size=64):
        """
        Przetwarza surowe dane wykresu i zwraca słownik z przetworzonymi wynikami.
        
        Args:
            plot_data: Słownik zawierający surowe dane, np. 'x_history', 'lumps_history', 'diameter_history', etc.
            fft_buffer_size: Rozmiar bufora do obliczeń FFT.
        
        Returns:
            processed_data: Słownik z danymi gotowymi do aktualizacji wykresów.
        """
        start_time = time.perf_counter()
        processed_data = {}
        
        # Przetwarzanie wykresu statusowego
        if 'x_history' in plot_data and 'lumps_history' in plot_data and 'necks_history' in plot_data:
            processed_data['status_plot'] = {
                'x_vals': plot_data['x_history'],
                'lumps_vals': plot_data['lumps_history'],
                'necks_vals': plot_data['necks_history'],
                'batch_name': plot_data.get('batch_name', 'Unknown'),
                'current_x': plot_data.get('current_x', 0),
                'plc_sample_time': plot_data.get('plc_sample_time', 0)
            }
        
        # Przetwarzanie wykresu średnicy
        if 'diameter_history' in plot_data and 'diameter_x' in plot_data:
            processed_data['diameter_plot'] = {
                'x': plot_data['diameter_x'],
                'y': plot_data['diameter_history'],
                'current_x': plot_data.get('current_x', 0),
                'diameter_preset': plot_data.get('diameter_preset', 0),
                'plc_sample_time': plot_data.get('plc_sample_time', 0)
            }
        
        # Przetwarzanie FFT (najbardziej obciążające obliczeniowo)
        if 'diameter_history' in plot_data and len(plot_data['diameter_history']) > 0:
            # Konwersja do numpy array dla analizy FFT
            data = np.array(plot_data['diameter_history'][-fft_buffer_size:], dtype=np.float32)
            if data.size > 0:
                # Obliczenie FFT – zakładamy, że funkcja analyze_window_fft jest dostępna
                fft_result = analyze_window_fft(data)
                processed_data['fft_plot'] = {
                    'fft_data': np.abs(fft_result).tolist(),
                    'fft_buffer_size': fft_buffer_size
                }
        
        processed_data['processing_time'] = time.perf_counter() - start_time
        return processed_data
    


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
        
            sample_time_ms = plc_sample_time * 1000  # konwersja do ms
            plot_widget.setTitle(f"Last {len(x_history)} samples - Batch: {batch_name} - PLC: {sample_time_ms:.1f}ms")
            plot_widget.setLabel('bottom', "X-Coord [m]")
            plot_widget.setLabel('left', "Błędy w cyklu")
            
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
            plot_widget.plot(diameter_x, diameter_history, pen='g', name='Actual')
            
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
                plot_widget.setTitle(f"Avg Diameter - {sample_count} samples, {meters_covered:.1f}m - PLC: {sample_time_ms:.1f}ms")
            
            plot_widget.showGrid(x=True, y=True)   
    def update_fft_plot(self, diameter_history, fft_buffer_size=64):
        """
        Aktualizuje wykres analizy FFT średnicy przy użyciu PyQtGraph.
        
        Args:
            diameter_history: Lista wartości średnicy
            fft_buffer_size: Liczba próbek używanych do obliczenia FFT
        """
        if 'fft' not in self.plot_widgets:
            return
        plot_widget = self.plot_widgets['fft']
        plot_widget.clear()
        
        if len(diameter_history) > 0:
            # Konwersja do numpy array do analizy FFT
            diameter_array = np.array(diameter_history[-fft_buffer_size:], dtype=np.float32)
            
            if len(diameter_array) > 0:
                # Obliczenie FFT – zakładamy, że funkcja analyze_window_fft jest dostępna
                diameter_fft = analyze_window_fft(diameter_array)
                
                plot_widget.setTitle("Diameter FFT Analysis")
                # Rysujemy wykres FFT; domyślnie oś X to indeksy próbek
                plot_widget.plot(np.abs(diameter_fft), pen='g', name="FFT")
                plot_widget.setLabel('bottom', "Frequency")
                plot_widget.setLabel('left', "Magnitude")
                plot_widget.showGrid(x=True, y=True)
    

    def check_plot_process(self):
        """Since we're updating plots in the main thread, no separate plot process is used."""
        print("[PlotManager] Using main thread for plotting; no plot process to check or restart.")
        return False

        
    def update_all_plots(self, data_dict):
        """
        Główne wejście do aktualizacji wykresów z mechanizmem throttlingu,
        przystosowane do PyQtGraph.
        
        Args:
            data_dict: Słownik zawierający wszystkie dane potrzebne do rysowania.
        """
        now = time.time()
        if (self.last_update_time is None or (now - self.last_update_time) >= self.min_update_interval) and self.plot_dirty:
            try:
                # Aktualizacja odbywa się w głównym wątku – nie ma osobnego procesu
                self.plot_update_count += 1

                plc_sample_time = data_dict.get('plc_sample_time', 0)
                status_time = 0
                diameter_time = 0
                fft_time = 0

                # Aktualizacja wykresu średnicy (zawsze aktualizowany)
                if 'diameter' in self.plot_widgets:
                    start = time.perf_counter()
                    self.update_diameter_plot(
                        data_dict['diameter_x'],
                        data_dict['diameter_history'],
                        data_dict['current_x'],
                        data_dict.get('diameter_preset', 0),
                        plc_sample_time
                    )
                    diameter_time = time.perf_counter() - start

                # Aktualizacja wykresu statusu – aktualizujemy rzadziej przy wysokim poziomie throttle
                if 'status' in self.plot_widgets and (self.throttle_level < 3 or self.plot_update_count % 2 == 0):
                    start = time.perf_counter()
                    self.update_status_plot(
                        data_dict['x_history'], 
                        data_dict['lumps_history'], 
                        data_dict['necks_history'],
                        data_dict['current_x'],
                        data_dict['batch_name'],
                        plc_sample_time
                    )
                    status_time = time.perf_counter() - start

                # Aktualizacja wykresu FFT – tylko przy najniższym poziomie throttle
                if 'fft' in self.plot_widgets and self.throttle_level == 1:
                    start = time.perf_counter()
                    self.update_fft_plot(
                        data_dict['diameter_history'],
                        data_dict.get('fft_buffer_size', 64)
                    )
                    fft_time = time.perf_counter() - start

                # W PyQtGraph zmiany rysujemy bezpośrednio; opcjonalnie możemy wymusić odświeżenie widgetu
                for key, widget in self.plot_widgets.items():
                    if (key == 'diameter' or 
                        (key == 'status' and (self.throttle_level < 3 or self.plot_update_count % 2 == 0)) or
                        (key == 'fft' and self.throttle_level == 1)):
                        widget.repaint()  # Wymusza natychmiastowe odświeżenie

                self.plot_dirty = False
                self.last_update_time = now

            except Exception as e:
                print(f"[PlotManager] Error updating plots: {e}")

    def initialize_plots(self):
        # Configure each plot widget
        if self.plot_widgets['status']:
            self.plot_widgets['status'].setTitle("Status Plot")
        if self.plot_widgets['diameter']:
            self.plot_widgets['diameter'].setTitle("Diameter Plot")
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
