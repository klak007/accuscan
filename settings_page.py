import customtkinter as ctk
from tkinter import ttk, messagebox
import mysql.connector
from mysql.connector import Error
from datetime import datetime
from db_helper import check_database

class SettingsPage(ctk.CTkFrame):
    """
    Strona ustawień aplikacji – umożliwia przeglądanie, filtrowanie, edycję i zarządzanie recepturami (ustawieniami) dla danego produktu.
    """
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Zachowujemy istniejący top bar
        self._create_top_bar()

        # Dodajemy nowy panel zarządzania recepturami poniżej top baru
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self.main_frame.grid_rowconfigure(1, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        self._create_filter_panel()
        self._create_table()
        self._create_action_buttons()

        # Status bazy danych
        self.status_frame = ctk.CTkFrame(self.main_frame)
        self.status_frame.grid(row=3, column=0, sticky="ew", padx=5, pady=5)
        self.db_status_label = ctk.CTkLabel(self.status_frame, text="Status bazy danych: Sprawdzanie...")
        self.db_status_label.pack(side="left", padx=5)
        self.btn_check_db = ctk.CTkButton(self.status_frame, text="Sprawdź połączenie", command=self.check_db_connection)
        self.btn_check_db.pack(side="left", padx=5)

        # Załaduj dane przy inicjalizacji jeśli baza jest dostępna
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
            messagebox.showinfo("Połączenie z bazą danych", "Połączenie z bazą danych jest aktywne.")
            self.load_data()
        else:
            messagebox.showwarning("Problem z bazą danych", 
                                 "Nie można połączyć się z bazą danych. Dostęp do ustawień jest ograniczony.")
    
    def update_db_status(self):
        """Aktualizuje etykietę statusu połączenia z bazą."""
        if self.controller.db_connected:
            self.db_status_label.configure(text="Status bazy danych: Połączono", text_color="green")
        else:
            self.db_status_label.configure(text="Status bazy danych: Brak połączenia", text_color="red")

    def show_offline_message(self):
        """Wyświetla informację o braku dostępu do bazy danych w widoku tabeli."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        self.tree.insert("", "end", values=(
            "-", "<Brak połączenia z bazą>", "Funkcje edycji niedostępne", "-", "-", "-", "-", "-", "-", "-"
        ))

    def _create_top_bar(self):
        """Tworzy górny pasek nawigacyjny z przyciskami (dotychczasowa wersja)."""
        self.top_bar = ctk.CTkFrame(self)
        self.top_bar.grid(row=0, column=0, sticky="ew", padx=5, pady=(5, 0))
        self.btn_pomiary = ctk.CTkButton(self.top_bar, text="Back to Main", command=lambda: self.controller.toggle_page("MainPage"))
        self.btn_pomiary.pack(side="left", padx=5)
        self.btn_nastawy  = ctk.CTkButton(self.top_bar, text="nastawy",  command=self._on_nastawy_click)
        self.btn_nastawy.pack(side="left", padx=5)
        self.btn_historia  = ctk.CTkButton(self.top_bar, text="historia",  command=self._on_historia_click)
        self.btn_historia.pack(side="left", padx=5)
        self.btn_accuscan  = ctk.CTkButton(self.top_bar, text="Accuscan",  command=self._on_accuscan_click)
        self.btn_accuscan.pack(side="left", padx=5)
        self.btn_auth = ctk.CTkButton(self.top_bar, text="Log In", command=self._on_auth_click)
        self.btn_auth.pack(side="left", padx=5)
        # --- New indicators placed to the right of btn_auth ---
        self.ind_plc = ctk.CTkLabel(self.top_bar, text="PLC: Unknown", fg_color="transparent", text_color="orange")
        self.ind_plc.pack(side="right", padx=5)
        self.ind_db = ctk.CTkLabel(self.top_bar, text="DB: Unknown", fg_color="transparent", text_color="orange")
        self.ind_db.pack(side="right", padx=5)
        self.btn_exit = ctk.CTkButton(self.top_bar, text="Exit", command=self.controller.destroy, fg_color="red", hover_color="darkred")
        self.btn_exit.pack(side="right", padx=5)

    def update_connection_indicators(self):
        """Aktualizuje wskaźniki połączeń PLC i bazy danych."""
        # Update PLC indicator if plc_client exists and can report connection status.
        plc_connected = hasattr(self.controller.logic, "plc_client") and self.controller.logic.plc_client.get_connected() if getattr(self.controller.logic, "plc_client", None) else False
        if plc_connected:
            self.ind_plc.configure(text="PLC: OK", text_color="green")
        else:
            self.ind_plc.configure(text="PLC: OFF", text_color="red")
        # Update DB indicator based on controller's db_connected flag.
        if self.controller.db_connected:
            self.ind_db.configure(text="DB: OK", text_color="green")
        else:
            self.ind_db.configure(text="DB: OFF", text_color="red")

    def _on_nastawy_click(self):
        print("[GUI] Kliknięto przycisk 'nastawy'.")

    def _on_historia_click(self):
        print("[GUI] Kliknięto przycisk 'historia'.")

    def _on_accuscan_click(self):
        print("[GUI] Kliknięto przycisk 'Accuscan'.")

    def _on_auth_click(self):
        if not self.controller.user_manager.current_user:
            self._show_login_dialog()
        else:
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
        submit_btn = ctk.CTkButton(login_dialog, text="Submit", command=lambda: self._submit_login(username_entry, password_entry, login_dialog, submit_btn))
        submit_btn.pack(pady=(15, 10))

    def _submit_login(self, username_entry, password_entry, dialog, submit_btn):
        username = username_entry.get()
        password = password_entry.get()
        if username and password:
            if self.controller.user_manager.login(username, password):
                submit_btn.configure(text="Zalogowano", fg_color="green")
                self.btn_auth.configure(text="Log Out")
                dialog.after(1000, dialog.destroy)
            else:
                submit_btn.configure(text="Niepoprawne dane", fg_color="red")
        else:
            submit_btn.configure(text="Niepoprawne dane", fg_color="red")

    def _create_filter_panel(self):
        self.filter_frame = ctk.CTkFrame(self.main_frame)
        self.filter_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        self.filter_label = ctk.CTkLabel(self.filter_frame, text="Filtruj po produkcie:")
        self.filter_label.pack(side="left", padx=5)
        self.filter_entry = ctk.CTkEntry(self.filter_frame, width=200)
        self.filter_entry.pack(side="left", padx=5)
        self.btn_filter = ctk.CTkButton(self.filter_frame, text="Filtruj", command=self.load_data)
        self.btn_filter.pack(side="left", padx=5)
        self.btn_all = ctk.CTkButton(self.filter_frame, text="Wszystkie", command=self.clear_filter)
        self.btn_all.pack(side="left", padx=5)
        self.btn_reload = ctk.CTkButton(self.filter_frame, text="Załaduj", command=self.load_data)
        self.btn_reload.pack(side="left", padx=5)

    def clear_filter(self):
        self.filter_entry.delete(0, "end")
        self.load_data()

    def _create_table(self):
        self.table_container = ctk.CTkFrame(self.main_frame)
        self.table_container.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self.table_container.grid_rowconfigure(0, weight=1)
        self.table_container.grid_columnconfigure(0, weight=1)
        # Definiujemy kolumny – przykładowo:
        columns = (
            "id",
            "recipe_name",
            "product_nr",
            "preset_diameter",
            "diameter_over_tol",
            "diameter_under_tol",
            "lump_threshold",
            "neck_threshold",
            "flaw_window",
            "created_at"
        )
        self.tree = ttk.Treeview(self.table_container, columns=columns, show="headings", selectmode="browse")
        for col in columns:
            self.tree.heading(col, text=col.replace("_", " ").title())
            self.tree.column(col, anchor="center", width=100)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(self.table_container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.grid(row=0, column=1, sticky="ns")

    def _create_action_buttons(self):
        self.actions_frame = ctk.CTkFrame(self.main_frame)
        self.actions_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        self.btn_new = ctk.CTkButton(self.actions_frame, text="Nowa", command=self.new_setting)
        self.btn_new.pack(side="left", padx=5)
        self.btn_clone = ctk.CTkButton(self.actions_frame, text="Klonuj", command=self.clone_setting)
        self.btn_clone.pack(side="left", padx=5)
        self.btn_edit = ctk.CTkButton(self.actions_frame, text="Edytuj", command=self.edit_setting)
        self.btn_edit.pack(side="left", padx=5)
        self.btn_delete = ctk.CTkButton(self.actions_frame, text="Usuń", command=self.delete_setting)
        self.btn_delete.pack(side="left", padx=5)

    def load_data(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Sprawdzamy, czy jest połączenie z bazą
        if not check_database(self.controller.db_params):
            self.controller.db_connected = False
            self.show_offline_message()
            self.update_db_status()
            return
        
        try:
            connection = mysql.connector.connect(**self.controller.db_params)
            cursor = connection.cursor(dictionary=True)
            
            filter_text = self.filter_entry.get().strip()
            
            if filter_text:
                sql = "SELECT * FROM settings WHERE `Product nr` LIKE %s ORDER BY `Id Settings` DESC"
                cursor.execute(sql, (f"%{filter_text}%",))
            else:
                sql = """
                    SELECT `Id Settings` AS id_settings, `Recipe name`, `Product nr`, `Preset Diameter`, 
                        `Diameter Over tolerance`, `Diameter Under tolerance`, `Lump threshold`, 
                        `Neck threshold`, `Flaw Window`, `created_at` 
                    FROM settings 
                    ORDER BY id_settings DESC
                """
                cursor.execute(sql)
            
            rows = cursor.fetchall()
            
            for row in rows:
                # Jeśli alias został użyty, pobieraj 'id_settings'
                id_val = row.get("id_settings") or row.get("Id Settings")
                recipe_name = row.get("Recipe name") or ""
                product_nr = row.get("Product nr") or ""
                preset_diameter = row.get("Preset Diameter") or 0
                diameter_over_tol = row.get("Diameter Over tolerance") or 0
                diameter_under_tol = row.get("Diameter Under tolerance") or 0
                lump_threshold = row.get("Lump threshold") or 0
                neck_threshold = row.get("Neck threshold") or 0
                flaw_window = row.get("Flaw Window") or 0
                created_at = row.get("created_at")
                
                if created_at:
                    created_at = created_at.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    created_at = ""
                
                self.tree.insert("", "end", values=(
                    id_val, recipe_name, product_nr, preset_diameter,
                    diameter_over_tol, diameter_under_tol, lump_threshold,
                    neck_threshold, flaw_window, created_at
                 ))
            
            if connection and connection.is_connected():
                connection.close()
            
            # Aktualizacja statusu bazy danych
            self.controller.db_connected = True
            self.update_db_status()
                
        except Error as e:
            print("Błąd bazy:", e)  
            messagebox.showwarning("Błąd połączenia z bazą", 
                                 f"Nie można połączyć się z bazą danych: {str(e)}\nAplikacja będzie działać w trybie ograniczonym.")
            # Insert placeholder data to show UI structure
            self.show_offline_message()
            # Aktualizacja statusu bazy danych
            self.controller.db_connected = False
            self.update_db_status()
        except Exception as e:
            print("Nieoczekiwany błąd:", e)
            messagebox.showwarning("Błąd", f"Wystąpił nieoczekiwany błąd: {str(e)}")

    def new_setting(self):
        # Sprawdź połączenie przed operacją
        if not self.controller.db_connected and not check_database(self.controller.db_params):
            messagebox.showwarning("Brak połączenia z bazą",
                               "Nie można dodać nowej receptury bez połączenia z bazą danych.")
            return
        self.open_edit_modal(None)

    def clone_setting(self):
        # Sprawdź połączenie przed operacją
        if not self.controller.db_connected and not check_database(self.controller.db_params):
            messagebox.showwarning("Brak połączenia z bazą",
                               "Nie można klonować receptury bez połączenia z bazą danych.")
            return
        selected = self.tree.selection()
        if not selected:
            print("Ostrzeżenie: Wybierz recepturę do klonowania.")  # Added console logging
            messagebox.showwarning("Ostrzeżenie", "Wybierz recepturę do klonowania.")
            return
        item = self.tree.item(selected)
        values = item["values"]
        self.open_edit_modal(values, clone=True)

    def edit_setting(self):
        # Sprawdź połączenie przed operacją
        if not self.controller.db_connected and not check_database(self.controller.db_params):
            messagebox.showwarning("Brak połączenia z bazą",
                               "Nie można edytować receptury bez połączenia z bazą danych.")
            return
        selected = self.tree.selection()
        if not selected:
            print("Ostrzeżenie: Wybierz recepturę do edycji.")  # Added console logging
            messagebox.showwarning("Ostrzeżenie", "Wybierz recepturę do edycji.")
            return
        item = self.tree.item(selected)
        values = item["values"]
        self.open_edit_modal(values, clone=False)

    def delete_setting(self):
        # Sprawdź połączenie przed operacją
        if not self.controller.db_connected and not check_database(self.controller.db_params):
            messagebox.showwarning("Brak połączenia z bazą",
                               "Nie można usunąć receptury bez połączenia z bazą danych.")
            return
        selected = self.tree.selection()
        if not selected:
            print("Ostrzeżenie: Wybierz recepturę do usunięcia.")
            messagebox.showwarning("Ostrzeżenie", "Wybierz recepturę do usunięcia.")
            return
        if messagebox.askyesno("Potwierdzenie", "Czy na pewno chcesz usunąć wybraną recepturę?"):
            item = self.tree.item(selected)
            setting_id = item["values"][0]
            try:
                connection = mysql.connector.connect(**self.controller.db_params)
                cursor = connection.cursor()
                # Updated SQL with backticks around 'Id Settings'
                sql = "DELETE FROM settings WHERE `Id Settings` = %s"
                cursor.execute(sql, (setting_id,))
                connection.commit()
                print("Sukces: Receptura usunięta.")
                messagebox.showinfo("Sukces", "Receptura usunięta.")
                self.load_data()
                
                if connection and connection.is_connected():
                    connection.close()
            except Error as e:
                print("Błąd bazy:", e)
                messagebox.showwarning("Błąd połączenia z bazą", 
                                    f"Nie można połączyć się z bazą danych: {str(e)}\nOperacja nie została wykonana.")
            except Exception as e:
                print("Nieoczekiwany błąd:", e)
                messagebox.showwarning("Błąd", f"Wystąpił nieoczekiwany błąd: {str(e)}")

    def open_edit_modal(self, values, clone=False):
        modal = ctk.CTkToplevel(self)
        if values is None:
            modal.title("Nowa Receptura")
        else:
            modal.title("Klonuj Recepturę" if clone else "Edytuj Recepturę")
        modal.geometry("400x500")
        modal.resizable(False, False)
        fields = [
            ("Nazwa receptury", "recipe_name"),
            ("Nazwa produktu", "product_nr"),
            ("Preset Diameter", "preset_diameter"),
            ("Diameter Over tolerance", "diameter_over_tol"),
            ("Diameter Under tolerance", "diameter_under_tol"),
            ("Lump threshold", "lump_threshold"),
            ("Neck threshold", "neck_threshold")
        ]
        entries = {}
        for label_text, key in fields:
            lbl = ctk.CTkLabel(modal, text=label_text)
            lbl.pack(pady=(10, 0))
            ent = ctk.CTkEntry(modal)
            ent.pack(pady=(0, 10), fill="x", padx=20)
            if values is not None:
                mapping = {
                    "recipe_name": values[1],
                    "product_nr": values[2],
                    "preset_diameter": values[3],
                    "diameter_over_tol": values[4],
                    "diameter_under_tol": values[5],
                    "lump_threshold": values[6],
                    "neck_threshold": values[7],
                }
                if key in mapping:
                    ent.insert(0, str(mapping[key]))
            entries[key] = ent

        def save_modal():
            try:
                new_data = {
                    "recipe_name": entries["recipe_name"].get(),
                    "product_nr": entries["product_nr"].get(),
                    "preset_diameter": float(entries["preset_diameter"].get()),
                    "diameter_over_tol": float(entries["diameter_over_tol"].get()),
                    "diameter_under_tol": float(entries["diameter_under_tol"].get()),
                    "lump_threshold": float(entries["lump_threshold"].get()),
                    "neck_threshold": float(entries["neck_threshold"].get()),
                    "diameter_window": 0.0,
                    "diameter_std_dev": 0.0,
                    "flaw_window": 0.0,
                    "num_scans": 128,
                    "diameter_histeresis": 0.0,
                    "lump_histeresis": 0.0,
                    "neck_histeresis": 0.0,
                }
            except ValueError:
                print("Błąd: Niepoprawne wartości numeryczne.")  # Added console logging
                messagebox.showerror("Błąd", "Niepoprawne wartości numeryczne.")
                return
            
            connection = None
            try:
                connection = mysql.connector.connect(**self.controller.db_params)
                cursor = connection.cursor()
                if values is None or clone:
                    sql = """
                    INSERT INTO settings (
                        `Recipe name`, `Product nr`, `Preset Diameter`, `Diameter Over tolerance`,
                        `Diameter Under tolerance`, `Diameter window`, `Diameter standard deviation`,
                        `Lump threshold`, `Neck threshold`, `Flaw Window`,
                        `Number of scans for gauge to average`, `Diameter histeresis`,
                        `Lump histeresis`, `Neck histeresis`
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    ))
                else:
                    setting_id = values[0]
                    sql = """
                    UPDATE settings
                    SET `Recipe name`=%s, `Product nr`=%s, `Preset Diameter`=%s, `Diameter Over tolerance`=%s,
                        `Diameter Under tolerance`=%s, `Diameter window`=%s, `Diameter standard deviation`=%s,
                        `Lump threshold`=%s, `Neck threshold`=%s, `Flaw Window`=%s,
                        `Number of scans for gauge to average`=%s, `Diameter histeresis`=%s,
                        `Lump histeresis`=%s, `Neck histeresis`=%s
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
                        setting_id
                    ))
                connection.commit()
                print("Sukces: Receptura zapisana.")  # Added console logging
                messagebox.showinfo("Sukces", "Receptura zapisana.")
                modal.destroy()
                self.load_data()
                
                if connection and connection.is_connected():
                    connection.close()
            except Error as e:
                print("Błąd bazy:", e)
                messagebox.showwarning("Błąd połączenia z bazą", 
                                     f"Nie można połączyć się z bazą danych: {str(e)}\nZmiany nie zostały zapisane.")
            except Exception as e:
                print("Nieoczekiwany błąd:", e)
                messagebox.showwarning("Błąd", f"Wystąpił nieoczekiwany błąd: {str(e)}")

        btn_save = ctk.CTkButton(modal, text="Zapisz", command=save_modal)
        btn_save.pack(pady=20)
