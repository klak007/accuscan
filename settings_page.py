import mysql.connector
from mysql.connector import Error
from datetime import datetime
from db_helper import check_database
from PyQt5.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox, QLineEdit, QTableWidgetItem, QDialog, QApplication, QShortcut, QMenu, QAction, QCheckBox
from PyQt5.QtGui import QFont, QKeySequence
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QSpacerItem, QSizePolicy, QTableWidget, QHeaderView
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox
from edit_setting import EditSettingDialog  # import klasy dialogu
class SettingsPage(QFrame):
    """
    Strona ustawień aplikacji – umożliwia przeglądanie, filtrowanie, edycję i zarządzanie recepturami (ustawieniami) dla danego produktu.
    """
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Utwórz główny layout (np. grid) dla tego widgetu
        main_layout = QGridLayout(self)
        self.setLayout(main_layout)

        # Zachowujemy istniejący top bar (przy założeniu, że _create_top_bar zostało przepisane na PyQt)
        self._create_top_bar()

        # Dodajemy nowy panel zarządzania recepturami poniżej top baru
        self.main_frame = QFrame(self)
        main_frame_layout = QGridLayout(self.main_frame)
        self.main_frame.setLayout(main_frame_layout)
        main_layout.addWidget(self.main_frame, 1, 0)  # np. w wierszu 1, kolumna 0

        self._create_filter_panel()
        self._create_table()
        self._create_action_buttons()

        # Status bazy danych
        self.status_frame = QFrame(self.main_frame)
        status_layout = QHBoxLayout(self.status_frame)
        self.status_frame.setLayout(status_layout)
        status_layout.setContentsMargins(5, 5, 5, 5)

        self.db_status_label = QLabel("Status bazy danych: Sprawdzanie...", self.status_frame)
        status_layout.addWidget(self.db_status_label)

        self.btn_check_db = QPushButton("Sprawdź połączenie", self.status_frame)
        self.btn_check_db.setFixedSize(200, 40)
        self.btn_check_db.clicked.connect(self.check_db_connection)
        status_layout.addWidget(self.btn_check_db)

        # Dodaj status_frame do main_frame – przykładowo w wierszu 3, kolumna 0
        main_frame_layout.addWidget(self.status_frame, 3, 0)
        main_layout.addWidget(self.top_bar, 0, 0) # FIXED: Changed self.layout to main_layout
        # Załaduj dane przy inicjalizacji, jeśli baza jest dostępna
        if controller.db_connected:
            self.load_data()
        else:
            self.show_offline_message()
            self.update_db_status()

    def check_db_connection(self):
        """Sprawdza połączenie z bazą danych i aktualizuje status."""
        self.controller.db_connected = check_database(self.controller.db_params)
        self.update_db_status()
        if self.controller.db_connected:
            QMessageBox.information(self, "Połączenie z bazą danych", "Połączenie z bazą danych jest aktywne.")
            self.load_data()
        else:
            QMessageBox.warning(self, "Problem z bazą danych", "Nie można połączyć się z bazą danych. Dostęp do ustawień jest ograniczony.")    
    
    def update_db_status(self):
        """Aktualizuje etykietę statusu połączenia z bazą."""
        if self.controller.db_connected:
            self.db_status_label.setText("Status bazy danych: Połączono")
            self.db_status_label.setStyleSheet("color: green;")
        else:
            self.db_status_label.setText("Status bazy danych: Brak połączenia")
            self.db_status_label.setStyleSheet("color: red;")

    def show_offline_message(self):
        """Wyświetla informację o braku dostępu do bazy danych w widoku tabeli."""
        # Note: No equivalent in QTableWidget like tree.delete/insert - need to clear and add rows
        self.table.setRowCount(0)
        self.table.insertRow(0)
        for col in range(self.table.columnCount()):
            text = "<Błąd bazy danych>" if col == 1 else "-"
            if col == 2:
                text = "Funkcje edycji niedostępne"
            item = QTableWidgetItem(text)
            self.table.setItem(0, col, item)

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

        # Pomiary - F2
        self.btn_pomiary = QPushButton("Pomiary (F2)", self.top_bar)
        self.btn_pomiary.setFont(top_bar_font)
        self.btn_pomiary.setFixedSize(140, 40)
        self.btn_pomiary.clicked.connect(self._on_pomiary_click)
        top_bar_layout.addWidget(self.btn_pomiary, 0, Qt.AlignLeft)

        shortcut_pomiary = QShortcut(QKeySequence('F2'), self)
        shortcut_pomiary.activated.connect(self.btn_pomiary.click)

        # Nastawy - F3
        self.btn_nastawy = QPushButton("Nastawy (F3)", self.top_bar)
        self.btn_nastawy.setFont(top_bar_font)
        self.btn_nastawy.setFixedSize(140, 40)
        top_bar_layout.addWidget(self.btn_nastawy, 0, Qt.AlignLeft)

        shortcut_nastawy = QShortcut(QKeySequence('F3'), self)
        shortcut_nastawy.activated.connect(self.btn_nastawy.click)

        # Historia - F4
        self.btn_historia = QPushButton("Historia (F4)", self.top_bar)
        self.btn_historia.setFont(top_bar_font)
        self.btn_historia.setFixedSize(140, 40)
        self.btn_historia.clicked.connect(self._on_historia_click)
        top_bar_layout.addWidget(self.btn_historia, 0, Qt.AlignLeft)

        shortcut_historia = QShortcut(QKeySequence('F4'), self)
        shortcut_historia.activated.connect(self.btn_historia.click)

        # Accuscan - F5
        self.btn_accuscan = QPushButton("Accuscan (F5)", self.top_bar)
        self.btn_accuscan.setFont(top_bar_font)
        self.btn_accuscan.setFixedSize(140, 40)
        self.btn_accuscan.clicked.connect(self._on_accuscan_click)
        top_bar_layout.addWidget(self.btn_accuscan, 0, Qt.AlignLeft)

        shortcut_accuscan = QShortcut(QKeySequence('F5'), self)
        shortcut_accuscan.activated.connect(self.btn_accuscan.click)

        spacer = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        top_bar_layout.addItem(spacer)

        self.btn_exit = QPushButton("Zamknij", self.top_bar)
        self.btn_exit.setFont(top_bar_font)
        self.btn_exit.setFixedSize(140, 40)
        self.btn_exit.setStyleSheet("background-color: red;")
        self.btn_exit.clicked.connect(self._on_exit_click)
        top_bar_layout.addWidget(self.btn_exit, 0, Qt.AlignRight)

        self.plc_status_label = QLabel("PLC Status: Unknown", self.top_bar)
        top_bar_layout.addWidget(self.plc_status_label, 0, Qt.AlignRight)

    def _on_pomiary_click(self):
        self.controller.toggle_page("MainPage")

    def _on_historia_click(self):
        self.controller.toggle_page("HistoryPage")

    def _on_accuscan_click(self):
        print("[GUI] Kliknięto przycisk 'Accuscan'.")

    def _on_exit_click(self):
        if hasattr(self.controller, "run_measurement_flag"):
            self.controller.run_measurement_flag.value = 0
        if hasattr(self.controller, "process_running_flag"):
            self.controller.process_running_flag.value = 0
        self.controller.destroy()

    def _create_filter_panel(self):
        # Utwórz kontener (QFrame) dla panelu filtru w ramach main_frame
        self.filter_frame = QFrame(self.main_frame)
        filter_layout = QHBoxLayout(self.filter_frame)
        filter_layout.setContentsMargins(5, 5, 5, 5)
        filter_layout.setSpacing(5)
        
        # Przycisk "Wybierz kolumny" otwierający dialog wyboru kolumn
        self.btn_choose_columns = QPushButton("Wybierz kolumny", self.filter_frame)
        self.btn_choose_columns.setFixedSize(200, 40)
        self.btn_choose_columns.clicked.connect(self.open_column_selector_dialog)
        filter_layout.addWidget(self.btn_choose_columns)

        # Etykieta "Filtruj po produkcie:"
        self.filter_label = QLabel("Filtruj po produkcie:", self.filter_frame)
        filter_layout.addWidget(self.filter_label)
        
        # Pole tekstowe do wpisywania filtru, o stałej szerokości 200 pikseli
        self.filter_entry = QLineEdit(self.filter_frame)
        self.filter_entry.setFixedSize(600,40)
        filter_layout.addWidget(self.filter_entry)
        
        # Przycisk "Filtruj" – po kliknięciu wywołuje metodę load_data
        self.btn_filter = QPushButton("Filtruj", self.filter_frame)
        self.btn_filter.setFixedSize(200,40)
        self.btn_filter.clicked.connect(self.load_data)
        filter_layout.addWidget(self.btn_filter)
        
        # Przycisk "Wszystkie" – wywołuje metodę clear_filter
        self.btn_all = QPushButton("Wszystkie", self.filter_frame)
        self.btn_all.setFixedSize(200,40)
        self.btn_all.clicked.connect(self.clear_filter)
        filter_layout.addWidget(self.btn_all)
        
        # Przycisk "Odśwież" – wywołuje metodę load_data
        self.btn_reload = QPushButton("Odśwież", self.filter_frame)
        self.btn_reload.setFixedSize(200,40)
        self.btn_reload.clicked.connect(self.load_data)
        filter_layout.addWidget(self.btn_reload)
        
        # Dodaj panel filtru do głównego layoutu main_frame
        # Załóżmy, że main_frame ma przypisany QGridLayout; przykładowo dodajemy w wierszu 0, kolumnie 0
        self.main_frame.layout().addWidget(self.filter_frame, 0, 0)

    def open_column_selector_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Wybierz kolumny")
        layout = QVBoxLayout(dialog)
        
        # Lista kolumn – kolejność musi odpowiadać kolejności kolumn w metodzie _create_table
        columns = [
            "ID",
            "Nazwa receptury",
            "Nr produktu",
            "Docelowa\nśrednica",
            "Tolerancja średnicy\npowyżej",
            "Tolerancja średnicy\nponiżej",
            "Próg\nwybrzuszeń",
            "Próg\nwgłębień",
            "Długość okna\ndefektów",
            "Maksymalna liczba wybrzuszeń\nw oknie defektów",
            "Maksymalna liczba wgłębień\nw oknie defektów",
            "Próg\n pulsacji",
            "maks. owalność",
            "maks. odch. standardowe",
            "Data i godzina\nutworzenia"
        ]
        
        # Słownik przechowujący utworzone checkboxy
        checkboxes = {}
        for idx, col_name in enumerate(columns):
            cb = QCheckBox(col_name)
            # Ustawiamy stan początkowy na podstawie aktualnej widoczności kolumny
            cb.setChecked(not self.table.isColumnHidden(idx))
            checkboxes[idx] = cb
            layout.addWidget(cb)
        
        # Dodajemy przycisk zatwierdzający zmiany
        confirm_button = QPushButton("Zatwierdź")
        layout.addWidget(confirm_button)
        
        # Po kliknięciu przycisku aktualizujemy widoczność kolumn i zamykamy dialog
        confirm_button.clicked.connect(lambda: self.apply_column_visibility(checkboxes, dialog))
        
        dialog.exec_()

    def apply_column_visibility(self, checkboxes, dialog):
        # Iterujemy po checkboxach i ustawiamy widoczność kolumn w tabeli
        for idx, checkbox in checkboxes.items():
            self.table.setColumnHidden(idx, not checkbox.isChecked())
        dialog.accept()


    def clear_filter(self):
        self.filter_entry.clear()  # Use clear() instead of delete(0, "end")
        self.load_data()

    def _create_table(self):
        # Utwórz kontener dla tabeli
        self.table_container = QFrame(self.main_frame)
        table_layout = QGridLayout(self.table_container)
        self.table_container.setLayout(table_layout)
        table_layout.setRowStretch(0, 1)
        table_layout.setColumnStretch(0, 1)
        
        # Definicja kolumn – przykładowo
        columns = [
            "ID",
            "Nazwa receptury",
            "Nr produktu",
            "Docelowa\nśrednica",
            "Tolerancja średnicy\npowyżej",
            "Tolerancja średnicy\nponiżej",
            "Próg\nwybrzuszeń",
            "Próg\nwgłębień",
            "Długość okna\ndefektów",
            "Maksymalna liczba wybrzuszeń\nw oknie defektów",
            "Maksymalna liczba wgłębień\nw oknie defektów",
            "Próg\n pulsacji",
            "maks. owalność",
            "maks. odch. standardowe",
            "Data i godzina\nutworzenia"
        ]
        
        # Utwórz QTableWidget z odpowiednią liczbą kolumn
        self.table = QTableWidget(0, len(columns), self.table_container)
        self.table.setHorizontalHeaderLabels([col.replace("_", " ").title() for col in columns])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignCenter)
        for i, col in enumerate(columns):
            header.setSectionResizeMode(i, QHeaderView.Interactive)
            if col == "Nazwa receptury":
                self.table.setColumnWidth(i, 200)  # szersza kolumna
            elif col == "ID":
                self.table.setColumnWidth(i, 30)
            elif col == "Nr produktu":
                self.table.setColumnWidth(i, 180)  # szersza kolumna
            elif col == "Data i godzina\nutworzenia":
                self.table.setColumnWidth(i, 50)   # węższa kolumna
            elif col in ["Próg\nwybrzuszeń", "Próg\nwgłębień", "Próg\n pulsacji", "Długość okna\ndefektów", "Docelowa\nśrednica"]:
                self.table.setColumnWidth(i, 90)
            elif col in ["Maksymalna liczba wybrzuszeń\nw oknie defektów", "Maksymalna liczba wgłębień\nw oknie defektów"]:
                self.table.setColumnWidth(i, 200)
            else:
                self.table.setColumnWidth(i, 140)  # domyślna szerokość
        header.setStretchLastSection(True)
        
        table_layout.addWidget(self.table, 0, 0)
        # QTableWidget ma wbudowane paski przewijania – dodatkowy scrollbar nie jest potrzebny.

        # Dodaj table_container do main_frame
        self.main_frame.layout().addWidget(self.table_container, 1, 0)

    def _create_action_buttons(self):
        # Utwórz kontener dla przycisków akcji
        self.actions_frame = QFrame(self.main_frame)
        actions_layout = QHBoxLayout(self.actions_frame)
        actions_layout.setContentsMargins(5, 5, 5, 5)
        actions_layout.setSpacing(5)
        self.actions_frame.setLayout(actions_layout)
        
        self.btn_new = QPushButton("Nowa", self.actions_frame)
        self.btn_new.setFixedHeight(40)
        self.btn_new.clicked.connect(self.new_setting)
        actions_layout.addWidget(self.btn_new)
        
        self.btn_clone = QPushButton("Klonuj", self.actions_frame)
        self.btn_clone.setFixedHeight(40)
        self.btn_clone.clicked.connect(self.clone_setting)
        actions_layout.addWidget(self.btn_clone)
        
        self.btn_edit = QPushButton("Edytuj", self.actions_frame)
        self.btn_edit.setFixedHeight(40)
        self.btn_edit.clicked.connect(self.edit_setting)
        actions_layout.addWidget(self.btn_edit)
        
        self.btn_delete = QPushButton("Usuń", self.actions_frame)
        self.btn_delete.setFixedHeight(40)
        self.btn_delete.clicked.connect(self.delete_setting)
        actions_layout.addWidget(self.btn_delete)

        self.btn_load_current = QPushButton("Załaduj do aktualnych nastaw", self.actions_frame)
        self.btn_load_current.setFixedHeight(40)
        self.btn_load_current.clicked.connect(self.load_current_settings)
        actions_layout.addWidget(self.btn_load_current)
        
        # Dodaj actions_frame do main_frame – przykładowo w wierszu 2, kolumna 0
        self.main_frame.layout().addWidget(self.actions_frame, 2, 0)

    def load_data(self):
        # Usuń wszystkie wiersze w tabeli
        self.table.setRowCount(0)
        
        # Sprawdzamy, czy jest połączenie z bazą
        if not check_database(self.controller.db_params):
            self.controller.db_connected = False
            self.show_offline_message()
            self.update_db_status()
            return

        try:
            connection = mysql.connector.connect(**self.controller.db_params)
            cursor = connection.cursor(dictionary=True)
            
            filter_text = self.filter_entry.text().strip()
            if filter_text:
                sql = "SELECT * FROM settings WHERE `Product nr` LIKE %s ORDER BY `Id Settings` DESC"
                cursor.execute(sql, (f"%{filter_text}%",))
            else:
                sql = """
                    SELECT `Id Settings` AS id_settings, `Recipe name`, `Product nr`, `Preset Diameter`, 
                        `Diameter Over tolerance`, `Diameter Under tolerance`, `Lump threshold`, 
                        `Neck threshold`, `Flaw Window`, `Max lumps in flaw window`, 
                        `Max necks in flaw window`, `Pulsation_threshold`, `Max_ovality`, `Max_standard_deviation`, `created_at`
                    FROM settings 
                    ORDER BY id_settings DESC
                """
                cursor.execute(sql)
            
            rows = cursor.fetchall()
            
            for row in rows:
                id_val = row.get("id_settings") or row.get("Id Settings")
                recipe_name = row.get("Recipe name") or ""
                product_nr = row.get("Product nr") or ""
                preset_diameter = row.get("Preset Diameter") or 0
                diameter_over_tol = row.get("Diameter Over tolerance") or 0
                diameter_under_tol = row.get("Diameter Under tolerance") or 0
                lump_threshold = row.get("Lump threshold") or 0
                neck_threshold = row.get("Neck threshold") or 0
                flaw_window = row.get("Flaw Window") or 0
                max_lumps_in_flaw_window = row.get("Max lumps in flaw window") or 3
                max_necks_in_flaw_window = row.get("Max necks in flaw window") or 3
                pulsation_threshold = row.get("Pulsation_threshold") or 0
                max_ovality = row.get("Max_ovality") or 0
                max_standard_deviation = row.get("Max_standard_deviation") or 0
                created_at = row.get("created_at")
                if created_at:
                    created_at = created_at.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    created_at = ""
                
                current_row = self.table.rowCount()
                self.table.insertRow(current_row)
                
                values = [
                    str(id_val), recipe_name, product_nr, str(preset_diameter),
                    str(diameter_over_tol), str(diameter_under_tol), str(lump_threshold),
                    str(neck_threshold), str(flaw_window), str(max_lumps_in_flaw_window),
                    str(max_necks_in_flaw_window), str(pulsation_threshold),
                    str(max_ovality), str(max_standard_deviation), created_at
                ]
                
                for col, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setTextAlignment(Qt.AlignCenter)
                    self.table.setItem(current_row, col, item)

            
            if connection and connection.is_connected():
                connection.close()
            
            # Aktualizacja statusu bazy danych
            self.controller.db_connected = True
            self.update_db_status()
                    
        except mysql.connector.Error as e:
            # QMessageBox.warning(self, "Błąd połączenia z bazą", 
                # f"Nie można połączyć się z bazą danych: {str(e)}\nAplikacja będzie działać w trybie ograniczonym.")
            print(self,f"Nie można połączyć się z bazą danych: {str(e)}. Aplikacja będzie działać w trybie ograniczonym.")
            self.show_offline_message()
            self.controller.db_connected = False
            self.update_db_status()
        except Exception as e:
            QMessageBox.warning(self, "Błąd", f"Wystąpił nieoczekiwany błąd: {str(e)}")

    def load_current_settings(self):
        """Kopiowanie ustawień z wybranej receptury do głównych nastaw na stronie głównej."""

        selected_items = self.table.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Brak wybranej receptury", "Proszę wybrać recepturę z listy.")
            return

        # Ponieważ tryb selekcji to pojedynczy wiersz, pobieramy numer pierwszego zaznaczonego wiersza
        row = selected_items[0].row()

        # Zakładając, że kolumny są w tej kolejności:
        # 0: id, 1: recipe_name, 2: product_nr, 3: preset_diameter,
        # 4: diameter_over_tol, 5: diameter_under_tol, 6: lump_threshold, 7: neck_threshold, ...
        recipe_name = self.table.item(row, 1).text() if self.table.item(row, 1) else ""
        product_nr = self.table.item(row, 2).text() if self.table.item(row, 2) else ""
        preset_diameter = self.table.item(row, 3).text() if self.table.item(row, 3) else ""
        diameter_over_tol = self.table.item(row, 4).text() if self.table.item(row, 4) else ""
        diameter_under_tol = self.table.item(row, 5).text() if self.table.item(row, 5) else ""
        lump_threshold = self.table.item(row, 6).text() if self.table.item(row, 6) else ""
        neck_threshold = self.table.item(row, 7).text() if self.table.item(row, 7) else ""
        flaw_window = self.table.item(row, 8).text() if self.table.item(row, 8) else ""
        max_lumps_in_flaw_window = self.table.item(row, 9).text() if self.table.item(row, 9) else ""
        max_necks_in_flaw_window = self.table.item(row, 10).text() if self.table.item(row, 10) else ""
        pulsation_threshold = self.table.item(row, 11).text() if self.table.item(row, 11) else ""
        max_ovality = self.table.item(row, 12).text() if self.table.item(row, 12) else ""
        max_standard_deviation = self.table.item(row, 13).text() if self.table.item(row, 13) else ""

        # Teraz ustawiamy te wartości w lewym panelu strony głównej
        main_page = self.controller.main_page
        main_page.entry_recipe_name.setText(recipe_name)
        main_page.entry_product.setText(product_nr)
        main_page.entry_diameter_setpoint.setText(preset_diameter)
        main_page.entry_tolerance_plus.setText(diameter_over_tol)
        main_page.entry_tolerance_minus.setText(diameter_under_tol)
        main_page.entry_lump_threshold.setText(lump_threshold)
        main_page.entry_neck_threshold.setText(neck_threshold)
        main_page.entry_flaw_window.setText(flaw_window)
        main_page.entry_max_lumps.setText(max_lumps_in_flaw_window)
        main_page.entry_max_necks.setText(max_necks_in_flaw_window)
        main_page.entry_pulsation_threshold.setText(pulsation_threshold)
        main_page.entry_max_ovality.setText(max_ovality)
        main_page.entry_max_std_dev.setText(max_standard_deviation)

        QMessageBox.information(self, "Załadowano", "Ustawienia zostały załadowane do aktualnych nastaw.")

         # Dodatkowo, wysyłamy te ustawienia do PLC
        try:
            write_cmd = {
                "command": "write_plc_settings",
                "db_number": 2,
                "lump_threshold": float(lump_threshold) if lump_threshold else 0.0,
                "neck_threshold": float(neck_threshold) if neck_threshold else 0.0,
                "flaw_preset_diameter": float(preset_diameter) if preset_diameter else 0.0,
                "upper_tol": float(diameter_over_tol) if diameter_over_tol else 0.0,
                "under_tol": float(diameter_under_tol) if diameter_under_tol else 0.0
            }
            self.controller.plc_write_queue.put_nowait(write_cmd)
            print("[GUI] Ustawienia zostały wysłane do PLC po załadowaniu do aktualnych nastaw.")
        except Exception as e:
            print(f"[GUI] Błąd przy wysyłaniu ustawień do PLC: {e}")


    def open_edit_modal(self, values=None, clone=False):
        # Tworzymy i wyświetlamy nasz dialog
        dialog = EditSettingDialog(
            controller=self.controller,  # przekazujemy referencję do kontrolera
            parent=self,
            values=values,
            clone=clone
        )
        # Uruchamiamy dialog modalnie
        if dialog.exec_() == QDialog.Accepted:
            # Jeśli użytkownik zatwierdził zmiany (dialog wywołał self.accept()),
            # odświeżamy tabelę:
            self.load_data()

    def new_setting(self):
        if not self.controller.db_connected and not check_database(self.controller.db_params):
            QMessageBox.warning(self, "Brak połączenia z bazą",
                                "Nie można dodać nowej receptury bez połączenia z bazą danych.")
            return
        self.open_edit_modal(values=None, clone=False)

    def clone_setting(self):
        # Sprawdź połączenie przed operacją
        if not self.controller.db_connected and not check_database(self.controller.db_params):
            QMessageBox.warning(self, "Brak połączenia z bazą",
                                "Nie można klonować receptury bez połączenia z bazą danych.")
            return
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "Ostrzeżenie", "Wybierz recepturę do klonowania.")
            return
        row = selected_rows[0].row()
        # Pobierz dane z wybranego wiersza
        values = []
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            values.append(item.text() if item else "")
        self.open_edit_modal(values, clone=True)

    def edit_setting(self):
        # Sprawdź połączenie przed operacją
        if not self.controller.db_connected and not check_database(self.controller.db_params):
            QMessageBox.warning(self, "Brak połączenia z bazą",
                                "Nie można edytować receptury bez połączenia z bazą danych.")
            return
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "Ostrzeżenie", "Wybierz recepturę do edycji.")
            return
        row = selected_rows[0].row()
        values = []
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            values.append(item.text() if item else "")
        self.open_edit_modal(values, clone=False)

    def delete_setting(self):
        # Sprawdź połączenie przed operacją
        if not self.controller.db_connected and not check_database(self.controller.db_params):
            QMessageBox.warning(self, "Brak połączenia z bazą",
                                "Nie można usunąć receptury bez połączenia z bazą danych.")
            return
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "Ostrzeżenie", "Wybierz recepturę do usunięcia.")
            return
        reply = QMessageBox.question(self, "Potwierdzenie", 
                                    "Czy na pewno chcesz usunąć wybraną recepturę?",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            row = selected_rows[0].row()
            # Załóżmy, że pierwsza kolumna zawiera ID receptury
            setting_id_item = self.table.item(row, 0)
            setting_id = setting_id_item.text() if setting_id_item else None
            if setting_id is None:
                QMessageBox.warning(self, "Błąd", "Nie udało się uzyskać ID receptury.")
                return
            try:
                connection = mysql.connector.connect(**self.controller.db_params)
                cursor = connection.cursor()
                sql = "DELETE FROM settings WHERE `Id Settings` = %s"
                cursor.execute(sql, (setting_id,))
                connection.commit()
                QMessageBox.information(self, "Sukces", "Receptura usunięta.")
                self.load_data()
                if connection and connection.is_connected():
                    connection.close()
            except mysql.connector.Error as e:
                QMessageBox.warning(self, "Błąd połączenia z bazą", 
                                    f"Nie można połączyć się z bazą danych: {str(e)}\nOperacja nie została wykonana.")
            except Exception as e:
                QMessageBox.warning(self, "Błąd", f"Wystąpił nieoczekiwany błąd: {str(e)}")
