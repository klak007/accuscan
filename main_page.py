from datetime import datetime
import time
import db_helper
from db_helper import save_settings, save_settings_history
import plc_helper

# Import new modules
from visualization import PlotManager
from data_processing import WindowProcessor, FastAcquisitionBuffer
from flaw_detection import FlawDetector
from stream_redirector import EmittingStream
# PyQtGraph imports
import pyqtgraph as pg

# PyQt5 imports - consolidated
from PyQt5.QtWidgets import (
    QFrame, QGridLayout, QVBoxLayout, QWidget, QMessageBox,
    QHBoxLayout, QPushButton, QLabel, QSpacerItem, QSizePolicy, QLineEdit, QGroupBox, QApplication, QPlainTextEdit, QShortcut
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QDoubleValidator, QIntValidator, QKeySequence

import sys

class MainPage(QWidget):
    """
    Main page of the application, with the following components:
    - Top bar with navigation buttons
    - Left panel with batch/product settings
    - Middle panel with real-time plots
    - Right panel with status messages and FFT plot
    """
    def __init__(self, parent, controller, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.controller = controller

        # Layout 
        self.layout = QGridLayout(self)
        self.setLayout(self.layout)
        
        # Row Stretch
        self.layout.setRowStretch(0, 0)
        self.layout.setRowStretch(1, 1)

        # Column stretch
        self.layout.setColumnStretch(0, 0)
        self.layout.setColumnStretch(1, 0)
        self.layout.setColumnStretch(2, 1)
        
        self.lumps_history = []         # Store lumps history for plotting
        self.necks_history = []         # Store necks history for plotting
        self.x_history = []             # X-coordinates for history plots
        self.MAX_POINTS = 1024          # Maximum number of points to display on the plot
        # self.display_range = 10         # Display range for the plot
        self.last_update_time = None    # Last update time for the plot
        self.current_x = 0.0            # Current X-coordinate for plotting
        self.FFT_BUFFER_SIZE = 512      # Size of the FFT buffer
        self.diameter_history = []      # Store diameter values for plotting
        self.diameter_x = []            # X-coordinates for diameter values
        self.last_plot_update = None    # attribute for plot update frequency
        self.plc_sample_time = 0.0      # Time taken to retrieve a sample from PLC

        # UI interaction state
        self.ui_busy = False  # Flag to indicate UI interaction is in progress
        self.last_save_time = 0  # Track last database save time
        self.save_in_progress = False  # Flag to prevent multiple simultaneous saves

        # # Counters for flaws in the window
        # self.flaw_lumps_count = 0  # Lumps in the current flaw window
        # self.flaw_necks_count = 0  # Necks in the current flaw window
        # self.flaw_lumps_coords = []  # Coordinates of lumps for flaw window tracking
        # self.flaw_necks_coords = []  # Coordinates of necks for flaw window tracking

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
        self.fft_threshold_value = 1000.0
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
        # self.flaw_detector = FlawDetector(flaw_window_size=0.5)


    # ---------------------------------------------------------------------------------
    # 1. Górna belka nawigacji (row=0, col=0..2)
    # ---------------------------------------------------------------------------------
    def _create_top_bar(self):
        # Use QFrame to create a frame surrounding the top bar
        self.top_bar = QFrame(self)
        self.top_bar.setFrameShape(QFrame.Box)
        self.top_bar.setLineWidth(2)
        self.top_bar.setFrameShadow(QFrame.Raised)  # Gives a raised (or Sunken) look
        self.top_bar.setStyleSheet("fusion")
        top_bar_layout = QHBoxLayout(self.top_bar)
        top_bar_layout.setContentsMargins(5, 5, 5, 5)
        top_bar_layout.setSpacing(5)
        top_bar_font = QFont(QApplication.font())
        top_bar_font.setPointSize(12)
        top_bar_font.setBold(False)

        # Pomiary button: fixed size and green background
        self.btn_pomiary = QPushButton("Pomiary (F2)", self.top_bar)
        self.btn_pomiary.setFont(top_bar_font)
        self.btn_pomiary.setFixedSize(140, 40)
        

        shortcut_pomiary = QShortcut(QKeySequence('F2'), self)
        shortcut_pomiary.activated.connect(self.btn_pomiary.click)

        # Nastawy button: fixed size
        self.btn_nastawy = QPushButton("Nastawy (F3)", self.top_bar)
        self.btn_nastawy.setFont(top_bar_font)
        self.btn_nastawy.setFixedSize(140, 40)
        self.btn_nastawy.clicked.connect(lambda: self.controller.toggle_page("SettingsPage"))

        shortcut_nastawy = QShortcut(QKeySequence('F3'), self)
        shortcut_nastawy.activated.connect(self.btn_nastawy.click)

        # Historia button: fixed size
        self.btn_historia = QPushButton("Historia (F4)", self.top_bar)
        self.btn_historia.setFont(top_bar_font)
        self.btn_historia.setFixedSize(140, 40)
        self.btn_historia.clicked.connect(lambda: self.controller.toggle_page("HistoryPage"))

        shortcut_historia = QShortcut(QKeySequence('F4'), self)
        shortcut_historia.activated.connect(self.btn_historia.click)

        # Accuscan button: fixed size
        self.btn_accuscan = QPushButton("Accuscan (F5)", self.top_bar)
        self.btn_accuscan.setFont(top_bar_font)
        self.btn_accuscan.setFixedSize(140, 40)
        self.btn_accuscan.clicked.connect(self._on_accuscan_click)

        shortcut_accuscan = QShortcut(QKeySequence('F5'), self)
        shortcut_accuscan.activated.connect(self.btn_accuscan.click)

        
        # Add left-side buttons
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
        self.btn_start.setFont(top_bar_font)
        self.btn_start.setFixedSize(140, 40)
        self.btn_start.clicked.connect(self._on_start)
        
        self.btn_stop = QPushButton("Stop", self.control_frame)
        self.btn_stop.setFont(top_bar_font)
        self.btn_stop.setFixedSize(140, 40)
        self.btn_stop.clicked.connect(self._on_stop)
        
        self.btn_ack = QPushButton("Kwituj", self.control_frame)
        self.btn_ack.setFont(top_bar_font)
        self.btn_ack.setFixedSize(140,40)
        self.btn_ack.clicked.connect(self._on_ack)
        
        control_layout.addWidget(self.btn_start)
        control_layout.addWidget(self.btn_stop)
        control_layout.addWidget(self.btn_ack)
        
        top_bar_layout.addWidget(self.control_frame, 0, Qt.AlignRight)
        
        # Exit button: fixed size and red background
        self.btn_exit = QPushButton("Zamknij", self.top_bar)
        self.btn_exit.setFont(top_bar_font)
        self.btn_exit.setFixedSize(140, 40)
        self.btn_exit.setStyleSheet("background-color: red;")
        self.btn_exit.clicked.connect(self._on_exit_click)
        top_bar_layout.addWidget(self.btn_exit, 0, Qt.AlignRight)
        
        # NEW: Dodaj etykietę statusu PLC
        self.plc_status_label = QLabel("PLC Status: Unknown", self.top_bar)
        top_bar_layout.addWidget(self.plc_status_label, 0, Qt.AlignRight)


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

    def show_alarm(self, defect_type, current_count, max_allowed):
        """
        Zawsze wyświetlaj bieżącą liczbę defektów i maksymalną dozwoloną.
        Jeśli liczba defektów przekracza wartość dopuszczalną, kolor jest czerwony
        i dodajemy prefiks 'ALARM:'.
        """
        if defect_type == "Wybrzuszenia":
            if current_count > max_allowed:
                self.label_alarm_lumps.setText(f"ALARM: Wybrzuszenia {current_count}/{max_allowed}")
                self.label_alarm_lumps.setStyleSheet("color: red;")
            else:
                self.label_alarm_lumps.setText(f"Wybrzuszenia {current_count}/{max_allowed}")
                self.label_alarm_lumps.setStyleSheet("color: black;")
        elif defect_type == "Zagłębienia":
            if current_count > max_allowed:
                self.label_alarm_necks.setText(f"ALARM: Zagłębienia {current_count}/{max_allowed}")
                self.label_alarm_necks.setStyleSheet("color: red;")
            else:
                self.label_alarm_necks.setText(f"Zagłębienia {current_count}/{max_allowed}")
                self.label_alarm_necks.setStyleSheet("color: black;")

    def clear_alarm(self, defect_type):
        """
        Czyści alarmy (lub resetuje licznik na 0/0, w razie potrzeby).
        """
        if defect_type == "Wybrzuszenia":
            self.label_alarm_lumps.setText("Wybrzuszenia OK")
            self.label_alarm_lumps.setStyleSheet("color: black;")
        elif defect_type == "Zagłębienia":
            self.label_alarm_necks.setText("Zagłębienia OK")
            self.label_alarm_necks.setStyleSheet("color: black;")


    # ---------------------------------------------------------------------------------
    # 2. Lewa kolumna (row=1, col=0) – Batch, Product, itp.
    # ---------------------------------------------------------------------------------
    def _create_left_panel(self):
        # Utworzenie lewego panelu o stałej szerokości 400
        self.left_panel = QFrame(self)
        self.left_panel.setFrameShape(QFrame.Box)
        self.left_panel.setFrameShadow(QFrame.Raised)
        self.left_panel.setLineWidth(2)
        self.left_panel.setMinimumWidth(400)
        self.left_panel.setMaximumWidth(400)

        # Główny layout pionowy dzielący panel na dwie części
        main_layout = QVBoxLayout(self.left_panel)
        self.left_panel.setLayout(main_layout)

        # ------ GÓRNA CZĘŚĆ - parametry programu ------
        self.upper_frame = QFrame(self.left_panel)
        upper_layout = QGridLayout(self.upper_frame)
        self.upper_frame.setLayout(upper_layout)
        main_layout.addWidget(self.upper_frame)

        # Wiersz 0: Etykieta "Batch"
        self.label_batch = QLabel("Batch", self.upper_frame)
        upper_layout.addWidget(self.label_batch, 0, 0, alignment=Qt.AlignLeft | Qt.AlignVCenter)

        # Wiersz 1: Pole tekstowe dla batch
        self.entry_batch = QLineEdit(self.upper_frame)
        self.entry_batch.setPlaceholderText("IADTX0000")
        self.entry_batch.setText("IADTX0000")
        upper_layout.addWidget(self.entry_batch, 1, 0)

        # Wiersz 2: Etykieta "Produkt"
        self.label_product = QLabel("Produkt", self.upper_frame)
        upper_layout.addWidget(self.label_product, 2, 0, alignment=Qt.AlignLeft | Qt.AlignVCenter)

        # Wiersz 3: Pole tekstowe dla produktu
        self.entry_product = QLineEdit(self.upper_frame)
        self.entry_product.setPlaceholderText("18X0600")
        self.entry_product.setText("18X0600")
        upper_layout.addWidget(self.entry_product, 3, 0)

        # Wiersz 4: Przycisk "Przykładowe nastawy"
        self.btn_typowy = QPushButton("Przykładowe nastawy", self.upper_frame)
        self.btn_typowy.setToolTip("Ustawia przykładowe nastawy dla receptury.")
        self.btn_typowy.setFixedHeight(40)
        self.btn_typowy.clicked.connect(self._on_typowy_click)
        upper_layout.addWidget(self.btn_typowy, 4, 0)

        # Wiersz 5: Przycisk "Zapisz nastawy"
        self.btn_save_settings_to_db = QPushButton("Zapisz nastawy do bazy danych", self.upper_frame)
        self.btn_save_settings_to_db.setToolTip("Zapisuje aktualne nastawy do bazy danych.")
        self.btn_save_settings_to_db.setFixedHeight(40)
        self.btn_save_settings_to_db.clicked.connect(self._save_settings_to_db)
        self.btn_save_settings_to_db.setAutoDefault(True)
        upper_layout.addWidget(self.btn_save_settings_to_db, 5, 0)

        # Wiersz 6: Etykieta "Nazwa receptury:"
        self.label_recipe_name = QLabel("Nazwa receptury:", self.upper_frame)
        upper_layout.addWidget(self.label_recipe_name, 6, 0, alignment=Qt.AlignCenter)

        # Wiersz 7: Pole tekstowe dla nazwy receptury
        self.entry_recipe_name = QLineEdit(self.upper_frame)
        self.entry_recipe_name.setPlaceholderText("Receptura X")
        upper_layout.addWidget(self.entry_recipe_name, 7, 0)

        # Wiersz 8: Etykieta "Długość okna defektów [m]:"
        self.label_flaw_window = QLabel("Długość okna defektów [m]:", self.upper_frame)
        upper_layout.addWidget(self.label_flaw_window, 8, 0, alignment=Qt.AlignCenter)

        # Wiersz 9: Sekcja "Długość okna defektów" (pole tekstowe i przyciski)
        flaw_window_frame = QFrame(self.upper_frame)
        flaw_window_layout = QHBoxLayout(flaw_window_frame)
        flaw_window_layout.setContentsMargins(0, 0, 0, 0)
        flaw_window_frame.setLayout(flaw_window_layout)
        upper_layout.addWidget(flaw_window_frame, 9, 0, alignment=Qt.AlignCenter)

        self.btn_flaw_window_dec_10 = QPushButton("--", flaw_window_frame)
        self.btn_flaw_window_dec_10.setFixedWidth(30)
        self.btn_flaw_window_dec_10.clicked.connect(lambda: self._adjust_flaw_window(-0.1))
        flaw_window_layout.addWidget(self.btn_flaw_window_dec_10)

        self.btn_flaw_window_dec_05 = QPushButton("-", flaw_window_frame)
        self.btn_flaw_window_dec_05.setFixedWidth(30)
        self.btn_flaw_window_dec_05.clicked.connect(lambda: self._adjust_flaw_window(-0.05))
        flaw_window_layout.addWidget(self.btn_flaw_window_dec_05)

        self.entry_flaw_window = QLineEdit(flaw_window_frame)
        self.entry_flaw_window.setValidator(QDoubleValidator(0.0, 100.0, 3))
        self.entry_flaw_window.setPlaceholderText("0.5")
        self.entry_flaw_window.setMinimumWidth(220)
        self.entry_flaw_window.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        flaw_window_layout.addWidget(self.entry_flaw_window)

        self.btn_flaw_window_inc_05 = QPushButton("+", flaw_window_frame)
        self.btn_flaw_window_inc_05.setFixedWidth(30)
        self.btn_flaw_window_inc_05.clicked.connect(lambda: self._adjust_flaw_window(0.05))
        flaw_window_layout.addWidget(self.btn_flaw_window_inc_05)

        self.btn_flaw_window_inc_10 = QPushButton("++", flaw_window_frame)
        self.btn_flaw_window_inc_10.setFixedWidth(30)
        self.btn_flaw_window_inc_10.clicked.connect(lambda: self._adjust_flaw_window(0.1))
        flaw_window_layout.addWidget(self.btn_flaw_window_inc_10)

        # Wiersz 10: Etykieta "Maksymalna liczba wybrzuszeń w oknie defektów:"
        self.label_max_lumps = QLabel("Maksymalna liczba wybrzuszeń w oknie defektów:", self.upper_frame)
        upper_layout.addWidget(self.label_max_lumps, 10, 0, alignment=Qt.AlignCenter)

        # Wiersz 11: Sekcja "Maksymalna liczba wybrzuszeń" (pole tekstowe i przyciski)
        max_lumps_frame = QFrame(self.upper_frame)
        max_lumps_layout = QHBoxLayout(max_lumps_frame)
        max_lumps_layout.setContentsMargins(0, 0, 0, 0)
        max_lumps_frame.setLayout(max_lumps_layout)
        upper_layout.addWidget(max_lumps_frame, 11, 0, alignment=Qt.AlignCenter)

        self.btn_max_lumps_dec_5 = QPushButton("--", max_lumps_frame)
        self.btn_max_lumps_dec_5.setFixedWidth(30)
        self.btn_max_lumps_dec_5.clicked.connect(lambda: self._adjust_max_lumps(-5))
        max_lumps_layout.addWidget(self.btn_max_lumps_dec_5)

        self.btn_max_lumps_dec = QPushButton("-", max_lumps_frame)
        self.btn_max_lumps_dec.setFixedWidth(30)
        self.btn_max_lumps_dec.clicked.connect(lambda: self._adjust_max_lumps(-1))
        max_lumps_layout.addWidget(self.btn_max_lumps_dec)

        self.entry_max_lumps = QLineEdit(max_lumps_frame)
        self.entry_max_lumps.setValidator(QIntValidator(0, 1000))
        self.entry_max_lumps.setPlaceholderText("3")
        self.entry_max_lumps.setMinimumWidth(220)
        self.entry_max_lumps.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        max_lumps_layout.addWidget(self.entry_max_lumps)

        self.btn_max_lumps_inc = QPushButton("+", max_lumps_frame)
        self.btn_max_lumps_inc.setFixedWidth(30)
        self.btn_max_lumps_inc.clicked.connect(lambda: self._adjust_max_lumps(1))
        max_lumps_layout.addWidget(self.btn_max_lumps_inc)

        self.btn_max_lumps_inc_5 = QPushButton("++", max_lumps_frame)
        self.btn_max_lumps_inc_5.setFixedWidth(30)
        self.btn_max_lumps_inc_5.clicked.connect(lambda: self._adjust_max_lumps(5))
        max_lumps_layout.addWidget(self.btn_max_lumps_inc_5)

        # Wiersz 12: Etykieta "Maksymalna liczba zagłębień w oknie defektów:"
        self.label_max_necks = QLabel("Maksymalna liczba zagłębień w oknie defektów:", self.upper_frame)
        upper_layout.addWidget(self.label_max_necks, 12, 0, alignment=Qt.AlignCenter)

        # Wiersz 13: Sekcja "Maksymalna liczba zagłębień" (pole tekstowe i przyciski)
        max_necks_frame = QFrame(self.upper_frame)
        max_necks_layout = QHBoxLayout(max_necks_frame)
        max_necks_layout.setContentsMargins(0, 0, 0, 0)
        max_necks_frame.setLayout(max_necks_layout)
        upper_layout.addWidget(max_necks_frame, 13, 0, alignment=Qt.AlignCenter)

        self.btn_max_necks_dec_5 = QPushButton("--", max_necks_frame)
        self.btn_max_necks_dec_5.setFixedWidth(30)
        self.btn_max_necks_dec_5.clicked.connect(lambda: self._adjust_max_necks(-5))
        max_necks_layout.addWidget(self.btn_max_necks_dec_5)

        self.btn_max_necks_dec = QPushButton("-", max_necks_frame)
        self.btn_max_necks_dec.setFixedWidth(30)
        self.btn_max_necks_dec.clicked.connect(lambda: self._adjust_max_necks(-1))
        max_necks_layout.addWidget(self.btn_max_necks_dec)

        self.entry_max_necks = QLineEdit(max_necks_frame)
        self.entry_max_necks.setValidator(QIntValidator(0, 1000))
        self.entry_max_necks.setPlaceholderText("3")
        self.entry_max_necks.setMinimumWidth(220)
        self.entry_max_necks.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        max_necks_layout.addWidget(self.entry_max_necks)

        self.btn_max_necks_inc = QPushButton("+", max_necks_frame)
        self.btn_max_necks_inc.setFixedWidth(30)
        self.btn_max_necks_inc.clicked.connect(lambda: self._adjust_max_necks(1))
        max_necks_layout.addWidget(self.btn_max_necks_inc)

        self.btn_max_necks_inc_5 = QPushButton("++", max_necks_frame)
        self.btn_max_necks_inc_5.setFixedWidth(30)
        self.btn_max_necks_inc_5.clicked.connect(lambda: self._adjust_max_necks(5))
        max_necks_layout.addWidget(self.btn_max_necks_inc_5)

        # Wiersz 14: Etykieta "Próg pulsacji:"
        self.label_pulsation_threshold = QLabel("Próg pulsacji:", self.upper_frame)
        upper_layout.addWidget(self.label_pulsation_threshold, 14, 0, alignment=Qt.AlignCenter)

        # Wiersz 15: Sekcja "Próg pulsacji" (pole tekstowe i przyciski)
        pulsation_frame = QFrame(self.upper_frame)
        pulsation_layout = QHBoxLayout(pulsation_frame)
        pulsation_layout.setContentsMargins(0, 0, 0, 0)
        pulsation_frame.setLayout(pulsation_layout)
        upper_layout.addWidget(pulsation_frame, 15, 0, alignment=Qt.AlignCenter)

        self.btn_pulsation_dec_2 = QPushButton("--", pulsation_frame)
        self.btn_pulsation_dec_2.setFixedWidth(30)
        self.btn_pulsation_dec_2.clicked.connect(lambda: self._adjust_pulsation_threshold(-100))
        pulsation_layout.addWidget(self.btn_pulsation_dec_2)

        self.btn_pulsation_dec = QPushButton("-", pulsation_frame)
        self.btn_pulsation_dec.setFixedWidth(30)
        self.btn_pulsation_dec.clicked.connect(lambda: self._adjust_pulsation_threshold(-50))
        pulsation_layout.addWidget(self.btn_pulsation_dec)

        self.entry_pulsation_threshold = QLineEdit(pulsation_frame)
        self.entry_pulsation_threshold.setValidator(QDoubleValidator(0.0, 10000.0, 1))
        self.entry_pulsation_threshold.setPlaceholderText("np.: 500.0")
        self.entry_pulsation_threshold.setMinimumWidth(220)
        self.entry_pulsation_threshold.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        pulsation_layout.addWidget(self.entry_pulsation_threshold)

        self.btn_pulsation_inc = QPushButton("+", pulsation_frame)
        self.btn_pulsation_inc.setFixedWidth(30)
        self.btn_pulsation_inc.clicked.connect(lambda: self._adjust_pulsation_threshold(50))
        pulsation_layout.addWidget(self.btn_pulsation_inc)

        self.btn_pulsation_inc_2 = QPushButton("++", pulsation_frame)
        self.btn_pulsation_inc_2.setFixedWidth(30)
        self.btn_pulsation_inc_2.clicked.connect(lambda: self._adjust_pulsation_threshold(100))
        pulsation_layout.addWidget(self.btn_pulsation_inc_2)

        # Wstawiamy poziomą linię:
        separator_line = QFrame(self.left_panel)
        separator_line.setFrameShape(QFrame.HLine)
        separator_line.setFrameShadow(QFrame.Sunken)
        separator_line.setLineWidth(4)
        main_layout.addWidget(separator_line)
        # ------ DOLNA CZĘŚĆ - Parametry w PLC ------
        self.lower_frame = QFrame(self.left_panel)
        self.lower_frame.setStyleSheet("background-color: #f0f0f0;")
        lower_layout = QGridLayout(self.lower_frame)
        self.lower_frame.setLayout(lower_layout)
        main_layout.addWidget(self.lower_frame)

        # Wiersz 0: Etykieta "Parametry w PLC"
        label_plc = QLabel("Parametry w PLC", self.lower_frame)
        label_plc.setAlignment(Qt.AlignCenter)
        font = label_plc.font()
        font.setPointSize(16)
        font.setBold(True)
        label_plc.setFont(font)
        lower_layout.addWidget(label_plc, 0, 0, 1, 1)

        # Wiersz 1: Przycisk "Zapisz do PLC"
        self.btn_save_plc = QPushButton("Zapisz do PLC", self.lower_frame)
        self.btn_save_plc.setToolTip("Wysyła ustawienia do sterownika PLC.")
        self.btn_save_plc.setFixedSize(350, 40)
        self.btn_save_plc.setAutoDefault(True)
        self.btn_save_plc.clicked.connect(self._save_settings_to_plc)
        lower_layout.addWidget(self.btn_save_plc, 1, 0, alignment=Qt.AlignCenter)

        # Wiersz 2: Etykieta "Średnica docelowa [mm]:"
        self.label_diameter_setpoint = QLabel("Średnica docelowa [mm]:", self.lower_frame)
        lower_layout.addWidget(self.label_diameter_setpoint, 2, 0, alignment=Qt.AlignCenter)

        # Wiersz 3: Sekcja "Średnica docelowa" (pole tekstowe i przyciski)
        diameter_frame = QFrame(self.lower_frame)
        diameter_layout = QHBoxLayout(diameter_frame)
        diameter_layout.setContentsMargins(0, 0, 0, 0)
        diameter_frame.setLayout(diameter_layout)
        lower_layout.addWidget(diameter_frame, 3, 0, alignment=Qt.AlignCenter)

        self.btn_diam_decrease_05 = QPushButton("--", diameter_frame)
        self.btn_diam_decrease_05.setFixedWidth(30)
        self.btn_diam_decrease_05.clicked.connect(lambda: self._adjust_diameter(-0.5))
        diameter_layout.addWidget(self.btn_diam_decrease_05)

        self.btn_diam_decrease_01 = QPushButton("-", diameter_frame)
        self.btn_diam_decrease_01.setFixedWidth(30)
        self.btn_diam_decrease_01.clicked.connect(lambda: self._adjust_diameter(-0.1))
        diameter_layout.addWidget(self.btn_diam_decrease_01)

        self.entry_diameter_setpoint = QLineEdit(diameter_frame)
        self.entry_diameter_setpoint.setValidator(QDoubleValidator(0.0, 100.0, 3))
        self.entry_diameter_setpoint.setPlaceholderText("39.745")
        self.entry_diameter_setpoint.setMinimumWidth(220)
        self.entry_diameter_setpoint.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        diameter_layout.addWidget(self.entry_diameter_setpoint)

        self.btn_diam_increase_01 = QPushButton("+", diameter_frame)
        self.btn_diam_increase_01.setFixedWidth(30)
        self.btn_diam_increase_01.clicked.connect(lambda: self._adjust_diameter(0.1))
        diameter_layout.addWidget(self.btn_diam_increase_01)

        self.btn_diam_increase_05 = QPushButton("++", diameter_frame)
        self.btn_diam_increase_05.setFixedWidth(30)
        self.btn_diam_increase_05.clicked.connect(lambda: self._adjust_diameter(0.5))
        diameter_layout.addWidget(self.btn_diam_increase_05)

        # Wiersz 4: Etykieta "Górna granica tolerancji (różnica od dAvg) [mm]:"
        self.label_tolerance_plus = QLabel("Górna granica tolerancji (różnica od dAvg) [mm]:", self.lower_frame)
        lower_layout.addWidget(self.label_tolerance_plus, 4, 0, alignment=Qt.AlignCenter)

        # Wiersz 5: Sekcja "Górna granica tolerancji" (pole tekstowe i przyciski)
        plus_frame = QFrame(self.lower_frame)
        plus_layout = QHBoxLayout(plus_frame)
        plus_layout.setContentsMargins(0, 0, 0, 0)
        plus_frame.setLayout(plus_layout)
        lower_layout.addWidget(plus_frame, 5, 0, alignment=Qt.AlignCenter)

        self.btn_tolerance_plus_dec_05 = QPushButton("--", plus_frame)
        self.btn_tolerance_plus_dec_05.setFixedWidth(30)
        self.btn_tolerance_plus_dec_05.clicked.connect(lambda: self._adjust_tolerance_plus(-0.5))
        plus_layout.addWidget(self.btn_tolerance_plus_dec_05)

        self.btn_tolerance_plus_dec_01 = QPushButton("-", plus_frame)
        self.btn_tolerance_plus_dec_01.setFixedWidth(30)
        self.btn_tolerance_plus_dec_01.clicked.connect(lambda: self._adjust_tolerance_plus(-0.1))
        plus_layout.addWidget(self.btn_tolerance_plus_dec_01)

        self.entry_tolerance_plus = QLineEdit(plus_frame)
        self.entry_tolerance_plus.setValidator(QDoubleValidator(0.0, 100.0, 3))
        self.entry_tolerance_plus.setPlaceholderText("0.5")
        self.entry_tolerance_plus.setMinimumWidth(220)
        self.entry_tolerance_plus.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        plus_layout.addWidget(self.entry_tolerance_plus)

        self.btn_tolerance_plus_inc_01 = QPushButton("+", plus_frame)
        self.btn_tolerance_plus_inc_01.setFixedWidth(30)
        self.btn_tolerance_plus_inc_01.clicked.connect(lambda: self._adjust_tolerance_plus(0.1))
        plus_layout.addWidget(self.btn_tolerance_plus_inc_01)

        self.btn_tolerance_plus_inc_05 = QPushButton("++", plus_frame)
        self.btn_tolerance_plus_inc_05.setFixedWidth(30)
        self.btn_tolerance_plus_inc_05.clicked.connect(lambda: self._adjust_tolerance_plus(0.5))
        plus_layout.addWidget(self.btn_tolerance_plus_inc_05)

        # Wiersz 6: Etykieta "Dolna granica tolerancji (różnica od dAvg) [mm]:"
        self.label_tolerance_minus = QLabel("Dolna granica tolerancji (różnica od dAvg) [mm]:", self.lower_frame)
        lower_layout.addWidget(self.label_tolerance_minus, 6, 0, alignment=Qt.AlignCenter)

        # Wiersz 7: Sekcja "Dolna granica tolerancji" (pole tekstowe i przyciski)
        minus_frame = QFrame(self.lower_frame)
        minus_layout = QHBoxLayout(minus_frame)
        minus_layout.setContentsMargins(0, 0, 0, 0)
        minus_frame.setLayout(minus_layout)
        lower_layout.addWidget(minus_frame, 7, 0, alignment=Qt.AlignCenter)

        self.btn_tolerance_minus_dec_05 = QPushButton("--", minus_frame)
        self.btn_tolerance_minus_dec_05.setFixedWidth(30)
        self.btn_tolerance_minus_dec_05.clicked.connect(lambda: self._adjust_tolerance_minus(-0.5))
        minus_layout.addWidget(self.btn_tolerance_minus_dec_05)

        self.btn_tolerance_minus_dec_01 = QPushButton("-", minus_frame)
        self.btn_tolerance_minus_dec_01.setFixedWidth(30)
        self.btn_tolerance_minus_dec_01.clicked.connect(lambda: self._adjust_tolerance_minus(-0.1))
        minus_layout.addWidget(self.btn_tolerance_minus_dec_01)

        self.entry_tolerance_minus = QLineEdit(minus_frame)
        self.entry_tolerance_minus.setValidator(QDoubleValidator(0.0, 100.0, 3))
        self.entry_tolerance_minus.setPlaceholderText("0.5")
        self.entry_tolerance_minus.setMinimumWidth(220)
        self.entry_tolerance_minus.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        minus_layout.addWidget(self.entry_tolerance_minus)

        self.btn_tolerance_minus_inc_01 = QPushButton("+", minus_frame)
        self.btn_tolerance_minus_inc_01.setFixedWidth(30)
        self.btn_tolerance_minus_inc_01.clicked.connect(lambda: self._adjust_tolerance_minus(0.1))
        minus_layout.addWidget(self.btn_tolerance_minus_inc_01)

        self.btn_tolerance_minus_inc_05 = QPushButton("++", minus_frame)
        self.btn_tolerance_minus_inc_05.setFixedWidth(30)
        self.btn_tolerance_minus_inc_05.clicked.connect(lambda: self._adjust_tolerance_minus(0.5))
        minus_layout.addWidget(self.btn_tolerance_minus_inc_05)

        # Wiersz 8: Etykieta "Próg wybrzuszeń [mm]:"
        self.label_lump_threshold = QLabel("Próg wybrzuszeń [mm]:", self.lower_frame)
        lower_layout.addWidget(self.label_lump_threshold, 8, 0, alignment=Qt.AlignCenter)

        # Wiersz 9: Sekcja "Próg wybrzuszeń" (pole tekstowe i przyciski)
        lumps_threshold_frame = QFrame(self.lower_frame)
        lumps_threshold_layout = QHBoxLayout(lumps_threshold_frame)
        lumps_threshold_layout.setContentsMargins(0, 0, 0, 0)
        lumps_threshold_frame.setLayout(lumps_threshold_layout)
        lower_layout.addWidget(lumps_threshold_frame, 9, 0, alignment=Qt.AlignCenter)

        self.btn_lump_thres_dec_05 = QPushButton("--", lumps_threshold_frame)
        self.btn_lump_thres_dec_05.setFixedWidth(30)
        self.btn_lump_thres_dec_05.clicked.connect(lambda: self._adjust_lump_threshold(-0.5))
        lumps_threshold_layout.addWidget(self.btn_lump_thres_dec_05)

        self.btn_lump_thres_dec_01 = QPushButton("-", lumps_threshold_frame)
        self.btn_lump_thres_dec_01.setFixedWidth(30)
        self.btn_lump_thres_dec_01.clicked.connect(lambda: self._adjust_lump_threshold(-0.1))
        lumps_threshold_layout.addWidget(self.btn_lump_thres_dec_01)

        self.entry_lump_threshold = QLineEdit(lumps_threshold_frame)
        self.entry_lump_threshold.setValidator(QDoubleValidator(0.0, 100.0, 3))
        self.entry_lump_threshold.setPlaceholderText("0.3")
        self.entry_lump_threshold.setMinimumWidth(220)
        self.entry_lump_threshold.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lumps_threshold_layout.addWidget(self.entry_lump_threshold)

        self.btn_lump_thres_inc_01 = QPushButton("+", lumps_threshold_frame)
        self.btn_lump_thres_inc_01.setFixedWidth(30)
        self.btn_lump_thres_inc_01.clicked.connect(lambda: self._adjust_lump_threshold(0.1))
        lumps_threshold_layout.addWidget(self.btn_lump_thres_inc_01)

        self.btn_lump_thres_inc_05 = QPushButton("++", lumps_threshold_frame)
        self.btn_lump_thres_inc_05.setFixedWidth(30)
        self.btn_lump_thres_inc_05.clicked.connect(lambda: self._adjust_lump_threshold(0.5))
        lumps_threshold_layout.addWidget(self.btn_lump_thres_inc_05)

        # Wiersz 10: Etykieta "Próg zagłębienia [mm]:"
        self.label_neck_threshold = QLabel("Próg zagłębienia [mm]:", self.lower_frame)
        lower_layout.addWidget(self.label_neck_threshold, 10, 0, alignment=Qt.AlignCenter)

        # Wiersz 11: Sekcja "Próg zagłębienia" (pole tekstowe i przyciski)
        necks_threshold_frame = QFrame(self.lower_frame)
        necks_threshold_layout = QHBoxLayout(necks_threshold_frame)
        necks_threshold_layout.setContentsMargins(0, 0, 0, 0)
        necks_threshold_frame.setLayout(necks_threshold_layout)
        lower_layout.addWidget(necks_threshold_frame, 11, 0, alignment=Qt.AlignCenter)

        self.btn_neck_thres_dec_05 = QPushButton("--", necks_threshold_frame)
        self.btn_neck_thres_dec_05.setFixedWidth(30)
        self.btn_neck_thres_dec_05.clicked.connect(lambda: self._adjust_neck_threshold(-0.5))
        necks_threshold_layout.addWidget(self.btn_neck_thres_dec_05)

        self.btn_neck_thres_dec_01 = QPushButton("-", necks_threshold_frame)
        self.btn_neck_thres_dec_01.setFixedWidth(30)
        self.btn_neck_thres_dec_01.clicked.connect(lambda: self._adjust_neck_threshold(-0.1))
        necks_threshold_layout.addWidget(self.btn_neck_thres_dec_01)

        self.entry_neck_threshold = QLineEdit(necks_threshold_frame)
        self.entry_neck_threshold.setValidator(QDoubleValidator(0.0, 100.0, 3))
        self.entry_neck_threshold.setPlaceholderText("0.3")
        self.entry_neck_threshold.setMinimumWidth(220)
        self.entry_neck_threshold.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        necks_threshold_layout.addWidget(self.entry_neck_threshold)

        self.btn_neck_thres_inc_01 = QPushButton("+", necks_threshold_frame)
        self.btn_neck_thres_inc_01.setFixedWidth(30)
        self.btn_neck_thres_inc_01.clicked.connect(lambda: self._adjust_neck_threshold(0.1))
        necks_threshold_layout.addWidget(self.btn_neck_thres_inc_01)

        self.btn_neck_thres_inc_05 = QPushButton("++", necks_threshold_frame)
        self.btn_neck_thres_inc_05.setFixedWidth(30)
        self.btn_neck_thres_inc_05.clicked.connect(lambda: self._adjust_neck_threshold(0.5))
        necks_threshold_layout.addWidget(self.btn_neck_thres_inc_05)

        # Ustawiamy kolejność przechodzenia klawiszem Tab
        self.setTabOrder(self.entry_batch, self.entry_product)
        self.setTabOrder(self.entry_product, self.entry_recipe_name)
        self.setTabOrder(self.entry_recipe_name, self.entry_flaw_window)
        self.setTabOrder(self.entry_flaw_window, self.entry_max_lumps)
        self.setTabOrder(self.entry_max_lumps, self.entry_max_necks)
        self.setTabOrder(self.entry_max_necks, self.entry_pulsation_threshold)
        self.setTabOrder(self.entry_pulsation_threshold, self.entry_diameter_setpoint)
        self.setTabOrder(self.entry_diameter_setpoint, self.entry_tolerance_plus)
        self.setTabOrder(self.entry_tolerance_plus, self.entry_tolerance_minus)
        self.setTabOrder(self.entry_tolerance_minus, self.entry_lump_threshold)
        self.setTabOrder(self.entry_lump_threshold, self.entry_neck_threshold)
        self.setTabOrder(self.entry_neck_threshold, self.btn_save_settings_to_db)
        self.setTabOrder(self.btn_save_settings_to_db, self.btn_save_plc)
        self.setTabOrder(self.btn_save_plc, self.entry_batch)





    def _adjust_pulsation_threshold(self, delta: float):
        val_str = self.entry_pulsation_threshold.text() or "0"
        try:
            val = float(val_str)
        except ValueError:
            val = 0.0
        new_val = max(0.0, val + delta)
        self.entry_pulsation_threshold.setText(f"{new_val:.1f}")
        # Wywołaj metodę, która ustawia próg w PlotManager:
        self._adjust_fft_threshold(new_val)

    def _adjust_fft_threshold(self, new_value: float):
        self.fft_threshold_value = new_value
        self.plot_manager.fft_threshold = new_value
        print(f"[GUI] FFT threshold set to: {new_value:.1f}")

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

    def _adjust_flaw_window(self, delta: float):
        """Adjust the flaw window size value"""
        val_str = self.entry_flaw_window.text() or "0.5"
        try:
            val = float(val_str)
        except ValueError:
            val = 0.5
        # Ensure the value doesn't go below 0.1
        new_val = max(0.1, val + delta)  
        self.entry_flaw_window.clear()
        self.entry_flaw_window.setText(f"{new_val:.2f}")
        
        # Update the flaw detector with the new window size if available
        if hasattr(self, 'flaw_detector'):
            self.controller.flaw_detector.update_flaw_window_size(new_val)

    def _save_settings_to_db(self):
        """
        1. Odczytuje i parsuje dane z pól tekstowych.
        2. Zapisuje ustawienia do bazy danych (tabele: settings + settings_register).
        3. Zwraca słownik `settings_data` w razie powodzenia,
        lub None jeśli coś poszło nie tak (wtedy wyświetla QMessageBox).
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
        pulsation_str = self.entry_pulsation_threshold.text() or "550.0"

        # 2. Konwersje na float/int
        try:
            diameter_setpoint = float(diameter_setpoint_str)
            tolerance_plus = float(tolerance_plus_str)
            tolerance_minus = float(tolerance_minus_str)
            lump_threshold = float(lump_threshold_str)
            neck_threshold = float(neck_threshold_str)
            flaw_window = float(flaw_window_str)
            max_lumps = int(max_lumps_str)
            max_necks = int(max_necks_str)
            pulsation_threshold = float(pulsation_str)
        except ValueError:
            QMessageBox.critical(self, "Błąd", "Błędne dane wejściowe.")
            return None

        # 3. Zbuduj słownik do zapisu w bazie
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
            "pulsation_threshold": pulsation_threshold
        }

        # 4. Zapis do bazy
        try:
            settings_id = save_settings(self.controller.db_params, settings_data)
            print(f"[GUI] Zapisano ustawienia do DB z ID: {settings_id}")
            print("[GUI] Wysłano nowe nastawy do DB.")
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie udało się zapisać ustawień do DB: {str(e)}")
            return None

        return settings_data

    def _save_settings_to_plc(self, settings_data):
        """
        Przyjmuje słownik `settings_data` (taki jak zwracany przez _save_settings_to_db)
        i wysyła parametry do PLC asynchronicznie poprzez kolejkę.
        """
        if not settings_data:
            return  # Brak danych, nic nie robimy

        # Zbuduj komendę do zapisu w PLC:
        write_cmd = {
            "command": "write_plc_settings",
            "db_number": 2,
            "lump_threshold":    settings_data["lump_threshold"],
            "neck_threshold":    settings_data["neck_threshold"],
            "flaw_preset_diameter": settings_data["preset_diameter"],
            "upper_tol":         settings_data["diameter_over_tol"],
            "under_tol":         settings_data["diameter_under_tol"],
        }

        try:
            self.controller.plc_write_queue.put_nowait(write_cmd)
            print("[GUI] Komenda zapisu nastaw do PLC wysłana asynchronicznie.")
        except Exception as e:
            print(f"[GUI] Błąd przy wysyłaniu komendy do PLC: {e}")

    def _save_settings(self):
        """
        Główna metoda (np. podpięta pod przycisk).
        1. Najpierw zapisuje do bazy danych (metoda _save_settings_to_db).
        2. Jeśli się uda, wysyła parametry do PLC (metoda _save_settings_to_plc).
        """
        settings_data = self._save_settings_to_db()
        if settings_data is not None:
            # Zapis do bazy się udał, więc wysyłamy do PLC:
            self._save_settings_to_plc(settings_data)



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
                "entry_flaw_window": "2",
                "entry_max_lumps": "3",
                "entry_max_necks": "3",
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
        # Utwórz panel środkowy
        self.middle_panel = QFrame(self)
        self.middle_panel.setFrameShape(QFrame.Box)
        self.middle_panel.setFrameShadow(QFrame.Raised)
        self.middle_panel.setLineWidth(2)
        # Ustawienia rozmiaru panelu – tutaj możesz dostosować szerokość
        self.middle_panel.setMinimumWidth(400)
        self.middle_panel.setMaximumWidth(800)
        
        # Layout główny dla panelu środkowego
        middle_layout = QGridLayout(self.middle_panel)
        middle_layout.setContentsMargins(10, 10, 10, 10)
        middle_layout.setSpacing(10)
        self.middle_panel.setLayout(middle_layout)
        
        # Ramka główna z układem pionowym na wszystkie grupy
        self.readings_frame = QFrame(self.middle_panel)
        readings_layout = QVBoxLayout(self.readings_frame)
        readings_layout.setSpacing(15)
        self.readings_frame.setLayout(readings_layout)
        middle_layout.addWidget(self.readings_frame, 0, 0, 1, 1, Qt.AlignTop)
        
        # --------------------------
        # Grupa 1: Wymiary pojedynczych pomiarów
        # --------------------------
        group_measurements = QGroupBox("Wymiary pojedynczych pomiarów", self.readings_frame)
        measure_layout = QHBoxLayout()
        self.label_d1 = QLabel("d1 [mm]: --", group_measurements)
        self.label_d2 = QLabel("d2 [mm]: --", group_measurements)
        self.label_d3 = QLabel("d3 [mm]: --", group_measurements)
        self.label_d4 = QLabel("d4 [mm]: --", group_measurements)
        measure_layout.addWidget(self.label_d1)
        measure_layout.addWidget(self.label_d2)
        measure_layout.addWidget(self.label_d3)
        measure_layout.addWidget(self.label_d4)
        group_measurements.setLayout(measure_layout)
        readings_layout.addWidget(group_measurements)
        
        # --------------------------
        # Grupa 2: Średnie wartości
        # --------------------------
        group_avg = QGroupBox("Średnie wartości", self.readings_frame)
        avg_layout = QHBoxLayout()
        self.label_davg = QLabel("dAvg [mm]: --", group_avg)
        self.label_dmin = QLabel("dMin [mm]: --", group_avg)
        self.label_dmax = QLabel("dMax [mm]: --", group_avg)
        avg_layout.addWidget(self.label_davg)
        avg_layout.addWidget(self.label_dmin)
        avg_layout.addWidget(self.label_dmax)
        group_avg.setLayout(avg_layout)
        readings_layout.addWidget(group_avg)
        
        # --------------------------
        # Grupa 3: Statystyki
        # --------------------------
        group_stats = QGroupBox("Statystyki", self.readings_frame)
        stats_layout = QHBoxLayout()
        self.label_dsd = QLabel("dSD [mm]: --", group_stats)
        self.label_dov = QLabel("dOV [%]: --", group_stats)
        stats_layout.addWidget(self.label_dsd)
        stats_layout.addWidget(self.label_dov)
        group_stats.setLayout(stats_layout)
        readings_layout.addWidget(group_stats)
        
        # --------------------------
        # Grupa 4: Pozycja i prędkość
        # --------------------------
        group_pos_speed = QGroupBox("Pozycja i prędkość", self.readings_frame)
        pos_speed_layout = QHBoxLayout()
        self.label_xcoord = QLabel("xCoord [m]: --", group_pos_speed)
        
        pos_speed_layout.addWidget(self.label_xcoord)
        self.label_speed = QLabel("Speed [m/min]: --", group_pos_speed)
        pos_speed_layout.addWidget(self.label_speed)
        
        group_pos_speed.setLayout(pos_speed_layout)
        readings_layout.addWidget(group_pos_speed)
        
        default_font = QApplication.font()
        default_font.setPointSize(15)
        
        alarms_layout = QHBoxLayout()
        self.label_alarm_lumps = QLabel("Wybrzuszenia OK", self.readings_frame)
        self.label_alarm_lumps.setFont(default_font)
        alarms_layout.addWidget(self.label_alarm_lumps)

        self.label_alarm_necks = QLabel("Zagłębienia OK", self.readings_frame)
        self.label_alarm_necks.setFont(default_font)
        alarms_layout.addWidget(self.label_alarm_necks)

        alarms_layout.setAlignment(Qt.AlignCenter)
        readings_layout.addLayout(alarms_layout)

        # Wskaźniki średnicy
        self.label_diameter_indicator = QLabel("Średnica: OK", self.readings_frame)
        readings_layout.addWidget(self.label_diameter_indicator)
        self.diameter_deviation_label = QLabel("Odchylenie: 0.00 mm", self.readings_frame)
        readings_layout.addWidget(self.diameter_deviation_label)
        
        
        # --------------------------
        # Grupa 5: Szczegółowe statystyki dla flaw window dla średnic
        # --------------------------
        group_flaw_stats = QGroupBox("Szczegółowe statystyki dla flaw window dla średnic", self.readings_frame)
        flaw_stats_layout = QGridLayout()

        # Nagłówki kolumn
        headers = ["Średnica", "Średnia", "Odchylenie std.", "Min", "Max"]
        for idx, header in enumerate(headers):
            flaw_stats_layout.addWidget(QLabel(f"<b>{header}</b>"), 0, idx)

        # Dane dla średnic (inicjalizacja)
        diameters = ["D1", "D2", "D3", "D4"]
        self.flaw_stats_labels = {}

        for row, diameter in enumerate(diameters, start=1):
            flaw_stats_layout.addWidget(QLabel(f"{diameter}"), row, 0)

            # Tworzenie i dodawanie etykiet dla poszczególnych wartości
            for col, stat in enumerate(["mean", "std", "min", "max"], start=1):
                label = QLabel("--")
                flaw_stats_layout.addWidget(label, row, col)
                self.flaw_stats_labels[f"{diameter}_{stat}"] = label

        group_flaw_stats.setLayout(flaw_stats_layout)
        readings_layout.addWidget(group_flaw_stats)
        
        # # Create the terminal output field (using QPlainTextEdit)
        # self.terminal_output = QPlainTextEdit(self.middle_panel)
        # self.terminal_output.setReadOnly(True)
        # self.terminal_output.setFixedHeight(120)  # Adjust height as needed

        # # Add the terminal_output widget to the layout, e.g. in a new row:
        # middle_layout.addWidget(self.terminal_output, 1, 0)

        # # Set up the emitting stream to capture print output
        # self.emitting_stream = EmittingStream()
        # self.emitting_stream.textWritten.connect(self.terminal_output.insertPlainText)
        # sys.stdout = self.emitting_stream  # Redirect standard output to the terminal widget


    # ---------------------------------------------------------------------------------
    # 4. Prawa kolumna (row=1, col=2) – Wykres 
    # ---------------------------------------------------------------------------------
    def _create_right_panel(self):
        # Utwórz prawy panel jako QFrame i ustaw layout grid
        self.right_panel = QFrame(self)
        self.right_panel.setFrameShape(QFrame.Box)         # Sets a box around the frame
        self.right_panel.setFrameShadow(QFrame.Raised)       # Gives a raised (or Sunken) look
        self.right_panel.setLineWidth(2) 
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
        
        self.status_plot = pg.PlotWidget(title="Defekty na dystansie", parent=self.plot_frame)
        self.status_plot.setLabel('left', "Liczba defektów")
        self.status_plot.setLabel('bottom', "Dystans [m]")
        # self.status_plot.setYRange(0, 2.1)
        self.status_plot.showGrid(x=False, y=False)
        plot_frame_layout.addWidget(self.status_plot)

        # -------------------------------
        # Diameter plot – row 2
        # -------------------------------
        self.diameter_frame = QFrame(self.right_panel)
        diameter_frame_layout = QVBoxLayout(self.diameter_frame)
        self.diameter_frame.setLayout(diameter_frame_layout)
        right_layout.addWidget(self.diameter_frame, 2, 0)
        
        self.diameter_plot = pg.PlotWidget(title="Średnica uśredniona na dystansie", parent=self.diameter_frame)
        self.diameter_plot.setLabel('left', "Średnica [mm]")
        self.diameter_plot.setLabel('bottom', "Dystans [m]")
        self.diameter_plot.showGrid(x=False, y=False)
        diameter_frame_layout.addWidget(self.diameter_plot)
        
        # ---------------------------
        # FFT plot – row 3
        # ---------------------------
        self.fft_frame = QFrame(self.right_panel)
        fft_frame_layout = QVBoxLayout(self.fft_frame)
        self.fft_frame.setLayout(fft_frame_layout)
        right_layout.addWidget(self.fft_frame, 3, 0)
        
        self.fft_plot = pg.PlotWidget(title="Analiza FFT", parent=self.fft_frame)
        self.fft_plot.setLabel('left', "Amplituda")
        self.fft_plot.setLabel('bottom', "Częstotliwośc [Hz]")
        self.fft_plot.showGrid(x=False, y=False)
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
            from plc_helper import write_plc_data
            print("[GUI] Clearing reset bits")
            write_plc_data(
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
            from plc_helper import write_plc_data
            print("[GUI] Clearing ALL reset bits after Kwituj")
            write_plc_data(
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

        # Check diameter tolerance 
        diameter_preset = float(self.entry_diameter_setpoint.text() or 0.0)
        tolerance_plus = float(self.entry_tolerance_plus.text() or 0.5)
        tolerance_minus = float(self.entry_tolerance_minus.text() or 0.5)
     
        lower = diameter_preset - tolerance_minus
        upper = diameter_preset + tolerance_plus

        color = "black" if lower <= d1 <= upper else "red"
        self.label_d1.setText(f"<small>D1 [mm]:</small><br><span style='font-size: 40px; color:{color};'>{d1:.2f}</span>")

        color = "black" if lower <= d2 <= upper else "red"
        self.label_d2.setText(f"<small>D2 [mm]:</small><br><span style='font-size: 40px; color:{color};'>{d2:.2f}</span>")

        color = "black" if lower <= d3 <= upper else "red"
        self.label_d3.setText(f"<small>D3 [mm]:</small><br><span style='font-size: 40px; color:{color};'>{d3:.2f}</span>")

        color = "black" if lower <= d4 <= upper else "red"
        self.label_d4.setText(f"<small>D4 [mm]:</small><br><span style='font-size: 40px; color:{color};'>{d4:.2f}</span>")

        self.label_davg.setText(f"<small>dAvg [mm]:</small><br><span style='font-size: 40px;'>{davg:.2f}</span>")
        self.label_dmin.setText(f"<small>Dmin [mm]:</small><br><span style='font-size: 40px;'>{dmin:.2f}</span>")
        self.label_dmax.setText(f"<small>Dmax [mm]:</small><br><span style='font-size: 40px;'>{dmax:.2f}</span>")
        self.label_dsd.setText(f"<small>dSD [mm]:</small><br><span style='font-size: 40px;'>{dsd:.3f}</span>")
        self.label_dov.setText(f"<small>dOV [%]:</small><br><span style='font-size: 40px;'>{dov:.2f}</span>")
        
            
        # Get window data directly from the acquisition buffer, adds the sample to ensure it's processed
        self.window_processor.process_sample(
            data
        )
        
        # Get the window data directly from controller's acquisition buffer
        window_data = self.controller.acquisition_buffer.get_window_data()
        
        # Update current_x from window data
        self.current_x = window_data['current_x']
        
        # Update xCoord label
        self.label_xcoord.setText(f"<small>Dystans [m]:</small><br><span style='font-size: 20px;'>{self.current_x:.1f}</span>")

        # Process flaw detection - this is fast
        # Update flaw window size from UI
        try:
            flaw_window_size = float(self.entry_flaw_window.text() or "0.5")
            
        except ValueError:
            flaw_window_size = 0.95
        # self.controller.flaw_detector.update_flaw_window_size(flaw_window_size)
        current_x = data.get("xCoord", 0)
        self.current_x = current_x  # zapisujemy do pola, żeby mieć spójność

        # Obliczenie liczby próbek mieszczących się w bieżącym flaw window
        samples = list(self.controller.acquisition_buffer.samples)
        n = 0
        for sample in reversed(samples):
            if current_x - sample.get("xCoord", 0) <= flaw_window_size:
                n += 1
            else:
                break

        # Wyliczenie statystyk dla ostatnich n próbek
        stats = self.controller.acquisition_buffer.get_statistics(last_n=n)
        if stats:
            diameters = ["D1", "D2", "D3", "D4"]
            stats_keys = ["mean", "std", "min", "max"]

            for diameter in diameters:
                for stat_key in stats_keys:
                    label_key = f"{diameter}_{stat_key}"
                    value = stats.get(label_key, 0)
                    self.flaw_stats_labels[label_key].setText(f"{value:.2f}")


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

        

        # Prepare data for the plot manager using window_data from acquisition buffer
        self.plot_manager.plot_dirty = True
        
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
            'timestamp': time.time(),  
            'update_id': id(self) % 10000,  
            'processing_time': self.controller.processing_time,
        }

        if hasattr(self.controller, "fft_data") and self.controller.fft_data:
            plot_data.update(self.controller.fft_data)
        
        # Add debug log if we have data but no visible updates
        if self.controller.run_measurement:
            if window_data['x_history'] and len(window_data['x_history']) > 0:
                num_points = len(window_data['x_history'])
                # print(f"[MainPage] Plot data ready: {num_points} points, X range: {window_data['x_history'][0]:.1f}-{self.current_x:.1f}m")
            
            # Force a direct update in the main thread to ensure plots are visible even if process is not working
            if not hasattr(self.plot_manager, 'plot_process') or not self.plot_manager.plot_process or not self.plot_manager.plot_process.is_alive():
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
                self.plot_manager.update_fft_plot(
                    measurement_data=plot_data,
                    processing_time=plot_data.get('processing_time', 0)
                )

                # modulated_history = self.plot_manager.apply_pulsation(plot_data['diameter_history'], sample_rate=100, modulation_frequency=10, modulation_depth=0.5)
                # self.plot_manager.update_fft_plot(
                #     modulated_history,
                #     plot_data.get('fft_buffer_size', 512)
                # )
                
                
        else:
            # Optionally clear or skip plot updates when measurement is stopped.
            pass

    def update_alarm_labels(self):
        # Pobierz aktualne liczby defektów z flaw_detector (przyjmujemy, że jest dostępny przez self.controller.flaw_detector)
        current_lumps = self.controller.flaw_detector.flaw_lumps_count
        current_necks = self.controller.flaw_detector.flaw_necks_count

        # Pobierz maksymalne wartości ustawione przez użytkownika (konwersja na int, domyślnie 0 jeśli błąd)
        try:
            max_lumps = int(self.entry_max_lumps.text())
        except ValueError:
            max_lumps = 0

        try:
            max_necks = int(self.entry_max_necks.text())
        except ValueError:
            max_necks = 0

        # print(f"[GUI] Aktualizacja etykiet alarmowych: Wybrzuszenia: {current_lumps}/{max_lumps}, Zagłębienia: {current_necks}/{max_necks}")

        # Aktualizuj etykiety alarmowe (metoda show_alarm ustawia kolor i treść)
        self.show_alarm("Wybrzuszenia", current_lumps, max_lumps)
        self.show_alarm("Zagłębienia", current_necks, max_necks)

    def update_data(self):
        # Pobierz najnowsze dane z bufora akwizycji
        data = self.controller.acquisition_buffer.get_latest_data() or {}
        
        # Scal z danymi FFT, jeśli są dostępne
        if hasattr(self.controller, "fft_data") and self.controller.fft_data:
            data.update(self.controller.fft_data)
        
        # Przetwarzanie danych – przykładowo aktualizacja wykresów i odczytów
        self.update_readings(data)
        
        speed = data.get("speed", 0.0)
        self.label_speed.setText(f"<small>Speed [m/min]:</small><br><span style='font-size: 20px;'>{speed:.2f}</span>")
        self.update_alarm_labels()




    # def update_flaw_counts(self, lumps, necks):
    #     # Zakładając, że etykiety do wyświetlania wyników istnieją (np. self.label_alarm_lumps, self.label_alarm_necks)
    #     if hasattr(self, "label_alarm_lumps"):
    #         self.label_alarm_lumps.setText(f"Lumps: {lumps}")
    #     if hasattr(self, "label_alarm_necks"):
    #         self.label_alarm_necks.setText(f"Necks: {necks}")

