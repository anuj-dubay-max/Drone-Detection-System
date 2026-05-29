import cv2
import numpy as np
from ultralytics import YOLO
import os
import time
import platform
import threading
from queue import Queue
from collections import defaultdict, deque
import sqlite3
from datetime import datetime
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
import mimetypes
import random
import math

# ==================== CONFIGURATION ====================
class Config:
    CONFIDENCE_THRESHOLD = 0.55
    DRONE_CLASS_ID = 0
    BIRD_CLASS_ID = 1
    TARGET_FPS = 10

    MAX_TRACK_AGE = 30
    MIN_TRACK_HITS = 3
    IOU_THRESHOLD = 0.3

    THREAT_DISTANCE_CRITICAL = 50
    THREAT_DISTANCE_HIGH = 100
    THREAT_DISTANCE_MEDIUM = 150
    THREAT_SPEED_HIGH = 200

    BEEP_INTERVAL = 2
    ALERT_COOLDOWN = 5

    LASER_RANGE = 300
    JAMMER_RADIUS = 200
    NET_RANGE = 150

    ACOUSTIC_ENABLED = True
    ACOUSTIC_THRESHOLD = 0.6

    # Screenshot folder
    ALERT_SCREENSHOT_DIR = "alerts_screenshots"
    os.makedirs(ALERT_SCREENSHOT_DIR, exist_ok=True)


