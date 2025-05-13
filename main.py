from SS_RM_admin import SmartsheetRmAdmin
from auto_rm import AutoRM
import tkinter as tk
from tkinter import messagebox, scrolledtext
import threading
import json
import traceback
import os
import smartsheet
import smartsheet.models
from smartsheet.models import Workspace
from smartsheet.workspaces import Workspaces
from smartsheet.models import Sheet
from smartsheet.sheets import Sheets
from configs.setup_logger import setup_logger, get_log_file_path
import time
import sys
import signal

def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

def get_writable_path(relative_path):
    # Use %APPDATA% or local working dir
    base = os.getenv("APPDATA") or os.path.abspath(".")
    return os.path.join(base, relative_path)
#logger
log_path = get_writable_path("DCT_RM_Tools/log.log")
os.makedirs(os.path.dirname(log_path), exist_ok=True)
log = setup_logger(__name__)

LOG_FILE_PATH = get_log_file_path()

# Global uncaught exception handler
def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        # Allow Ctrl+C to work normally
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    log.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = handle_exception

# --------------------- File Tailer (Live Log File Output) ---------------------
def tail_log_file(file_path, interval=0.5):
    def follow():
        try:
            with open(file_path, "r") as f:
                f.seek(0, os.SEEK_END)
                while True:
                    line = f.readline()
                    if not line:
                        time.sleep(interval)
                        continue
                    log_box.config(state=tk.NORMAL)
                    log_box.insert(tk.END, line)
                    log_box.see(tk.END)
                    log_box.config(state=tk.DISABLED)
        except FileNotFoundError:
            log_message(f"Log file not found: {file_path}")
    threading.Thread(target=follow, daemon=True).start()

# --------------------- Button Logic ---------------------
def log_message(text):
    log_box.config(state=tk.NORMAL)
    log_box.insert(tk.END, f"{text}\n")
    log_box.see(tk.END)
    log_box.config(state=tk.DISABLED)

def confirm_and_run(action_name, action_fn):
    if messagebox.askyesno("Confirm", f"Are you sure you want to run '{action_name}'?"):
        for b in [btn1, btn2, btn3]:
            b.config(state="disabled")

        log_box.config(state=tk.NORMAL)
        log_box.delete(1.0, tk.END)
        log_box.config(state=tk.DISABLED)

        def run():
            try:
                log.info(f"Running: {action_name}...\n")
                action_fn()
                log.info(f"\n{action_name} complete.")
            except Exception:
                error_trace = traceback.format_exc()
                log.error(f"\nUnhandled error:\n{error_trace}")
            finally:
                for b in [btn1, btn2, btn3]:
                    b.config(state="normal")

        threading.Thread(target=run).start()

# --------------------- Run Project Updates  ---------------------
def run_project_updates():
    rmm = AutoRM()
    log.info("Syncing Projects...")
    rmm.sync_projects()
    log.info("Completed sync updates.")
    messagebox.showinfo("Complete", "Project updates complete.")

# --------------------- Run Time Updates  ------------------------
def run_time_updates():
    with open(get_resource_path("configs/config.json"), "r") as f:
        config = json.load(f)
    log.info("Running hours updates...")
    sra = SmartsheetRmAdmin(config)
    sra.grab_rm_data()
    sra.run_hours_update()
    log.info("Completed hours updates.")
    messagebox.showinfo("Complete", "Time updates complete.")

# --------------------- Run Time Updates  ------------------------
def run_assignment_updates():
    with open(get_resource_path("configs/config.json"), "r") as f:
        config = json.load(f)
    log.info("Running assignment updates...")
    sra = SmartsheetRmAdmin(config)
    sra.grab_rm_data()
    sra.run_assignment_updates()
    messagebox.showinfo("Complete", "Assignments updates complete.")

# --------------------- Run All Updates  ------------------------
def run_all_updates():
    with open(get_resource_path("configs/config.json"), "r") as f:
        config = json.load(f)
    run_project_updates()
    sra = SmartsheetRmAdmin(config)
    sra.run_all()

# ---------------------- Quit  ----------------------------------
def quit_app():
    try:
        root.destroy()
    except:
        pass  # in case root is already destroyed
    # Ensure full process termination
    os.kill(os.getpid(), signal.SIGTERM)

def style_button(btn, bg_color, fg_color, hover_color):
    btn.configure(bg=bg_color, fg=fg_color, activebackground=hover_color, relief="flat", cursor="hand2", bd=0)
    btn.bind("<Enter>", lambda e: btn.config(bg=hover_color))
    btn.bind("<Leave>", lambda e: btn.config(bg=bg_color))

# --------------------- GUI Setup ---------------------
root = tk.Tk()
root.title("DCT RM Automation")
root.geometry("600x520")
root.configure(bg="#fdf9f4")  # Light warm background

# Header
tk.Label(
    root,
    text="Smartsheet RM Automation",
    font=("Segoe UI", 20, "bold"),
    bg="#fdf9f4",
    fg="#F5A623"
).pack(pady=(20, 10))

tk.Label(
    root,
    text="Select an automation task:",
    font=("Segoe UI", 13),
    bg="#fdf9f4",
    fg="#333333"
).pack(pady=(0, 20))

btn_frame = tk.Frame(root, bg="#fdf9f4")
btn_frame.pack()

# Buttons
btn1 = tk.Button(btn_frame, text="Update Projects (DCT + RM)", font=("Segoe UI", 11), width=28, command=lambda: confirm_and_run("Update Projects", run_project_updates))
btn2 = tk.Button(btn_frame, text="Update Time Entries", font=("Segoe UI", 11), width=28, command=lambda: confirm_and_run("Update Time Entries", run_time_updates))
btn3 = tk.Button(btn_frame, text="Update Assignments", font=("Segoe UI", 11), width=28, command=lambda: confirm_and_run("Update Assignments", run_assignment_updates))
btn_all = tk.Button(btn_frame, text="Run All Updates", font=("Segoe UI", 11), width=28, command=lambda: confirm_and_run("Run All Updates", run_all_updates))
btn4 = tk.Button(btn_frame, text="Exit", font=("Segoe UI", 11), width=28, command=quit_app)

btn1.pack(pady=5)
btn2.pack(pady=5)
btn3.pack(pady=5)
btn_all.pack(pady=(15, 5))
btn4.pack(pady=(10, 0))

# Top 3 (light gray buttons)
style_button(btn1, "#E0E0E0", "black", "#CFCFCF")
style_button(btn2, "#E0E0E0", "black", "#CFCFCF")
style_button(btn3, "#E0E0E0", "black", "#CFCFCF")

# Run All (orange highlight)
style_button(btn_all, "#D87F27", "white", "#BA6B1F")

# Exit (charcoal gray)
style_button(btn4, "#5C5C5C", "white", "#444444")


# Log Output
tk.Label(
    root,
    text="Live Log Output:",
    font=("Segoe UI", 11, "bold"),
    bg="#fdf9f4",
    fg="#333333",
    anchor="w"
).pack(padx=20, pady=(20, 0), anchor="w")

log_box = scrolledtext.ScrolledText(
    root,
    height=12,
    state=tk.DISABLED,
    wrap=tk.WORD,
    font=("Consolas", 10),
    bg="#ffffff",
    borderwidth=1,
    relief="solid"
)
log_box.pack(padx=20, fill=tk.BOTH, expand=True, pady=(0, 15))
log_box.tag_config("error", foreground="red")

# Init log file tailer
tail_log_file(LOG_FILE_PATH)

# Launch GUI
root.mainloop()