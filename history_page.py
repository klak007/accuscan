import mysql.connector
from mysql.connector import Error
from PyQt5.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTableWidget, QTableWidgetItem, QMessageBox, QSpacerItem, QSizePolicy, QHeaderView, QApplication, QComboBox  
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QFont, QKeySequence
from PyQt5.QtWidgets import QShortcut, QDateEdit
from db_helper import check_database

class HistoryPage(QFrame):
    """
    Strona historii – wyświetla zdarzenia alarmów w trybie tylko do odczytu.
    Dane odczytywane są z bazy i mogą być filtrowane po dacie, batchu i produkcie.
    """
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Główny layout
        main_layout = QGridLayout(self)
        self.setLayout(main_layout)

        # Top bar (nawigacja między stronami)
        self._create_top_bar()
        main_layout.addWidget(self.top_bar, 0, 0)

        # Główny panel
        self.main_frame = QFrame(self)
        main_frame_layout = QGridLayout(self.main_frame)
        self.main_frame.setLayout(main_frame_layout)
        main_layout.addWidget(self.main_frame, 1, 0)

        # Panel filtrów
        self._create_filter_panel()

        # Tabela do wyświetlania historii
        self._create_table()

        # Panel statusu bazy danych
        self.status_frame = QFrame(self.main_frame)
        self.offset = 0
        self.base_query = ""
        status_layout = QHBoxLayout(self.status_frame)
        self.status_frame.setLayout(status_layout)
        status_layout.setContentsMargins(5, 5, 5, 5)

        self.db_status_label = QLabel("Status bazy danych: Sprawdzanie...", self.status_frame)
        status_layout.addWidget(self.db_status_label)

        self.btn_check_db = QPushButton("Sprawdź połączenie", self.status_frame)
        self.btn_check_db.setFixedSize(200, 40)
        self.btn_check_db.clicked.connect(self.check_db_connection)
        status_layout.addWidget(self.btn_check_db)

        self.btn_load_200 = QPushButton("Załaduj kolejne 200", self.status_frame)
        self.btn_load_200.setFixedSize(200, 40)
        self.btn_load_200.clicked.connect(lambda: self.load_more(200))
        status_layout.addWidget(self.btn_load_200)

        self.btn_load_1000 = QPushButton("Załaduj kolejne 1000", self.status_frame)
        self.btn_load_1000.setFixedSize(200, 40)
        self.btn_load_1000.clicked.connect(lambda: self.load_more(1000))
        status_layout.addWidget(self.btn_load_1000)

        main_frame_layout.addWidget(self.status_frame, 3, 0)

        # Ładowanie danych przy inicjalizacji
        if controller.db_connected:
            self.load_data()
        else:
            self.show_offline_message()
            self.update_db_status()

    def _create_top_bar(self):
        self.top_bar = QFrame(self)
        self.top_bar.setFrameShape(QFrame.Box)
        self.top_bar.setLineWidth(2)
        self.top_bar.setFrameShadow(QFrame.Raised)
        self.top_bar.setStyleSheet("fusion")
        top_bar_layout = QHBoxLayout(self.top_bar)
        top_bar_layout.setContentsMargins(5, 5, 5, 5)
        top_bar_layout.setSpacing(5)
        top_bar_font = QFont(QApplication.font())
        top_bar_font.setPointSize(12)
        top_bar_font.setBold(False)

        # Przycisk Pomiary
        self.btn_pomiary = QPushButton("Pomiary (F2)", self.top_bar)
        self.btn_pomiary.setFont(top_bar_font)
        self.btn_pomiary.setFixedSize(140, 40)
        self.btn_pomiary.clicked.connect(lambda: self.controller.toggle_page("MainPage"))
        top_bar_layout.addWidget(self.btn_pomiary)
        QShortcut(QKeySequence('F2'), self).activated.connect(self.btn_pomiary.click)

        # Przycisk Nastawy
        self.btn_nastawy = QPushButton("Nastawy (F3)", self.top_bar)
        self.btn_nastawy.setFont(top_bar_font)
        self.btn_nastawy.setFixedSize(140, 40)
        self.btn_nastawy.clicked.connect(lambda: self.controller.toggle_page("SettingsPage"))
        top_bar_layout.addWidget(self.btn_nastawy)
        QShortcut(QKeySequence('F3'), self).activated.connect(self.btn_nastawy.click)

        # Przycisk Historia (aktywny)
        self.btn_historia = QPushButton("Historia (F4)", self.top_bar)
        self.btn_historia.setFont(top_bar_font)
        self.btn_historia.setFixedSize(140, 40)
        top_bar_layout.addWidget(self.btn_historia)
        QShortcut(QKeySequence('F4'), self).activated.connect(self.btn_historia.click)

        # Przycisk Accuscan
        self.btn_accuscan = QPushButton("Accuscan (F5)", self.top_bar)
        self.btn_accuscan.setFont(top_bar_font)
        self.btn_accuscan.setFixedSize(140, 40)
        self.btn_accuscan.clicked.connect(lambda: self.controller.toggle_page("AccuscanPage"))
        top_bar_layout.addWidget(self.btn_accuscan)
        QShortcut(QKeySequence('F5'), self).activated.connect(self.btn_accuscan.click)

        spacer = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        top_bar_layout.addItem(spacer)

        # Przycisk Zamknij
        self.btn_exit = QPushButton("Zamknij", self.top_bar)
        self.btn_exit.setFont(top_bar_font)
        self.btn_exit.setFixedSize(140, 40)
        self.btn_exit.setStyleSheet("background-color: red;")
        self.btn_exit.clicked.connect(self.controller.destroy)
        top_bar_layout.addWidget(self.btn_exit)

        # Status PLC
        self.plc_status_label = QLabel("PLC Status: Unknown", self.top_bar)
        top_bar_layout.addWidget(self.plc_status_label)

    def _create_filter_panel(self):
        self.filter_frame = QFrame(self.main_frame)
        filter_layout = QHBoxLayout(self.filter_frame)
        filter_layout.setContentsMargins(5, 5, 5, 5)
        filter_layout.setSpacing(5)

        # Filtruj od daty
        self.start_date_label = QLabel("Od daty:", self.filter_frame)
        filter_layout.addWidget(self.start_date_label)

        self.start_date_edit = QDateEdit(self.filter_frame)
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.start_date_edit.setDate(QDate.currentDate())
        filter_layout.addWidget(self.start_date_edit)

        # Filtruj do daty
        self.end_date_label = QLabel("Do daty:", self.filter_frame)
        filter_layout.addWidget(self.end_date_label)

        self.end_date_edit = QDateEdit(self.filter_frame)
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.end_date_edit.setDate(QDate.currentDate())
        filter_layout.addWidget(self.end_date_edit)

        # Filtruj po batchu
        self.batch_label = QLabel("Filtruj po batchu:", self.filter_frame)
        filter_layout.addWidget(self.batch_label)
        self.batch_entry = QLineEdit(self.filter_frame)
        self.batch_entry.setFixedSize(150, 40)
        filter_layout.addWidget(self.batch_entry)

        # Filtruj po produkcie
        self.product_label = QLabel("Filtruj po produkcie:", self.filter_frame)
        filter_layout.addWidget(self.product_label)
        self.product_entry = QLineEdit(self.filter_frame)
        self.product_entry.setFixedSize(150, 40)
        filter_layout.addWidget(self.product_entry)

        # Filtruj po typie alarmu
        self.alarm_label = QLabel("Filtruj po typie alarmu:", self.filter_frame)
        filter_layout.addWidget(self.alarm_label)

        self.alarm_combo = QComboBox(self.filter_frame)
        self.alarm_combo.setFixedSize(150, 40)

        # Dodajemy opcję "Wszystkie", która oznacza brak filtra
        self.alarm_combo.addItem("Wszystkie")
        self.alarm_combo.addItem("defects_alarm")
        self.alarm_combo.addItem("pulsation_error")
        self.alarm_combo.addItem("diameter_error")
        self.alarm_combo.addItem("std_dev_high")
        self.alarm_combo.addItem("ovality_high")

        filter_layout.addWidget(self.alarm_combo)

        # Przycisk Filtruj
        self.btn_filter = QPushButton("Filtruj", self.filter_frame)
        self.btn_filter.setFixedSize(150, 40)
        self.btn_filter.clicked.connect(self.load_data)
        filter_layout.addWidget(self.btn_filter)

        # Przycisk Wszystkie
        self.btn_all = QPushButton("Wszystkie", self.filter_frame)
        self.btn_all.setFixedSize(150, 40)
        self.btn_all.clicked.connect(self.clear_filter)
        filter_layout.addWidget(self.btn_all)

        # Przycisk Odśwież
        self.btn_reload = QPushButton("Odśwież", self.filter_frame)
        self.btn_reload.setFixedSize(150, 40)
        self.btn_reload.clicked.connect(self.load_data)
        filter_layout.addWidget(self.btn_reload)

        self.main_frame.layout().addWidget(self.filter_frame, 0, 0)


    def _create_table(self):
        self.table_container = QFrame(self.main_frame)
        table_layout = QGridLayout(self.table_container)
        self.table_container.setLayout(table_layout)

        # Zmodyfikowana lista kolumn – teraz osobno "Data" i "Godzina"
        columns = [
            "Data", "Godzina", "Batch", "Produkt", "D1", "D2", "D3", "D4",
            "Liczba flawów", "Liczba necków", "Koordynat", "Komentarz", "Typ alarmu"
        ]
        self.table = QTableWidget(0, len(columns), self.table_container)
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)

        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignCenter)
        for i, col in enumerate(columns):
            header.setSectionResizeMode(i, QHeaderView.Interactive)
            self.table.setColumnWidth(i, 120)
        header.setStretchLastSection(True)

        table_layout.addWidget(self.table, 0, 0)
        self.main_frame.layout().addWidget(self.table_container, 1, 0)

    def check_db_connection(self):
        self.controller.db_connected = check_database(self.controller.db_params)
        self.update_db_status()
        if self.controller.db_connected:
            QMessageBox.information(self, "Połączenie z bazą danych", "Połączenie z bazą danych jest aktywne.")
            self.load_data()
        else:
            QMessageBox.warning(self, "Problem z bazą danych", "Nie można połączyć się z bazą danych.")

    def update_db_status(self):
        if self.controller.db_connected:
            self.db_status_label.setText("Status bazy danych: Połączono")
            self.db_status_label.setStyleSheet("color: green;")
        else:
            self.db_status_label.setText("Status bazy danych: Brak połączenia")
            self.db_status_label.setStyleSheet("color: red;")

    def show_offline_message(self):
        self.table.setRowCount(0)
        self.table.insertRow(0)
        for col in range(self.table.columnCount()):
            text = "<Brak połączenia z bazą>" if col == 0 else "-"
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(0, col, item)

    def clear_filter(self):
        self.batch_entry.clear()
        self.product_entry.clear()
        self.alarm_entry.clear()
        # pomijamy daty → ignorujemy je tylko przy tej jednej akcji
        self.load_data(ignore_date=True)

    def load_data(self, ignore_date=False):
        self.table.setRowCount(0)
        self.offset = 0

        if not check_database(self.controller.db_params):
            self.controller.db_connected = False
            self.show_offline_message()
            self.update_db_status()
            return

        filters = []
        if not ignore_date:
            start = self.start_date_edit.date().toString("yyyy-MM-dd")
            end   = self.end_date_edit.date().toString("yyyy-MM-dd")
            filters.append(f"DATE(`Date time`) >= '{start}'")
            filters.append(f"DATE(`Date time`) <= '{end}'")

        for col, val in (
            ("Batch nr", self.batch_entry.text().strip()),
            ("Product nr", self.product_entry.text().strip())
        ):
            if val:
                filters.append(f"{col} LIKE '%{val}%'")

        # Filtruj po typie alarmu tylko, gdy nie wybrano opcji "Wszystkie"
        selected_alarm = self.alarm_combo.currentText().strip()
        if selected_alarm and selected_alarm != "Wszystkie":
            filters.append(f"alarm_type = '{selected_alarm}'")

        self.base_query = """
            SELECT DATE_FORMAT(`Date time`, '%Y-%m-%d') AS data,
                DATE_FORMAT(`Date time`, '%H:%i:%s') AS godzina,
                `Batch nr` AS batch, `Product nr` AS produkt,
                D1, D2, D3, D4,
                `lumps number of` AS flaws, `necks number of` AS necks,
                `X-coordinate` AS koordynat, comment, alarm_type
            FROM event
        """
        if filters:
            self.base_query += " WHERE " + " AND ".join(filters)

        sql = self.base_query + " ORDER BY `Date time` DESC LIMIT 500"
        self._execute_and_populate(sql)
        self.offset = self.table.rowCount()
        self.controller.db_connected = True
        self.update_db_status()

    def load_more(self, count):
        if not self.controller.db_connected:
            return

        sql = self.base_query + f" ORDER BY `Date time` DESC LIMIT {self.offset}, {count}"
        added = self._execute_and_populate(sql, append=True)
        self.offset += added

    def _execute_and_populate(self, sql, append=False):
        connection = mysql.connector.connect(**self.controller.db_params)
        cursor = connection.cursor(dictionary=True)
        cursor.execute(sql)
        rows = cursor.fetchall()
        start_row = self.table.rowCount() if append else 0

        for row in rows:
            idx = self.table.rowCount()
            self.table.insertRow(idx)
            values = [
                row["data"], row["godzina"], row["batch"], row["produkt"],
                row["D1"], row["D2"], row["D3"], row["D4"],
                row["flaws"], row["necks"], row["koordynat"],
                row["comment"], row["alarm_type"]
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(idx, col, item)

        connection.close()
        return len(rows)
