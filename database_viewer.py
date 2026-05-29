import sqlite3
import csv
from datetime import datetime
import os

DB_FILE = "drone_detections.db"

class DatabaseViewer:
    def __init__(self, db_name=DB_FILE):
        if not os.path.exists(db_name):
            print(f"❌ Database '{db_name}' not found. Run adv_Dds first to create it.")
            raise SystemExit(1)
        self.conn = sqlite3.connect(db_name)
        self.cur = self.conn.cursor()

    def menu(self):
        while True:
            print("\n1. Overall stats\n2. Recent detections\n3. Incidents log\n4. Drone-wise analysis\n5. Export CSV\n6. Generate simple report\n7. Exit")
            choice = input("Choice: ").strip()
            if choice == "1":
                self.overall_stats()
            elif choice == "2":
                self.recent_detections()
            elif choice == "3":
                self.incidents_log()
            elif choice == "4":
                self.drone_wise()
            elif choice == "5":
                self.export_csv()
            elif choice == "6":
                self.generate_report()
            elif choice == "7":
                break
            else:
                print("Invalid")

    def overall_stats(self):
        self.cur.execute("SELECT COUNT(*) FROM detections")
        total = self.cur.fetchone()[0]
        self.cur.execute("SELECT COUNT(DISTINCT drone_id) FROM detections")
        unique = self.cur.fetchone()[0]
        self.cur.execute("SELECT COUNT(*) FROM incidents")
        incidents = self.cur.fetchone()[0]
        self.cur.execute("SELECT AVG(confidence) FROM detections")
        avg_conf = self.cur.fetchone()[0] or 0
        self.cur.execute("SELECT AVG(speed) FROM detections WHERE speed > 0")
        avg_speed = self.cur.fetchone()[0] or 0
        self.cur.execute("SELECT COUNT(*) FROM detections WHERE in_restricted_area = 1")
        breaches = self.cur.fetchone()[0]
        print(f"\nTotal detections: {total}\nUnique drones: {unique}\nIncidents: {incidents}\nAvg conf: {avg_conf:.2f}\nAvg speed: {avg_speed:.2f}\nBreaches: {breaches}")

    def recent_detections(self, n=20):
        self.cur.execute("""
            SELECT timestamp, drone_id, x, y, confidence, speed, threat_level, in_restricted_area
            FROM detections ORDER BY timestamp DESC LIMIT ?
        """, (n,))
        rows = self.cur.fetchall()
        if not rows:
            print("No detections.")
            return
        print(f"\n{'Time':<20} {'ID':<4} {'Pos':<12} {'Conf':<6} {'Speed':<8} {'Threat':<8} {'Breach'}")
        for r in rows:
            t, did, x, y, conf, speed, threat, breach = r
            tstr = datetime.fromisoformat(t).strftime("%Y-%m-%d %H:%M:%S")
            pos = f"({x},{y})"
            confs = f"{conf*100:.1f}%" if conf is not None else "N/A"
            speeds = f"{speed:.1f}" if speed and speed > 0 else "N/A"
            breach_s = "YES" if breach else "NO"
            print(f"{tstr:<20} {did:<4} {pos:<12} {confs:<6} {speeds:<8} {threat:<8} {breach_s}")

    def incidents_log(self):
        self.cur.execute("""
            SELECT timestamp, drone_id, threat_level, duration, max_speed, deflection_method, screenshot_path
            FROM incidents ORDER BY timestamp DESC
        """)
        rows = self.cur.fetchall()
        if not rows:
            print("No incidents.")
            return
        print(f"\n{'Time':<20} {'ID':<4} {'Threat':<8} {'Dur':<6} {'MaxSpd':<8} {'Method':<12} {'Screenshot'}")
        for r in rows:
            t, did, threat, dur, msp, method, shot = r
            tstr = datetime.fromisoformat(t).strftime("%Y-%m-%d %H:%M:%S")
            print(f"{tstr:<20} {did:<4} {threat:<8} {dur if dur else 0:<6} {msp if msp else 0:<8} {method:<12} {shot}")

    def drone_wise(self):
        self.cur.execute("""
            SELECT drone_id, COUNT(*) as cnt, AVG(confidence) as avg_conf, AVG(speed) as avg_spd, MAX(speed) as max_spd,
                   SUM(in_restricted_area) as breaches
            FROM detections GROUP BY drone_id ORDER BY cnt DESC
        """)
        rows = self.cur.fetchall()
        if not rows:
            print("No drone data.")
            return
        print(f"\n{'ID':<4} {'Detections':<10} {'AvgConf':<8} {'AvgSpd':<8} {'MaxSpd':<8} {'Breaches'}")
        for r in rows:
            did, cnt, ac, avs, mxs, br = r
            acs = f"{(ac*100):.1f}%" if ac else "N/A"
            avs_s = f"{avs:.1f}" if avs else "N/A"
            mxs_s = f"{mxs:.1f}" if mxs else "N/A"
            print(f"{did:<4} {cnt:<10} {acs:<8} {avs_s:<8} {mxs_s:<8} {br}")

    def export_csv(self):
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.cur.execute("SELECT * FROM detections")
        rows = self.cur.fetchall()
        if rows:
            fname = f"detections_{now}.csv"
            with open(fname, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([c[0] for c in self.cur.description])
                writer.writerows(rows)
            print("Exported:", fname)
        self.cur.execute("SELECT * FROM incidents")
        rows2 = self.cur.fetchall()
        if rows2:
            fname2 = f"incidents_{now}.csv"
            with open(fname2, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([c[0] for c in self.cur.description])
                writer.writerows(rows2)
            print("Exported:", fname2)

    def generate_report(self):
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"report_{now}.txt"
        with open(fname, "w") as f:
            f.write("DRONE DETECTION REPORT\n")
            f.write("======================\n")
            self.cur.execute("SELECT COUNT(*) FROM detections")
            f.write(f"Total detections: {self.cur.fetchone()[0]}\n")
            self.cur.execute("SELECT COUNT(DISTINCT drone_id) FROM detections")
            f.write(f"Unique drones: {self.cur.fetchone()[0]}\n")
            self.cur.execute("SELECT COUNT(*) FROM incidents")
            f.write(f"Incidents: {self.cur.fetchone()[0]}\n")
        print("Report generated:", fname)

if __name__ == "__main__":
    v = DatabaseViewer()
    v.menu()
