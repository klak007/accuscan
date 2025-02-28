# main_page.py
import customtkinter as ctk
import matplotlib
matplotlib.use("TkAgg")  # wymagane dla matplotlib + tkinter
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from db_helper import save_settings, save_settings_history
import matplotlib.pyplot as plt
from datetime import datetime
from tkinter import messagebox
from tkinter import simpledialog, messagebox
import db_helper
import plc_helper
from window_fft_analysis import analyze_window_fft
import time

class MainPage(ctk.CTkFrame):
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
        
        # Ustawiamy siatkę (3 kolumny):
        self.grid_rowconfigure(0, weight=0)  # top bar
        self.grid_rowconfigure(1, weight=1)  # reszta
        self.grid_columnconfigure(0, minsize=300, weight=0)  # lewa kolumna (batch / product)
        self.grid_columnconfigure(1, minsize=300, weight=0)  # środkowa kolumna (symulacja)
        self.grid_columnconfigure(2, weight=1)  # prawa kolumna (wykres + przyciski)

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
        self.last_plot_update = None  # <-- new attribute for plot update frequency
        
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

        self._create_top_bar()
        if self.controller.user_manager.current_user:
            self.btn_auth.configure(text="Log Out")
        self._create_left_panel()
        self._create_middle_panel()
        self._create_right_panel()

    # ---------------------------------------------------------------------------------
    # 1. Górna belka nawigacji (row=0, col=0..2)
    # ---------------------------------------------------------------------------------
    def _create_top_bar(self):
        self.top_bar = ctk.CTkFrame(self)
        self.top_bar.grid(row=0, column=0, columnspan=3, sticky="ew", padx=5, pady=(5, 0))

        # Create pomiary button with green highlight
        self.btn_pomiary = ctk.CTkButton(
            self.top_bar, 
            text="pomiary", 
            command=self._on_pomiary_click,
            fg_color="green",  # Set initial color to green
            hover_color="dark green"  # Darker green when hovering
        )
        
        self.btn_nastawy  = ctk.CTkButton(self.top_bar, text="nastawy",  command=lambda: self.controller.toggle_page("SettingsPage"))
        self.btn_historia  = ctk.CTkButton(self.top_bar, text="historia",  command=self._on_historia_click)
        self.btn_accuscan  = ctk.CTkButton(self.top_bar, text="Accuscan",  command=self._on_accuscan_click)
        # Single authentication button (toggle login/logout)
        self.btn_auth = ctk.CTkButton(self.top_bar, text="Log In", command=self._on_auth_click)

        self.btn_pomiary.pack(side="left", padx=5)
        self.btn_nastawy.pack(side="left", padx=5)
        self.btn_historia.pack(side="left", padx=5)
        self.btn_accuscan.pack(side="left", padx=5)
        self.btn_auth.pack(side="left", padx=5)
        
        # New control frame added for measurement buttons (Start/Stop/Kwituj)
        self.control_frame = ctk.CTkFrame(self.top_bar)
        self.control_frame.pack(side="right", padx=5)
        self.btn_start = ctk.CTkButton(self.control_frame, text="Start", command=self._on_start)
        self.btn_stop = ctk.CTkButton(self.control_frame, text="Stop", command=self._on_stop)
        self.btn_ack = ctk.CTkButton(self.control_frame, text="Kwituj", command=self._on_ack)
        self.btn_start.pack(side="left", padx=2)
        self.btn_stop.pack(side="left", padx=2)
        self.btn_ack.pack(side="left", padx=2)
        
        # Add exit button (aligned to the right)
        self.btn_exit = ctk.CTkButton(
            self.top_bar, 
            text="Exit", 
            command=self._on_exit_click,
            fg_color="red",
            hover_color="darkred"
        )
        self.btn_exit.pack(side="right", padx=5)

        self.ind_plc = ctk.CTkLabel(self.top_bar, text="PLC: Unknown")
        self.ind_plc.pack(side="right", padx=5)

    def _on_pomiary_click(self):
        print("[GUI] Kliknięto przycisk 'pomiary'.")

    def _on_nastawy_click(self):
        self.controller.show_settings_page()

    def _on_historia_click(self):
        print("[GUI] Kliknięto przycisk 'historia'.")

    def _on_accuscan_click(self):
        print("[GUI] Kliknięto przycisk 'Accuscan'.")

    def _on_auth_click(self):
        # If no user is logged in, prompt login dialog.
        if not self.controller.user_manager.current_user:
            self._show_login_dialog()
        else:
            # Log out the current user and update button text.
            self.controller.user_manager.logout()
            self.btn_auth.configure(text="Log In")
            print("[GUI] Wylogowano.")

    def _show_login_dialog(self):
        login_dialog = ctk.CTkToplevel(self)
        login_dialog.title("Log In")
        login_dialog.geometry("300x300")
        login_dialog.resizable(False, False)
        
        username_label = ctk.CTkLabel(login_dialog, text="Username:")
        username_label.pack(pady=(20, 5))
        username_entry = ctk.CTkEntry(login_dialog)
        username_entry.pack(pady=5)
        
        password_label = ctk.CTkLabel(login_dialog, text="Password:")
        password_label.pack(pady=(10, 5))
        password_entry = ctk.CTkEntry(login_dialog, show="*")
        password_entry.pack(pady=5)
        
        submit_btn = ctk.CTkButton(
            login_dialog, text="Submit",
            command=lambda: self._submit_login(username_entry, password_entry, login_dialog, submit_btn)
        )
        submit_btn.pack(pady=(15, 10))

    def _submit_login(self, username_entry, password_entry, dialog, submit_btn):
        username = username_entry.get()
        password = password_entry.get()
        if username and password:
            if self.controller.user_manager.login(username, password):
                submit_btn.configure(text="Zalogowano", fg_color="green")
                # Update the auth button text to "Log Out"
                self.btn_auth.configure(text="Log Out")
                dialog.after(1000, dialog.destroy)
            else:
                submit_btn.configure(text="Niepoprawne dane", fg_color="red")
        else:
            submit_btn.configure(text="Niepoprawne dane", fg_color="red")

    def _on_exit_click(self):
        """Safely close the application"""
        # Stop measurements
        self.controller.run_measurement = False
        # Close PLC connection through logic
        self.controller.logic.close_logic()
        # Destroy the main window
        self.controller.destroy()

    # ---------------------------------------------------------------------------------
    # 2. Lewa kolumna (row=1, col=0) – Batch, Product, itp.
    # ---------------------------------------------------------------------------------
    def _create_left_panel(self):
        self.left_panel = ctk.CTkFrame(self, width=400)  # increased from 200
        self.left_panel.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        self.left_panel.grid_columnconfigure(0, weight=1)

        self.label_batch = ctk.CTkLabel(self.left_panel, text="Batch")
        self.label_batch.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.entry_batch = ctk.CTkEntry(self.left_panel, placeholder_text="IADTX0000", width=180)
        self.entry_batch.grid(row=1, column=0, padx=5, pady=5)

        self.label_product = ctk.CTkLabel(self.left_panel, text="Produkt")
        self.label_product.grid(row=2, column=0, padx=5, pady=5, sticky="w")

        self.entry_product = ctk.CTkEntry(self.left_panel, placeholder_text="18X0600", width=180)
        self.entry_product.grid(row=3, column=0, padx=5, pady=5)

        self.btn_typowy = ctk.CTkButton(
            self.left_panel,
            text="Przykładowe nastawy",
            command=self._on_typowy_click
        )
        self.btn_typowy.grid(row=4, column=0, padx=5, pady=(10,5), sticky="ew")

        self.btn_save_settings = ctk.CTkButton(
            self.left_panel,
            text="Zapisz nastawy",
            command=self._save_settings
        )
        self.btn_save_settings.grid(row=5, column=0, padx=5, pady=15, sticky="ew")

        # # Add the simulation button below "Zapisz nastawy"
        # self.btn_simulation = ctk.CTkButton(
        #     self.left_panel,
        #     text="Włącz symulację",
        #     command=self._toggle_simulation,
        #     fg_color="blue",
        #     hover_color="dark blue"
        # )
        # self.btn_simulation.grid(row=6, column=0, padx=5, pady=5, sticky="ew")

        # # Indykatory lumps/necks
        # self.indicator_frame = ctk.CTkFrame(self.left_panel)
        # self.indicator_frame.grid(row=7, column=0, padx=5, pady=5, sticky="ew")
        
        # # Create a frame for indicators and counters
        # indicator_content = ctk.CTkFrame(self.indicator_frame)
        # indicator_content.pack(fill="x", expand=True)
        
        # # Left side - Lump indicator and counter
        # lump_frame = ctk.CTkFrame(indicator_content)
        # lump_frame.pack(side="left", padx=5)
        # self.label_lump_indicator = ctk.CTkLabel(lump_frame, text="Lump: Off")
        # self.label_lump_indicator.pack(pady=2)
        # self.lumps_count_label = ctk.CTkLabel(lump_frame, text="Count: 0")
        # self.lumps_count_label.pack(pady=2)
        
        # # Right side - Neck indicator and counter
        # neck_frame = ctk.CTkFrame(indicator_content)
        # neck_frame.pack(side="left", padx=5)
        # self.label_neck_indicator = ctk.CTkLabel(neck_frame, text="Neck: Off")
        # self.label_neck_indicator.pack(pady=2)
        # self.necks_count_label = ctk.CTkLabel(neck_frame, text="Count: 0")
        # self.necks_count_label.pack(pady=2)

        # # Right side - Diameter tolerance indicator
        # diameter_frame = ctk.CTkFrame(indicator_content)
        # diameter_frame.pack(side="left", padx=5)
        # self.label_diameter_indicator = ctk.CTkLabel(diameter_frame, text="Diameter: OK")
        # self.label_diameter_indicator.pack(pady=2)
        # self.diameter_deviation_label = ctk.CTkLabel(diameter_frame, text="Dev: 0.00 mm")
        # self.diameter_deviation_label.pack(pady=2)

        # =============================
        # NOWE POLE NASTAW DLA RECEPTURY
        # =============================
        row_start = 8  # Wstawiamy poniżej lumps/necks

        self.label_recipe_name = ctk.CTkLabel(self.left_panel, text="Nazwa receptury:")
        self.label_recipe_name.grid(row=row_start, column=0, padx=5, pady=(10,2), sticky="w")
        self.entry_recipe_name = ctk.CTkEntry(self.left_panel, placeholder_text="Recipe X", width=180)
        self.entry_recipe_name.grid(row=row_start+1, column=0, padx=5, pady=2)

        self.label_diameter_setpoint = ctk.CTkLabel(self.left_panel, text="Średnica docelowa [mm]:")
        self.label_diameter_setpoint.grid(row=row_start+2, column=0, padx=5, pady=(10,2), sticky="w")

        diameter_frame = ctk.CTkFrame(self.left_panel)
        diameter_frame.grid(row=row_start+3, column=0, sticky="w")

        self.btn_diam_decrease_05 = ctk.CTkButton(
            diameter_frame, text="--", width=30,
            command=lambda: self._adjust_diameter(-0.5)
        )
        self.btn_diam_decrease_05.grid(row=0, column=0, padx=2, pady=2)

        self.btn_diam_decrease_01 = ctk.CTkButton(
            diameter_frame, text="-", width=30,
            command=lambda: self._adjust_diameter(-0.1)
        )
        self.btn_diam_decrease_01.grid(row=0, column=1, padx=2, pady=2)

        self.entry_diameter_setpoint = ctk.CTkEntry(diameter_frame, placeholder_text="18.0", width=80)
        self.entry_diameter_setpoint.grid(row=0, column=2, padx=2, pady=2)

        self.btn_diam_increase_01 = ctk.CTkButton(
            diameter_frame, text="+", width=30,
            command=lambda: self._adjust_diameter(0.1)
        )
        self.btn_diam_increase_01.grid(row=0, column=3, padx=2, pady=2)

        self.btn_diam_increase_05 = ctk.CTkButton(
            diameter_frame, text="++", width=30,
            command=lambda: self._adjust_diameter(0.5)
        )
        self.btn_diam_increase_05.grid(row=0, column=4, padx=2, pady=2)

        self.label_tolerance_plus = ctk.CTkLabel(self.left_panel, text="Gorna granica (roznica od dAvg) [mm]:")
        self.label_tolerance_plus.grid(row=row_start+4, column=0, padx=5, pady=(10,2), sticky="w")

        plus_frame = ctk.CTkFrame(self.left_panel)
        plus_frame.grid(row=row_start+5, column=0, sticky="w")

        self.btn_tolerance_plus_dec_05 = ctk.CTkButton(
            plus_frame, text="--", width=30,
            command=lambda: self._adjust_tolerance_plus(-0.5)
        )
        self.btn_tolerance_plus_dec_05.grid(row=0, column=0, padx=2, pady=2)

        self.btn_tolerance_plus_dec_01 = ctk.CTkButton(
            plus_frame, text="-", width=30,
            command=lambda: self._adjust_tolerance_plus(-0.1)
        )
        self.btn_tolerance_plus_dec_01.grid(row=0, column=1, padx=2, pady=2)

        self.entry_tolerance_plus = ctk.CTkEntry(
            plus_frame, placeholder_text="0.5", width=80
        )
        self.entry_tolerance_plus.grid(row=0, column=2, padx=2, pady=2)

        self.btn_tolerance_plus_inc_01 = ctk.CTkButton(
            plus_frame, text="+", width=30,
            command=lambda: self._adjust_tolerance_plus(0.1)
        )
        self.btn_tolerance_plus_inc_01.grid(row=0, column=3, padx=2, pady=2)

        self.btn_tolerance_plus_inc_05 = ctk.CTkButton(
            plus_frame, text="++", width=30,
            command=lambda: self._adjust_tolerance_plus(0.5)
        )
        self.btn_tolerance_plus_inc_05.grid(row=0, column=4, padx=2, pady=2)

        self.label_tolerance_minus = ctk.CTkLabel(self.left_panel, text="Dolna granica  (roznica od dAvg) [mm]:")
        self.label_tolerance_minus.grid(row=row_start+6, column=0, padx=5, pady=(10,2), sticky="w")

        minus_frame = ctk.CTkFrame(self.left_panel)
        minus_frame.grid(row=row_start+7, column=0, sticky="w")

        self.btn_tolerance_minus_dec_05 = ctk.CTkButton(
            minus_frame, text="--", width=30,
            command=lambda: self._adjust_tolerance_minus(-0.5)
        )
        self.btn_tolerance_minus_dec_05.grid(row=0, column=0, padx=2, pady=2)

        self.btn_tolerance_minus_dec_01 = ctk.CTkButton(
            minus_frame, text="-", width=30,
            command=lambda: self._adjust_tolerance_minus(-0.1)
        )
        self.btn_tolerance_minus_dec_01.grid(row=0, column=1, padx=2, pady=2)

        self.entry_tolerance_minus = ctk.CTkEntry(
            minus_frame, placeholder_text="0.5", width=80
        )
        self.entry_tolerance_minus.grid(row=0, column=2, padx=2, pady=2)

        self.btn_tolerance_minus_inc_01 = ctk.CTkButton(
            minus_frame, text="+", width=30,
            command=lambda: self._adjust_tolerance_minus(0.1)
        )
        self.btn_tolerance_minus_inc_01.grid(row=0, column=3, padx=2, pady=2)

        self.btn_tolerance_minus_inc_05 = ctk.CTkButton(
            minus_frame, text="++", width=30,
            command=lambda: self._adjust_tolerance_minus(0.5)
        )
        self.btn_tolerance_minus_inc_05.grid(row=0, column=4, padx=2, pady=2)

        self.label_lump_threshold = ctk.CTkLabel(self.left_panel, text="Próg lumps [mm]:")
        self.label_lump_threshold.grid(row=row_start+8, column=0, padx=5, pady=(10,2), sticky="w")
        lumps_threshold_frame = ctk.CTkFrame(self.left_panel)
        lumps_threshold_frame.grid(row=row_start+9, column=0, sticky="w")

        self.btn_lump_thres_dec_05 = ctk.CTkButton(
            lumps_threshold_frame, text="--", width=30,
            command=lambda: self._adjust_lump_threshold(-0.5)
        )
        self.btn_lump_thres_dec_05.grid(row=0, column=0, padx=2, pady=2)

        self.btn_lump_thres_dec_01 = ctk.CTkButton(
            lumps_threshold_frame, text="-", width=30,
            command=lambda: self._adjust_lump_threshold(-0.1)
        )
        self.btn_lump_thres_dec_01.grid(row=0, column=1, padx=2, pady=2)

        self.entry_lump_threshold = ctk.CTkEntry(
            lumps_threshold_frame, placeholder_text="0.3", width=80
        )
        self.entry_lump_threshold.grid(row=0, column=2, padx=2, pady=2)

        self.btn_lump_thres_inc_01 = ctk.CTkButton(
            lumps_threshold_frame, text="+", width=30,
            command=lambda: self._adjust_lump_threshold(0.1)
        )
        self.btn_lump_thres_inc_01.grid(row=0, column=3, padx=2, pady=2)

        self.btn_lump_thres_inc_05 = ctk.CTkButton(
            lumps_threshold_frame, text="++", width=30,
            command=lambda: self._adjust_lump_threshold(0.5)
        )
        self.btn_lump_thres_inc_05.grid(row=0, column=4, padx=2, pady=2)

        self.label_neck_threshold = ctk.CTkLabel(self.left_panel, text="Próg necks [mm]:")
        self.label_neck_threshold.grid(row=row_start+10, column=0, padx=5, pady=(10,2), sticky="w")
        necks_threshold_frame = ctk.CTkFrame(self.left_panel)
        necks_threshold_frame.grid(row=row_start+11, column=0, sticky="w")

        self.btn_neck_thres_dec_05 = ctk.CTkButton(
            necks_threshold_frame, text="--", width=30,
            command=lambda: self._adjust_neck_threshold(-0.5)
        )
        self.btn_neck_thres_dec_05.grid(row=0, column=0, padx=2, pady=2)

        self.btn_neck_thres_dec_01 = ctk.CTkButton(
            necks_threshold_frame, text="-", width=30,
            command=lambda: self._adjust_neck_threshold(-0.1)
        )
        self.btn_neck_thres_dec_01.grid(row=0, column=1, padx=2, pady=2)

        self.entry_neck_threshold = ctk.CTkEntry(
            necks_threshold_frame, placeholder_text="0.3", width=80
        )
        self.entry_neck_threshold.grid(row=0, column=2, padx=2, pady=2)

        self.btn_neck_thres_inc_01 = ctk.CTkButton(
            necks_threshold_frame, text="+", width=30,
            command=lambda: self._adjust_neck_threshold(0.1)
        )
        self.btn_neck_thres_inc_01.grid(row=0, column=3, padx=2, pady=2)

        self.btn_neck_thres_inc_05 = ctk.CTkButton(
            necks_threshold_frame, text="++", width=30,
            command=lambda: self._adjust_neck_threshold(0.5)
        )
        self.btn_neck_thres_inc_05.grid(row=0, column=4, padx=2, pady=2)

        self.label_flaw_window = ctk.CTkLabel(self.left_panel, text="Flaw window [m]:")
        self.label_flaw_window.grid(row=row_start+12, column=0, padx=5, pady=(10,2), sticky="w")

        self.entry_flaw_window = ctk.CTkEntry(self.left_panel, placeholder_text="2.0", width=80)
        self.entry_flaw_window.grid(row=row_start+13, column=0, padx=5, pady=2)

        # Add new UI elements for max lumps/necks in flaw window
        self.label_max_lumps = ctk.CTkLabel(self.left_panel, text="Max lumps in flaw window:")
        self.label_max_lumps.grid(row=row_start+14, column=0, padx=5, pady=(10,2), sticky="w")

        max_lumps_frame = ctk.CTkFrame(self.left_panel)
        max_lumps_frame.grid(row=row_start+15, column=0, sticky="w")

        self.btn_max_lumps_dec = ctk.CTkButton(
            max_lumps_frame, text="-", width=30,
            command=lambda: self._adjust_max_lumps(-1)
        )
        self.btn_max_lumps_dec.grid(row=0, column=0, padx=2, pady=2)

        self.entry_max_lumps = ctk.CTkEntry(
            max_lumps_frame, placeholder_text="3", width=80
        )
        self.entry_max_lumps.grid(row=0, column=1, padx=2, pady=2)

        self.btn_max_lumps_inc = ctk.CTkButton(
            max_lumps_frame, text="+", width=30,
            command=lambda: self._adjust_max_lumps(1)
        )
        self.btn_max_lumps_inc.grid(row=0, column=2, padx=2, pady=2)

        self.label_max_necks = ctk.CTkLabel(self.left_panel, text="Max necks in flaw window:")
        self.label_max_necks.grid(row=row_start+16, column=0, padx=5, pady=(10,2), sticky="w")

        max_necks_frame = ctk.CTkFrame(self.left_panel)
        max_necks_frame.grid(row=row_start+17, column=0, sticky="w")

        self.btn_max_necks_dec = ctk.CTkButton(
            max_necks_frame, text="-", width=30,
            command=lambda: self._adjust_max_necks(-1)
        )
        self.btn_max_necks_dec.grid(row=0, column=0, padx=2, pady=2)

        self.entry_max_necks = ctk.CTkEntry(
            max_necks_frame, placeholder_text="3", width=80
        )
        self.entry_max_necks.grid(row=0, column=1, padx=2, pady=2)

        self.btn_max_necks_inc = ctk.CTkButton(
            max_necks_frame, text="+", width=30,
            command=lambda: self._adjust_max_necks(1)
        )
        self.btn_max_necks_inc.grid(row=0, column=2, padx=2, pady=2)

    def _adjust_diameter(self, delta: float):
        val_str = self.entry_diameter_setpoint.get() or "0"
        try:
            val = float(val_str)
        except ValueError:
            val = 0.0
        new_val = val + delta
        self.entry_diameter_setpoint.delete(0, "end")
        self.entry_diameter_setpoint.insert(0, f"{new_val:.1f}")

    def _adjust_tolerance_plus(self, delta: float):
        val_str = self.entry_tolerance_plus.get() or "0"
        try:
            val = float(val_str)
        except ValueError:
            val = 0.0
        new_val = val + delta
        self.entry_tolerance_plus.delete(0, "end")
        self.entry_tolerance_plus.insert(0, f"{new_val:.1f}")

    def _adjust_tolerance_minus(self, delta: float):
        val_str = self.entry_tolerance_minus.get() or "0"
        try:
            val = float(val_str)
        except ValueError:
            val = 0.0
        new_val = val + delta
        self.entry_tolerance_minus.delete(0, "end")
        self.entry_tolerance_minus.insert(0, f"{new_val:.1f}")

    def _adjust_lump_threshold(self, delta: float):
        val_str = self.entry_lump_threshold.get() or "0"
        try:
            val = float(val_str)
        except ValueError:
            val = 0.0
        new_val = val + delta
        self.entry_lump_threshold.delete(0, "end")
        self.entry_lump_threshold.insert(0, f"{new_val:.1f}")

    def _adjust_neck_threshold(self, delta: float):
        val_str = self.entry_neck_threshold.get() or "0"
        try:
            val = float(val_str)
        except ValueError:
            val = 0.0
        new_val = val + delta
        self.entry_neck_threshold.delete(0, "end")
        self.entry_neck_threshold.insert(0, f"{new_val:.1f}")

    def _adjust_max_lumps(self, delta: int):
        """Adjust the max lumps in flaw window value"""
        val_str = self.entry_max_lumps.get() or "0"
        try:
            val = int(val_str)
        except ValueError:
            val = 0
        new_val = max(0, val + delta)  # Ensure the value is not negative
        self.entry_max_lumps.delete(0, "end")
        self.entry_max_lumps.insert(0, f"{new_val}")

    def _adjust_max_necks(self, delta: int):
        """Adjust the max necks in flaw window value"""
        val_str = self.entry_max_necks.get() or "0"
        try:
            val = int(val_str)
        except ValueError:
            val = 0
        new_val = max(0, val + delta)  # Ensure the value is not negative
        self.entry_max_necks.delete(0, "end")
        self.entry_max_necks.insert(0, f"{new_val}")

    def _save_settings(self):
        """
        Zczytuje wartości z entry i zapisuje do bazy (settings + settings_register),
        a następnie wysyła parametry do PLC.
        """
        # 1. Zczytaj wartości z pól
        recipe_name = self.entry_recipe_name.get() or ""
        diameter_setpoint_str = self.entry_diameter_setpoint.get() or "18.0"
        tolerance_plus_str = self.entry_tolerance_plus.get() or "0.5"
        tolerance_minus_str = self.entry_tolerance_minus.get() or "0.5"
        lump_threshold_str = self.entry_lump_threshold.get() or "0.3"
        neck_threshold_str = self.entry_neck_threshold.get() or "0.3"
        flaw_window_str = self.entry_flaw_window.get() or "2.0"
        max_lumps_str = self.entry_max_lumps.get() or "3"
        max_necks_str = self.entry_max_necks.get() or "3"

        # Konwersje na float lub int
        diameter_setpoint = float(diameter_setpoint_str)
        tolerance_plus = float(tolerance_plus_str)
        tolerance_minus = float(tolerance_minus_str)
        lump_threshold = float(lump_threshold_str)
        neck_threshold = float(neck_threshold_str)
        flaw_window = float(flaw_window_str)
        max_lumps = int(max_lumps_str)
        max_necks = int(max_necks_str)

        # 2. Zbuduj słownik do zapisu w bazie, używając kluczy zgodnych z tymi oczekiwanymi przez db_helper:
        settings_data = {
            "recipe_name": recipe_name,
            "product_nr": self.entry_product.get() or "",
            "preset_diameter": diameter_setpoint,
            "diameter_over_tol": tolerance_plus,
            "diameter_under_tol": tolerance_minus,
            "lump_threshold": lump_threshold,
            "neck_threshold": neck_threshold,
            "flaw_window": flaw_window,
            "max_lumps_in_flaw_window": max_lumps,
            "max_necks_in_flaw_window": max_necks,
            # Dodatkowe wartości – możesz je ustawić na stałe lub odczytać z innych pól,
            # jeżeli są dostępne w interfejsie użytkownika:
            "diameter_window": 0.0,
            "diameter_std_dev": 0.0,
            "num_scans": 128,
            "diameter_histeresis": 0.0,
            "lump_histeresis": 0.0,
            "neck_histeresis": 0.0,
        }

        # 3. Zapis do bazy (settings + history)
        try:
            from db_helper import save_settings, save_settings_history
            settings_id = save_settings(self.controller.db_params, settings_data)
            # Jeśli chcesz, możesz także wywołać save_settings_history – funkcja save_settings
            # sama już ją wywołuje w niektórych implementacjach.
            print("[GUI] Wysłano nowe nastawy do DB.")
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie udało się zapisać ustawień do DB: {str(e)}")

        # 4. Zapis do PLC przez plc_helper:
        try:
            plc_helper.write_accuscan_out_settings(
                self.controller.logic.plc_client,  # zakładam, że połączenie do PLC mamy w logic
                db_number=2,  # np. DB2
                lump_threshold=lump_threshold,
                neck_threshold=neck_threshold,
                flaw_preset_diameter=diameter_setpoint,
                upper_tol=tolerance_plus,
                under_tol=tolerance_minus,
                zt=True  # Reset tolerancji
            )
            # Reset ZT in next cycle:
            self.after(100, lambda: plc_helper.write_accuscan_out_settings(
                self.controller.logic.plc_client,
                db_number=2,
                zt=False,
                lump_threshold=lump_threshold,
                neck_threshold=neck_threshold,
                flaw_preset_diameter=diameter_setpoint,
                upper_tol=tolerance_plus,
                under_tol=tolerance_minus
            ))
            print("[GUI] Wysłano nowe nastawy do PLC.")
        except Exception as e:
            print(f"[GUI] Błąd zapisu do PLC: {e}")


    def _on_speed_change(self, value: float):
        self.production_speed = float(value)
        self.speed_label.configure(text=f"Speed: {self.production_speed:.1f}")

    def _on_typowy_click(self):
        import datetime
        now = datetime.datetime.now()
        date_time_str = f"{now.day:02d}_{now.month:02d}_{now.hour:02d}_{now.minute:02d}"  # Format: dd_MM_HH_mm
        self.entry_batch.delete(0, "end")
        self.entry_batch.insert(0, f"btch_{date_time_str}")
        self.entry_product.delete(0, "end")
        self.entry_product.insert(0, f"prdct_{date_time_str}")
        self.entry_recipe_name.delete(0, "end")
        self.entry_recipe_name.insert(0, f"recipe_{date_time_str}")
        self.entry_diameter_setpoint.delete(0, "end")
        self.entry_diameter_setpoint.insert(0, "39")
        self.entry_tolerance_plus.delete(0, "end")
        self.entry_tolerance_plus.insert(0, "0.5")
        self.entry_tolerance_minus.delete(0, "end")
        self.entry_tolerance_minus.insert(0, "0.5")
        self.entry_lump_threshold.delete(0, "end")
        self.entry_lump_threshold.insert(0, "0.1")
        self.entry_neck_threshold.delete(0, "end")
        self.entry_neck_threshold.insert(0, "0.1")
        self.entry_flaw_window.delete(0, "end")
        self.entry_flaw_window.insert(0, "2.0")
        self.entry_max_lumps.delete(0, "end")
        self.entry_max_lumps.insert(0, "30")
        self.entry_max_necks.delete(0, "end")
        self.entry_max_necks.insert(0, "7")

    # ---------------------------------------------------------------------------------
    # 3. Środkowa kolumna (row=1, col=1) – parametry symulacji
    # ---------------------------------------------------------------------------------
    def _create_middle_panel(self):
        self.middle_panel = ctk.CTkFrame(self, width=800)
        self.middle_panel.grid(row=1, column=1, sticky="nsew", padx=10, pady=10)
        self.middle_panel.grid_columnconfigure(0, weight=1)

        # Dodaj ramkę odczytów u góry middle panel (row=0)
        self.readings_frame = ctk.CTkFrame(self.middle_panel)
        self.readings_frame.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        
        # Dodaj etykiety odczytów - wszystkie w jednej kolumnie
        self.label_d1 = ctk.CTkLabel(self.readings_frame, text="D1 [mm]: --")
        self.label_d2 = ctk.CTkLabel(self.readings_frame, text="D2 [mm]: --")
        self.label_d3 = ctk.CTkLabel(self.readings_frame, text="D3 [mm]: --")
        self.label_d4 = ctk.CTkLabel(self.readings_frame, text="D4 [mm]: --")
        self.label_davg = ctk.CTkLabel(self.readings_frame, text="dAVG [mm]: --")
        self.label_dmin = ctk.CTkLabel(self.readings_frame, text="Dmin [mm]: --")
        self.label_dmax = ctk.CTkLabel(self.readings_frame, text="Dmax [mm]: --")
        self.label_dsd = ctk.CTkLabel(self.readings_frame, text="dSD [mm]: --")
        self.label_dov = ctk.CTkLabel(self.readings_frame, text="dOV [%]: --")
        self.label_xcoord = ctk.CTkLabel(self.readings_frame, text="xCoord [m]: --")
        self.label_speed = ctk.CTkLabel(self.readings_frame, text="Speed [m/min]: --")
        
        # Pakowanie etykiet odczytów
        self.label_d1.pack(anchor="w", pady=2)
        self.label_d2.pack(anchor="w", pady=2)
        self.label_d3.pack(anchor="w", pady=2)
        self.label_d4.pack(anchor="w", pady=2)
        self.label_davg.pack(anchor="w", pady=2)
        self.label_dmin.pack(anchor="w", pady=2)
        self.label_dmax.pack(anchor="w", pady=2)
        self.label_dsd.pack(anchor="w", pady=2)
        self.label_dov.pack(anchor="w", pady=2)
        self.label_xcoord.pack(anchor="w", pady=2)
        self.label_speed.pack(anchor="w", pady=2)
        
        
        
        
        
        # Dodaj etykiety wskaźników bezpośrednio do readings_frame
        # Wskaźnik Lump i licznik
        self.label_lump_indicator = ctk.CTkLabel(self.readings_frame, text="Lump: Off")
        self.label_lump_indicator.pack(anchor="w", pady=2)
        self.lumps_count_label = ctk.CTkLabel(self.readings_frame, text="Count: 0")
        self.lumps_count_label.pack(anchor="w", pady=2)
        
        # Wskaźnik Neck i licznik
        self.label_neck_indicator = ctk.CTkLabel(self.readings_frame, text="Neck: Off")
        self.label_neck_indicator.pack(anchor="w", pady=2)
        self.necks_count_label = ctk.CTkLabel(self.readings_frame, text="Count: 0")
        self.necks_count_label.pack(anchor="w", pady=2)
        
        # Wskaźnik średnicy i odchylenie
        self.label_diameter_indicator = ctk.CTkLabel(self.readings_frame, text="Diameter: OK")
        self.label_diameter_indicator.pack(anchor="w", pady=2)
        self.diameter_deviation_label = ctk.CTkLabel(self.readings_frame, text="Dev: 0.00 mm")
        self.diameter_deviation_label.pack(anchor="w", pady=2)


        # Simulation parameters frame - now at row=1
        self.sim_frame = ctk.CTkFrame(self.middle_panel, fg_color="transparent") 
        self.sim_frame.grid(row=1, column=0, padx=5, pady=5, sticky="nsew")
        
        # Parametry symulacji
        self.label_lumps_chance = ctk.CTkLabel(self.sim_frame, text="Prawd. grudek:")
        self.label_lumps_chance.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.entry_lumps_chance = ctk.CTkEntry(self.sim_frame, placeholder_text="0.01")
        self.entry_lumps_chance.grid(row=0, column=1, padx=5, pady=5)

        self.label_necks_chance = ctk.CTkLabel(self.sim_frame, text="Prawd. przewężeń:")
        self.label_necks_chance.grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.entry_necks_chance = ctk.CTkEntry(self.sim_frame, placeholder_text="0.01")
        self.entry_necks_chance.grid(row=1, column=1, padx=5, pady=5)

        self.label_d1_mean = ctk.CTkLabel(self.sim_frame, text="d1 średnia:")
        self.label_d1_mean.grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.entry_d1_mean = ctk.CTkEntry(self.sim_frame, placeholder_text="18.0")
        self.entry_d1_mean.grid(row=2, column=1, padx=5, pady=5)

        self.label_d1_std = ctk.CTkLabel(self.sim_frame, text="d1 odchylenie:")
        self.label_d1_std.grid(row=3, column=0, padx=5, pady=5, sticky="w")
        self.entry_d1_std = ctk.CTkEntry(self.sim_frame, placeholder_text="0.1")
        self.entry_d1_std.grid(row=3, column=1, padx=5, pady=5)

        self.label_d2_mean = ctk.CTkLabel(self.sim_frame, text="d2 średnia:")
        self.label_d2_mean.grid(row=4, column=0, padx=5, pady=5, sticky="w")
        self.entry_d2_mean = ctk.CTkEntry(self.sim_frame, placeholder_text="18.0")
        self.entry_d2_mean.grid(row=4, column=1, padx=5, pady=5)

        self.label_d2_std = ctk.CTkLabel(self.sim_frame, text="d2 odchylenie:")
        self.label_d2_std.grid(row=5, column=0, padx=5, pady=5, sticky="w")
        self.entry_d2_std = ctk.CTkEntry(self.sim_frame, placeholder_text="0.1")
        self.entry_d2_std.grid(row=5, column=1, padx=5, pady=5)

        self.label_d3_mean = ctk.CTkLabel(self.sim_frame, text="d3 średnia:")
        self.label_d3_mean.grid(row=6, column=0, padx=5, pady=5, sticky="w")
        self.entry_d3_mean = ctk.CTkEntry(self.sim_frame, placeholder_text="18.0")
        self.entry_d3_mean.grid(row=6, column=1, padx=5, pady=5)

        self.label_d3_std = ctk.CTkLabel(self.sim_frame, text="d3 odchylenie:")
        self.label_d3_std.grid(row=7, column=0, padx=5, pady=5, sticky="w")
        self.entry_d3_std = ctk.CTkEntry(self.sim_frame, placeholder_text="0.1")
        self.entry_d3_std.grid(row=7, column=1, padx=5, pady=5)

        self.label_d4_mean = ctk.CTkLabel(self.sim_frame, text="d4 średnia:")
        self.label_d4_mean.grid(row=8, column=0, padx=5, pady=5, sticky="w")
        self.entry_d4_mean = ctk.CTkEntry(self.sim_frame, placeholder_text="18.0")
        self.entry_d4_mean.grid(row=8, column=1, padx=5, pady=5)

        self.label_d4_std = ctk.CTkLabel(self.sim_frame, text="d4 odchylenie:")
        self.label_d4_std.grid(row=9, column=0, padx=5, pady=5, sticky="w")
        self.entry_d4_std = ctk.CTkEntry(self.sim_frame, placeholder_text="0.1")
        self.entry_d4_std.grid(row=9, column=1, padx=5, pady=5)

        self.speed_label = ctk.CTkLabel(self.sim_frame, text="Prędkość symulacji:")
        self.speed_label.grid(row=11, column=0, padx=5, pady=5, sticky="w")
        
        self.speed_slider = ctk.CTkSlider(self.sim_frame, from_=0, to=100, command=self._on_speed_change)
        self.speed_slider.set(self.production_speed)
        self.speed_slider.grid(row=11, column=1, padx=5, pady=5, sticky="ew")
        
        self.speed_value_label = ctk.CTkLabel(self.sim_frame, text=f"Speed: {self.production_speed}")
        self.speed_value_label.grid(row=12, column=0, columnspan=2, padx=5, pady=5, sticky="w")

        self.btn_save_sim_settings = ctk.CTkButton(
            self.sim_frame, text="Zapisz symulację", command=self._save_sim_settings
        )
        self.btn_save_sim_settings.grid(row=13, column=0, columnspan=2, padx=5, pady=10, sticky="ew")

        # domyślnie chowamy parametry, jeśli symulacja nie jest aktywna
        self._toggle_simulation_visibility(False)

    def _toggle_simulation(self):
        # Check permissions
        if not self.controller.user_manager.is_admin():
            print("[GUI] Brak uprawnień do uruchomienia symulacji!")
            messagebox.showwarning("Brak uprawnień", 
                                "Musisz być zalogowany jako admin, aby włączyć symulację.")
            return
        
        # Toggle simulation state
        self.controller.use_simulation = not self.controller.use_simulation
        
        # Update button text and appearance based on state
        if self.controller.use_simulation:
            self.btn_simulation.configure(
                text="Wyłącz symulację",
                fg_color="orange", 
                hover_color="dark orange"
            )
            self._toggle_simulation_visibility(True)
        else:
            self.btn_simulation.configure(
                text="Włącz symulację",
                fg_color="blue",
                hover_color="dark blue"
            )
            self._toggle_simulation_visibility(False)
        
        print(f"[GUI] Symulacja={self.controller.use_simulation}")

    def _toggle_simulation_visibility(self, visible: bool):
        if visible:
            self.sim_frame.grid()
        else:
            self.sim_frame.grid_remove()

    def _save_sim_settings(self):
        d1_mean_str = self.entry_d1_mean.get()
        lumps_str = self.entry_lumps_chance.get()
        d2_mean_str = self.entry_d2_mean.get()
        d3_mean_str = self.entry_d3_mean.get()
        d4_mean_str = self.entry_d4_mean.get()
        d1_std_str = self.entry_d1_std.get()
        d2_std_str = self.entry_d2_std.get()
        d3_std_str = self.entry_d3_std.get()
        d4_std_str = self.entry_d4_std.get()
        necks_str = self.entry_necks_chance.get()

        # nastawy do symulatora
        if d1_mean_str:
            self.controller.simulator.d1_mean = float(d1_mean_str)
        if lumps_str:
            self.controller.simulator.lumps_chance = float(lumps_str)
        if d2_mean_str:
            self.controller.simulator.d2_mean = float(d2_mean_str)
        if d3_mean_str:
            self.controller.simulator.d3_mean = float(d3_mean_str)
        if d4_mean_str:
            self.controller.simulator.d4_mean = float(d4_mean_str)
        if d1_std_str:
            self.controller.simulator.d1_std = float(d1_std_str)
        if d2_std_str:
            self.controller.simulator.d2_std = float(d2_std_str)
        if d3_std_str:
            self.controller.simulator.d3_std = float(d3_std_str)
        if d4_std_str:
            self.controller.simulator.d4_std = float(d4_std_str)
        if necks_str:
            self.controller.simulator.necks_chance = float(necks_str)

        print("[GUI] Zapisano parametry symulacji w obiekcie simulator.")

    # ---------------------------------------------------------------------------------
    # 4. Prawa kolumna (row=1, col=2) – Wykres + przyciski
    # ---------------------------------------------------------------------------------
    def _create_right_panel(self):
        self.right_panel = ctk.CTkFrame(self)
        self.right_panel.grid(row=1, column=2, sticky="nsew", padx=10, pady=10)

        # Adjust grid: row 0 for buttons, rows 1-3 for plots
        self.right_panel.grid_rowconfigure(0, weight=0)  # buttons
        self.right_panel.grid_rowconfigure(1, weight=1)  # status plot
        self.right_panel.grid_rowconfigure(2, weight=1)  # diameter plot (was FFT plot)
        self.right_panel.grid_rowconfigure(3, weight=1)  # FFT plot (was diameter plot)
        self.right_panel.grid_columnconfigure(0, weight=1)

        self.plot_frame = ctk.CTkFrame(self.right_panel)
        self.plot_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        self.fig = plt.Figure(figsize=(5, 2), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas.get_tk_widget().pack(side="top", fill="both", expand=True)
        
        # Adjust figure layout to make room for axis labels
        self.fig.subplots_adjust(bottom=0.2, left=0.05, right=0.95)
        
        # Swap the order - diameter plot comes before FFT plot
        self.diameter_frame = ctk.CTkFrame(self.right_panel)
        self.diameter_frame.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)

        self.fig_diameter = plt.Figure(figsize=(5, 2), dpi=100)
        self.ax_diameter = self.fig_diameter.add_subplot(111)
        self.canvas_diameter = FigureCanvasTkAgg(self.fig_diameter, master=self.diameter_frame)
        self.canvas_diameter.get_tk_widget().pack(side="top", fill="both", expand=True)
        
        # Adjust figure layout to make room for axis labels
        self.fig_diameter.subplots_adjust(bottom=0.2, left=0.05, right=0.95)
        
        self.ax_diameter.set_title("Average Diameter History")
        self.ax_diameter.set_xlabel("Sample")
        self.ax_diameter.set_ylabel("Diameter [mm]")
        self.ax_diameter.grid(True)

        # FFT plot is now last
        self.fft_frame = ctk.CTkFrame(self.right_panel)
        self.fft_frame.grid(row=3, column=0, sticky="nsew", padx=5, pady=5)

        self.fig_fft = plt.Figure(figsize=(5, 2), dpi=100)
        self.ax_fft = self.fig_fft.add_subplot(111)
        self.canvas_fft = FigureCanvasTkAgg(self.fig_fft, master=self.fft_frame)
        self.canvas_fft.get_tk_widget().pack(side="top", fill="both", expand=True)
        
        # Adjust figure layout to make room for axis labels
        self.fig_fft.subplots_adjust(bottom=0.2, left=0.05, right=0.95)

        # Initialize plots
        self.ax.set_title("Lumps/Necks vs X-Coord")
        self.ax.set_xlabel("X-Coord")
        self.ax.set_ylabel("Status")
        self.ax.set_ylim(0, 2.1)
        self.ax.grid(False)

        self.ax_fft.set_title("FFT Analysis")
        self.ax_fft.set_xlabel("Frequency")
        self.ax_fft.set_ylabel("Magnitude")
        self.ax_fft.grid(True)

    def _on_start(self):
        print("[GUI] Start pressed!")
        self.controller.run_measurement = True

    def _on_stop(self):
        print("[GUI] Stop pressed!")
        self.controller.run_measurement = False

    def _on_ack(self):
        print("[GUI] Kwituj pressed!")

    # ---------------------------------------------------------------------------------
    # 5. Metoda update_readings – aktualizacja etykiet i wykresu
    # ---------------------------------------------------------------------------------
    def update_readings(self, data: dict):
        if data is None or (hasattr(data, "empty") and data.empty):
            return

        # Performance timing
        update_start = time.perf_counter()

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
        self.label_d1.configure(text=f"D1 [mm]: {d1:.2f}")
        self.label_d2.configure(text=f"D2 [mm]: {d2:.2f}")
        self.label_d3.configure(text=f"D3 [mm]: {d3:.2f}")
        self.label_d4.configure(text=f"D4 [mm]: {d4:.2f}")
        self.label_davg.configure(text=f"dAVG [mm]: {davg:.2f}")
        self.label_dmin.configure(text=f"Dmin [mm]: {dmin:.2f}")
        self.label_dmax.configure(text=f"Dmax [mm]: {dmax:.2f}")
        self.label_dsd.configure(text=f"dSD [mm]: {dsd:.3f}")
        self.label_dov.configure(text=f"dOV [%]: {dov:.2f}")

        # Update xCoord and speed labels
        self.label_xcoord.configure(text=f"xCoord [m]: {self.current_x:.1f}")
        self.label_speed.configure(text=f"Speed [m/min]: {self.production_speed:.1f}")

        # Indicators - this is fast
        lumps = data.get("lumps", 0)
        necks = data.get("necks", 0)
        if lumps:
            self.label_lump_indicator.configure(text="Lump ON", text_color="red")
        else:
            self.label_lump_indicator.configure(text="Lump OFF", text_color="green")
        if necks:
            self.label_neck_indicator.configure(text="Neck ON", text_color="red")
        else:
            self.label_neck_indicator.configure(text="Neck OFF", text_color="green")
        label_update_time = time.perf_counter() - label_update_start

        # Update data collections - this is fast
        data_update_start = time.perf_counter()
        # Mark plots as needing update
        self.plot_dirty = True
        
        # Data collection: store history
        self.lumps_history.append(lumps)
        self.necks_history.append(necks)

        # Aktualizacja xCoord – wykorzystujemy go jako oś X
        current_time = data.get("timestamp", datetime.now())
        dt = 0 if self.last_update_time is None else (current_time - self.last_update_time).total_seconds()
        self.last_update_time = current_time
        speed_mps = self.production_speed / 60.0
        self.current_x += dt * speed_mps
        self.x_history.append(self.current_x)
        
        # Tracking lumps and necks in flaw window
        # Get flaw window size from user input
        try:
            flaw_window_size = float(self.entry_flaw_window.get() or "2.0")
        except ValueError:
            flaw_window_size = 2.0
            
        # If there's a lump in current reading, add it to tracked lumps with current position
        if lumps > 0:
            self.flaw_lumps_coords.append(self.current_x)
            self.flaw_lumps_count += 1
            
        # If there's a neck in current reading, add it to tracked necks with current position
        if necks > 0:
            self.flaw_necks_coords.append(self.current_x)
            self.flaw_necks_count += 1
            
        # Remove lumps that are outside the flaw window (too old)
        while self.flaw_lumps_coords and self.flaw_lumps_coords[0] < (self.current_x - flaw_window_size):
            self.flaw_lumps_coords.pop(0)
            self.flaw_lumps_count -= 1
            
        # Remove necks that are outside the flaw window (too old)
        while self.flaw_necks_coords and self.flaw_necks_coords[0] < (self.current_x - flaw_window_size):
            self.flaw_necks_coords.pop(0)
            self.flaw_necks_count -= 1

        # Utrzymujemy ograniczenie historii do maksymalnie MAX_POINTS próbek
        # Nawet jeśli historia jest obcinana, zachowujemy współrzędne X dla poprawnego wykresu
        while len(self.lumps_history) > self.MAX_POINTS:
            self.lumps_history.pop(0)
            if len(self.x_history) > self.MAX_POINTS:
                self.x_history.pop(0)
                
        while len(self.necks_history) > self.MAX_POINTS:
            self.necks_history.pop(0)

        # Add to diameter history with x-coordinate
        self.diameter_history.append(davg)
        self.diameter_x.append(self.current_x)
        
        # Keep only MAX_POINTS samples in diameter history
        while len(self.diameter_history) > self.MAX_POINTS:
            self.diameter_x.pop(0)
            self.diameter_history.pop(0)
        data_update_time = time.perf_counter() - data_update_start

        # Add diameter tolerance status check - this is fast
        diameter_preset = float(self.entry_diameter_setpoint.get() or 0.0)
        tolerance_plus = float(self.entry_tolerance_plus.get() or 0.5)
        tolerance_minus = float(self.entry_tolerance_minus.get() or 0.5)
        
        deviation = davg - diameter_preset
        self.diameter_deviation_label.configure(text=f"Dev: {deviation:.2f} mm")
        
        if deviation > tolerance_plus:
            self.label_diameter_indicator.configure(text="Diameter: HIGH", text_color="red")
        elif deviation < -tolerance_minus:
            self.label_diameter_indicator.configure(text="Diameter: LOW", text_color="red")
        else:
            self.label_diameter_indicator.configure(text="Diameter: OK", text_color="green")

        # Update plots only if enough time has passed - this is slow
        # and likely the bottleneck causing spikes
        now = time.time()  
        plot_update_start = time.perf_counter()      
        if (self.last_plot_update is None or 
            (now - self.last_plot_update) >= self.min_plot_interval) and self.plot_dirty:
            self._update_plot()
            self.plot_dirty = False
            self.last_plot_update = now
        plot_update_time = time.perf_counter() - plot_update_start

        # Show counter updates
        counters = self.controller.logic.get_counters()
        self.lumps_count_label.configure(text=f"Count: {counters['lumps_count']} (Window: {self.flaw_lumps_count})")
        self.necks_count_label.configure(text=f"Count: {counters['necks_count']} (Window: {self.flaw_necks_count})")
        
        # Performance logging (only for slow updates)
        total_update_time = time.perf_counter() - update_start
        if total_update_time > 0.1:  # >100ms is considered slow
            print(f"[MainPage] Update time: {total_update_time:.4f}s | Labels: {label_update_time:.4f}s | Data: {data_update_time:.4f}s | Plot: {plot_update_time:.4f}s")


    def _update_plot(self):
        """Update all plots - this is an expensive operation."""
        try:
            plot_start = time.perf_counter()
            
            # OPTIMIZATION: Clear + reset axis is faster than creating new plots
            self.ax.clear()
    
            # Ustawienia osi i tytuł z informacją o batchu
            current_batch = self.entry_batch.get() or "NO BATCH"
            self.ax.set_title(f"Last {self.MAX_POINTS} samples - Batch: {current_batch}")
            self.ax.set_xlabel("X-Coord [m]")
            self.ax.set_ylabel("Błędy w cyklu")
            
            # Calculate the x-axis limits based on available data
            if self.x_history:
                x_min = self.x_history[0] if self.x_history else self.current_x - self.display_range
                x_max = self.current_x
                self.ax.set_xlim(x_min, x_max)
    
            # Use all collected data points (up to MAX_POINTS) rather than filtering by distance
            filtered_indices = list(range(len(self.x_history)))
            
            if filtered_indices:
                # Only plot visible data
                x_vals = [self.x_history[i] for i in filtered_indices]
                lumps_vals = [self.lumps_history[i] for i in filtered_indices]
                necks_vals = [self.necks_history[i] for i in filtered_indices]
                
                # OPTIMIZATION: Use numpy for bar plotting
                import numpy as np
                x_vals = np.array(x_vals)
                width = 0.3  # szerokość słupka w jednostkach x (metry)
                
                # OPTIMIZATION: Use faster plotting methods with reduced options
                self.ax.bar(x_vals - width/2, lumps_vals, width=width, color="red", label="Lumps")
                self.ax.bar(x_vals + width/2, necks_vals, width=width, color="blue", label="Necks")
    
                self.ax.legend()
            plot1_time = time.perf_counter() - plot_start
            
            # OPTIMIZATION: Only update plots if they're visible
            # FFT plot - update separately to avoid unnecessary work
            fft_start = time.perf_counter()
            self.ax_fft.clear()
            import numpy as np
            diameter_array = np.array(self.diameter_history[-self.FFT_BUFFER_SIZE:], dtype=np.float32)
            if len(diameter_array) > 0:  # Only calculate if we have data
                from window_fft_analysis import analyze_window_fft
                diameter_fft = analyze_window_fft(diameter_array)
                self.ax_fft.set_title("Diameter FFT Analysis")
                self.ax_fft.plot(np.abs(diameter_fft), label="FFT", color="green")
                self.ax_fft.legend()
                self.ax_fft.grid(True)
            fft_time = time.perf_counter() - fft_start
            
            # OPTIMIZATION: Diameter plot - update separately
            diameter_start = time.perf_counter()
            self.ax_diameter.clear()
            if self.diameter_history:
                self.ax_diameter.set_title(f"Average Diameter History - Last {self.MAX_POINTS} samples")
                
                # Plot all diameter points directly - no downsampling needed
                self.ax_diameter.plot(self.diameter_x, self.diameter_history, 'g-', label='Actual')
                
                # Horizontal target line
                diameter_preset = float(self.entry_diameter_setpoint.get() or 0.0)
                self.ax_diameter.axhline(y=diameter_preset, color='r', linestyle='--', label='Preset')
                
                self.ax_diameter.set_xlabel("X-Coord [m]")
                self.ax_diameter.set_ylabel("Diameter [mm]")
                
                # Optimize y-axis limits
                y_min = min(min(self.diameter_history), diameter_preset)
                y_max = max(max(self.diameter_history), diameter_preset)
                margin = (y_max - y_min) * 0.2
                lower_bound = max(y_min - margin, 0)
                upper_bound = y_max + margin
                self.ax_diameter.set_ylim(lower_bound, upper_bound)
                
                # Set x-axis limits to match the data window
                if self.diameter_x:
                    x_min = self.diameter_x[0]
                    x_max = self.current_x
                    self.ax_diameter.set_xlim(x_min, x_max)
                self.ax_diameter.grid(True)
                self.ax_diameter.legend()
            diameter_time = time.perf_counter() - diameter_start
            
            # OPTIMIZATION: Draw all canvas at once after updates
            draw_start = time.perf_counter()
            self.canvas.draw()
            self.canvas_fft.draw()
            self.canvas_diameter.draw()
            draw_time = time.perf_counter() - draw_start
            
            total_plot_time = time.perf_counter() - plot_start
            # Log plot time if it's slow
            if total_plot_time > 0.1:
                print(f"[Plot] Total: {total_plot_time:.4f}s | Main: {plot1_time:.4f}s | FFT: {fft_time:.4f}s | Diameter: {diameter_time:.4f}s | Draw: {draw_time:.4f}s")
                
        except Exception as e:
            print(f"Error updating plot: {e}")

    def _on_speed_change(self, value: float):
        self.production_speed = float(value)
        self.speed_value_label.configure(text=f"Speed: {self.production_speed:.1f}")

    def update_data(self):
        df = self.controller.data_mgr.get_current_data()
        if not df.empty:
            data = df.iloc[-1].to_dict()  # select the most recent row as a dict
            self.update_readings(data)

    def update_connection_indicators(self):
        import plc_helper
        plc_connected = plc_helper.is_plc_connected(self.controller.logic)
        if plc_connected:
            self.ind_plc.configure(text="PLC: OK", text_color="green")
        else:
            self.ind_plc.configure(text="PLC: OFF", text_color="red")

