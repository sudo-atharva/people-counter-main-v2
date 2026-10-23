# People Counter

Live camera feed with a box drawn around every person and a large count of how many people are in view.

![screenshot](screenshots/people.png)

## Quick start (Windows)
1. Install [Python 3.10+](https://www.python.org/downloads/) and tick **"Add python.exe to PATH"** during setup.
2. Download this repo (**Code → Download ZIP**) and unzip it.
3. Double-click:

| File | What it does |
|---|---|
| `install.bat` | Creates a `venv` folder, installs the packages and offers to install YOLO (optional, ~2 GB) |
| `run.bat` | Starts the app (runs `install.bat` first if needed)|
| `stop.bat` | Closes the running app |

Command-line options can be passed through, e.g. `run.bat --source 1`.

## Manual setup (any OS)
```bash
pip install -r requirements.txt          # Linux also needs: sudo apt install python3-tk
pip install -r requirements-yolo.txt     # optional, much better detection
python app.py                        # default webcam
python app.py --source 1             # second camera
python app.py --source crowd.mp4     # a video file
python app.py --detector hog         # force the lightweight detector
```

## Features
- Live count, plus the peak count since the last reset
- Confidence slider (raise it to cut false detections)
- Save a snapshot of the current frame as PNG
- Export a CSV log with one row each time the count changes
- **Alarm limit:** "Alarm when more than N people". Over the limit, the count turns red, the PC beeps

## ESP32: 3 LEDs + relay
Plug an ESP32 into the PC with a USB cable. The app decides what is on; the ESP32 just switches:

| Count | Output |
|---|---|
| nobody | all off |
| 1 person | LED1 |
| 2 people | LED1 + LED2 |
| 3 or more | LED1 + LED2 + LED3 **+ relay** |

![wiring](docs/wiring.svg)

| ESP32 pin | Connects to |
|---|---|
| GPIO27 | 220 Ω → LED1 long leg (+), short leg (−) → GND |
| GPIO26 | 220 Ω → LED2 long leg (+), short leg (−) → GND |
| GPIO25 | 220 Ω → LED3 long leg (+), short leg (−) → GND |
| GPIO18 | Relay module **IN** |
| 5V / VIN | Relay module **VCC** |
| GND | Relay module **GND**, all LED − legs |

Most relay modules switch on when IN is LOW. If yours is on when it should be off, flip
`RELAY_ACTIVE_LOW` in the firmware.

**Steps**
1. Wire it as shown above.
2. Flash the firmware with the Arduino IDE. Install the **esp32 by Espressif** board package
   (Boards Manager), open `firmware/people_counter_esp32/people_counter_esp32.ino`, select
   **ESP32 Dev Module** and the right COM port, then click Upload.
3. *(Optional)* Test without the app: open the Serial Monitor at 115200 baud and type `S1111`.
   All LEDs and the relay should turn on for 3 s.
4. Close the Serial Monitor, then start the app. In the **ESP32 (USB)** panel, pick the COM port and
   click **Connect**. You can also start it with `run.bat --port COM3 --limit 10`.

**Protocol:** one line per update at 115200 baud: `S<led1><led2><led3><relay>`, each `0` or `1`,
e.g. `S1100`. The app sends it whenever something changes, and at least once a second. If nothing
arrives for 3 s, the ESP32 turns everything off.

## Detectors
| | YOLO (`ultralytics`) | HOG (built into OpenCV) |
|---|---|---|
| Accuracy | High: finds sitting, partly hidden and distant people | Standing people only, misses small ones |
| Speed | Fast with a GPU, fine on a modern CPU | Fast on a CPU |
| First run | Downloads `yolov8n.pt` (~6 MB) | Nothing to download |

With the default `--detector auto`, YOLO is used when it is installed and HOG otherwise.
