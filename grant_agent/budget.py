"""A tiny thread-safe call counter so every loop has a hard stop."""
import threading


class Budget:
    def __init__(self, **limits):
        self.limits = limits
        self.used = {name: 0 for name in limits}
        self._lock = threading.Lock()

    def take(self, name, n=1):
        """Use n units. Returns False (and uses nothing) if it would overspend."""
        with self._lock:
            if self.used[name] + n > self.limits[name]:
                return False
            self.used[name] += n
            return True

    def left(self, name):
        return self.limits[name] - self.used[name]

    def __repr__(self):
        return " ".join(f"{k}={self.used[k]}/{self.limits[k]}" for k in self.limits)
