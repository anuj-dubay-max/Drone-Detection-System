# Drone Detection System

A real-time drone surveillance and threat assessment system built using YOLOv8, OpenCV, SQLite, and automated email alerts.

The system detects drones from live camera feeds, tracks their movement, evaluates threat levels, logs incidents to a database, and notifies operators when potential threats are detected.

---

## Features

* Real-time drone detection using YOLOv8
* Bird filtering to reduce false positives
* Persistent drone tracking with unique IDs
* Speed and trajectory estimation
* Threat classification (LOW, MEDIUM, HIGH, CRITICAL)
* Restricted zone intrusion detection
* Automated email alerts with screenshots
* SQLite-based incident logging
* Drone deflection strategy recommendations
* Database viewer with CSV export support

---

## System Overview

The application processes video frames from a webcam, IP camera, mobile camera stream, or recorded video file.

Detected drones are tracked across frames, allowing the system to estimate movement patterns and speed. A configurable restricted zone is monitored continuously. Drones entering this zone are classified as critical threats and trigger immediate alerts.

Each incident is logged to a local SQLite database, and screenshots can be automatically attached to email notifications.

---

## Project Structure

```text
Drone-Detection-System/
│
├── dds.py
├── alert_integration.py
├── database_viewer.py
├── requirements.txt
├── README.md
└── .gitignore
```

---

## Installation

Clone the repository:

```bash
git clone https://github.com/anuj-dubay-max/Drone-Detection-System.git
cd Drone-Detection-System
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Model Files

The trained YOLO model files are not included in this repository because of their size.

Place the required model files in the project directory before running the application:

```text
model.pt
bird.pt
```

---

## Running the System

```bash
python dds.py
```

Choose an input source:

* Laptop webcam
* Mobile camera stream (DroidCam)
* Video file

The system will open a real-time monitoring window and begin processing frames.

---

## Email Alerts

The application can automatically send email notifications whenever a HIGH or CRITICAL threat is detected.

Configure your email settings in the alert configuration section:

```python
alert_system.configure_email(
    smtp_server="smtp.gmail.com",
    smtp_port=587,
    from_email="your_email@gmail.com",
    from_password="your_app_password",
    to_email="recipient@gmail.com"
)
```

For Gmail accounts, use an App Password instead of your normal account password.

---

## Database Viewer

Launch the database viewer:

```bash
python database_viewer.py
```

The viewer provides:

* Detection history
* Threat statistics
* Incident logs
* CSV export functionality
* Summary reports

---

## Controls

While the monitoring window is active:

| Key | Action           |
| --- | ---------------- |
| q   | Quit application |
| s   | Save screenshot  |

The restricted zone can also be repositioned by dragging its corners.

---

## Technologies Used

* Python
* YOLOv8 (Ultralytics)
* OpenCV
* SQLite
* NumPy
* SMTP Email Integration

---

## Future Improvements

* Multi-camera monitoring
* Drone type classification
* Web dashboard
* GPS integration
* Advanced counter-drone analytics

---



