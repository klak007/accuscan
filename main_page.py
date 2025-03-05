from datetime import datetime
import db_helper
import plc_helper
import time
from db_helper import save_settings, save_settings_history

# Import new modules
from visualization import PlotManager
from data_processing import WindowProcessor, FastAcquisitionBuffer
from flaw_detection import FlawDetector

import pyqtgraph as pg
from PyQt5.QtWidgets import QFrame, QGridLayout, QVBoxLayout
from PyQt5.QtWidgets import QWidget, QGridLayout, QMessageBox, QSlider
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QSpacerItem, QSizePolicy
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QFrame, QLabel, QLineEdit, QPushButton, QGridLayout, QHBoxLayout
)
from PyQt5.QtCore import Qt

class MainPage(QWidget):
    """
    Główna strona aplikacji z:
    1. Górną belką na przyciski,
    2. Kolumna 0 (lewa) – batch, product, przycisk,
    3. Kolumna 1 (środkowa) – parametry symulacji,
    4. Kolumna 2 (prawa) – wykres, przyciski sterujące (Start/Stop/Kwituj).
    """
    def __init__(self, parent, controller, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.controller = controller

        # Utworzenie layoutu grid
        self.layout = QGridLayout(self)
        self.setLayout(self.layout)
        
        # Ustawiamy rozciąganie wierszy:
        # Wiersz 0: top bar, nie rozciąga się (stretch = 0)
        # Wiersz 1: pozostałe elementy, rozciąga się (stretch = 1)
        self.layout.setRowStretch(0, 0)
        self.layout.setRowStretch(1, 1)


        

        
        # Ustawiamy kolumny:
        # Kolumna 0 (lewa): minimalna szerokość 300, brak rozciągania (stretch = 0)
        # Kolumna 1 (środkowa): minimalna szerokość 300, brak rozciągania (stretch = 0)
        # Kolumna 2 (prawa): rozciąga się (stretch = 1)
        self.layout.setColumnStretch(0, 0)
        self.layout.setColumnStretch(1, 0)
        self.layout.setColumnStretch(2, 1)
        # Aby zapewnić minimalną szerokość, można ustawić to na widgetach w kolejnych metodach
        
        # Historie lumps/necks do wykresu
        self.lumps_history = []
        self.necks_history = []
        self.x_history = []
        self.MAX_POINTS = 1024  # Increased to 1024 samples
        self.display_range = 10  # ile „metrów” pokazywać na wykresie
        self.production_speed = 50
        self.last_update_time = None
        self.current_x = 0.0
        self.FFT_BUFFER_SIZE = 64
        self.diameter_history = []  # Values
        self.diameter_x = []        # X-coordinates for diameter values
        self.last_plot_update = None  # new attribute for plot update frequency
        self.plc_sample_time = 0.0  # Time taken to retrieve a sample from PLC

        # UI interaction state
        self.ui_busy = False  # Flag to indicate UI interaction is in progress
        self.last_save_time = 0  # Track last database save time
        self.save_in_progress = False  # Flag to prevent multiple simultaneous saves

        # Counters for flaws in the window
        self.flaw_lumps_count = 0  # Lumps in the current flaw window
        self.flaw_necks_count = 0  # Necks in the current flaw window
        self.flaw_lumps_coords = []  # Coordinates of lumps for flaw window tracking
        self.flaw_necks_coords = []  # Coordinates of necks for flaw window tracking

        # Performance optimization
        self.plot_update_interval = 1.0  # Update plots every 1 second
        self.last_plot_update = None

        # Additional threshold to control plot updates
        self.plot_dirty = False  # Set to True when data changes
        self.min_plot_interval = 0.8  # Minimum seconds between plot updates

        # Initialize the plot manager BEFORE creating the panels
        self.plot_manager = PlotManager(
            plot_widgets={
                'status': None,
                'diameter': None,
                'fft': None
            }, 
            min_update_interval=0.2  # Reduce interval for more responsive updates
        )
        print("[MainPage] Plot manager initialized for PyQtGraph")

        # Tworzenie poszczególnych części interfejsu
        self._create_top_bar()
        self._create_left_panel()
        self._create_middle_panel()
        self._create_right_panel()

        # Pasek u góry, wiersz=0, od kolumny 0 do 2 (czyli colSpan=3)
        self.layout.addWidget(self.top_bar, 0, 0, 1, 3)

        # Panel lewy: wiersz=1, kolumna=0
        self.layout.addWidget(self.left_panel, 1, 0)

        # Panel środkowy: wiersz=1, kolumna=1
        self.layout.addWidget(self.middle_panel, 1, 1)

        # Panel prawy: wiersz=1, kolumna=2
        self.layout.addWidget(self.right_panel, 1, 2)
        # Initialize new components after right panel is created
        self.window_processor = WindowProcessor(max_samples=self.MAX_POINTS)
        self.flaw_detector = FlawDetector(flaw_window_size=0.5)


    # ---------------------------------------------------------------------------------
    # 1. Górna belka nawigacji (row=0, col=0..2)
    # ---------------------------------------------------------------------------------
    def _create_top_bar(self):
        # Utwórz pasek górny jako QWidget z poziomym layoutem
        self.top_bar = QWidget(self)
        top_bar_layout = QHBoxLayout(self.top_bar)
        top_bar_layout.setContentsMargins(5, 5, 5, 0)
        top_bar_layout.setSpacing(5)
        
        # Przycisk "pomiary" z zielonym tłem
        self.btn_pomiary = QPushButton("pomiary", self.top_bar)
        self.btn_pomiary.setStyleSheet("background-color: green; color: white;")
        self.btn_pomiary.clicked.connect(self._on_pomiary_click)
        
        self.btn_nastawy = QPushButton("nastawy", self.top_bar)
        self.btn_nastawy.clicked.connect(lambda: self.controller.toggle_page("SettingsPage"))
        
        self.btn_historia = QPushButton("historia", self.top_bar)
        self.btn_historia.clicked.connect(self._on_historia_click)
        
        self.btn_accuscan = QPushButton("Accuscan", self.top_bar)
        self.btn_accuscan.clicked.connect(self._on_accuscan_click)
        
        # Dodaj przyciski po lewej stronie
        top_bar_layout.addWidget(self.btn_pomiary, 0, Qt.AlignLeft)
        top_bar_layout.addWidget(self.btn_nastawy, 0, Qt.AlignLeft)
        top_bar_layout.addWidget(self.btn_historia, 0, Qt.AlignLeft)
        top_bar_layout.addWidget(self.btn_accuscan, 0, Qt.AlignLeft)
        
        # Dodaj rozciągacz, aby następne elementy wypchnąć w prawo
        spacer = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        top_bar_layout.addItem(spacer)
        
        # Kontener dla przycisków Start/Stop/Kwituj
        self.control_frame = QWidget(self.top_bar)
        control_layout = QHBoxLayout(self.control_frame)
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.setSpacing(2)
        
        self.btn_start = QPushButton("Start", self.control_frame)
        self.btn_start.clicked.connect(self._on_start)
        
        self.btn_stop = QPushButton("Stop", self.control_frame)
        self.btn_stop.clicked.connect(self._on_stop)
        
        self.btn_ack = QPushButton("Kwituj", self.control_frame)
        self.btn_ack.clicked.connect(self._on_ack)
        
        control_layout.addWidget(self.btn_start)
        control_layout.addWidget(self.btn_stop)
        control_layout.addWidget(self.btn_ack)
        
        top_bar_layout.addWidget(self.control_frame, 0, Qt.AlignRight)
        
        # Przycisk Exit z czerwonym tłem, ustawiony po prawej stronie
        self.btn_exit = QPushButton("Exit", self.top_bar)
        self.btn_exit.setStyleSheet("background-color: red; color: white;")
        self.btn_exit.clicked.connect(self._on_exit_click)
        top_bar_layout.addWidget(self.btn_exit, 0, Qt.AlignRight)
        

    def _on_pomiary_click(self):
        print("[GUI] Kliknięto przycisk 'pomiary'.")

    def _on_nastawy_click(self):
        self.controller.show_settings_page()

    def _on_historia_click(self):
        print("[GUI] Kliknięto przycisk 'historia'.")

    def _on_accuscan_click(self):
        print("[GUI] Kliknięto przycisk 'Accuscan'.")

    def _on_exit_click(self):
        # Stop measurements if flags exist
        if hasattr(self.controller, "run_measurement_flag"):
            self.controller.run_measurement_flag.value = 0
        if hasattr(self.controller, "process_running_flag"):
            self.controller.process_running_flag.value = 0
        # Exit application
        self.controller.destroy()


    # ---------------------------------------------------------------------------------
    # 2. Lewa kolumna (row=1, col=0) – Batch, Product, itp.
    # ---------------------------------------------------------------------------------
    def _create_left_panel(self):
        # Utwórz lewy panel jako QFrame o stałej szerokości 400
        self.left_panel = QFrame(self)
        self.left_panel.setMinimumWidth(400)
        self.left_panel.setMaximumWidth(400)
        left_layout = QGridLayout(self.left_panel)
        self.left_panel.setLayout(left_layout)

        # Rząd 0: Etykieta "Batch"
        self.label_batch = QLabel("Batch", self.left_panel)
        left_layout.addWidget(self.label_batch, 0, 0, alignment=Qt.AlignLeft | Qt.AlignVCenter)

        # Rząd 1: Pole tekstowe dla batch
        self.entry_batch = QLineEdit(self.left_panel)
        self.entry_batch.setPlaceholderText("IADTX0000")
        self.entry_batch.setText("IADTX0000")
        left_layout.addWidget(self.entry_batch, 1, 0)
        # TODO: podpiąć focusInEvent / focusOutEvent, jeśli potrzebne

        # Rząd 2: Etykieta "Produkt"
        self.label_product = QLabel("Produkt", self.left_panel)
        left_layout.addWidget(self.label_product, 2, 0, alignment=Qt.AlignLeft | Qt.AlignVCenter)

        # Rząd 3: Pole tekstowe dla produktu
        self.entry_product = QLineEdit(self.left_panel)
        self.entry_product.setPlaceholderText("18X0600")
        self.entry_product.setText("18X0600")
        left_layout.addWidget(self.entry_product, 3, 0)
        # TODO: podpiąć focus eventy, jeśli wymagane

        # Rząd 4: Przycisk "Przykładowe nastawy"
        self.btn_typowy = QPushButton("Przykładowe nastawy", self.left_panel)
        self.btn_typowy.clicked.connect(self._on_typowy_click)
        left_layout.addWidget(self.btn_typowy, 4, 0)

        # Rząd 5: Przycisk "Zapisz nastawy"
        self.btn_save_settings = QPushButton("Zapisz nastawy", self.left_panel)
        self.btn_save_settings.clicked.connect(self._save_settings)
        left_layout.addWidget(self.btn_save_settings, 5, 0)

        # =============================
        # NOWE POLE NASTAW DLA RECEPTURY
        # =============================
        row_start = 8  # kolejne elementy zaczynają się od rzędu 8

        # Rząd row_start: Etykieta "Nazwa receptury:"
        self.label_recipe_name = QLabel("Nazwa receptury:", self.left_panel)
        left_layout.addWidget(self.label_recipe_name, row_start, 0, alignment=Qt.AlignLeft | Qt.AlignVCenter)

        # Rząd row_start+1: Pole tekstowe dla nazwy receptury
        self.entry_recipe_name = QLineEdit(self.left_panel)
        self.entry_recipe_name.setPlaceholderText("Recipe X")
        left_layout.addWidget(self.entry_recipe_name, row_start+1, 0)

        # Rząd row_start+2: Etykieta "Średnica docelowa [mm]:"
        self.label_diameter_setpoint = QLabel("Średnica docelowa [mm]:", self.left_panel)
        left_layout.addWidget(self.label_diameter_setpoint, row_start+2, 0, alignment=Qt.AlignLeft | Qt.AlignVCenter)

        # Rząd row_start+3: Ramka dla przycisków regulujących średnicę i pole wejściowe
        diameter_frame = QFrame(self.left_panel)
        diameter_layout = QHBoxLayout(diameter_frame)
        diameter_frame.setLayout(diameter_layout)
        left_layout.addWidget(diameter_frame, row_start+3, 0, alignment=Qt.AlignLeft)

        self.btn_diam_decrease_05 = QPushButton("--", diameter_frame)
        self.btn_diam_decrease_05.setFixedWidth(30)
        self.btn_diam_decrease_05.clicked.connect(lambda: self._adjust_diameter(-0.5))
        diameter_layout.addWidget(self.btn_diam_decrease_05)

        self.btn_diam_decrease_01 = QPushButton("-", diameter_frame)
        self.btn_diam_decrease_01.setFixedWidth(30)
        self.btn_diam_decrease_01.clicked.connect(lambda: self._adjust_diameter(-0.1))
        diameter_layout.addWidget(self.btn_diam_decrease_01)

        self.entry_diameter_setpoint = QLineEdit(diameter_frame)
        self.entry_diameter_setpoint.setPlaceholderText("18.0")
        self.entry_diameter_setpoint.setFixedWidth(80)
        diameter_layout.addWidget(self.entry_diameter_setpoint)

        self.btn_diam_increase_01 = QPushButton("+", diameter_frame)
        self.btn_diam_increase_01.setFixedWidth(30)
        self.btn_diam_increase_01.clicked.connect(lambda: self._adjust_diameter(0.1))
        diameter_layout.addWidget(self.btn_diam_increase_01)

        self.btn_diam_increase_05 = QPushButton("++", diameter_frame)
        self.btn_diam_increase_05.setFixedWidth(30)
        self.btn_diam_increase_05.clicked.connect(lambda: self._adjust_diameter(0.5))
        diameter_layout.addWidget(self.btn_diam_increase_05)

        # Rząd row_start+4: Etykieta "Gorna granica (roznica od dAvg) [mm]:"
        self.label_tolerance_plus = QLabel("Gorna granica (roznica od dAvg) [mm]:", self.left_panel)
        left_layout.addWidget(self.label_tolerance_plus, row_start+4, 0, alignment=Qt.AlignLeft | Qt.AlignVCenter)

        # Rząd row_start+5: Ramka plus
        plus_frame = QFrame(self.left_panel)
        plus_layout = QHBoxLayout(plus_frame)
        plus_frame.setLayout(plus_layout)
        left_layout.addWidget(plus_frame, row_start+5, 0, alignment=Qt.AlignLeft)

        self.btn_tolerance_plus_dec_05 = QPushButton("--", plus_frame)
        self.btn_tolerance_plus_dec_05.setFixedWidth(30)
        self.btn_tolerance_plus_dec_05.clicked.connect(lambda: self._adjust_tolerance_plus(-0.5))
        plus_layout.addWidget(self.btn_tolerance_plus_dec_05)

        self.btn_tolerance_plus_dec_01 = QPushButton("-", plus_frame)
        self.btn_tolerance_plus_dec_01.setFixedWidth(30)
        self.btn_tolerance_plus_dec_01.clicked.connect(lambda: self._adjust_tolerance_plus(-0.1))
        plus_layout.addWidget(self.btn_tolerance_plus_dec_01)

        self.entry_tolerance_plus = QLineEdit(plus_frame)
        self.entry_tolerance_plus.setPlaceholderText("0.5")
        self.entry_tolerance_plus.setFixedWidth(80)
        plus_layout.addWidget(self.entry_tolerance_plus)

        self.btn_tolerance_plus_inc_01 = QPushButton("+", plus_frame)
        self.btn_tolerance_plus_inc_01.setFixedWidth(30)
        self.btn_tolerance_plus_inc_01.clicked.connect(lambda: self._adjust_tolerance_plus(0.1))
        plus_layout.addWidget(self.btn_tolerance_plus_inc_01)

        self.btn_tolerance_plus_inc_05 = QPushButton("++", plus_frame)
        self.btn_tolerance_plus_inc_05.setFixedWidth(30)
        self.btn_tolerance_plus_inc_05.clicked.connect(lambda: self._adjust_tolerance_plus(0.5))
        plus_layout.addWidget(self.btn_tolerance_plus_inc_05)

        # Rząd row_start+6: Etykieta "Dolna granica  (roznica od dAvg) [mm]:"
        self.label_tolerance_minus = QLabel("Dolna granica (roznica od dAvg) [mm]:", self.left_panel)
        left_layout.addWidget(self.label_tolerance_minus, row_start+6, 0, alignment=Qt.AlignLeft | Qt.AlignVCenter)

        # Rząd row_start+7: Ramka minus
        minus_frame = QFrame(self.left_panel)
        minus_layout = QHBoxLayout(minus_frame)
        minus_frame.setLayout(minus_layout)
        left_layout.addWidget(minus_frame, row_start+7, 0, alignment=Qt.AlignLeft)

        self.btn_tolerance_minus_dec_05 = QPushButton("--", minus_frame)
        self.btn_tolerance_minus_dec_05.setFixedWidth(30)
        self.btn_tolerance_minus_dec_05.clicked.connect(lambda: self._adjust_tolerance_minus(-0.5))
        minus_layout.addWidget(self.btn_tolerance_minus_dec_05)

        self.btn_tolerance_minus_dec_01 = QPushButton("-", minus_frame)
        self.btn_tolerance_minus_dec_01.setFixedWidth(30)
        self.btn_tolerance_minus_dec_01.clicked.connect(lambda: self._adjust_tolerance_minus(-0.1))
        minus_layout.addWidget(self.btn_tolerance_minus_dec_01)

        self.entry_tolerance_minus = QLineEdit(minus_frame)
        self.entry_tolerance_minus.setPlaceholderText("0.5")
        self.entry_tolerance_minus.setFixedWidth(80)
        minus_layout.addWidget(self.entry_tolerance_minus)

        self.btn_tolerance_minus_inc_01 = QPushButton("+", minus_frame)
        self.btn_tolerance_minus_inc_01.setFixedWidth(30)
        self.btn_tolerance_minus_inc_01.clicked.connect(lambda: self._adjust_tolerance_minus(0.1))
        minus_layout.addWidget(self.btn_tolerance_minus_inc_01)

        self.btn_tolerance_minus_inc_05 = QPushButton("++", minus_frame)
        self.btn_tolerance_minus_inc_05.setFixedWidth(30)
        self.btn_tolerance_minus_inc_05.clicked.connect(lambda: self._adjust_tolerance_minus(0.5))
        minus_layout.addWidget(self.btn_tolerance_minus_inc_05)

        # Rząd row_start+8: Etykieta "Próg lumps [mm]:"
        self.label_lump_threshold = QLabel("Próg lumps [mm]:", self.left_panel)
        left_layout.addWidget(self.label_lump_threshold, row_start+8, 0, alignment=Qt.AlignLeft | Qt.AlignVCenter)

        # Rząd row_start+9: Ramka dla ustawień progu lumps
        lumps_threshold_frame = QFrame(self.left_panel)
        lumps_threshold_layout = QHBoxLayout(lumps_threshold_frame)
        lumps_threshold_frame.setLayout(lumps_threshold_layout)
        left_layout.addWidget(lumps_threshold_frame, row_start+9, 0, alignment=Qt.AlignLeft)

        self.btn_lump_thres_dec_05 = QPushButton("--", lumps_threshold_frame)
        self.btn_lump_thres_dec_05.setFixedWidth(30)
        self.btn_lump_thres_dec_05.clicked.connect(lambda: self._adjust_lump_threshold(-0.5))
        lumps_threshold_layout.addWidget(self.btn_lump_thres_dec_05)

        self.btn_lump_thres_dec_01 = QPushButton("-", lumps_threshold_frame)
        self.btn_lump_thres_dec_01.setFixedWidth(30)
        self.btn_lump_thres_dec_01.clicked.connect(lambda: self._adjust_lump_threshold(-0.1))
        lumps_threshold_layout.addWidget(self.btn_lump_thres_dec_01)

        self.entry_lump_threshold = QLineEdit(lumps_threshold_frame)
        self.entry_lump_threshold.setPlaceholderText("0.3")
        self.entry_lump_threshold.setFixedWidth(80)
        lumps_threshold_layout.addWidget(self.entry_lump_threshold)

        self.btn_lump_thres_inc_01 = QPushButton("+", lumps_threshold_frame)
        self.btn_lump_thres_inc_01.setFixedWidth(30)
        self.btn_lump_thres_inc_01.clicked.connect(lambda: self._adjust_lump_threshold(0.1))
        lumps_threshold_layout.addWidget(self.btn_lump_thres_inc_01)

        self.btn_lump_thres_inc_05 = QPushButton("++", lumps_threshold_frame)
        self.btn_lump_thres_inc_05.setFixedWidth(30)
        self.btn_lump_thres_inc_05.clicked.connect(lambda: self._adjust_lump_threshold(0.5))
        lumps_threshold_layout.addWidget(self.btn_lump_thres_inc_05)

        # Rząd row_start+10: Etykieta "Próg necks [mm]:"
        self.label_neck_threshold = QLabel("Próg necks [mm]:", self.left_panel)
        left_layout.addWidget(self.label_neck_threshold, row_start+10, 0, alignment=Qt.AlignLeft | Qt.AlignVCenter)

        # Rząd row_start+11: Ramka dla ustawień progu necks
        necks_threshold_frame = QFrame(self.left_panel)
        necks_threshold_layout = QHBoxLayout(necks_threshold_frame)
        necks_threshold_frame.setLayout(necks_threshold_layout)
        left_layout.addWidget(necks_threshold_frame, row_start+11, 0, alignment=Qt.AlignLeft)

        self.btn_neck_thres_dec_05 = QPushButton("--", necks_threshold_frame)
        self.btn_neck_thres_dec_05.setFixedWidth(30)
        self.btn_neck_thres_dec_05.clicked.connect(lambda: self._adjust_neck_threshold(-0.5))
        necks_threshold_layout.addWidget(self.btn_neck_thres_dec_05)

        self.btn_neck_thres_dec_01 = QPushButton("-", necks_threshold_frame)
        self.btn_neck_thres_dec_01.setFixedWidth(30)
        self.btn_neck_thres_dec_01.clicked.connect(lambda: self._adjust_neck_threshold(-0.1))
        necks_threshold_layout.addWidget(self.btn_neck_thres_dec_01)

        self.entry_neck_threshold = QLineEdit(necks_threshold_frame)
        self.entry_neck_threshold.setPlaceholderText("0.3")
        self.entry_neck_threshold.setFixedWidth(80)
        necks_threshold_layout.addWidget(self.entry_neck_threshold)

        self.btn_neck_thres_inc_01 = QPushButton("+", necks_threshold_frame)
        self.btn_neck_thres_inc_01.setFixedWidth(30)
        self.btn_neck_thres_inc_01.clicked.connect(lambda: self._adjust_neck_threshold(0.1))
        necks_threshold_layout.addWidget(self.btn_neck_thres_inc_01)

        self.btn_neck_thres_inc_05 = QPushButton("++", necks_threshold_frame)
        self.btn_neck_thres_inc_05.setFixedWidth(30)
        self.btn_neck_thres_inc_05.clicked.connect(lambda: self._adjust_neck_threshold(0.5))
        necks_threshold_layout.addWidget(self.btn_neck_thres_inc_05)

        # Rząd row_start+12: Etykieta "Flaw window [m]:"
        self.label_flaw_window = QLabel("Flaw window [m]:", self.left_panel)
        left_layout.addWidget(self.label_flaw_window, row_start+12, 0, alignment=Qt.AlignLeft | Qt.AlignVCenter)

        # Rząd row_start+13: Pole tekstowe dla flaw window
        self.entry_flaw_window = QLineEdit(self.left_panel)
        self.entry_flaw_window.setPlaceholderText("0.5")
        self.entry_flaw_window.setFixedWidth(80)
        left_layout.addWidget(self.entry_flaw_window, row_start+13, 0)

        # Rząd row_start+14: Etykieta "Max lumps in flaw window:"
        self.label_max_lumps = QLabel("Max lumps in flaw window:", self.left_panel)
        left_layout.addWidget(self.label_max_lumps, row_start+14, 0, alignment=Qt.AlignLeft | Qt.AlignVCenter)

        # Rząd row_start+15: Ramka dla max lumps
        max_lumps_frame = QFrame(self.left_panel)
        max_lumps_layout = QHBoxLayout(max_lumps_frame)
        max_lumps_frame.setLayout(max_lumps_layout)
        left_layout.addWidget(max_lumps_frame, row_start+15, 0, alignment=Qt.AlignLeft)

        self.btn_max_lumps_dec = QPushButton("-", max_lumps_frame)
        self.btn_max_lumps_dec.setFixedWidth(30)
        self.btn_max_lumps_dec.clicked.connect(lambda: self._adjust_max_lumps(-1))
        max_lumps_layout.addWidget(self.btn_max_lumps_dec)

        self.entry_max_lumps = QLineEdit(max_lumps_frame)
        self.entry_max_lumps.setPlaceholderText("3")
        self.entry_max_lumps.setFixedWidth(80)
        max_lumps_layout.addWidget(self.entry_max_lumps)

        self.btn_max_lumps_inc = QPushButton("+", max_lumps_frame)
        self.btn_max_lumps_inc.setFixedWidth(30)
        self.btn_max_lumps_inc.clicked.connect(lambda: self._adjust_max_lumps(1))
        max_lumps_layout.addWidget(self.btn_max_lumps_inc)

        # Rząd row_start+16: Etykieta "Max necks in flaw window:"
        self.label_max_necks = QLabel("Max necks in flaw window:", self.left_panel)
        left_layout.addWidget(self.label_max_necks, row_start+16, 0, alignment=Qt.AlignLeft | Qt.AlignVCenter)

        # Rząd row_start+17: Ramka dla max necks
        max_necks_frame = QFrame(self.left_panel)
        max_necks_layout = QHBoxLayout(max_necks_frame)
        max_necks_frame.setLayout(max_necks_layout)
        left_layout.addWidget(max_necks_frame, row_start+17, 0, alignment=Qt.AlignLeft)

        self.btn_max_necks_dec = QPushButton("-", max_necks_frame)
        self.btn_max_necks_dec.setFixedWidth(30)
        self.btn_max_necks_dec.clicked.connect(lambda: self._adjust_max_necks(-1))
        max_necks_layout.addWidget(self.btn_max_necks_dec)

        self.entry_max_necks = QLineEdit(max_necks_frame)
        self.entry_max_necks.setPlaceholderText("3")
        self.entry_max_necks.setFixedWidth(80)
        max_necks_layout.addWidget(self.entry_max_necks)

        self.btn_max_necks_inc = QPushButton("+", max_necks_frame)
        self.btn_max_necks_inc.setFixedWidth(30)
        self.btn_max_necks_inc.clicked.connect(lambda: self._adjust_max_necks(1))
        max_necks_layout.addWidget(self.btn_max_necks_inc)

    def _adjust_diameter(self, delta: float):
        val_str = self.entry_diameter_setpoint.text() or "0"
        try:
            val = float(val_str)
        except ValueError:
            val = 0.0
        new_val = val + delta
        self.entry_diameter_setpoint.clear()
        self.entry_diameter_setpoint.setText(f"{new_val:.1f}")

    def _adjust_tolerance_plus(self, delta: float):
        val_str = self.entry_tolerance_plus.text() or "0"
        try:
            val = float(val_str)
        except ValueError:
            val = 0.0
        new_val = val + delta
        self.entry_tolerance_plus.clear()
        self.entry_tolerance_plus.setText(f"{new_val:.1f}")

    def _adjust_tolerance_minus(self, delta: float):
        val_str = self.entry_tolerance_minus.text() or "0"
        try:
            val = float(val_str)
        except ValueError:
            val = 0.0
        new_val = val + delta
        self.entry_tolerance_minus.clear()
        self.entry_tolerance_minus.setText(f"{new_val:.1f}")

    def _adjust_lump_threshold(self, delta: float):
        val_str = self.entry_lump_threshold.text() or "0"
        try:
            val = float(val_str)
        except ValueError:
            val = 0.0
        new_val = val + delta
        self.entry_lump_threshold.clear()
        self.entry_lump_threshold.setText(f"{new_val:.1f}")

    def _adjust_neck_threshold(self, delta: float):
        val_str = self.entry_neck_threshold.text() or "0"
        try:
            val = float(val_str)
        except ValueError:
            val = 0.0
        new_val = val + delta
        self.entry_neck_threshold.clear()
        self.entry_neck_threshold.setText(f"{new_val:.1f}")

    def _adjust_max_lumps(self, delta: int):
        """Adjust the max lumps in flaw window value"""
        val_str = self.entry_max_lumps.text() or "0"
        try:
            val = int(val_str)
        except ValueError:
            val = 0
        new_val = max(0, val + delta)  # Ensure the value is not negative
        self.entry_max_lumps.clear()
        self.entry_max_lumps.setText(f"{new_val}")

    def _adjust_max_necks(self, delta: int):
        """Adjust the max necks in flaw window value"""
        val_str = self.entry_max_necks.text() or "0"
        try:
            val = int(val_str)
        except ValueError:
            val = 0
        new_val = max(0, val + delta)  # Ensure the value is not negative
        self.entry_max_necks.clear()
        self.entry_max_necks.setText(f"{new_val}")

    def _save_settings(self):
        """
        Zczytuje wartości z pól tekstowych i zapisuje do bazy (settings + settings_register),
        a następnie wysyła parametry do PLC asynchronicznie.
        """
        # 1. Zczytaj wartości z pól
        recipe_name = self.entry_recipe_name.text() or ""
        diameter_setpoint_str = self.entry_diameter_setpoint.text() or "18.0"
        tolerance_plus_str = self.entry_tolerance_plus.text() or "0.5"
        tolerance_minus_str = self.entry_tolerance_minus.text() or "0.5"
        lump_threshold_str = self.entry_lump_threshold.text() or "0.3"
        neck_threshold_str = self.entry_neck_threshold.text() or "0.3"
        flaw_window_str = self.entry_flaw_window.text() or "2.0"
        max_lumps_str = self.entry_max_lumps.text() or "3"
        max_necks_str = self.entry_max_necks.text() or "3"

        # Konwersje na float lub int
        try:
            diameter_setpoint = float(diameter_setpoint_str)
            tolerance_plus = float(tolerance_plus_str)
            tolerance_minus = float(tolerance_minus_str)
            lump_threshold = float(lump_threshold_str)
            neck_threshold = float(neck_threshold_str)
            flaw_window = float(flaw_window_str)
            max_lumps = int(max_lumps_str)
            max_necks = int(max_necks_str)
        except ValueError:
            QMessageBox.critical(self, "Błąd", "Błędne dane wejściowe.")
            return

        # 2. Zbuduj słownik do zapisu w bazie (tak jak wcześniej)
        settings_data = {
            "recipe_name": recipe_name,
            "product_nr": self.entry_product.text() or "",
            "preset_diameter": diameter_setpoint,
            "diameter_over_tol": tolerance_plus,
            "diameter_under_tol": tolerance_minus,
            "lump_threshold": lump_threshold,
            "neck_threshold": neck_threshold,
            "flaw_window": flaw_window,
            "max_lumps_in_flaw_window": max_lumps,
            "max_necks_in_flaw_window": max_necks,
            "diameter_window": 0.0,
            "diameter_std_dev": 0.0,
            "num_scans": 128,
            "diameter_histeresis": 0.0,
            "lump_histeresis": 0.0,
            "neck_histeresis": 0.0,
        }

        # 3. Zapis do bazy
        try:
            settings_id = save_settings(self.controller.db_params, settings_data)
            print("[GUI] Wysłano nowe nastawy do DB.")
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie udało się zapisać ustawień do DB: {str(e)}")
            return

        # 4. Wysyłanie komendy do PLC asynchronicznie poprzez kolejkę:
        write_cmd = {
            "command": "write_settings",
            "params": {
                "db_number": 2,
                "lump_threshold": lump_threshold,
                "neck_threshold": neck_threshold,
                "flaw_preset_diameter": diameter_setpoint,
                "upper_tol": tolerance_plus,
                "under_tol": tolerance_minus
                # Nie przekazujemy tu dodatkowych parametrów, bo reset jest cykliczny
            }
        }
        try:
            self.controller.plc_write_queue.put_nowait(write_cmd)
            print("[GUI] Komenda zapisu nastaw do PLC wysłana asynchronicznie.")
        except Exception as e:
            print(f"[GUI] Błąd przy wysyłaniu komendy do PLC: {e}")



    def _on_speed_change(self, value: float):
        self.production_speed = float(value)
        self.speed_label.setText(f"Speed: {self.production_speed:.1f}")

    def _on_entry_focus(self, event=None):
        """Handler for entry field focus - marks UI as busy to reduce processing"""
        # Signal to data receiver that UI might be busy
        self.ui_busy = True
        # This method intentionally does minimal work to avoid blocking
        
    def _on_entry_unfocus(self, event=None):
        """Handler for entry field unfocus - releases UI busy flag"""
        # Use QTimer.singleShot instead of after() to delay the UI busy flag reset
        QTimer.singleShot(100, self._release_ui_busy)
    
    def _release_ui_busy(self):
        """Release the UI busy flag after all pending operations complete"""
        self.ui_busy = False
        
    def get_batch_name(self):
        return self.entry_batch.text() or "XABC1566"
        
    def get_product_name(self):
        return self.entry_product.text() or "18X0600"
        
    def get_max_lumps(self):
        """Safely get the max lumps setting"""
        try:
            return int(self.entry_max_lumps.text() or "30")
        except (ValueError, AttributeError):
            return 30
            
    def get_max_necks(self):
        """Safely get the max necks setting"""
        try:
            return int(self.entry_max_necks.text() or "7")
        except (ValueError, AttributeError):
            return 7

    def _on_typowy_click(self):
        """Set example settings with batch UI update to avoid blocking data processing"""
        # First ensure measurement continues without blocking
        if hasattr(self.controller, 'run_measurement_flag'):
            self.controller.run_measurement_flag.value = 1
            
        # Signal that UI is busy to reduce impact on acquisition
        self.ui_busy = True
            
        # Use QTimer.singleShot instead of after() to schedule UI updates in the next idle cycle
        def update_ui_fields():
            # Get current date/time string
            import datetime
            now = datetime.datetime.now()
            date_time_str = f"{now.day:02d}_{now.month:02d}_{now.hour:02d}_{now.minute:02d}"
            
            # Update entry fields - in PyQt we directly set text instead of using StringVars
            self.entry_batch.setText(f"btch_{date_time_str}")
            self.entry_product.setText(f"prdct_{date_time_str}")
            
            # Prepare all values first (batch operations) for other fields
            field_values = {
                "entry_recipe_name": f"recipe_{date_time_str}",
                "entry_diameter_setpoint": "39",
                "entry_tolerance_plus": "0.5",
                "entry_tolerance_minus": "0.5",
                "entry_lump_threshold": "0.1",
                "entry_neck_threshold": "0.1",
                "entry_flaw_window": "0.5",
                "entry_max_lumps": "30",
                "entry_max_necks": "7",
                "speed_fluct_entry": "2.0"
            }
            
            # Update all fields in a single batch to minimize UI processing
            for field_name, value in field_values.items():
                if hasattr(self, field_name):
                    field = getattr(self, field_name)
                    field.clear()
                    field.setText(value)
            
            print("[GUI] Example settings applied without blocking")
            
            # Release UI busy flag after all operations complete
            QTimer.singleShot(100, self._release_ui_busy)
        
        # Schedule the UI update for the next idle cycle
        QTimer.singleShot(10, update_ui_fields)
        
        # Immediately return to avoid blocking
        return

    # ---------------------------------------------------------------------------------
    # 3. Środkowa kolumna (row=1, col=1) – parametry symulacji
    # ---------------------------------------------------------------------------------
    def _create_middle_panel(self):
        # Utwórz panel środkowy o minimalnej szerokości 1200
        self.middle_panel = QFrame(self)
        self.middle_panel.setMinimumWidth(400)
        self.middle_panel.setMaximumWidth(400)
        middle_layout = QGridLayout(self.middle_panel)
        self.middle_panel.setLayout(middle_layout)
        middle_layout.setColumnStretch(0, 1)  # Jedna kolumna, rozciągnięta

        # --------------------------
        # Ramka odczytów (readings_frame)
        # --------------------------
        self.readings_frame = QFrame(self.middle_panel)
        readings_layout = QVBoxLayout(self.readings_frame)
        self.readings_frame.setLayout(readings_layout)
        middle_layout.addWidget(self.readings_frame, 0, 0, 1, 1, Qt.AlignTop)

        # Dodaj etykiety odczytów (wszystkie ułożone pionowo)
        self.label_d1 = QLabel("D1 [mm]: --", self.readings_frame)
        self.label_d2 = QLabel("D2 [mm]: --", self.readings_frame)
        self.label_d3 = QLabel("D3 [mm]: --", self.readings_frame)
        self.label_d4 = QLabel("D4 [mm]: --", self.readings_frame)
        self.label_davg = QLabel("dAVG [mm]: --", self.readings_frame)
        self.label_dmin = QLabel("Dmin [mm]: --", self.readings_frame)
        self.label_dmax = QLabel("Dmax [mm]: --", self.readings_frame)
        self.label_dsd = QLabel("dSD [mm]: --", self.readings_frame)
        self.label_dov = QLabel("dOV [%]: --", self.readings_frame)
        self.label_xcoord = QLabel("xCoord [m]: --", self.readings_frame)
        self.label_speed = QLabel("Speed [m/min]: --", self.readings_frame)
        
        for lbl in [self.label_d1, self.label_d2, self.label_d3, self.label_d4,
                    self.label_davg, self.label_dmin, self.label_dmax, self.label_dsd,
                    self.label_dov, self.label_xcoord, self.label_speed]:
            readings_layout.addWidget(lbl)

        # Wskaźniki: Lump, Neck, Diameter i ich liczniki
        self.label_lump_indicator = QLabel("Lump: Off", self.readings_frame)
        readings_layout.addWidget(self.label_lump_indicator)
        self.lumps_count_label = QLabel("Count: 0", self.readings_frame)
        readings_layout.addWidget(self.lumps_count_label)

        self.label_neck_indicator = QLabel("Neck: Off", self.readings_frame)
        readings_layout.addWidget(self.label_neck_indicator)
        self.necks_count_label = QLabel("Count: 0", self.readings_frame)
        readings_layout.addWidget(self.necks_count_label)

        self.label_diameter_indicator = QLabel("Diameter: OK", self.readings_frame)
        readings_layout.addWidget(self.label_diameter_indicator)
        self.diameter_deviation_label = QLabel("Dev: 0.00 mm", self.readings_frame)
        readings_layout.addWidget(self.diameter_deviation_label)

        # --------------------------
        # Kontrola prędkości produkcji
        # --------------------------
        self.speed_control_frame = QFrame(self.readings_frame)
        speed_control_layout = QVBoxLayout(self.speed_control_frame)
        self.speed_control_frame.setLayout(speed_control_layout)
        readings_layout.addWidget(self.speed_control_frame)

        # Etykieta prędkości produkcji
        self.prod_speed_label = QLabel("Production Speed [m/min]:", self.speed_control_frame)
        speed_control_layout.addWidget(self.prod_speed_label)

        # Ramka dla slidera prędkości
        slider_frame = QFrame(self.speed_control_frame)
        slider_layout = QHBoxLayout(slider_frame)
        slider_frame.setLayout(slider_layout)
        speed_control_layout.addWidget(slider_frame)

        self.prod_speed_slider = QSlider(Qt.Horizontal, slider_frame)
        self.prod_speed_slider.setRange(0, 100)
        self.prod_speed_slider.setValue(self.production_speed)
        self.prod_speed_slider.valueChanged.connect(self._on_prod_speed_change)
        slider_layout.addWidget(self.prod_speed_slider)

        self.prod_speed_value = QLabel(f"{self.production_speed:.1f}", slider_frame)
        slider_layout.addWidget(self.prod_speed_value)

        # Ramka dla ustawienia fluktuacji prędkości
        fluct_frame = QFrame(self.speed_control_frame)
        fluct_layout = QHBoxLayout(fluct_frame)
        fluct_frame.setLayout(fluct_layout)
        speed_control_layout.addWidget(fluct_frame)

        self.fluct_label = QLabel("Speed Fluctuation (%):", fluct_frame)
        fluct_layout.addWidget(self.fluct_label)

        self.speed_fluct_entry = QLineEdit(fluct_frame)
        self.speed_fluct_entry.setFixedWidth(50)
        self.speed_fluct_entry.setText("2.0")  # Domyślnie 2%
        fluct_layout.addWidget(self.speed_fluct_entry)

        # Po zakończeniu konfiguracji, self.middle_panel powinna zostać dodana do głównego layoutu
        # (np. przez self.layout.addWidget(self.middle_panel) w konstruktorze)


    # ---------------------------------------------------------------------------------
    # 4. Prawa kolumna (row=1, col=2) – Wykres 
    # ---------------------------------------------------------------------------------
    def _create_right_panel(self):
        # Utwórz prawy panel jako QFrame i ustaw layout grid
        self.right_panel = QFrame(self)
        self.right_panel.setMinimumWidth(400)
        self.right_panel.setMaximumWidth(800)
        right_layout = QGridLayout(self.right_panel)
        self.right_panel.setLayout(right_layout)
        right_layout.setContentsMargins(10, 10, 10, 10)
        # max width to 800, min width to 400
        
        
        # Ustawienie gridu:
        # Rząd 0 – przyciski (jeśli będą), rzędy 1-3 – wykresy
        right_layout.setRowStretch(0, 0)  # przyciski (opcjonalnie)
        right_layout.setRowStretch(1, 1)  # status plot
        right_layout.setRowStretch(2, 1)  # diameter plot
        right_layout.setRowStretch(3, 1)  # FFT plot
        right_layout.setColumnStretch(0, 1)

        # -----------------------
        # Status plot – row 1
        # -----------------------
        self.plot_frame = QFrame(self.right_panel)
        plot_frame_layout = QVBoxLayout(self.plot_frame)
        self.plot_frame.setLayout(plot_frame_layout)
        right_layout.addWidget(self.plot_frame, 1, 0)
        
        self.status_plot = pg.PlotWidget(title="Lumps/Necks vs X-Coord", parent=self.plot_frame)
        self.status_plot.setLabel('left', "Status")
        self.status_plot.setLabel('bottom', "X-Coord")
        self.status_plot.setYRange(0, 2.1)
        self.status_plot.showGrid(x=False, y=False)
        plot_frame_layout.addWidget(self.status_plot)

        # -------------------------------
        # Diameter plot – row 2
        # -------------------------------
        self.diameter_frame = QFrame(self.right_panel)
        diameter_frame_layout = QVBoxLayout(self.diameter_frame)
        self.diameter_frame.setLayout(diameter_frame_layout)
        right_layout.addWidget(self.diameter_frame, 2, 0)
        
        self.diameter_plot = pg.PlotWidget(title="Average Diameter History", parent=self.diameter_frame)
        self.diameter_plot.setLabel('left', "Diameter [mm]")
        self.diameter_plot.setLabel('bottom', "Sample")
        self.diameter_plot.showGrid(x=True, y=True)
        diameter_frame_layout.addWidget(self.diameter_plot)
        
        # ---------------------------
        # FFT plot – row 3
        # ---------------------------
        self.fft_frame = QFrame(self.right_panel)
        fft_frame_layout = QVBoxLayout(self.fft_frame)
        self.fft_frame.setLayout(fft_frame_layout)
        right_layout.addWidget(self.fft_frame, 3, 0)
        
        self.fft_plot = pg.PlotWidget(title="FFT Analysis", parent=self.fft_frame)
        self.fft_plot.setLabel('left', "Magnitude")
        self.fft_plot.setLabel('bottom', "Frequency")
        self.fft_plot.showGrid(x=True, y=True)
        fft_frame_layout.addWidget(self.fft_plot)

        self.plot_manager.plot_widgets['status'] = self.status_plot
        self.plot_manager.plot_widgets['diameter'] = self.diameter_plot
        self.plot_manager.plot_widgets['fft'] = self.fft_plot

        self.plot_manager.initialize_plots()

    def _on_start(self):
        print("[GUI] Start pressed!")
        if hasattr(self.controller, "run_measurement_flag"):
            self.controller.run_measurement_flag.value = True
        if hasattr(self.controller, "process_running_flag"):
            self.controller.process_running_flag.value = True

        self.controller.run_measurement = True

        # Wysyłamy komendę do PLC writer
        try:
            # Przygotowujemy słownik komendy resetu.
            # Nazwa komendy to np. "write_reset".
            # Parametry: ustaw resetujące bity na True.
            reset_cmd = {
                "command": "write_reset",
                "params": {
                    "db_number": 2,
                    "zl": True, 
                    "zn": True, 
                    "zf": True, 
                    "zt": False,
                    # Pozostałe parametry nie są potrzebne – mogą być None albo pominięte,
                    # bo cykliczny reset z tą częścią wykonuje się w workerze.
                }
            }
            # Wysyłamy komendę do kolejki PLC writer.
            self.controller.plc_write_queue.put_nowait(reset_cmd)
            print("[GUI] Initial reset command sent to PLC via queue.")

            # Opcjonalnie – wyślij komendę czyszczącą (clear reset bits) po 100ms.
            def clear_reset():
                clear_cmd = {
                    "command": "write_reset",
                    "params": {
                        "db_number": 2,
                        "zl": False, 
                        "zn": False, 
                        "zf": False, 
                        "zt": False
                    }
                }
                self.controller.plc_write_queue.put_nowait(clear_cmd)
                print("[GUI] Clear reset command sent to PLC via queue.")
            QTimer.singleShot(100, clear_reset)
        except Exception as e:
            print(f"[GUI] Error sending reset command: {e}")
        
        # Ustaw flagę pomiaru, aby rozpocząć akwizycję.
        if hasattr(self.controller, 'run_measurement_flag'):
            self.controller.run_measurement_flag.value = 1
            self.controller.initial_reset_needed = True
            
    def _clear_reset_bits(self, plc_client):
        """Clear the reset bits after the initial reset"""
        try:
            from plc_helper import write_accuscan_out_settings
            print("[GUI] Clearing reset bits")
            write_accuscan_out_settings(
                plc_client, db_number=2,
                # Clear all reset bits
                zl=False, zn=False, zf=False, zt=False,
                # Keep other settings at current values
                lump_threshold=None,
                neck_threshold=None,
                flaw_preset_diameter=None,
                upper_tol=None,
                under_tol=None
            )
        except Exception as e:
            print(f"[GUI] Error clearing reset bits: {e}")

    def _on_stop(self):
        print("[GUI] Stop pressed!")
        self.controller.run_measurement = False
        if hasattr(self.controller, 'run_measurement_flag'):
            self.controller.run_measurement_flag.value = 0

    def _on_ack(self):
        """Handle Kwituj button press by asynchronously resetting all PLC counters."""
        print("[GUI] Kwituj pressed!")
        
        try:
            # Przygotuj komendę resetu dla przycisku Kwituj.
            # Tutaj chcemy ustawić wszystkie bity resetu (zl, zn, zf, zt) na True.
            ack_cmd = {
                "command": "ack_reset",
                "params": {
                    "db_number": 2,
                    "zl": True,
                    "zn": True,
                    "zf": True,
                    "zt": True
                    # Inne parametry (lump_threshold, neck_threshold, flaw_preset_diameter, upper_tol, under_tol)
                    # nie są wymagane, jeśli PLC worker odczytuje bieżące wartości lub reset wykonuje się cyklicznie.
                }
            }
            # Wysłanie komendy do kolejki PLC writer
            self.controller.plc_write_queue.put_nowait(ack_cmd)
            print("[GUI] Kwituj reset command sent asynchronously.")
            
            # Po 100 ms wysyłamy komendę, która czyści bity resetu (ustawia wszystkie na False).
            def clear_ack():
                clear_ack_cmd = {
                    "command": "ack_reset_clear",
                    "params": {
                        "db_number": 2,
                        "zl": False,
                        "zn": False,
                        "zf": False,
                        "zt": False
                    }
                }
                self.controller.plc_write_queue.put_nowait(clear_ack_cmd)
                print("[GUI] Ack clear reset command sent asynchronously.")
            
            QTimer.singleShot(100, clear_ack)
            
        except Exception as e:
            print(f"[GUI] Error during asynchronous Kwituj reset: {e}")

    
    def _clear_reset_bits_all(self, plc_client):
        """Clear ALL reset bits after Kwituj reset"""
        try:
            from plc_helper import write_accuscan_out_settings
            print("[GUI] Clearing ALL reset bits after Kwituj")
            write_accuscan_out_settings(
                plc_client, db_number=2,
                # Clear all reset bits including zt
                zl=False, zn=False, zf=False, zt=False,
                # Keep other settings at current values
                lump_threshold=None,
                neck_threshold=None,
                flaw_preset_diameter=None,
                upper_tol=None,
                under_tol=None
            )
        except Exception as e:
            print(f"[GUI] Error clearing reset bits: {e}")

    # ---------------------------------------------------------------------------------
    # 5. Metoda update_readings – aktualizacja etykiet i wykresu
    # ---------------------------------------------------------------------------------
    def update_readings(self, data: dict):
        if data is None or (hasattr(data, "empty") and data.empty):
            return

        # Performance timing
        update_start = time.perf_counter()
        
        # Store PLC sample time if available
        if "plc_sample_time" in data:
            self.plc_sample_time = data.get("plc_sample_time", 0.0)
        # Alternatively calculate from time difference if not provided directly
        elif "timestamp" in data and self.last_update_time is not None:
            self.plc_sample_time = (data["timestamp"] - self.last_update_time).total_seconds()

        # Retrieve diameters and calculate statistics
        d1 = data.get("D1", 0)
        d2 = data.get("D2", 0)
        d3 = data.get("D3", 0)
        d4 = data.get("D4", 0)
        diameters = [d1, d2, d3, d4]
        dmin = min(diameters)
        dmax = max(diameters)
        davg = sum(diameters) / 4.0
        dsd = (sum((x - davg) ** 2 for x in diameters) / 4.0) ** 0.5
        dov = ((dmax - dmin) / davg * 100) if davg != 0 else 0

        # Update labels - this is fast
        label_update_start = time.perf_counter()
        self.label_d1.setText(f"D1 [mm]: {d1:.2f}")
        self.label_d2.setText(f"D2 [mm]: {d2:.2f}")
        self.label_d3.setText(f"D3 [mm]: {d3:.2f}")
        self.label_d4.setText(f"D4 [mm]: {d4:.2f}")
        self.label_davg.setText(f"dAVG [mm]: {davg:.2f}")
        self.label_dmin.setText(f"Dmin [mm]: {dmin:.2f}")
        self.label_dmax.setText(f"Dmax [mm]: {dmax:.2f}")
        self.label_dsd.setText(f"dSD [mm]: {dsd:.3f}")
        self.label_dov.setText(f"dOV [%]: {dov:.2f}")
        
        # Get fluctuation percentage for speed calculation
        try:
            fluctuation_percent = float(self.speed_fluct_entry.text() or "0")
        except ValueError:
            fluctuation_percent = 0
            
        # Get window data directly from the acquisition buffer
        # This still adds the sample to ensure it's processed
        self.window_processor.process_sample(
            data, 
            production_speed=self.production_speed,
            speed_fluctuation_percent=fluctuation_percent
        )
        
        # Get the window data directly from controller's acquisition buffer
        # for better thread safety and performance
        window_data = self.controller.acquisition_buffer.get_window_data()
        
        # Update current_x from window data
        self.current_x = window_data['current_x']
        
        # Update xCoord and speed labels
        self.label_xcoord.setText(f"xCoord [m]: {self.current_x:.1f}")
        
        # Display production speed (potentially with fluctuation)
        try:
            if (fluctuation_percent > 0):
                # Calculate a representative speed value
                import random
                fluctuation_factor = 1.0 + random.uniform(-fluctuation_percent/100, fluctuation_percent/100)
                current_speed = self.production_speed * fluctuation_factor
                self.label_speed.setText(f"Speed [m/min]: {current_speed:.1f} (±{fluctuation_percent}%)")
            else:
                self.label_speed.setText(f"Speed [m/min]: {self.production_speed:.1f}")
        except ValueError:
            self.label_speed.setText(f"Speed [m/min]: {self.production_speed:.1f}")

        # Process flaw detection - this is fast
        # Update flaw window size from UI
        try:
            flaw_window_size = float(self.entry_flaw_window.text() or "0.5")
            self.flaw_detector.update_flaw_window_size(flaw_window_size)
        except ValueError:
            pass
            
        flaw_results = self.flaw_detector.process_flaws(data, self.current_x)
        
        # Update indicators based on current data
        lumps = data.get("lumps", 0)
        necks = data.get("necks", 0)
        if lumps:
            self.label_lump_indicator.setText("Lump ON")
            self.label_lump_indicator.setStyleSheet("color: red;")
        else:
            self.label_lump_indicator.setText("Lump OFF")
            self.label_lump_indicator.setStyleSheet("color: green;")
        if necks:
            self.label_neck_indicator.setText("Neck ON")
            self.label_neck_indicator.setStyleSheet("color: red;")
        else:
            self.label_neck_indicator.setText("Neck OFF")
            self.label_neck_indicator.setStyleSheet("color: green;")
        
        label_update_time = time.perf_counter() - label_update_start

        # Check diameter tolerance - this is fast
        diameter_preset = float(self.entry_diameter_setpoint.text() or 0.0)
        tolerance_plus = float(self.entry_tolerance_plus.text() or 0.5)
        tolerance_minus = float(self.entry_tolerance_minus.text() or 0.5)
        
        deviation = davg - diameter_preset
        self.diameter_deviation_label.setText(f"Dev: {deviation:.2f} mm")
        
        if deviation > tolerance_plus:
            self.label_diameter_indicator.setText("Diameter: HIGH")
            self.label_diameter_indicator.setStyleSheet("color: red;")
        elif deviation < -tolerance_minus:
            self.label_diameter_indicator.setText("Diameter: LOW")
            self.label_diameter_indicator.setStyleSheet("color: red;")
        else:
            self.label_diameter_indicator.setText("Diameter: OK")
            self.label_diameter_indicator.setStyleSheet("color: green;")

        # Prepare plot data and update plots - this is the slower part
        plot_update_start = time.perf_counter()
        
        # Set the plot_dirty flag on the PlotManager
        self.plot_manager.plot_dirty = True
        
        # Prepare data for the plot manager using window_data from acquisition buffer
        plot_data = {
            'x_history': window_data['x_history'],
            'lumps_history': window_data['lumps_history'],
            'necks_history': window_data['necks_history'],
            'current_x': self.current_x,
            'batch_name': self.entry_batch.text() or "NO BATCH",
            'plc_sample_time': self.plc_sample_time,
            'diameter_x': window_data['diameter_x'],
            'diameter_history': window_data['diameter_history'],
            'diameter_preset': diameter_preset,
            'fft_buffer_size': self.FFT_BUFFER_SIZE,
            'timestamp': time.time(),  # Add timestamp for debugging
            'update_id': id(self) % 10000  # Add unique update ID for tracking updates
        }
        
        # Add debug log if we have data but no visible updates
        if self.controller.run_measurement:
            if window_data['x_history'] and len(window_data['x_history']) > 0:
                num_points = len(window_data['x_history'])
                # print(f"[MainPage] Plot data ready: {num_points} points, X range: {window_data['x_history'][0]:.1f}-{self.current_x:.1f}m")
            
            # Force a direct update in the main thread to ensure plots are visible even if process is not working
            if not hasattr(self.plot_manager, 'plot_process') or not self.plot_manager.plot_process or not self.plot_manager.plot_process.is_alive():
                # print("[MainPage] Plot process not active, updating in main thread")
                # Do direct updates for the important plots
                self.plot_manager.update_status_plot(
                    plot_data['x_history'], 
                    plot_data['lumps_history'], 
                    plot_data['necks_history'],
                    plot_data['current_x'],
                    plot_data['batch_name'],
                    plot_data['plc_sample_time']
                )
                
                self.plot_manager.update_diameter_plot(
                    plot_data['diameter_x'],
                    plot_data['diameter_history'],
                    plot_data['current_x'],
                    plot_data['diameter_preset'],
                    plot_data['plc_sample_time']
                )
                
            else:
                # Normal case - update through PlotManager process 
                self.plot_manager.update_all_plots(plot_data)
        else:
            # Optionally clear or skip plot updates when measurement is stopped.
            pass

        plot_update_time = time.perf_counter() - plot_update_start
        
        # Performance logging (only for slow updates)
        total_update_time = time.perf_counter() - update_start
        if total_update_time > 0.1:  # >100ms is considered slow
            print(f"[MainPage] Update time: {total_update_time:.4f}s | "
                  f"Labels: {label_update_time:.4f}s | "
                  f"Window: {window_data.get('processing_time', 0):.4f}s | "
                  f"Flaw: {self.flaw_detector.processing_time:.4f}s | "
                  f"Plot: {plot_update_time:.4f}s")


    # This method is deprecated and replaced by PlotManager.update_all_plots
    # Kept for reference but no longer used
    def _update_plot(self):
        """Update all plots - this is an expensive operation."""
        pass
        # Method replaced by PlotManager.update_all_plots

    def _on_speed_change(self, value: float):
        self.production_speed = float(value)
        self.speed_value_label.setText(f"Speed: {self.production_speed:.1f}")
        
    def _on_prod_speed_change(self, value: float):
        """Handle production speed slider change"""
        self.production_speed = value
        self.prod_speed_value.setText(f"{self.production_speed:.1f}")

    def update_data(self):
        # Get latest data directly from the acquisition buffer instead of data_mgr
        data = self.controller.acquisition_buffer.get_latest_data()
        if data:  # If there's data available
            # Update flaw window size from UI before processing
            try:
                flaw_window_size = float(self.entry_flaw_window.text() or "0.5")
                self.flaw_detector.update_flaw_window_size(flaw_window_size)
            except ValueError:
                pass
                
            # Process data through our pipeline
            self.update_readings(data)
