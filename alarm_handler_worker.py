import queue
import threading
from alarm_handling import AlarmHandler
import db_helper

# Utwórz globalną kolejkę zdarzeń alarmowych
alarm_events_queue = queue.Queue()

def alarm_logger_worker(alarm_handler: AlarmHandler):
    while True:
        try:
            # Pobierz zdarzenie z kolejki (blokująco)
            event = alarm_events_queue.get()
            if event is None:
                break  # Sygnał do zakończenia pracy
            
            # Wykonaj logowanie zdarzenia
            alarm_handler.log_event(*event)
            alarm_events_queue.task_done()
        except Exception as e:
            print(f"[AlarmLogger] Błąd: {e}")

# Inicjalizacja wątku logującego (uruchom go przy starcie aplikacji)
def start_alarm_logger(alarm_handler: AlarmHandler):
    t = threading.Thread(target=alarm_logger_worker, args=(alarm_handler,), daemon=True)
    t.start()
    return t
