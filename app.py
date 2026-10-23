"""People Counter: counts the people a camera can see, with a Tkinter GUI.

Run:  python app.py
"""
import argparse
import os
import csv
import queue
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

from detector import create_detector, draw_detections
from esp32_link import Esp32Link, Esp32Panel

VIDEO_W, VIDEO_H = 800, 600
ESP32_KEEPALIVE = 1.0  # seconds; the ESP32 turns everything off if it hears nothing for 3 s
ESP32_OFF = "S0000"


def esp32_message(count):
    """S<led1><led2><led3><relay>: LEDs light up one per person; 3+ people adds the relay."""
    return "S" + "".join(str(int(b)) for b in (count >= 1, count >= 2, count >= 3, count >= 3))


class CameraWorker(threading.Thread):
    """Reads frames and runs detection off the GUI thread so the window stays responsive."""

    def __init__(self, source, detector, settings, out_queue):
        super().__init__(daemon=True)
        self.source = source
        self.detector = detector
        self.settings = settings  # dict shared with the GUI; read each frame
        self.out_queue = out_queue
        self.running = threading.Event()
        self.running.set()
        self.error = None

    def run(self):
        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            self.error = f"Could not open camera/video: {self.source}"
            return
        # Video files would otherwise play as fast as they decode; webcams pace themselves.
        frame_time = 1 / (cap.get(cv2.CAP_PROP_FPS) or 30) if isinstance(self.source, str) else 0
        last = time.time()
        while self.running.is_set():
            ok, frame = cap.read()
            if not ok:
                self.error = "Camera stream ended."
                break
            detections = self.detector.detect(frame, self.settings["confidence"])
            draw_detections(frame, detections)
            now = time.time()
            fps = 1 / max(now - last, 1e-6)
            last = now
            # Only the newest frame matters; drop an unread one instead of lagging behind.
            try:
                self.out_queue.get_nowait()
            except queue.Empty:
                pass
            self.out_queue.put((frame, len(detections), fps))
            time.sleep(max(0, frame_time - (time.time() - now)))
        cap.release()

    def stop(self):
        self.running.clear()


