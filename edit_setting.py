import mysql.connector
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox, QMessageBox
)
from PyQt5.QtCore import Qt

class EditSettingDialog(QDialog):
    def __init__(self, controller, parent=None, values=None, clone=False):
        super().__init__(parent)
        self.controller = controller
        self.values = values
        self.clone = clone
        
        if values is None:
            self.setWindowTitle("Nowa Receptura")
        else:
            self.setWindowTitle("Klonuj Recepturę" if clone else "Edytuj Recepturę")
        
        self.setFixedSize(400, 600)  # Rozmiar okna dialogowego
        
        # Layout główny
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 10, 20, 10)
        self.layout.setSpacing(10)
        
        # Pola do wprowadzania danych – klucz: label_text, docelowy klucz w bazie, index w values
        self.fields_map = [
            ("Nazwa receptury", "recipe_name", 1),
            ("Nazwa produktu", "product_nr", 2),
            ("Preset Diameter", "preset_diameter", 3),
            ("Diameter Over tolerance", "diameter_over_tol", 4),
            ("Diameter Under tolerance", "diameter_under_tol", 5),
            ("Lump threshold", "lump_threshold", 6),
            ("Neck threshold", "neck_threshold", 7),
            ("Flaw Window", "flaw_window", 8),
            ("Max lumps in flaw window", "max_lumps_in_flaw_window", 9),
            ("Max necks in flaw window", "max_necks_in_flaw_window", 10),
        ]
        
        self.entries = {}
        
        # Inicjalizacja pól
        for label_text, key, idx in self.fields_map:
            lbl = QLabel(label_text, self)
            self.layout.addWidget(lbl)
            
            ent = QLineEdit(self)
            ent.setPlaceholderText(label_text)
            self.layout.addWidget(ent)
            
            # Jeśli mamy istniejące wartości
            if self.values is not None and idx < len(self.values):
                ent.setText(str(self.values[idx]))
            
            self.entries[key] = ent
        
        # Dodaj przyciski OK / Anuluj
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.button_box.accepted.connect(self.save_modal)
        self.button_box.rejected.connect(self.reject)
        self.layout.addWidget(self.button_box)
    
    def save_modal(self):
        """Metoda wywoływana po kliknięciu OK."""
        try:
            new_data = {
                "recipe_name": self.entries["recipe_name"].text(),
                "product_nr": self.entries["product_nr"].text(),
                "preset_diameter": float(self.entries["preset_diameter"].text()),
                "diameter_over_tol": float(self.entries["diameter_over_tol"].text()),
                "diameter_under_tol": float(self.entries["diameter_under_tol"].text()),
                "lump_threshold": float(self.entries["lump_threshold"].text()),
                "neck_threshold": float(self.entries["neck_threshold"].text()),
                "flaw_window": float(self.entries["flaw_window"].text()),
                "max_lumps_in_flaw_window": int(self.entries["max_lumps_in_flaw_window"].text()),
                "max_necks_in_flaw_window": int(self.entries["max_necks_in_flaw_window"].text()),
                "diameter_window": 0.0,
                "diameter_std_dev": 0.0,
                "num_scans": 128,
                "diameter_histeresis": 0.0,
                "lump_histeresis": 0.0,
                "neck_histeresis": 0.0,
            }
        except ValueError:
            print("Błąd: Niepoprawne wartości numeryczne.")
            QMessageBox.critical(self, "Błąd", "Niepoprawne wartości numeryczne.")
            return
        
        connection = None
        try:
            connection = mysql.connector.connect(**self.controller.db_params)
            cursor = connection.cursor()
            
            if self.values is None or self.clone:
                # INSERT
                sql = """
                INSERT INTO settings (
                    `Recipe name`, `Product nr`, `Preset Diameter`, `Diameter Over tolerance`,
                    `Diameter Under tolerance`, `Diameter window`, `Diameter standard deviation`,
                    `Lump threshold`, `Neck threshold`, `Flaw Window`,
                    `Number of scans for gauge to average`, `Diameter histeresis`,
                    `Lump histeresis`, `Neck histeresis`, `Max lumps in flaw window`,
                    `Max necks in flaw window`
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(sql, (
                    new_data["recipe_name"],
                    new_data["product_nr"],
                    new_data["preset_diameter"],
                    new_data["diameter_over_tol"],
                    new_data["diameter_under_tol"],
                    new_data["diameter_window"],
                    new_data["diameter_std_dev"],
                    new_data["lump_threshold"],
                    new_data["neck_threshold"],
                    new_data["flaw_window"],
                    new_data["num_scans"],
                    new_data["diameter_histeresis"],
                    new_data["lump_histeresis"],
                    new_data["neck_histeresis"],
                    new_data["max_lumps_in_flaw_window"],
                    new_data["max_necks_in_flaw_window"],
                ))
            else:
                # UPDATE
                setting_id = self.values[0]  # Załóżmy, że ID jest w kolumnie 0
                sql = """
                UPDATE settings
                SET `Recipe name`=%s, `Product nr`=%s, `Preset Diameter`=%s, `Diameter Over tolerance`=%s,
                    `Diameter Under tolerance`=%s, `Diameter window`=%s, `Diameter standard deviation`=%s,
                    `Lump threshold`=%s, `Neck threshold`=%s, `Flaw Window`=%s,
                    `Number of scans for gauge to average`=%s, `Diameter histeresis`=%s,
                    `Lump histeresis`=%s, `Neck histeresis`=%s, `Max lumps in flaw window`=%s,
                    `Max necks in flaw window`=%s
                WHERE `Id Settings`=%s
                """
                cursor.execute(sql, (
                    new_data["recipe_name"],
                    new_data["product_nr"],
                    new_data["preset_diameter"],
                    new_data["diameter_over_tol"],
                    new_data["diameter_under_tol"],
                    new_data["diameter_window"],
                    new_data["diameter_std_dev"],
                    new_data["lump_threshold"],
                    new_data["neck_threshold"],
                    new_data["flaw_window"],
                    new_data["num_scans"],
                    new_data["diameter_histeresis"],
                    new_data["lump_histeresis"],
                    new_data["neck_histeresis"],
                    new_data["max_lumps_in_flaw_window"],
                    new_data["max_necks_in_flaw_window"],
                    setting_id
                ))
            
            connection.commit()
            print("Sukces: Receptura zapisana.")
            QMessageBox.information(self, "Sukces", "Receptura zapisana.")
            
            # Zamyka dialog z kodem "QDialog.Accepted"
            self.accept()
            
            if connection and connection.is_connected():
                connection.close()
        
        except mysql.connector.Error as e:
            print("Błąd bazy:", e)
            QMessageBox.warning(self, "Błąd połączenia z bazą", 
                                f"Nie można połączyć się z bazą danych: {str(e)}\nZmiany nie zostały zapisane.")
        except Exception as e:
            print("Nieoczekiwany błąd:", e)
            QMessageBox.warning(self, "Błąd", f"Wystąpił nieoczekiwany błąd: {str(e)}")
