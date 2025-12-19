#app.py
import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, emit, join_room, leave_room
from functools import wraps
from database import Database
from ml_engine import FraudDetector
from dotenv import load_dotenv
import csv
from io import StringIO
import datetime
import time
from flask import session
# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
# Generate a secret key for session management
app.secret_key = os.urandom(24) 

db = Database()
fraud_detector = FraudDetector() 

# INIT APP
load_dotenv()
app = Flask(__name__)
app.secret_key = os.urandom(24)
db = Database()
fraud_detector = FraudDetector()

socketio = SocketIO(app, cors_allowed_origins="*", ping_interval=5, ping_timeout=10)

# AUTH DECORATORS
def login_required(f):
    """Decorator to check if an employee is logged in."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'employee_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    """Decorator to check if an admin is logged in."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'admin_id' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return wrapper

# USER LOGIN / LOGOUT
@app.route('/')
def index():
    """
    Landing Page route for the PaperSet AI website.
    It links to the Employee Login and Admin Access pages.
    """
    # If the user is already logged in, redirect them to their respective dashboard
    if 'employee_id' in session:
        return redirect(url_for('dashboard'))
    if 'admin_id' in session:
        return redirect(url_for('admin_dashboard'))
        
    return render_template("index.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get("email")
        password = request.form.get("password")
        employee = db.get_employee_by_email(email)
        
        if employee and check_password_hash(employee['password_hash'], password):
            # Establish session
            session['employee_id'] = employee['id']
            session['employee_name'] = employee['name']
            session['employee_email'] = employee['email']
            
            # Log login event (IP/Device details are for fraud detection)
            ip_address = request.remote_addr
            device_id = request.headers.get('User-Agent', 'Unknown')[:50]
            db.create_login_log(employee['id'], ip_address, device_id)
            
            return redirect(url_for('dashboard'))
        
        flash("Invalid email or password", "error")
    return render_template("login.html")

@app.route('/logout')
def logout():
    """Logs out the employee, records the logout time, and signals the desktop agent to stop."""
    if 'employee_id' in session:
        emp_id = session['employee_id']
        
        db.update_logout_time(emp_id)
        
        socketio.emit('server_control_agent', 
                      {'command': 'stop'}, 
                      room=f"employee_{emp_id}")

        session.clear()
    return redirect(url_for("login"))

# EMPLOYEE DASHBOARD
@app.route('/dashboard')
@login_required
def dashboard():
    """Employee view showing their activity summary and recent logs."""
    emp_id = session['employee_id']
    employee_info = db.get_employee_by_id(emp_id)
    if employee_info:
        employee_info['department'] = employee_info.get('department', 'Information Technology')
        employee_info['shift_time'] = employee_info.get('shift_time', '9:00 AM - 5:00 PM')
    activity_summary = db.get_activity_summary(emp_id)
    recent_logs = db.get_recent_activity_logs(emp_id, limit=10)
    
    return render_template(
        "dashboard.html",
        user_name=session['employee_name'],
        employee_info=employee_info,
        activity_summary=activity_summary,
        recent_logs=recent_logs
    )


# SOCKETIO EVENTS
@socketio.on('connect')
def handle_connect():
    """Handles new SocketIO connections and assigns rooms based on session."""
    if 'admin_id' in session:
        # If the user is an admin, join the 'admin' room
        join_room('admin')
        print(f"Admin {session['admin_id']} joined 'admin' room")
    elif 'employee_id' in session:
        # If the user is an employee, join their specific room
        room_id = f"employee_{session['employee_id']}"
        join_room(room_id)
        print(f"Employee {session['employee_id']} connected. Awaiting client room request.")
    else:
        print("Unauthenticated client connected.")
@socketio.on('employee_join_room')
def handle_employee_join_room(data):
    employee_id = data.get('employee_id')
    if employee_id:
        room_id = f"employee_{employee_id}"
        join_room(room_id)
        print(f"Employee {employee_id} explicitly joined room {room_id}")

@socketio.on('desktop_activity_log')
def handle_desktop_activity_log(data):
    """
    Receives activity from the Desktop Agent via SocketIO, logs it,
    analyzes it, and pushes updates to the Admin Dashboard.
    """
    employee_id = data.get("employee_id")
    active_window = data.get("active_window_title", "Desktop Agent Unspecified")
    mouse = data.get("mouse_activity", 0)
    keyboard = data.get("keyboard_activity", 0)
    idle = data.get("idle_time", 0)

    if not employee_id:
        return
    
    if not db.is_employee_active(employee_id):
        print(f"Activity log received for non-active employee {employee_id}. Ignoring.")
        # CRITICAL: If not active, signal the agent one last time to stop itself
        socketio.emit('server_control_agent', 
                      {'command': 'stop'}, 
                      room=f"employee_{employee_id}")
        return

    new_log_id = db.create_activity_log(employee_id, mouse, keyboard, idle, active_window)
    new_log = db.get_activity_log_by_id(new_log_id)
   
    if new_log and isinstance(new_log.get('timestamp'), datetime.datetime):
        new_log['timestamp'] = new_log['timestamp'].isoformat()
  
    analysis_result = fraud_detector.analyze_and_flag(db, employee_id)

    activity_summary = db.get_activity_summary(employee_id)
    
    #ADD CONVERSION LOGICERE
    if activity_summary:
        for key in ['total_mouse', 'total_keyboard', 'total_idle', 'total_time']:
            if key in activity_summary and activity_summary[key] is not None:
                # Convert any Decimal/MySQL numeric type to Python float
                activity_summary[key] = float(activity_summary[key])

    socketio.emit('employee_dashboard_update', {
        'new_log': new_log, # Push the new log entry
        'summary': activity_summary, # Push updated summary stats
        'risk_score': analysis_result.get('risk_score', 0) if analysis_result else 0
    }, room=f"employee_{employee_id}")

    # 4. Push real-time update to Admin Dashboard
    latest_alerts = db.get_recent_alerts(limit=1)
    latest_alert_json = None
    if latest_alerts:
        latest_alert = latest_alerts[0]
        # Convert the datetime object to a string format (ISO 8601 is best practice)
        if isinstance(latest_alert.get('timestamp'), datetime.datetime):
            latest_alert['timestamp'] = latest_alert['timestamp'].isoformat()
        latest_alert_json = latest_alert
    
    stats = db.get_dashboard_stats()
    employees_at_risk = db.get_employees_with_risk_scores()
   
    socketio.emit('admin_dashboard_update', {
        'type': 'activity_log',
        'employee_id': employee_id,
        'risk_score': analysis_result.get('risk_score', 0) if analysis_result else 0,
        'latest_alert': latest_alert_json,
        'new_stats': stats,                  
        'employees_at_risk': employees_at_risk
    }, room='admin')

@socketio.on('send_warning_to_employee')
@admin_required
def send_warning_to_employee(data):
    """Admin sends a real-time warning message to an employee's room (Goal 4)."""
    employee_id = data.get('employee_id')
    message = data.get('message', 'Warning: Irregular activity detected.')
    
    room_id = f"employee_{employee_id}"
    
    socketio.emit('employee_warning', {'message': message}, room=room_id)
    print(f"Warning sent to employee {employee_id}")

@socketio.on('request_screen_share')
@admin_required
def request_screen_share(data):
    """
    NEW: Admin sends a real-time screen share request to an employee's room.
    The client-side code will handle the actual screen capture/WebRTC initiation.
    """
    employee_id = data.get('employee_id')
    room_id = f"employee_{employee_id}"
    
    socketio.emit('screen_share_request', {'employee_id': employee_id}, room=room_id)
    print(f"Screen share request sent to employee {employee_id}")

@socketio.on('screen_share_accepted')
def handle_screen_share_accepted(data):
    """Employee confirms screen share acceptance."""
    employee_id = data.get('employee_id')
    
    socketio.emit('screen_share_accepted_admin_notification', {
        'employee_id': employee_id,
        'message': f"Employee {employee_id} ACCEPTED the screen share. Initiating WebRTC..."
    }, room='admin')
    
    print(f"Employee {employee_id} accepted screen share.")

@socketio.on('webrtc_signal')
def handle_webrtc_signal(data):
    """
    Relays WebRTC signaling data (Offer, Answer, ICE Candidates)
    from the sender to the intended receiver.
    """
    sender_id = data.get('sender_id')
    receiver_id = data.get('receiver_id')
    signal_type = data.get('type') # 'offer', 'answer', or 'ice'
    payload = data.get('payload')
    
    if receiver_id == 'admin':
        room_id = 'admin'
    else:
        room_id = f"employee_{receiver_id}"

    emit('webrtc_signal', {
        'type': signal_type,
        'sender_id': sender_id,
        'payload': payload
    }, room=room_id)
    
    print(f"Relayed WebRTC Signal: {signal_type} from {sender_id} to {receiver_id} in room {room_id}")

# API ROUTES
# ADMIN LOGIN/LOGOUT

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        admin = db.get_admin_by_email(email)
        
        if admin and check_password_hash(admin['password_hash'], password):
            session['admin_id'] = admin['id']
            session['admin_email'] = admin['email']
            return redirect(url_for("admin_dashboard"))
        
        flash("Invalid admin credentials", "error")
    return render_template("admin_login.html")

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


# ADMIN DASHBOARD & ALERTS

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    """Main admin interface displaying overall stats and high-risk employees."""
    stats = db.get_dashboard_stats()
    recent_alerts = db.get_recent_alerts(limit=10)
    employees_at_risk = db.get_employees_with_risk_scores()
    
    return render_template(
        "admin_dashboard.html",
        stats=stats,
        recent_alerts=recent_alerts,
        employees_at_risk=employees_at_risk
    )

@app.route('/admin/alerts')
@admin_required
def alerts():
    """Displays a full history of all fraud alerts."""
    alerts = db.get_all_alerts()
    return render_template("alerts.html", alerts=alerts)

# EMPLOYEE MANAGEMENT

@app.route('/admin/employees', methods=['GET'])
@admin_required
def employee_management():
    """Page for admins to view, add, and delete employee accounts."""
    employees = db.get_all_employees()
    return render_template("employee_management.html", employees=employees)

@app.route('/admin/employees/add', methods=['POST'])
@admin_required
def add_employee():
    name = request.form.get('name')
    email = request.form.get('email')
    password = request.form.get('password')
    role = request.form.get('role', 'employee')
    
    if not all([name, email, password]):
        flash("All fields are required.", "error")
        return redirect(url_for('employee_management'))
        
    hashed_password = generate_password_hash(password)
    
    try:
        db.create_employee(name, email, hashed_password, role)
        flash(f"Employee {name} added successfully.", "success")
    except Exception as e:
        # Catch potential database errors (e.g., duplicate email)
        flash(f"Error adding employee: Email already exists or connection failed.", "error")
        
    return redirect(url_for('employee_management'))

@app.route('/admin/employees/delete/<int:employee_id>', methods=['POST'])
@admin_required
def delete_employee(employee_id):
    try:
        db.delete_employee(employee_id)
        flash("Employee and all related data deleted successfully.", "success")
    except Exception as e:
        flash("Error deleting employee. Check database constraints.", "error")
        
    return redirect(url_for('employee_management'))


# EMPLOYEE REPORTING

@app.route('/admin/employee/report/<int:employee_id>')
@admin_required
def employee_activity_report(employee_id):
    """Detailed report for a single employee, showing raw logs and risk factors."""
    employee_info = db.get_employee_by_id(employee_id)
    activity_data = db.get_detailed_activity(employee_id, limit=100)
    
    # Analyze the employee's activity data using the ML engine
    risk_summary = fraud_detector.get_risk_score(db, employee_id)
    
    return render_template(
        "employee_report.html",
        employee=employee_info,
        activity_data=activity_data,
        risk_summary=risk_summary
    )

# API ROUTES

@app.route('/api/log-activity', methods=['POST'])
def log_activity():
    """
    Receives activity data from the external Desktop Agent.
    This endpoint is designed to handle key/mouse events, idle time, 
    and the crucial active_window_title from external sources.
    """
    data = request.json
    employee_id = data.get("employee_id")

    active_window = data.get("active_window_title", "Desktop Agent Unspecified")
    
    if not employee_id:
        return jsonify({"error": "Employee ID required"}), 400
    
    # Log the received activity data
    db.create_activity_log(
        employee_id,
        data.get("mouse_activity", 0),
        data.get("keyboard_activity", 0),
        data.get("idle_time", 0),
        active_window # Pass the foreground window title
    )
    
    # Run ML analysis immediately after logging
    fraud_detector.analyze_and_flag(db, employee_id)
    
    return jsonify({"status": "success", "message": "Activity logged and analyzed"})

@app.route('/api/employee-summary/<int:employee_id>') # New API endpoint for client refresh
@login_required
def api_employee_summary(employee_id):
    """API endpoint to get the employee's activity summary and latest log for SocketIO updates."""
    if employee_id != session['employee_id']:
        return jsonify({"error": "Unauthorized"}), 403
        
    summary = db.get_activity_summary(employee_id)
    latest_log = db.get_recent_activity_logs(employee_id, limit=1)
    
    # Calculate Productivity Score (P1.1)
    total_activity = summary.get('total_mouse', 0) + summary.get('total_keyboard', 0)
    total_time = total_activity + summary.get('total_idle', 0)
    productivity_score = 0
    if total_time > 0:
        # P1.1: Score = (Active Time / (Active Time + Idle Time)) * 100
        productivity_score = round((total_activity / total_time) * 100)

    # Calculate Total Active Time in seconds (P1.1: Active Time = Total Activity - Total Idle)
    total_active_seconds = total_time - summary.get('total_idle', 0)

    return jsonify({
        'summary': summary,
        'productivity_score': productivity_score,
        'total_active_seconds': total_active_seconds,
        'latest_log': latest_log[0] if latest_log else None
    })

@app.route('/api/log-login', methods=['POST'])
def log_login():
    # Helper API for desktop agent to log login events explicitly
    data = request.json
    employee_id = data.get("employee_id")
    if not employee_id:
        return jsonify({"error": "Employee ID required"}), 400
    
    ip = data.get("ip_address", request.remote_addr)
    device = data.get("device_id", "Unknown")
    
    log_id = db.create_login_log(employee_id, ip, device)
    return jsonify({"status": "success", "log_id": log_id})

@app.route('/api/log-logout', methods=['POST'])
def api_logout_log():
    # Helper API for desktop agent to log logout events
    data = request.json
    employee_id = data.get("employee_id")
    if not employee_id:
        return jsonify({"error": "Employee ID required"}), 400
    
    db.update_logout_time(employee_id)
    return jsonify({"status": "success"})

@app.route('/api/fraud-score/<int:employee_id>')
def fraud_score(employee_id):
    """API endpoint to get the latest fraud score for an employee."""
    score = fraud_detector.get_risk_score(db, employee_id)
    return jsonify(score)

@app.route('/api/anomaly-data')
@admin_required
def api_anomaly_data():
    """API for the dashboard chart showing hourly activity trends."""
    hourly_data = db.get_hourly_activity_data()
    hours = [f"{d['hour']}:00" for d in hourly_data]
    activity = [d['avg_activity'] for d in hourly_data]
    return jsonify({
        "hours": hours,
        "activity": activity
    })

@app.route('/api/admin/alerts')
@admin_required
def api_alerts():
    return jsonify(db.get_all_alerts())

@app.route('/api/admin/dashboard')
@admin_required
def api_dashboard():
    return jsonify({
        "stats": db.get_dashboard_stats(),
        "hourly_data": db.get_hourly_activity_data(),
        "risk_distribution": db.get_risk_distribution()
    })

# EXPORT CSV

@app.route('/api/admin/export')
@admin_required
def export_data():
    """Exports all fraud alerts into a downloadable CSV file."""
    alerts = db.get_all_alerts()
    output = StringIO()
    # Ensure all required fields are present for DictWriter
    fieldnames=['id', 'employee_id', 'employee_name', 'employee_role', 'risk_score', 'alert_level', 'description', 'timestamp']
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in alerts:
        writer.writerow(row)
        
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=fraud_alerts.csv'}
    )

# INIT DB ON FIRST RUN

with app.app_context():
    db.init_db()
    db.seed_demo_data()

if __name__ == "__main__":
    #app.run(host="0.0.0.0", port=5000, debug=True)
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, allow_unsafe_werkzeug=True)