class PeopleCounterApp:
    def __init__(self, root, source, backend, port="", limit=5):
        self.root = root
        self.root.title("People Counter")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.backend = backend
        self.detector = None
        self.worker = None
        self.frames = queue.Queue(maxsize=1)
        self.settings = {"confidence": 0.35}
        self.peak = 0
        self.log_rows = []  # (timestamp, count) whenever the count changes
        self.last_count = None
        self.count = 0
        self.alarm = False
        self.esp32 = Esp32Link()
        self.esp32_last = (None, 0.0)  # (message, time sent)

        self.source_var = tk.StringVar(value=str(source))
        self.conf_var = tk.DoubleVar(value=0.35)
        self.count_var = tk.StringVar(value="0")
        self.peak_var = tk.StringVar(value="Peak: 0")
        self.status_var = tk.StringVar(value="Stopped")
        self.limit_var = tk.IntVar(value=limit)
        self.limit = limit
        self.port = port

        self._build_ui()
        self.root.after(30, self.update_frame)

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.video = tk.Label(self.root, bg="black")
        self.video.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")

        side = ttk.Frame(self.root, padding=10)
        side.grid(row=0, column=1, sticky="ns")

        ttk.Label(side, text="People in view", font=("Helvetica", 14)).pack()
        self.count_label = tk.Label(side, textvariable=self.count_var, font=("Helvetica", 72, "bold"),
                                    fg="#1a7f37")
        self.count_label.pack()
        ttk.Label(side, textvariable=self.peak_var, font=("Helvetica", 12)).pack()
        self.alarm_label = tk.Label(side, text="", font=("Helvetica", 12, "bold"), fg="white")
        self.alarm_label.pack(fill="x", pady=(4, 0))
        limit_row = ttk.Frame(side)
        limit_row.pack(fill="x", pady=(4, 16))
        ttk.Label(limit_row, text="Alarm when more than").pack(side="left")
        ttk.Spinbox(limit_row, from_=0, to=500, width=5, textvariable=self.limit_var).pack(side="left", padx=4)
        ttk.Label(limit_row, text="people").pack(side="left")

        ttk.Label(side, text="Camera index or video file:").pack(anchor="w")
        src_row = ttk.Frame(side)
        src_row.pack(fill="x")
        ttk.Entry(src_row, textvariable=self.source_var, width=18).pack(side="left", fill="x", expand=True)
        ttk.Button(src_row, text="…", width=3, command=self.browse).pack(side="left")

        ttk.Label(side, text="Min confidence:").pack(anchor="w", pady=(12, 0))
        ttk.Scale(side, from_=0.1, to=0.95, variable=self.conf_var,
                  command=lambda v: self.settings.update(confidence=float(v))).pack(fill="x")

        self.start_btn = ttk.Button(side, text="▶ Start", command=self.toggle)
        self.start_btn.pack(fill="x", pady=(16, 4))
        ttk.Button(side, text="Reset peak", command=self.reset_peak).pack(fill="x", pady=4)
        ttk.Button(side, text="Save snapshot", command=self.snapshot).pack(fill="x", pady=4)
        ttk.Button(side, text="Export count log (CSV)", command=self.export_log).pack(fill="x", pady=4)
        self.esp32_panel = Esp32Panel(side, self.esp32, self.port)
        self.esp32_panel.pack(fill="x", pady=(12, 0))

        ttk.Label(side, textvariable=self.status_var, foreground="gray").pack(side="bottom", anchor="w")
        self.current_frame = None
        self.show(np.zeros((VIDEO_H, VIDEO_W, 3), dtype=np.uint8))  # black placeholder

    # ---- actions -------------------------------------------------------
    def toggle(self):
        if self.worker:
            self.stop()
        else:
            self.start()

    def start(self):
        if self.detector is None:
            self.status_var.set("Loading detector…")
            self.root.update_idletasks()
            try:
                self.detector = create_detector(self.backend)
            except Exception as exc:
                messagebox.showerror("People Counter", f"Could not load the detector:\n{exc}")
                self.status_var.set("Stopped")
                return
        text = self.source_var.get().strip()
        source = int(text) if text.isdigit() else text
        self.worker = CameraWorker(source, self.detector, self.settings, self.frames)
        self.worker.start()
        self.start_btn.config(text="■ Stop")
        self.status_var.set(f"Running ({self.detector.name})")

    def stop(self):
        if self.worker:
            self.worker.stop()
            self.worker.join(timeout=2)
            self.worker = None
        self.start_btn.config(text="▶ Start")
        self.status_var.set("Stopped")
        self.count = 0
        self.count_var.set("0")

    def browse(self):
        path = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.avi *.mov *.mkv"), ("All", "*.*")])
        if path:
            self.source_var.set(path)

    def reset_peak(self):
        self.peak = 0
        self.peak_var.set("Peak: 0")

    def snapshot(self):
        if self.current_frame is None:
            return
        name = datetime.now().strftime("snapshot_%Y%m%d_%H%M%S.png")
        cv2.imwrite(name, self.current_frame)
        self.status_var.set(f"Saved {name}")

    def export_log(self):
        if not self.log_rows:
            messagebox.showinfo("People Counter", "No counts recorded yet.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="people_count_log.csv")
        if path:
            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "people"])
                writer.writerows(self.log_rows)
            self.status_var.set(f"Saved {path}")

    # ---- GUI loop ------------------------------------------------------
    def update_frame(self):
        if self.worker and self.worker.error:
            messagebox.showerror("People Counter", self.worker.error)
            self.stop()
        try:
            frame, count, fps = self.frames.get_nowait()
        except queue.Empty:
            pass
        else:
            self.current_frame = frame
            self.count = count
            self.count_var.set(str(count))
            if count > self.peak:
                self.peak = count
                self.peak_var.set(f"Peak: {count}")
            if count != self.last_count:
                self.log_rows.append((datetime.now().isoformat(timespec="seconds"), count))
                self.last_count = count
            self.status_var.set(f"Running ({self.detector.name}) · {fps:.1f} FPS")
            self.show(frame)
        self.update_alarm()
        self.root.after(15, self.update_frame)

    def update_alarm(self):
        try:
            limit = int(self.limit_var.get())
        except (tk.TclError, ValueError):
            limit = None  # spinbox being edited
        if limit is not None:
            self.limit = limit
            alarm = self.worker is not None and self.count > limit
            if alarm and not self.alarm:
                self.root.bell()
            self.alarm = alarm
        self.count_label.config(fg="#c62828" if self.alarm else "#1a7f37")
        self.alarm_label.config(text="⚠ TOO MANY PEOPLE" if self.alarm else "",
                                bg="#c62828" if self.alarm else self.root.cget("bg"))

        # ESP32: send on every change, and repeat every second so it knows we're alive.
        message = esp32_message(self.count) if self.worker else ESP32_OFF
        last_message, last_time = self.esp32_last
        if message != last_message or time.time() - last_time >= ESP32_KEEPALIVE:
            if self.esp32.send(message):
                self.esp32_last = (message, time.time())
        self.esp32_panel.update_status()

    def show(self, frame):
        h, w = frame.shape[:2]
        scale = min(VIDEO_W / w, VIDEO_H / h)
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
        image = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
        self.video.configure(image=image)
        self.video.image = image  # keep a reference or Tk drops the image

    def on_close(self):
        self.stop()
        self.esp32.send(ESP32_OFF)
        self.esp32.close()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description="Count people seen by a camera.")
    parser.add_argument("--source", default="0", help="camera index (0 = default webcam) or video file")
    parser.add_argument("--detector", choices=["auto", "yolo", "hog"], default="auto")
    parser.add_argument("--port", default="", help="ESP32 serial port to connect at startup, e.g. COM3")
    parser.add_argument("--limit", type=int, default=5, help="alarm when more than this many people")
    args = parser.parse_args()

    pid_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.pid")
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))  # lets stop.bat find this process
    root = tk.Tk()
    PeopleCounterApp(root, args.source, args.detector, args.port, args.limit)
    try:
        root.mainloop()
    finally:
        if os.path.exists(pid_file):
            os.remove(pid_file)


if __name__ == "__main__":
    main()
