# fraud_schedular.py
from database import Database
from ml_engine import FraudDetector
import time

db = Database()
fd = FraudDetector()

print("Scheduler running...")

while True:
    conn = db.get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id FROM employees")
    employees = cur.fetchall()
    cur.close()
    conn.close()

    for emp in employees:
        fd.analyze_and_flag(db, emp["id"])

    time.sleep(60)
 