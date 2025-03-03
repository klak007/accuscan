# logic.py
import config
from plc_helper import connect_plc, read_accuscan_data, write_accuscan_out_settings
from db_helper import save_measurement_sample, save_event
# ewentualnie data_manager, itp.

class MeasurementLogic:
    def __init__(self, controller=None):
        self.plc_client = None
        self.controller = controller  # Reference to the App instance
        # ewentualne stany maszyny, liczniki stref nieczułości itp.
        self.reset_pending = False
        self.lumps_count = 0
        self.necks_count = 0

    def init_logic(self):
        """Nawiązanie połączenia, ustawienie początkowych parametrów."""
        self.plc_client = connect_plc(config.PLC_IP, config.PLC_RACK, config.PLC_SLOT)
        print(f"[Logic] Połączono z PLC {config.PLC_IP}")

    def close_logic(self):
        """Zamykanie połączenia z PLC."""
        if self.plc_client:
            self.plc_client.disconnect()
            self.plc_client = None
            print("[Logic] Rozłączono z PLC.")

    def poll_plc_data(self, data: dict):
        """
        Tu realizujesz np. maszynę stanową, strefę nieczułości,
        alarmy, itp. data to próbka już pobrana w main.py.
        """
        # Przykład prostego filtra: jeśli lumps > 0 -> zapisz event
        lumps = data.get("lumps", 0)
        necks = data.get("necks", 0)
        self.lumps_count += lumps
        self.necks_count += necks

        if lumps > 0 or necks > 0:
            # Use the queue to send PLC write requests asynchronously
            if self.controller and hasattr(self.controller, 'plc_write_queue'):
                # Queue the write operation instead of doing it directly
                self.controller.plc_write_queue.put(
                    ("write_accuscan_out_settings", 2, True, True, True, True)
                )
            else:
                # Fallback to direct write if queue not available
                write_accuscan_out_settings(
                    self.plc_client,
                    zl=True, zn=True, zf=True, zt=True
                )
            self.reset_pending = True
        
        if self.reset_pending:
            # Queue the clear bits operation
            if self.controller and hasattr(self.controller, 'plc_write_queue'):
                self.controller.plc_write_queue.put(
                    ("write_accuscan_out_settings", 2, False, False, False, False)
                )
            else:
                # Fallback to direct write if queue not available
                write_accuscan_out_settings(
                    self.plc_client,
                    zl=False, zn=False, zf=False, zt=False
                )
            self.reset_pending = False

        if lumps > 0:
            event_data = {
                "timestamp": data["timestamp"],
                "batch": data.get("batch", ""),
                "product": data.get("product", ""),
                "description": f"Wykryto lumps = {data['lumps']}"
            }
            save_event(config.DB_PARAMS, event_data)
        # Możesz tu zaimplementować strefy "waiting / collecting / finishing" itp.

    def get_counters(self) -> dict:
        return {
            "lumps_count": self.lumps_count,
            "necks_count": self.necks_count
        }
