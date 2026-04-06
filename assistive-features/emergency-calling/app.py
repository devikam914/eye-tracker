import tkinter as tk
from tkinter import simpledialog
import os
import pyautogui
import time
import pygetwindow as gw
import json

# Ensure we use absolute paths for the config and image
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, 'contacts.json')
IMAGE_PATH = os.path.join(SCRIPT_DIR, 'call_button.png')

def load_family_number():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
                return data.get('family_number', '+0000000000')
        except Exception:
            pass
    return '+00000000000'

def save_family_number(number):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump({'family_number': number}, f)
    except Exception as e:
        print(f"Error saving config: {e}")

def make_call(phone_number):
    print(f"Initiating call to: {phone_number}")
    os.startfile(f"tel:{phone_number}")
    
    # Wait for Phone Link to launch
    time.sleep(4)
    
    call_initiated = False
    
    # Try to find the Phone Link window
    for attempt in range(10):
        windows = gw.getWindowsWithTitle("Phone Link") or gw.getWindowsWithTitle("Your Phone")
        
        if windows:
            phone_window = windows[0]
            try:
                # If minimized, restore it first
                if phone_window.isMinimized:
                    phone_window.restore()
                    
                phone_window.activate()
                time.sleep(1) # Wait for window animation to finish
                
                # Check if the window is reporting realistic dimensions
                if phone_window.width > 200 and phone_window.height > 200:
                    # Search within the window region
                    region = (phone_window.left, phone_window.top, phone_window.width, phone_window.height)
                    call_button = pyautogui.locateOnScreen(IMAGE_PATH, confidence=0.8, region=region)
                else:
                    # Fallback: Dimensions are messed up (likely DPI scaling), search whole screen
                    print("Window region invalid. Scanning entire screen...")
                    call_button = pyautogui.locateOnScreen(IMAGE_PATH, confidence=0.8)
                
                if call_button:
                    # Adding duration=0.2 so you can visually confirm the mouse moving to the target
                    pyautogui.click(call_button, duration=0.2)
                    call_initiated = True
                    print("Call button clicked successfully via image recognition.")
                    break
            except Exception as e:
                # If region search fails, try one last time on the whole screen
                try:
                    call_button = pyautogui.locateOnScreen(IMAGE_PATH, confidence=0.8)
                    if call_button:
                        pyautogui.click(call_button, duration=0.2)
                        call_initiated = True
                        print("Call button found on full screen fallback.")
                        break
                except Exception as inner_e:
                    print(f"Vision error: {inner_e}")
        
        time.sleep(0.5)
    
    if not call_initiated:
        print("Could not detect the call button. Please ensure call_button.png is tightly cropped.")
        
    # Schedule automatic closure 
    root.after(30000, close_phone_link)

def close_phone_link():
    print("Attempting to close Phone Link window...")
    windows = gw.getWindowsWithTitle("Phone Link") or gw.getWindowsWithTitle("Your Phone")
    if windows:
        try:
            windows[0].close()
            print("Phone Link closed.")
        except Exception as e:
            print(f"Error closing Phone Link: {e}")
            
    print("Terminating Assistant UI in 5 seconds...")
    root.after(5000, root.destroy)

def edit_contact():
    current = load_family_number()
    new_num = simpledialog.askstring("Edit Contact", "Enter new number for Family:", initialvalue=current, parent=root)
    if new_num and new_num.strip():
        save_family_number(new_num.strip())
        print(f"Updated family number to: {new_num.strip()}")

# --- GUI Setup ---
root = tk.Tk()
root.title("Quick Call Assist")
root.geometry("800x600")
root.configure(bg="#1e1e2e")

main_frame = tk.Frame(root, bg="#1e1e2e")
main_frame.place(relx=0.5, rely=0.5, anchor="center")

title_lbl = tk.Label(
    main_frame,
    text="Quick Call Assist",
    font=("Segoe UI", 28, "bold"),
    fg="#ffffff",
    bg="#1e1e2e"
)
title_lbl.pack(pady=(0, 40))

button_style = {
    "font": ("Segoe UI", 18, "bold"),
    "fg": "white",
    "padx": 30,
    "pady": 15,
    "width": 22,
    "bd": 0,
    "cursor": "hand2",
    "relief": "flat"
}

dwell_timers = {}

def execute_click(widget):
    widget['background'] = "#2ecc71"
    widget.invoke()
    
def on_enter(e, hover_color):
    widget = e.widget
    widget['background'] = hover_color
    timer_id = root.after(1500, lambda: execute_click(widget))
    dwell_timers[widget] = timer_id

def on_leave(e, normal_color):
    widget = e.widget
    widget['background'] = normal_color
    if widget in dwell_timers:
        root.after_cancel(dwell_timers[widget])
        del dwell_timers[widget]

# Emergency Button
btn_emergency = tk.Button(main_frame, text="🚨 EMERGENCY CALL", bg="#ff4b4b", command=lambda: make_call("911"), **button_style)
btn_emergency.bind("<Enter>", lambda e: on_enter(e, "#ff6b6b"))
btn_emergency.bind("<Leave>", lambda e: on_leave(e, "#ff4b4b"))
btn_emergency.pack(pady=15)

# Family Button
btn_family = tk.Button(main_frame, text="🏠 CALL FAMILY", bg="#00b4d8", command=lambda: make_call(load_family_number()), **button_style)
btn_family.bind("<Enter>", lambda e: on_enter(e, "#48cae4"))
btn_family.bind("<Leave>", lambda e: on_leave(e, "#00b4d8"))
btn_family.pack(pady=15)

# Edit Button
btn_edit = tk.Button(main_frame, text="✏️ EDIT CONTACT", bg="#ffb703", command=edit_contact, **button_style)
btn_edit.bind("<Enter>", lambda e: on_enter(e, "#ffc300"))
btn_edit.bind("<Leave>", lambda e: on_leave(e, "#ffb703"))
btn_edit.pack(pady=15)

root.mainloop()