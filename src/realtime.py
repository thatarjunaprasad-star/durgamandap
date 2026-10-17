# src/realtime.py
import json
import random
import time
from threading import Thread
from datetime import datetime

from flask_socketio import SocketIO, emit

# SocketIO instance – will be attached to the Flask app in app.py
socketio: SocketIO = SocketIO(async_mode='eventlet')  # eventlet works on Windows

# ----------------------------------------------------------------------
# Simulated foot‑fall generator (replace with real sensor integration)
# ----------------------------------------------------------------------
def _generate_fake_data():
    """Emit a JSON payload every second with the fields needed by the UI."""
    capacity = 5000                       # total capacity of the pandal
    current_in = 0
    current_out = 0

    gates = {
        "A": {"name": "Main Entrance",     "velocity": 0},
        "B": {"name": "VIP Entry",         "velocity": 0},
        "C": {"name": "Queue Overflow",    "velocity": 0},
    }

    while True:
        # Random walk for demo – in reality replace with sensor values
        inc = random.randint(5, 30)
        outc = random.randint(0, 15)
        current_in += inc
        current_out += outc

        # Update gate velocities (people per minute)
        for g in gates:
            gates[g]["velocity"] = random.randint(80, 200)

        net = current_in - current_out
        occupancy = min(100, int(net / capacity * 100))

        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "in_flow": current_in,
            "out_flow": current_out,
            "net": net,
            "capacity_percent": occupancy,
            "gates": gates,
            # Optional heat‑map points: list of {x, y, value}
            "heatmap": [
                {"x": random.uniform(0, 1), "y": random.uniform(0, 1), "value": random.random()}
                for _ in range(20)
            ],
        }

        socketio.emit("footfall_update", payload)
        time.sleep(1)   # 1‑second cadence


def start_background_generator():
    """Launch the fake data generator in a daemon thread."""
    thread = Thread(target=_generate_fake_data, daemon=True)
    thread.start()