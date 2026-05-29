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
import json
import random
import math

# ==================== CONFIGURATION ====================
class Config:
    # Detection settings
    CONFIDENCE_THRESHOLD = 0.3
    DRONE_CLASS_ID = 0
    TARGET_FPS = 10
    
    # Tracking settings
    MAX_TRACK_AGE = 30
    MIN_TRACK_HITS = 3
    IOU_THRESHOLD = 0.3
    
    # Threat levels
    THREAT_DISTANCE_CRITICAL = 50
    THREAT_DISTANCE_HIGH = 100
    THREAT_DISTANCE_MEDIUM = 150
    THREAT_SPEED_HIGH = 200
    
    # Alert settings
    BEEP_INTERVAL = 2
    ALERT_COOLDOWN = 5
    
    # Deflection simulation
    LASER_RANGE = 300
    JAMMER_RADIUS = 200
    NET_RANGE = 150
    
    # NEW: Acoustic detection
    ACOUSTIC_ENABLED = True
    ACOUSTIC_THRESHOLD = 0.6  # Confidence boost if audio detected

# ==================== COLOR GENERATOR ====================
class ColorGenerator:
    """Generate unique colors for each drone"""
    def __init__(self):
        self.colors = {}
        self.used_colors = set()
        
    def get_color(self, drone_id):
        """Get unique color for drone"""
        if drone_id in self.colors:
            return self.colors[drone_id]
        
        # Generate distinct colors using golden ratio
        hue = (drone_id * 137.508) % 360  # Golden angle
        color = self._hsv_to_bgr(hue, 0.9, 0.9)
        self.colors[drone_id] = color
        return color
    
    def _hsv_to_bgr(self, h, s, v):
        """Convert HSV to BGR"""
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

# ==================== ACOUSTIC DETECTOR ====================
class AcousticDetector:
    """Simulated acoustic detection for drone propeller sound"""
    def __init__(self):
        self.enabled = Config.ACOUSTIC_ENABLED
        self.detection_history = deque(maxlen=30)
        
    def detect_sound(self, frame_region):
        """Simulate acoustic detection based on visual cues"""
        if not self.enabled:
            return False, 0.0
        
        # Simulate acoustic detection (in real: use microphone array)
        # For now: random chance based on visual detection
        acoustic_confidence = random.uniform(0.5, 0.95)
        detected = acoustic_confidence > Config.ACOUSTIC_THRESHOLD
        
        self.detection_history.append(detected)
        return detected, acoustic_confidence
    
    def get_acoustic_boost(self):
        """Get confidence boost from acoustic detection"""
        if len(self.detection_history) < 5:
            return 0.0
        
        recent_detections = sum(self.detection_history) / len(self.detection_history)
        return recent_detections * 0.1  # Up to 10% boost

