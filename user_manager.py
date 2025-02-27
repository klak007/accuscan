# user_manager.py

class UserManager:
    def __init__(self):
        # Poniżej przykładowa statyczna lista użytkowników, ale
        # w prawdziwym systemie najlepiej czytać z bazy danych lub pliku konfiguracyjnego.
        self.users = {
            "admin": {
                "password": "admin123",
                "role": "admin"
            },
            "user": {
                "password": "user123",
                "role": "operator"
            },
            "": {
                "password": "",
                "role": "admin"
            }
        }
        # Auto-login as operator on startup
        self.current_user = {
            "username": "user",
            "role": "operator"
        }

    def login(self, username: str, password: str) -> bool:
        """
        Zwraca True, jeśli logowanie się powiodło, False w przeciwnym wypadku.
        """
        user_data = self.users.get(username)
        if user_data and user_data["password"] == password:
            self.current_user = {
                "username": username,
                "role": user_data["role"]
            }
            return True
        return False

    def logout(self):
        self.current_user = None

    def get_current_role(self) -> str:
        """
        Zwraca rolę aktualnie zalogowanego użytkownika (np. 'admin' lub 'operator').
        """
        if self.current_user:
            return self.current_user["role"]
        return ""

    def is_admin(self) -> bool:
        return self.get_current_role() in ["admin", "operator"]