# ==================== ENHANCED ALERT SYSTEM (embedded) ====================
class EnhancedAlertSystem:
    def __init__(self):
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        self.from_email = ""      
        self.from_password = ""   
        self.to_email = ""   
        self.last_alert_time = {}

    def configure_email(self, smtp_server, smtp_port, from_email, from_password, to_email):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.from_email = from_email
        self.from_password = from_password
        self.to_email = to_email

    def should_send_alert(self, key, cooldown=Config.ALERT_COOLDOWN):
        now = time.time()
        if key not in self.last_alert_time or now - self.last_alert_time[key] > cooldown:
            self.last_alert_time[key] = now
            return True
        return False

    def send_email(self, subject, body, attachment_path=None):
        # If credentials not configured, just print and return
        if not self.from_email or not self.to_email or not self.from_password:
            print("⚠️ Email not configured (placeholder credentials). Skipping send.")
            print("Subject:", subject)
            return False

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.from_email
        msg["To"] = self.to_email
        msg.set_content(body)

        if attachment_path and os.path.exists(attachment_path):
            ctype, encoding = mimetypes.guess_type(attachment_path)
            if ctype is None:
                ctype = "application/octet-stream"
            maintype, subtype = ctype.split("/", 1)
            with open(attachment_path, "rb") as f:
                data = f.read()
            msg.add_attachment(data, maintype=maintype, subtype=subtype,
                               filename=os.path.basename(attachment_path))

        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10) as server:
                server.ehlo()
                server.starttls()
                server.login(self.from_email, self.from_password)
                server.send_message(msg)
            print("✓ Alert email sent.")
            return True
        except Exception as e:
            print("❌ Failed to send email:", e)
            return False

    def send_alert_with_screenshot(self, drone_id, threat_level, position, image):
        """Save screenshot and send email (if configured)."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{Config.ALERT_SCREENSHOT_DIR}/alert_{drone_id}_{threat_level}_{timestamp}.jpg"
        cv2.imwrite(filename, image)
        subject = f"[ALERT] Drone {drone_id} - {threat_level}"
        body = f"Drone ID: {drone_id}\nThreat: {threat_level}\nPosition: {position}\nTime: {datetime.now().isoformat()}"
        self.send_email(subject, body, attachment_path=filename)
        return filename

#===================== Detection ==============

class DroneDetector:
    def __init__(self, model_path="model.pt"):
        print("🔄 Loading model...")
        self.model = YOLO(model_path)
        print("✓ Classes:", self.model.names)

    def detect(self, frame):
        results = self.model(frame, verbose=False)

        detections = []
        bird_boxes = []

        for r in results:
            for box in r.boxes:
                conf = float(box.conf[0])
                cls = int(box.cls[0])

                x1, y1, x2, y2 = box.xyxy[0].int().tolist()

                if cls == 1:  # bird
                    bird_boxes.append((x1, y1, x2, y2))
                    continue

                if cls != 0:
                    continue

                if conf < Config.CONFIDENCE_THRESHOLD:
                    continue

                center = ((x1 + x2)//2, (y1 + y2)//2)

                detections.append({
                    'box': (x1, y1, x2, y2),
                    'center': center,
                    'confidence': conf,
                    'acoustic': False
                })

        return detections, bird_boxes


# ==================== COLOR GENERATOR ====================
class ColorGenerator:
    def __init__(self):
        self.colors = {}

    def get_color(self, drone_id):
        if drone_id in self.colors:
            return self.colors[drone_id]
        hue = (drone_id * 137.508) % 360
        color = self._hsv_to_bgr(hue, 0.95, 0.95)
        self.colors[drone_id] = color
        return color

    def _hsv_to_bgr(self, h, s, v):
        h = h / 360.0
        c = v * s
        x = c * (1 - abs((h * 6) % 2 - 1))
        m = v - c
        if h < 1/6:
            r, g, b = c, x, 0
        elif h < 2/6:
            r, g, b = x, c, 0
        elif h < 3/6:
            r, g, b = 0, c, x
        elif h < 4/6:
            r, g, b = 0, x, c
        elif h < 5/6:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x
        return (int((b + m) * 255), int((g + m) * 255), int((r + m) * 255))


# ==================== ACOUSTIC DETECTOR (simulated) ====================
class AcousticDetector:
    def __init__(self):
        self.enabled = Config.ACOUSTIC_ENABLED
        self.history = deque(maxlen=30)

    def detect_sound(self, frame_region):
        if not self.enabled:
            return False, 0.0
        conf = random.uniform(0.5, 0.95)
        detected = conf > Config.ACOUSTIC_THRESHOLD
        self.history.append(detected)
        return detected, conf

    def get_boost(self):
        if len(self.history) < 5:
            return 0.0
        return (sum(self.history) / len(self.history)) * 0.1


# ==================== DATABASE ====================
class DroneDatabase:
    def __init__(self, db_name="drone_detections.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cur = self.conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                drone_id INTEGER,
                x INTEGER,
                y INTEGER,
                confidence REAL,
                speed REAL,
                threat_level TEXT,
                in_restricted_area INTEGER
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                drone_id INTEGER,
                threat_level TEXT,
                duration REAL,
                max_speed REAL,
                deflection_method TEXT,
                screenshot_path TEXT
            )
        ''')
        self.conn.commit()

    def log_detection(self, drone_id, x, y, confidence, speed, threat_level, in_area):
        cur = self.conn.cursor()
        cur.execute('''
            INSERT INTO detections (timestamp, drone_id, x, y, confidence, speed, threat_level, in_restricted_area)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (datetime.now().isoformat(), drone_id, x, y, confidence, speed, threat_level, int(in_area)))
        self.conn.commit()

    def log_incident(self, drone_id, threat_level, duration, max_speed, deflection_method, screenshot_path):
        cur = self.conn.cursor()
        cur.execute('''
            INSERT INTO incidents (timestamp, drone_id, threat_level, duration, max_speed, deflection_method, screenshot_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (datetime.now().isoformat(), drone_id, threat_level, duration, max_speed, deflection_method, screenshot_path))
        self.conn.commit()

    def get_statistics(self):
        cur = self.conn.cursor()
        cur.execute('SELECT COUNT(*) FROM detections')
        total = cur.fetchone()[0]
        cur.execute('SELECT COUNT(DISTINCT drone_id) FROM detections')
        unique = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM incidents')
        incidents = cur.fetchone()[0]
        cur.execute('SELECT AVG(speed) FROM detections WHERE speed > 0')
        avg_speed = cur.fetchone()[0] or 0
        return {'total_detections': total, 'unique_drones': unique, 'total_incidents': incidents, 'avg_speed': avg_speed}


# ==================== TRACKER (simple IOU-based) ====================
class DroneTracker:
    def __init__(self):
        self.tracks = {}
        self.next_id = 1
        self.track_history = defaultdict(lambda: deque(maxlen=30))

    @staticmethod
    def iou(box1, box2):
        x1, y1, x2, y2 = box1
        a1, b1, a2, b2 = box2
        xi1 = max(x1, a1)
        yi1 = max(y1, b1)
        xi2 = min(x2, a2)
        yi2 = min(y2, b2)
        inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
        area1 = max(0, (x2 - x1) * (y2 - y1))
        area2 = max(0, (a2 - a1) * (b2 - b1))
        union = area1 + area2 - inter
        return inter / union if union > 0 else 0

    def update(self, detections):
        current = [(d['box'], d) for d in detections]
        updated = {}
        matched = set()

        for tid, track in list(self.tracks.items()):
            best_iou, best_idx = 0, -1
            for idx, (box, det) in enumerate(current):
                if idx in matched:
                    continue
                i = self.iou(track['box'], box)
                if i > best_iou:
                    best_iou = i
                    best_idx = idx
            if best_idx >= 0 and best_iou > Config.IOU_THRESHOLD:
                matched.add(best_idx)
                box, det = current[best_idx]
                updated[tid] = {
                    'box': box,
                    'center': det['center'],
                    'confidence': det['confidence'],
                    'age': 0,
                    'hits': track.get('hits', 1) + 1,
                    'acoustic': det.get('acoustic', False)
                }
                self.track_history[tid].append(det['center'])
            # else: drop old track (simple policy)

        for idx, (box, det) in enumerate(current):
            if idx in matched:
                continue
            new_id = self.next_id
            self.next_id += 1
            updated[new_id] = {
                'box': box,
                'center': det['center'],
                'confidence': det['confidence'],
                'age': 0,
                'hits': 1,
                'acoustic': det.get('acoustic', False)
            }
            self.track_history[new_id].append(det['center'])

        self.tracks = updated
        return self.tracks


# ==================== THREAT ANALYZER, DEFLECTION, VISUALS (kept similar) ====================
class ThreatAnalyzer:
    @staticmethod
    def distance_to_polygon(point, polygon):
        min_dist = float('inf')
        x, y = point
        for i in range(len(polygon)):
            p1 = polygon[i]
            p2 = polygon[(i + 1) % len(polygon)]
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            if dx == 0 and dy == 0:
                dist = math.hypot(x - p1[0], y - p1[1])
            else:
                t = max(0, min(1, ((x - p1[0]) * dx + (y - p1[1]) * dy) / (dx * dx + dy * dy)))
                proj_x = p1[0] + t * dx
                proj_y = p1[1] + t * dy
                dist = math.hypot(x - proj_x, y - proj_y)
            min_dist = min(min_dist, dist)
        return min_dist

    @staticmethod
    def assess_threat(drone_data, restricted_polygon, speed):
        center = drone_data['center']
        polygon = np.array(restricted_polygon, np.int32).reshape((-1, 1, 2))
        inside = cv2.pointPolygonTest(polygon, center, False) >= 0
        if inside:
            return "CRITICAL", 100
        distance = ThreatAnalyzer.distance_to_polygon(center, restricted_polygon)
        score = 0
        level = "LOW"
        if distance < Config.THREAT_DISTANCE_CRITICAL:
            score += 40
            level = "HIGH"
        elif distance < Config.THREAT_DISTANCE_HIGH:
            score += 30
            level = "MEDIUM"
        elif distance < Config.THREAT_DISTANCE_MEDIUM:
            score += 20
            level = "MEDIUM"
        else:
            score += 10
        if speed > Config.THREAT_SPEED_HIGH:
            score += 30
            if level == "MEDIUM":
                level = "HIGH"
        score += min(30, drone_data['confidence'] * 30)
        return level, min(100, score)


class DeflectionSystem:
    def __init__(self):
        self.active = {}
        self.jammer_active = False
        self.jammer_time = 0

    def select_method(self, threat_level, distance):
        if distance < Config.NET_RANGE:
            return "NET_LAUNCHER"
        if distance < Config.LASER_RANGE:
            return "LASER_POINTER"
        return "RF_JAMMER"

    def activate(self, drone_id, method, position):
        self.active[drone_id] = {'method': method, 'position': position, 'timestamp': time.time()}
        if method == "RF_JAMMER":
            self.jammer_active = True
            self.jammer_time = time.time()
            
    def update_jammer_state(self):
        if self.jammer_active and (time.time() - self.jammer_time > 8):
            self.jammer_active = False



class Visualizer:
    @staticmethod
    def draw_bird_indicators(frame, bird_boxes):
        for (x1, y1, x2, y2) in bird_boxes:
            overlay = frame.copy()
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (255, 150, 0), 2)
            cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)
            cv2.putText(frame, "BIRD", (x1, max(10, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 150, 0), 2)


# ==================== MAIN APPLICATION ====================
def main():
    print("🚀 Initializing Advanced Dual-Model Drone Detection System...")

    detector = DroneDetector("model.pt")
    db = DroneDatabase()
    tracker = DroneTracker()
    threat_analyzer = ThreatAnalyzer()
    deflection_system = DeflectionSystem()
    visualizer = Visualizer()
    alert_system = EnhancedAlertSystem()

    # Configure email placeholders (edit later)
    alert_system.configure_email(
        smtp_server='smtp.gmail.com',
        smtp_port=587,
        from_email='',            # <-- enter sender@gmail.com or leave blank placeholder
        from_password='',         # <-- enter app-password or leave blank placeholder
        to_email=''               # <-- enter recipient@gmail.com or leave blank placeholder
    )

    color_gen = ColorGenerator()
    acoustic = AcousticDetector()

    rectangle_coords = [(350, 50), (550, 50), (550, 250), (350, 250)]

    def mouse_event(event, x, y, flags, param):
        nonlocal rectangle_coords
        if event == cv2.EVENT_LBUTTONDOWN:
            for i, corner in enumerate(rectangle_coords):
                if abs(corner[0] - x) <= 10 and abs(corner[1] - y) <= 10:
                    param['drag'] = True
                    param['index'] = i
                    break
        elif event == cv2.EVENT_LBUTTONUP:
            param['drag'] = False
            param['index'] = -1
        elif event == cv2.EVENT_MOUSEMOVE and param.get('drag', False):
            idx = param.get('index', -1)
            if idx >= 0:
                rectangle_coords[idx] = (x, y)

    while True:
        print("\n" + "="*60)
        print("1. Live Stream (phone)")
        print("2. Recorded Video")
        print("3. Laptop Camera")
        print("4. View Statistics")
        print("5. Exit")
        choice = input("Enter choice: ").strip()

        if choice == "4":
            stats = db.get_statistics()
            print(stats)
            continue
        if choice == "5":
            break
        if choice not in ["1", "2", "3"]:
            print("Invalid")
            continue

        if choice == "1":
            stream = VideoStream("http://172.30.104.138:4747/video").start()
            cam_type = "phone"
        elif choice == "3":
            stream = VideoStream(0).start()
            cam_type = "laptop"
        else:
            video_path = input("Enter video path: ").strip()
            if not os.path.exists(video_path):
                print("File not found")
                continue
            stream = cv2.VideoCapture(video_path)
            cam_type = "video"

        cv2.namedWindow('Dual-Model Drone Detection')
        mouse_state = {'drag': False, 'index': -1}
        cv2.setMouseCallback('Dual-Model Drone Detection', mouse_event, mouse_state)

        prev_time = time.time()
        last_beep = 0

        while True:
            if cam_type in ["phone", "laptop"]:
                frame = stream.read()
                if frame is None:
                    time.sleep(0.01)
                    continue
                if cam_type == "laptop":
                    frame = cv2.flip(frame, 1)
            else:
                ret, frame = stream.read()
                if not ret:
                    break

            now = time.time()
            if now - prev_time < 1 / Config.TARGET_FPS:
                time.sleep(0.001)
                continue
            prev_time = now

            if cam_type == "phone":
                frame = cv2.resize(frame, (640, 480))
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            detections, bird_boxes = detector.detect(rgb)

            # acoustic boost
            for det in detections:
                x1, y1, x2, y2 = det['box']
                a_detected, a_conf = acoustic.detect_sound(frame[y1:y2, x1:x2])
                if a_detected:
                    det['confidence'] = min(1.0, det['confidence'] + acoustic.get_boost())
                    det['acoustic'] = True

            tracks = tracker.update(detections)

            polygon = np.array(rectangle_coords, np.int32).reshape((-1, 1, 2))
            restricted_center = tuple(np.mean(rectangle_coords, axis=0).astype(int))

            threat_count = 0
            max_threat = "CLEAR"
            annotated = frame.copy()

            for tid, track in tracks.items():
                if track['hits'] < Config.MIN_TRACK_HITS:
                    continue

                x1, y1, x2, y2 = track['box']
                center = track['center']

                # speed
                speed = 0
                if tid in tracker.track_history and len(tracker.track_history[tid]) >= 2:
                    p = list(tracker.track_history[tid])
                    dx = p[-1][0] - p[-2][0]
                    dy = p[-1][1] - p[-2][1]
                    speed = math.hypot(dx, dy) * Config.TARGET_FPS

                threat_level, threat_score = threat_analyzer.assess_threat(track, rectangle_coords, speed)
                inside = cv2.pointPolygonTest(polygon, center, False) >= 0

                # DB log detection
                db.log_detection(tid, center[0], center[1], track['confidence'], speed, threat_level, inside)

                if threat_level in ["HIGH", "CRITICAL"]:
                    threat_count += 1
                    max_threat = threat_level
                    key = f"{tid}_{threat_level}"
                    if alert_system.should_send_alert(key):
                        # attach screenshot of annotated frame (draw minimal before sending)
                        tmp = annotated.copy()
                        cv2.rectangle(tmp, (x1, y1), (x2, y2), (0, 0, 255), 2)
                        screenshot_path = alert_system.send_alert_with_screenshot(tid, threat_level, center, tmp)
                        db.log_incident(tid, threat_level, duration=0.0, max_speed=speed,
                                        deflection_method="AUTO", screenshot_path=screenshot_path)
                        if threat_level in ["HIGH", "CRITICAL"] and time.time() - last_beep >= Config.BEEP_INTERVAL:
                            try:
                                if platform.system() == "Windows":
                                    import winsound
                                    winsound.Beep(1000, 300)
                                else:
                                    print("\a")
                            except:
                                pass
                            last_beep = time.time()

                    # deflection activation
                    distance = threat_analyzer.distance_to_polygon(center, rectangle_coords)
                    method = deflection_system.select_method(threat_level, distance)
                    deflection_system.activate(tid, method, center)

                color = color_gen.get_color(tid)
                thickness = 4 if threat_level in ["HIGH", "CRITICAL"] else 2

                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, thickness)
                cv2.putText(annotated, f"ID:{tid} {threat_level}", (x1 + 2, y1 - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                cv2.putText(annotated, f"{int(track['confidence']*100)}%", (x2 - 45, y1 - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                if speed > 0:
                    cv2.putText(annotated, f"{int(speed)} px/s", (x1, y2 + 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 0), 2)

            deflection_system.update_jammer_state()

            visualizer.draw_bird_indicators(annotated, bird_boxes)

            # draw restricted polygon
            rect_color = (0, 255, 0) if max_threat == "CLEAR" else (0, 0, 255)
            overlay = annotated.copy()
            cv2.fillPoly(overlay, [polygon], rect_color)
            cv2.addWeighted(overlay, 0.08, annotated, 0.92, 0, annotated)
            for i in range(4):
                cv2.circle(annotated, rectangle_coords[i], 6, rect_color, -1)
                cv2.line(annotated, rectangle_coords[i], rectangle_coords[(i + 1) % 4], rect_color, 2)

            cv2.imshow('Dual-Model Drone Detection', annotated)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                shot = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                cv2.imwrite(shot, annotated)
                print("Saved:", shot)

        # cleanup
        if cam_type in ["phone", "laptop"]:
            stream.stop()
        else:
            stream.release()
        cv2.destroyAllWindows()

    print("Exiting.")


# ==================== VIDEO STREAM helper ====================
class VideoStream:
    def __init__(self, src):
        self.cap = cv2.VideoCapture(src)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.frame_queue = Queue(maxsize=3)
        self.stopped = False

    def start(self):
        threading.Thread(target=self.update, daemon=True).start()
        return self

    def update(self):
        while not self.stopped:
            ret, frame = self.cap.read()
            if ret:
                if self.frame_queue.full():
                    try:
                        self.frame_queue.get_nowait()
                    except:
                        pass
                self.frame_queue.put(frame)
            else:
                self.stopped = True

    def read(self):
        return self.frame_queue.get() if not self.frame_queue.empty() else None

    def stop(self):
        self.stopped = True
        self.cap.release()


if __name__ == "__main__":
    main()