# ==================== DATABASE SETUP ====================
class DroneDatabase:
    def __init__(self, db_name="drone_detections.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.create_tables()
        
    def create_tables(self):
        cursor = self.conn.cursor()
        # Simplified schema - only essential data
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                drone_id INTEGER,
                threat_level TEXT,
                speed REAL,
                in_restricted_area INTEGER
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                drone_id INTEGER,
                threat_level TEXT,
                deflection_method TEXT
            )
        ''')
        self.conn.commit()
    
    def log_detection(self, drone_id, threat, speed, in_area):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO detections (timestamp, drone_id, threat_level, speed, in_restricted_area)
            VALUES (?, ?, ?, ?, ?)
        ''', (datetime.now().isoformat(), drone_id, threat, speed, int(in_area)))
        self.conn.commit()
    
    def log_incident(self, drone_id, threat, deflection):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO incidents (timestamp, drone_id, threat_level, deflection_method)
            VALUES (?, ?, ?, ?)
        ''', (datetime.now().isoformat(), drone_id, threat, deflection))
        self.conn.commit()
    
    def get_statistics(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM detections')
        total = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(DISTINCT drone_id) FROM detections')
        unique = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM incidents')
        incidents = cursor.fetchone()[0]
        cursor.execute('SELECT AVG(speed) FROM detections WHERE speed > 0')
        avg_speed = cursor.fetchone()[0] or 0
        return {
            'total_detections': total,
            'unique_drones': unique,
            'total_incidents': incidents,
            'avg_speed': avg_speed
        }

# ==================== DRONE TRACKER ====================
class DroneTracker:
    def __init__(self):
        self.tracks = {}
        self.next_id = 1
        self.track_history = defaultdict(lambda: deque(maxlen=30))
        
    def calculate_iou(self, box1, box2):
        x1_1, y1_1, x2_1, y2_1 = box1
        x1_2, y1_2, x2_2, y2_2 = box2
        
        xi1 = max(x1_1, x1_2)
        yi1 = max(y1_1, y1_2)
        xi2 = min(x2_1, x2_2)
        yi2 = min(y2_1, y2_2)
        inter_area = max(0, xi2 - xi1) * max(0, yi2 - yi1)
        
        box1_area = (x2_1 - x1_1) * (y2_1 - y1_1)
        box2_area = (x2_2 - x1_2) * (y2_2 - y1_2)
        union_area = box1_area + box2_area - inter_area
        
        return inter_area / union_area if union_area > 0 else 0
    
    def update(self, detections):
        current_boxes = [(d['box'], d) for d in detections]
        matched_tracks = set()
        matched_detections = set()
        updated_tracks = {}
        
        for track_id, track in self.tracks.items():
            best_iou = 0
            best_idx = -1
            
            for idx, (box, det) in enumerate(current_boxes):
                if idx in matched_detections:
                    continue
                iou = self.calculate_iou(track['box'], box)
                if iou > best_iou and iou > Config.IOU_THRESHOLD:
                    best_iou = iou
                    best_idx = idx
            
            if best_idx >= 0:
                matched_tracks.add(track_id)
                matched_detections.add(best_idx)
                box, det = current_boxes[best_idx]
                updated_tracks[track_id] = {
                    'box': box,
                    'center': det['center'],
                    'confidence': det['confidence'],
                    'age': 0,
                    'hits': track['hits'] + 1
                }
                self.track_history[track_id].append(det['center'])
            else:
                if track_id in self.track_history:
                    del self.track_history[track_id]
                continue
        
        for idx, (box, det) in enumerate(current_boxes):
            if idx not in matched_detections:
                new_id = self.next_id
                self.next_id += 1
                updated_tracks[new_id] = {
                    'box': box,
                    'center': det['center'],
                    'confidence': det['confidence'],
                    'age': 0,
                    'hits': 1
                }
                self.track_history[new_id].append(det['center'])
        
        self.tracks = updated_tracks
        return self.tracks

# ==================== THREAT ANALYZER ====================
class ThreatAnalyzer:
    @staticmethod
    def calculate_distance_to_polygon(point, polygon):
        min_dist = float('inf')
        x, y = point
        
        for i in range(len(polygon)):
            p1 = polygon[i]
            p2 = polygon[(i + 1) % len(polygon)]
            
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            if dx == 0 and dy == 0:
                dist = np.sqrt((x - p1[0])**2 + (y - p1[1])**2)
            else:
                t = max(0, min(1, ((x - p1[0]) * dx + (y - p1[1]) * dy) / (dx * dx + dy * dy)))
                proj_x = p1[0] + t * dx
                proj_y = p1[1] + t * dy
                dist = np.sqrt((x - proj_x)**2 + (y - proj_y)**2)
            
            min_dist = min(min_dist, dist)
        
        return min_dist
    
    @staticmethod
    def assess_threat(drone_data, restricted_polygon, speed):
        center = drone_data['center']
        polygon = np.array(restricted_polygon, np.int32).reshape((-1, 1, 2))
        inside = cv2.pointPolygonTest(polygon, center, False) >= 0
        
        if inside:
            return "CRITICAL", 100
        
        distance = ThreatAnalyzer.calculate_distance_to_polygon(center, restricted_polygon)
        
        score = 0
        threat_level = "LOW"
        
        if distance < Config.THREAT_DISTANCE_CRITICAL:
            score += 40
            threat_level = "HIGH"
        elif distance < Config.THREAT_DISTANCE_HIGH:
            score += 30
            threat_level = "MEDIUM"
        elif distance < Config.THREAT_DISTANCE_MEDIUM:
            score += 20
            threat_level = "MEDIUM"
        else:
            score += 10
        
        if speed > Config.THREAT_SPEED_HIGH:
            score += 30
            if threat_level == "MEDIUM":
                threat_level = "HIGH"
        
        score += min(30, drone_data['confidence'] * 30)
        
        return threat_level, min(100, score)

# ==================== DEFLECTION SYSTEM ====================
class DeflectionSystem:
    def __init__(self):
        self.active_deflections = {}
        self.deflection_log = []
        self.jammer_active = False
        self.jammer_activation_time = 0
        
    def select_deflection_method(self, threat_level, distance):
        if distance < Config.NET_RANGE:
            return "NET_LAUNCHER"
        elif distance < Config.LASER_RANGE:
            return "LASER_POINTER"
        else:
            return "RF_JAMMER"
    
    def activate_deflection(self, drone_id, method, position):
        self.active_deflections[drone_id] = {
            'method': method,
            'position': position,
            'timestamp': time.time(),
            'status': 'ACTIVE'
        }
        
        # Activate jammer for all drones if method is RF_JAMMER
        if method == "RF_JAMMER":
            self.jammer_active = True
            self.jammer_activation_time = time.time()
        
        self.deflection_log.append({
            'drone_id': drone_id,
            'method': method,
            'timestamp': datetime.now().isoformat()
        })
        return True
    
    def is_jammer_active(self):
        # Jammer stays active for 3 seconds after last activation
        if self.jammer_active:
            if time.time() - self.jammer_activation_time < 3:
                return True
            else:
                self.jammer_active = False
        return False

# ==================== VISUALIZATION ====================
class Visualizer:
    @staticmethod
    def draw_trajectory(frame, track_history, drone_id, color):
        if drone_id in track_history and len(track_history[drone_id]) > 1:
            points = list(track_history[drone_id])
            for i in range(len(points) - 1):
                thickness = max(1, int(3 * (i + 1) / len(points)))
                cv2.line(frame, points[i], points[i + 1], color, thickness)
    
    @staticmethod
    def draw_prediction(frame, track_history, drone_id, color):
        if drone_id in track_history and len(track_history[drone_id]) >= 3:
            points = list(track_history[drone_id])
            dx = points[-1][0] - points[-3][0]
            dy = points[-1][1] - points[-3][1]
            
            pred_points = []
            for i in range(1, 6):
                pred_x = points[-1][0] + dx * i
                pred_y = points[-1][1] + dy * i
                pred_points.append((int(pred_x), int(pred_y)))
            
            for i in range(len(pred_points) - 1):
                cv2.line(frame, pred_points[i], pred_points[i + 1], color, 2, cv2.LINE_AA)
                cv2.circle(frame, pred_points[i], 3, color, -1)
    
    @staticmethod
    def draw_deflection_visual(frame, deflection_data, restricted_center):
        method = deflection_data['method']
        position = deflection_data['position']
        
        if method == "LASER_POINTER":
            # Animated laser beam
            cv2.line(frame, restricted_center, position, (0, 255, 255), 3)
            for i in range(3):
                offset = i * 5
                cv2.circle(frame, (position[0] + offset, position[1]), 3, (0, 255, 255), -1)
            cv2.putText(frame, "LASER", (position[0] + 15, position[1]), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        
        elif method == "NET_LAUNCHER":
            # Parabolic trajectory
            cv2.arrowedLine(frame, restricted_center, position, (0, 165, 255), 3, tipLength=0.3)
            # Draw net circles
            for i in range(3):
                radius = 10 + i * 5
                cv2.circle(frame, position, radius, (0, 165, 255), 1)
            cv2.putText(frame, "NET", (position[0] + 15, position[1]), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)
    
    @staticmethod
    def draw_jammer_effect(frame, restricted_center, jammer_radius, alpha=0.3):
        """Draw animated RF jammer effect with pulsing circles"""
        overlay = frame.copy()
        
        # Draw multiple pulsing circles
        pulse_offset = int((time.time() * 100) % 30)
        
        for i in range(4):
            radius = jammer_radius - (i * 30) + pulse_offset
            if radius > 20 and radius < jammer_radius:
                alpha_val = 1.0 - (radius / jammer_radius)
                cv2.circle(overlay, restricted_center, radius, (255, 0, 255), 3)
        
        # Main jammer circle
        cv2.circle(overlay, restricted_center, jammer_radius, (255, 0, 255), 2)
        
        # Add transparency
        cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
        
        # Jammer text
        cv2.putText(frame, "RF JAMMER ACTIVE", 
                   (restricted_center[0] - 80, restricted_center[1]), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)
        
        # Add warning symbols
        for angle in range(0, 360, 45):
            rad = math.radians(angle)
            x = int(restricted_center[0] + jammer_radius * math.cos(rad))
            y = int(restricted_center[1] + jammer_radius * math.sin(rad))
            cv2.circle(frame, (x, y), 5, (255, 0, 255), -1)
    
    @staticmethod
    def draw_analytics_panel(frame, stats, threat_count, acoustic_active):
        panel_height = 180
        panel = np.zeros((panel_height, frame.shape[1], 3), dtype=np.uint8)
        panel[:] = (30, 30, 30)
        
        # Column 1
        y_offset = 25
        cv2.putText(panel, f"Total Detections: {stats['total_detections']}", 
                   (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        y_offset += 25
        cv2.putText(panel, f"Unique Drones: {stats['unique_drones']}", 
                   (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        y_offset += 25
        cv2.putText(panel, f"Active Threats: {threat_count}", 
                   (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255) if threat_count > 0 else (0, 255, 0), 2)
        y_offset += 25
        cv2.putText(panel, f"Avg Speed: {stats['avg_speed']:.1f} px/s", 
                   (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # Column 2
        y_offset = 25
        cv2.putText(panel, f"Total Incidents: {stats['total_incidents']}", 
                   (300, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        y_offset += 25
        acoustic_status = "ACTIVE" if acoustic_active else "STANDBY"
        acoustic_color = (0, 255, 0) if acoustic_active else (150, 150, 150)
        cv2.putText(panel, f"Acoustic: {acoustic_status}", 
                   (300, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, acoustic_color, 1)
        y_offset += 25
        cv2.putText(panel, f"Time: {datetime.now().strftime('%H:%M:%S')}", 
                   (300, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # Legend
        y_offset = 130
        cv2.putText(panel, "Threat Levels:", (10, y_offset), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        cv2.rectangle(panel, (120, y_offset-10), (140, y_offset-5), (0, 255, 0), -1)
        cv2.putText(panel, "LOW", (145, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        cv2.rectangle(panel, (200, y_offset-10), (220, y_offset-5), (0, 255, 255), -1)
        cv2.putText(panel, "MEDIUM", (225, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        cv2.rectangle(panel, (310, y_offset-10), (330, y_offset-5), (0, 100, 255), -1)
        cv2.putText(panel, "HIGH", (335, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        cv2.rectangle(panel, (400, y_offset-10), (420, y_offset-5), (0, 0, 255), -1)
        cv2.putText(panel, "CRITICAL", (425, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        
        combined = np.vstack([frame, panel])
        return combined

# ==================== ALERT SYSTEM ====================
class AlertSystem:
    def __init__(self):
        self.last_alert_time = {}
        self.alert_log = []
        
    def should_send_alert(self, drone_id, threat_level):
        current_time = time.time()
        key = f"{drone_id}_{threat_level}"
        
        if key not in self.last_alert_time:
            self.last_alert_time[key] = current_time
            return True
        
        if current_time - self.last_alert_time[key] > Config.ALERT_COOLDOWN:
            self.last_alert_time[key] = current_time
            return True
        
        return False
    
    def send_alert(self, drone_id, threat_level, position):
        alert = {
            'timestamp': datetime.now().isoformat(),
            'drone_id': drone_id,
            'threat_level': threat_level,
            'position': position
        }
        self.alert_log.append(alert)
        print(f"\n⚠️  ALERT: Drone {drone_id} - {threat_level} threat")

def beep():
    try:
        if platform.system() == "Windows":
            import winsound
            winsound.Beep(1000, 300)
        else:
            print("\a")
    except:
        pass

# ==================== VIDEO STREAM ====================
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

# ==================== MAIN APPLICATION ====================
def main():
    print("🚀 Initializing Advanced Drone Detection System...")
    model = YOLO("model.pt")
    print(f"✓ Model loaded: {model.names}")
    
    db = DroneDatabase()
    tracker = DroneTracker()
    threat_analyzer = ThreatAnalyzer()
    deflection_system = DeflectionSystem()
    visualizer = Visualizer()
    alert_system = AlertSystem()
    color_gen = ColorGenerator()
    acoustic_detector = AcousticDetector()
    
    rectangle_coords = [(350, 50), (550, 50), (550, 250), (350, 250)]
    rectangle_drag = False
    drag_corner = -1
    
    def mouse_event(event, x, y, flags, param):
        nonlocal rectangle_coords, rectangle_drag, drag_corner
        if event == cv2.EVENT_LBUTTONDOWN:
            for i, corner in enumerate(rectangle_coords):
                if abs(corner[0]-x) <= 10 and abs(corner[1]-y) <= 10:
                    rectangle_drag = True
                    drag_corner = i
                    break
        elif event == cv2.EVENT_LBUTTONUP:
            rectangle_drag = False
        elif event == cv2.EVENT_MOUSEMOVE and rectangle_drag:
            rectangle_coords[drag_corner] = (x, y)
    
    while True:
        print("\n" + "="*50)
        print("🛸 ADVANCED DRONE DETECTION & DEFLECTION SYSTEM")
        print("="*50)
        print("1. 📱 Live Stream (Phone Camera)")
        print("2. 🎥 Recorded Video")
        print("3. 💻 Laptop Camera")
        print("4. 📊 View Statistics")
        print("5. 🚪 Exit")
        print("="*50)
        choice = input("Enter choice: ").strip()
        
        if choice == "4":
            stats = db.get_statistics()
            print("\n📊 SYSTEM STATISTICS")
            print(f"Total Detections: {stats['total_detections']}")
            print(f"Unique Drones: {stats['unique_drones']}")
            print(f"Total Incidents: {stats['total_incidents']}")
            print(f"Average Speed: {stats['avg_speed']:.2f} px/s")
            continue
        
        if choice == "5":
            print("👋 Exiting...")
            break
        
        if choice not in ["1", "2", "3"]:
            print("❌ Invalid choice")
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
                print("❌ File not found")
                continue
            stream = cv2.VideoCapture(video_path)
            cam_type = "video"
        
        cv2.namedWindow('Advanced Drone Detection')
        cv2.setMouseCallback('Advanced Drone Detection', mouse_event)
        
        frame_count = 0
        prev_time = time.time()
        last_beep_time = 0
        speed_tracker = defaultdict(lambda: deque(maxlen=10))
        
        print("\n✓ System active. Press 'q' to stop, 's' to save screenshot")
        
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
            
            current_time = time.time()
            if cam_type in ["phone", "laptop"] and current_time - prev_time < 1 / Config.TARGET_FPS:
                time.sleep(0.001)
                continue
            prev_time = current_time
            
            if cam_type == "phone":
                frame = cv2.resize(frame, (640, 480))
            
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = model(rgb_frame, verbose=False)
            annotated = frame.copy()
            
            detections = []
            for r in results:
                for box in r.boxes:
                    conf = float(box.conf[0])
                    cls = int(box.cls[0])
                    if conf < Config.CONFIDENCE_THRESHOLD or cls != Config.DRONE_CLASS_ID:
                        continue
                    
                    x1, y1, x2, y2 = box.xyxy[0].int().tolist()
                    center = ((x1+x2)//2, (y1+y2)//2)
                    
                    # Acoustic detection
                    acoustic_detected, acoustic_conf = acoustic_detector.detect_sound(frame[y1:y2, x1:x2])
                    if acoustic_detected:
                        conf = min(1.0, conf + acoustic_detector.get_acoustic_boost())
                    
                    detections.append({
                        'box': (x1, y1, x2, y2),
                        'center': center,
                        'confidence': conf,
                        'acoustic': acoustic_detected
                    })
            
            tracks = tracker.update(detections)
            
            for tid in list(tracker.track_history.keys()):
                if tid not in tracks:
                    del tracker.track_history[tid]
            
            polygon = np.array(rectangle_coords, np.int32).reshape((-1, 1, 2))
            restricted_center = tuple(np.mean(rectangle_coords, axis=0).astype(int))
            
            threat_count = 0
            max_threat_level = "CLEAR"
            acoustic_active = False
            
            for track_id, track in tracks.items():
                if track['hits'] < Config.MIN_TRACK_HITS:
                    continue
                
                x1, y1, x2, y2 = track['box']
                center = track['center']
                
                # Calculate speed
                speed = 0
                if track_id in tracker.track_history and len(tracker.track_history[track_id]) >= 2:
                    points = list(tracker.track_history[track_id])
                    dx = points[-1][0] - points[-2][0]
                    dy = points[-1][1] - points[-2][1]
                    speed = ((dx**2 + dy**2)**0.5) * Config.TARGET_FPS
                    speed_tracker[track_id].append(speed)
                
                # Assess threat
                threat_level, threat_score = threat_analyzer.assess_threat(track, rectangle_coords, speed)
                
                # Check if inside restricted area
                inside = cv2.pointPolygonTest(polygon, center, False) >= 0
                
                # Log to database
                db.log_detection(track_id, threat_level, speed, inside)
                
                # Check acoustic detection
                if 'acoustic' in track and track.get('acoustic', False):
                    acoustic_active = True
                
                # Update threat tracking
                if threat_level in ["HIGH", "CRITICAL"]:
                    threat_count += 1
                    max_threat_level = threat_level
                    
                    # Send alert
                    if alert_system.should_send_alert(track_id, threat_level):
                        alert_system.send_alert(track_id, threat_level, center)
                        
                        if threat_level == "CRITICAL" and current_time - last_beep_time >= Config.BEEP_INTERVAL:
                            beep()
                            last_beep_time = current_time
                    
                    # Activate deflection
                    distance = threat_analyzer.calculate_distance_to_polygon(center, rectangle_coords)
                    deflection_method = deflection_system.select_deflection_method(threat_level, distance)
                    deflection_system.activate_deflection(track_id, deflection_method, center)
                    
                    # Log incident
                    db.log_incident(track_id, threat_level, deflection_method)
                
                # Get unique color for this drone
                drone_color = color_gen.get_color(track_id)
                
                # Draw bounding box with drone-specific color
                thickness = 3 if threat_level in ["HIGH", "CRITICAL"] else 2
                cv2.rectangle(annotated, (x1, y1), (x2, y2), drone_color, thickness)
                
                # Draw info with background
                info_text = f"ID:{track_id} {threat_level}"
                text_size = cv2.getTextSize(info_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                cv2.rectangle(annotated, (x1, y1-text_size[1]-10), (x1+text_size[0]+5, y1), drone_color, -1)
                cv2.putText(annotated, info_text, (x1+2, y1-5), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                
                # Show speed
                if speed > 0:
                    cv2.putText(annotated, f"{speed:.0f}px/s", (x1, y2+20),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, drone_color, 2)
                
                # Acoustic indicator
                if track.get('acoustic', False):
                    cv2.circle(annotated, (x2-10, y1+10), 5, (0, 255, 0), -1)
                    cv2.putText(annotated, "A", (x2-8, y1+13), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 0, 0), 1)
                
                # Draw trajectory with drone-specific color
                visualizer.draw_trajectory(annotated, tracker.track_history, track_id, drone_color)
                
                # Draw prediction with brighter shade
                pred_color = tuple(min(255, c + 50) for c in drone_color)
                visualizer.draw_prediction(annotated, tracker.track_history, track_id, pred_color)
                
                # Draw threat score bar
                bar_width = 60
                bar_height = 8
                bar_x = x1
                bar_y = y1 - 25
                
                # Background
                cv2.rectangle(annotated, (bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height), (50, 50, 50), -1)
                
                # Threat level bar
                filled_width = int((threat_score / 100) * bar_width)
                bar_color = (0, 255, 0) if threat_score < 40 else (0, 255, 255) if threat_score < 70 else (0, 0, 255)
                cv2.rectangle(annotated, (bar_x, bar_y), (bar_x + filled_width, bar_y + bar_height), bar_color, -1)
                
                # Border
                cv2.rectangle(annotated, (bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height), (255, 255, 255), 1)
            
            # Draw RF Jammer effect if active
            if deflection_system.is_jammer_active():
                visualizer.draw_jammer_effect(annotated, restricted_center, Config.JAMMER_RADIUS, 0.2)
            
            # Draw other deflection visualizations
            for drone_id, deflection_data in deflection_system.active_deflections.items():
                if current_time - deflection_data['timestamp'] < 2:
                    if deflection_data['method'] != "RF_JAMMER":  # Don't redraw jammer
                        visualizer.draw_deflection_visual(annotated, deflection_data, restricted_center)
            
            # Draw restricted area
            rect_color = (0, 0, 255) if max_threat_level in ["HIGH", "CRITICAL"] else (0, 255, 0)
            
            # Draw filled semi-transparent zone
            overlay = annotated.copy()
            cv2.fillPoly(overlay, [polygon], rect_color)
            cv2.addWeighted(overlay, 0.15, annotated, 0.85, 0, annotated)
            
            # Draw border
            for i in range(4):
                cv2.circle(annotated, rectangle_coords[i], 7, rect_color, -1)
                cv2.circle(annotated, rectangle_coords[i], 8, (255, 255, 255), 2)
                cv2.line(annotated, rectangle_coords[i], rectangle_coords[(i+1)%4], rect_color, 3)
            
            # Status text with background
            status = f"Status: {max_threat_level}" if threat_count > 0 else "Status: CLEAR"
            text_size = cv2.getTextSize(status, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
            cv2.rectangle(annotated, (5, 5), (15+text_size[0], 40), (0, 0, 0), -1)
            cv2.putText(annotated, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, rect_color, 2)
            
            # Draw analytics panel
            stats = db.get_statistics()
            annotated = visualizer.draw_analytics_panel(annotated, stats, threat_count, acoustic_active)
            
            cv2.imshow('Advanced Drone Detection', annotated)
            frame_count += 1
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                screenshot_path = f"incident_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                cv2.imwrite(screenshot_path, annotated)
                print(f"📸 Screenshot saved: {screenshot_path}")
        
        # Cleanup
        if cam_type in ["phone", "laptop"]:
            stream.stop()
        else:
            stream.release()
        cv2.destroyAllWindows()
        
        print(f"\n✓ Session complete: {frame_count} frames processed")

if __name__ == "__main__":
    main()