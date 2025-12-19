# desktop_agent.py
import time
import sys
import platform
import socketio
import random 
import threading 

try:
    from pynput import mouse, keyboard
    import pygetwindow as gw
except ImportError:
    print("Warning: pynput or pygetwindow not installed. Install them using: pip install pynput pygetwindow")
    sys.exit(1)

#CONFIGURATION
EMPLOYEE_ID = 1         
SERVER_URL = "http://localhost:5000"
LOG_INTERVAL_SECONDS = 15 

#STATE VARIABLES
GLOBAL_MOUSE_COUNT = 0
GLOBAL_KEYSTROKE_COUNT = 0
LAST_ACTIVITY_TIME = time.time()
STATE_LOCK = threading.Lock() 
TRACKING_ENABLED = True
sio = socketio.Client()

#INPUT LISTENER FUNCTIONS

def on_input_event(key=None, x=None, y=None):
    """Universal handler for mouse/keyboard activity, updates global state."""
    global GLOBAL_MOUSE_COUNT
    global GLOBAL_KEYSTROKE_COUNT
    global LAST_ACTIVITY_TIME
    
    with STATE_LOCK:
        LAST_ACTIVITY_TIME = time.time()
        
        if key is not None:
            try:
                if isinstance(key, keyboard.KeyCode) or isinstance(key, keyboard.Key):
                    GLOBAL_KEYSTROKE_COUNT += 1
            except AttributeError:
                 pass

        elif x is not None and y is not None:
            GLOBAL_MOUSE_COUNT += 1

def start_listeners():
    """Starts mouse and keyboard listeners in separate threads."""
    mouse_listener = mouse.Listener(on_move=on_input_event, on_click=on_input_event)
    keyboard_listener = keyboard.Listener(on_press=on_input_event)
    
    mouse_listener.daemon = True
    keyboard_listener.daemon = True

    mouse_listener.start()
    keyboard_listener.start()
    print("Input Listeners: Started capturing keyboard and mouse events.")

#DATA CAPTURE FUNCTION
def get_real_time_activity():
    """
    Captures accumulated activity and system status, then resets counters.
    """
    global GLOBAL_MOUSE_COUNT
    global GLOBAL_KEYSTROKE_COUNT
    global LAST_ACTIVITY_TIME
    
    with STATE_LOCK:
        collected_mouse = GLOBAL_MOUSE_COUNT
        collected_keyboard = GLOBAL_KEYSTROKE_COUNT
        GLOBAL_MOUSE_COUNT = 0
        GLOBAL_KEYSTROKE_COUNT = 0

        time_since_last_input = time.time() - LAST_ACTIVITY_TIME

    MAX_IDLE_S = 60 
    current_idle_s = 0
    if time_since_last_input > MAX_IDLE_S:
        current_idle_s = LOG_INTERVAL_SECONDS 

    try:
        active_window = gw.getActiveWindow().title
        if not active_window:
            active_window = "Desktop or Minimized Application"
    except Exception:
        active_window = "System Error or Unknown"

    return {
        "mouse_activity": collected_mouse,
        "keyboard_activity": collected_keyboard,
        "idle_time": current_idle_s,
        "active_window_title": active_window
    }

#SOCKETIO LOGIC

@sio.event
def connect():
    print('Connection established with server.')

@sio.event
def disconnect():
    print('Disconnected from server.')

def get_device_info():
    """Generates a simple unique device ID."""
    system = platform.system()
    node = platform.node()
    return f"{system.upper()}-{node[:8]}".replace(' ', '_')

@sio.on('server_control_agent')
def handle_control_signal(data):
    global TRACKING_ENABLED
    command = data.get('command')
    if command == 'stop':
        TRACKING_ENABLED = False
        print("Server issued STOP command. Disabling tracking.")
    elif command == 'start':
        TRACKING_ENABLED = True
        print("Server issued START command. Enabling tracking.")

def send_activity_log(data):
    """Sends the collected activity data via SocketIO event."""
    global TRACKING_ENABLED
    
    if not TRACKING_ENABLED:
        print("Tracking is disabled. Skipping log send.")
        return
    payload = {
        "employee_id": EMPLOYEE_ID,
        "device_id": get_device_info(), 
        **data
    }
    sio.emit('desktop_activity_log', payload)

    print(f"[{time.strftime('%H:%M:%S')}] Log sent via SocketIO. M:{data['mouse_activity']} K:{data['keyboard_activity']} I:{data['idle_time']}s | Window: {data['active_window_title']}")

# MAIN EXECUTION
def main_loop():
    print(f"Desktop Agent running for Employee ID: {EMPLOYEE_ID}")
    print(f"Connecting to SocketIO server: {SERVER_URL}")

    start_listeners()

    while not sio.connected:
        try:
            sio.connect(SERVER_URL) 
        except Exception as e:
            print(f"Failed to connect to server: {e}. retrying in 5 seconds...")
            time.sleep(5)
    
    while sio.connected:
        try:
            activity_data = get_real_time_activity()
 
            send_activity_log(activity_data)

            time.sleep(LOG_INTERVAL_SECONDS)
        
        except KeyboardInterrupt:
            print("\nAgent stopped by user. Disconnecting.")
            sio.disconnect() 
            sys.exit(0)
        except Exception as e:
            print(f"Critical error in main loop: {e}")
            sio.disconnect()
            time.sleep(60) 

if __name__ == "__main__":
    main_loop()
