# Drone Detection System

Detects drones in real-time using two YOLOv8 models — one for drones, one for birds. When a drone triggers a HIGH or CRITICAL threat, the system sends an email with a screenshot attached and logs the incident to a local database.

Built as a desktop app with OpenCV. No web server, no Streamlit — just a Python script that opens a window and runs.

---

## What it actually does

Runs two YOLO models on every frame. The bird model's detections are used to filter out false positives from the drone model — if a detected box overlaps with a bird detection, it gets dropped. There's also an aspect ratio and area filter for cases where the bird model misses something.

Each confirmed drone gets a persistent track ID. The system calculates speed from the track history and plots a trajectory trail on screen. A restricted zone (draggable rectangle) sits in the middle of the frame — anything that enters it triggers CRITICAL. Approaching drones get scored HIGH or MEDIUM depending on distance and speed.

On HIGH or CRITICAL: an email goes out with a screenshot of the frame, the incident gets logged to SQLite, and a deflection method gets selected (laser, net launcher, or RF jammer depending on distance). The jammer shows as pulsing circles on screen.

There's also a separate `database_viewer.py` you can run to query the database, export CSVs, or generate a report.

---

## Setup

```bash
git clone https://github.com/anuj-dubay-max/Drone-Detection-System
cd Drone-Detection-System
pip install -r requirements.txt
```

You need two model files in the project folder:
- `model.pt` — trained drone detector
- `bird.pt` — bird detector for false positive filtering

Both are too large for GitHub. Download them from [Google Drive link here].

Then run:

```bash
python DDS.py
```

Pick your input source (laptop camera, phone stream, or video file) and the window opens.

---

## Email alerts

The system sends an email with a screenshot attached every time a HIGH or CRITICAL threat is detected (with a cooldown so you don't get flooded).

Edit these lines near the top of `DDS.py`:

```python
alert_system.configure_email(
    smtp_server='smtp.gmail.com',
    smtp_port=587,
    from_email='your_email@gmail.com',
    from_password='your_app_password',  # NOT your Gmail password
    to_email='recipient@gmail.com'
)
```

For Gmail, you need an App Password — go to myaccount.google.com → Security → 2FA → App Passwords and generate one.

Telegram alerts are also supported. Add your bot token and chat_id in the same section. Get a token from @BotFather on Telegram.

---

## Training your own model

`train_drone_model.py` handles the full pipeline — dataset download from Roboflow, training, and saving the result as `model.pt`.

```bash
pip install roboflow
# Set your API key inside train_drone_model.py, then:
python train_drone_model.py
```

Use `best.pt` from `runs/detect/drone_v1/weights/`, not `last.pt`. If validation loss was still dropping when training stopped, run more epochs.

---

## Database viewer

```bash
python database_viewer.py
```

Shows overall stats, recent detections, incidents log, and per-drone breakdown. Can export everything to CSV.

---

## Controls

While the detection window is open:
- `q` — quit
- `s` — save a screenshot
- drag the rectangle corners to reposition the restricted zone

---

## Stack

YOLOv8 (Ultralytics) · OpenCV · SQLite · Gmail SMTP · Telegram Bot API