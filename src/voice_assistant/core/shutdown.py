import threading

class GracefulShutdown:
    def __init__(self):
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def is_set(self):
        return self.stop_event.is_set()
