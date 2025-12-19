# database.py
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
import random
import decimal

class Database:
    def __init__(self):
        self.db_config = {
            "host": "localhost",
            "user": "root",
            "password": "Tanisha@1105",
            "database": "fraud_detection"
        }

    def get_connection(self):
        return mysql.connector.connect(**self.db_config)

    # ------------------------------
    # CREATE ALL TABLES
    # ------------------------------
    def init_db(self):
        conn = self.get_connection()
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100),
            email VARCHAR(100) UNIQUE,
            password_hash VARCHAR(255),
            role VARCHAR(50) DEFAULT 'employee'
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS login_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            employee_id INT,
            login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            logout_time TIMESTAMP NULL,
            ip_address VARCHAR(50),
            device_id VARCHAR(100),
            FOREIGN KEY (employee_id) REFERENCES employees(id)
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            employee_id INT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            mouse_activity INT DEFAULT 0,
            keyboard_activity INT DEFAULT 0,
            idle_time INT DEFAULT 0,
            active_window_title VARCHAR(255) NULL, 
            FOREIGN KEY (employee_id) REFERENCES employees(id)
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS fraud_alerts (
            id INT AUTO_INCREMENT PRIMARY KEY,
            employee_id INT,
            risk_score FLOAT,
            alert_level VARCHAR(20),
            description TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (employee_id) REFERENCES employees(id)
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            email VARCHAR(100) UNIQUE,
            password_hash VARCHAR(255)
        )
        """)

        conn.commit()
        cur.close()
        conn.close()

    # SEED DEMO DATA

    def seed_demo_data(self):
        conn = self.get_connection()
        cur = conn.cursor(dictionary=True)

        cur.execute("SELECT COUNT(*) AS count FROM employees")
        if cur.fetchone()['count'] > 0:
            cur.close()
            conn.close()
            return

        employees = [
            ('Vikram Singh', 'vikram@company.com', 'password123', 'employee'),
            ('Priya Sharma', 'priya@company.com', 'password123', 'employee'),
            ('Anand Patil', 'anand@company.com', 'password123', 'employee'),
            ('Kavita Mhatre', 'kavita@company.com', 'password123', 'manager'),
            ('Krish Patel', 'krish@company.com', 'password123', 'employee'),
            ('Saloni Shukla ', 'Saloni@company.com', 'password123', 'employee')
        ]

        for name, email, password, role in employees:
            cur.execute("""
                INSERT INTO employees (name, email, password_hash, role)
                VALUES (%s, %s, %s, %s)
            """, (name, email, generate_password_hash(password), role))

        cur.execute("""
            INSERT INTO admin_users (email, password_hash)
            VALUES (%s, %s)
        """, ('admin@company.com', generate_password_hash('admin123')))

        conn.commit()
        cur.close()
        conn.close()

    # ------------------------------
    # LOGIN / AUTH
    # ------------------------------
    def get_employee_by_email(self, email):
        conn = self.get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM employees WHERE email = %s", (email,))
        data = cur.fetchone()
        cur.close()
        conn.close()
        return data

    def get_admin_by_email(self, email):
        conn = self.get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM admin_users WHERE email = %s", (email,))
        data = cur.fetchone()
        cur.close()
        conn.close()
        return data
    def get_employee_by_id(self, employee_id): 
        """Fetches a single employee record by ID, including hardcoded Department/Shift."""
        conn = self.get_connection()
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute("""
                SELECT id, name, email, role
                FROM employees 
                WHERE id = %s
            """, (employee_id,))
            data = cur.fetchone()
            
            if data:
                data['department'] = 'Information Technology'
                data['shift_time'] = '9:00 AM - 5:00 PM'
            
            return data
        except Exception as e:
            print(f"Error fetching employee by ID: {e}")
            return None
        finally:
            cur.close()
            conn.close()

    # LOGIN LOGS
    def create_login_log(self, employee_id, ip_address, device_id):
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO login_logs (employee_id, ip_address, device_id)
            VALUES (%s, %s, %s)
        """, (employee_id, ip_address, device_id))
        conn.commit()
        cur.close()
        conn.close()

    def update_logout_time(self, employee_id):
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE login_logs
            SET logout_time = CURRENT_TIMESTAMP
            WHERE employee_id = %s AND logout_time IS NULL
        """, (employee_id,))
        conn.commit()
        cur.close()
        conn.close()

    def is_employee_active(self, employee_id):
        """Checks if an employee has a current login session (login_time set, logout_time is NULL)."""
        conn = self.get_connection()
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute("""
                SELECT COUNT(*) AS count 
                FROM login_logs
                WHERE employee_id = %s AND logout_time IS NULL
            """, (employee_id,))
            count = cur.fetchone()['count']
            return count > 0
        except Exception as e:
            print(f"Error checking active status: {e}")
            return False
        finally:
            cur.close()
            conn.close()

    # ------------------------------
    # ACTIVITY LOGS 
    # ------------------------------
    def create_activity_log(self, employee_id, mouse, keyboard, idle, active_window_title=''):
        """Inserts an activity log record, including the active window title."""
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO activity_logs (employee_id, mouse_activity, keyboard_activity, idle_time, active_window_title)
            VALUES (%s, %s, %s, %s, %s)
        """, (employee_id, mouse, keyboard, idle, active_window_title))
        last_id = cur.lastrowid
        conn.commit()
        cur.close()
        conn.close()
        return last_id
    
    def get_activity_log_by_id(self, log_id): # NEW: Helper to fetch single log by ID
        conn = self.get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM activity_logs WHERE id = %s", (log_id,))
        log = cur.fetchone()
        cur.close()
        conn.close()
        return log

    def get_activity_summary(self, employee_id):
        conn = self.get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT 
                SUM(mouse_activity) AS total_mouse,
                SUM(keyboard_activity) AS total_keyboard,
                SUM(idle_time) AS total_idle,
                COUNT(*) * 15 AS total_time,
                COUNT(*) AS log_count
            FROM activity_logs
            WHERE employee_id = %s
        """, (employee_id,))
        data = cur.fetchone()
        if data['total_mouse'] is None:
            data = {
                'total_mouse': 0,
                'total_keyboard': 0,
                'total_idle': 0,
                'total_time': 0,
                'log_count': 0
            }
        if data:
            for key in data:
                if isinstance(data[key], decimal.Decimal):
                    data[key] = float(data[key])
            
        cur.close()
        conn.close()
        return data

    def get_recent_activity_logs(self, employee_id, limit=10):
        conn = self.get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT * FROM activity_logs
            WHERE employee_id = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """, (employee_id, limit))
        logs = cur.fetchall()
        cur.close()
        conn.close()
        return logs
    
    def get_detailed_activity(self, employee_id, limit=100):
        """Retrieves detailed activity logs for a specific employee, including the window title."""
        conn = self.get_connection()
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute("""
                SELECT 
                    timestamp, mouse_activity, keyboard_activity, idle_time, active_window_title
                FROM activity_logs
                WHERE employee_id = %s
                ORDER BY timestamp DESC
                LIMIT %s
            """, (employee_id, limit))
            logs = cur.fetchall()
            return logs
        except Exception as e:
            print(f"Error fetching detailed activity: {e}")
            return []
        finally:
            cur.close()
            conn.close()


    # ------------------------------
    # ALERTS
    # ------------------------------
    def create_fraud_alert(self, employee_id, risk, level, description):
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO fraud_alerts (employee_id, risk_score, alert_level, description)
            VALUES (%s, %s, %s, %s)
        """, (employee_id, risk, level, description))
        conn.commit()
        cur.close()
        conn.close()

    def get_recent_alerts(self, limit=10):
        conn = self.get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT fa.*, e.name AS employee_name, e.role AS employee_role
            FROM fraud_alerts fa
            JOIN employees e ON fa.employee_id = e.id
            ORDER BY fa.timestamp DESC
            LIMIT %s
        """, (limit,))
        alerts = cur.fetchall()
        cur.close()
        conn.close()
        return alerts

    def get_all_alerts(self):
        conn = self.get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT fa.*, e.name AS employee_name, e.role AS employee_role
            FROM fraud_alerts fa
            JOIN employees e ON fa.employee_id = e.id
            ORDER BY fa.timestamp DESC
        """)
        data = cur.fetchall()
        cur.close()
        conn.close()
        return data

    # ------------------------------
    # ADMIN DASHBOARD QUERIES
    # ------------------------------
    def get_dashboard_stats(self):
        conn = self.get_connection()
        cur = conn.cursor(dictionary=True)

        cur.execute("SELECT COUNT(*) AS count FROM fraud_alerts WHERE alert_level='High'")
        critical_alerts = cur.fetchone()['count']

        cur.execute("SELECT COUNT(*) AS count FROM employees")
        total_employees = cur.fetchone()['count']

        cur.execute("""
            SELECT COUNT(DISTINCT employee_id) AS count
            FROM login_logs
            WHERE login_time > NOW() - INTERVAL 1 HOUR
        """)
        active_employees = cur.fetchone()['count']

        cur.execute("""
            SELECT 
                IFNULL(ROUND(
                    100 * SUM(mouse_activity + keyboard_activity) /
                    (SUM(mouse_activity + keyboard_activity) + SUM(idle_time)), 1
                ), 0) AS productivity
            FROM activity_logs
            WHERE DATE(timestamp) = CURDATE()
        """)
        avg_productivity = cur.fetchone()['productivity']

        cur.close()
        conn.close()

        return {
            "critical_alerts": critical_alerts,
            "total_employees": total_employees,
            "active_employees": active_employees,
            "avg_productivity": float(avg_productivity)
        }

    def get_employees_with_risk_scores(self):
        conn = self.get_connection()
        cur = conn.cursor(dictionary=True)

        cur.execute("""
            SELECT 
                e.id, e.name, e.email, e.role,
                    'Engineering' AS department, 
                    '9:00 AM - 5:00 PM' AS shift_time,
                COALESCE((
                    SELECT risk_score FROM fraud_alerts 
                    WHERE employee_id = e.id
                    ORDER BY timestamp DESC LIMIT 1
                ), 0) AS latest_risk_score,
                
                COALESCE((
                    SELECT alert_level FROM fraud_alerts 
                    WHERE employee_id = e.id
                    ORDER BY timestamp DESC LIMIT 1
                ), 'Low') AS alert_level

            FROM employees e
            ORDER BY latest_risk_score DESC
        """)

        data = cur.fetchall()
        cur.close()
        conn.close()
        return data

    # ------------------------------
    # HOURLY ACTIVITY (FOR CHARTS)
    # ------------------------------
    def get_hourly_activity_data(self):
        conn = self.get_connection()
        cur = conn.cursor(dictionary=True)

        cur.execute("""
            SELECT 
                HOUR(timestamp) AS hour,
                AVG(mouse_activity + keyboard_activity) AS avg_activity,
                AVG(idle_time) AS avg_idle
            FROM activity_logs
            WHERE timestamp > NOW() - INTERVAL 7 DAY
            GROUP BY HOUR(timestamp)
            ORDER BY hour
        """)

        data = cur.fetchall()
        cur.close()
        conn.close()
        return data

    # ------------------------------
    # ML ACTIVITY DATA
    # ------------------------------
    def get_employee_activity_for_ml(self, employee_id):
        """Returns latest activity logs for ML model using real database tables."""
        try:
            conn = self.get_connection()
            cur = conn.cursor(dictionary=True)

            cur.execute("""
                SELECT 
                    a.idle_time,
                    a.mouse_activity,
                    a.keyboard_activity,
                    HOUR(a.timestamp) AS hour,
                    l.ip_address,
                    l.device_id
                FROM activity_logs a
                LEFT JOIN login_logs l 
                    ON a.employee_id = l.employee_id
                    AND DATE(a.timestamp) = DATE(l.login_time)
                WHERE a.employee_id = %s
                ORDER BY a.timestamp DESC
                LIMIT 100
            """, (employee_id,))

            rows = cur.fetchall()
            cur.close()
            conn.close()
            return rows

        except Exception as e:
            print("Error fetching ML activity:", e)
            return []

    # ------------------------------
    # EMPLOYEE MANAGEMENT (NEW)
    # ------------------------------
    def get_employee_by_id(self, employee_id):
        """Fetches a single employee record by ID."""
        conn = self.get_connection()
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute("SELECT id, name, email, role FROM employees WHERE id = %s", (employee_id,))
            data = cur.fetchone()
            return data
        except Exception as e:
            print(f"Error fetching employee by ID: {e}")
            return None
        finally:
            cur.close()
            conn.close()

    def create_employee(self, name, email, password_hash, role='employee'):
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO employees (name, email, password_hash, role)
            VALUES (%s, %s, %s, %s)
        """, (name, email, password_hash, role))
        conn.commit()
        cur.close()
        conn.close()

    def delete_employee(self, employee_id):
        conn = self.get_connection()
        cur = conn.cursor()
        # MUST delete related records first due to foreign key constraints
        cur.execute("DELETE FROM fraud_alerts WHERE employee_id = %s", (employee_id,))
        cur.execute("DELETE FROM activity_logs WHERE employee_id = %s", (employee_id,))
        cur.execute("DELETE FROM login_logs WHERE employee_id = %s", (employee_id,))
        # Finally, delete the employee
        cur.execute("DELETE FROM employees WHERE id = %s", (employee_id,))
        conn.commit()
        cur.close()
        conn.close()

    def get_all_employees(self):
        """Fetches all employee records (ID, name, email, role) from the database."""
        conn = self.get_connection()
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute("SELECT id, name, email, role FROM employees ORDER BY name")
            data = cur.fetchall()
            return data
        except Exception as e:
            print(f"Error fetching all employees: {e}")
            return []
        finally:
            cur.close()
            conn.close()
    
    def get_risk_distribution(self):
        """
        Returns count of alerts grouped by alert level
        """
        conn = self.get_connection()
        cur = conn.cursor(dictionary=True)

        cur.execute("""
            SELECT 
                COALESCE(alert_level, 'Low') AS alert_level,
                COUNT(*) AS count
            FROM fraud_alerts
            GROUP BY alert_level
        """)

        rows = cur.fetchall()
        cur.close()
        conn.close()

        distribution = {
            "Low": 0,
            "Medium": 0,
            "High": 0
        }

        for row in rows:
            level = row["alert_level"]
            if level in distribution:
                distribution[level] = int(row["count"])

        return distribution

