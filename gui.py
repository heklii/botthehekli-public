import sys
import threading
import queue
import json
import os
import asyncio
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog
from datetime import datetime
from PIL import Image, ImageTk, ImageDraw
import pystray
from io import BytesIO

# Import bot modules
from config import *
from main import Bot
from token_manager import TokenManager

# File Constants
# File Constants come from config.py
# If any are missing, define them here or ensure config.py is updated
ENV_FILE = os.path.join(os.path.dirname(__file__), '.env')

# Reconfigure stdout for Windows Unicode support
if sys.stdout:
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
if sys.stderr:
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

class RedirectText:
    """Redirect stdout/stderr to a queue"""
    def __init__(self, log_queue):
        self.log_queue = log_queue

    def write(self, string):
        if string.strip():
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_queue.put(f"[{timestamp}] {string.strip()}")

    def flush(self):
        pass

class CommandEditorDialog(tk.Toplevel):
    def __init__(self, parent, title, initial_cmd="", initial_resp=""):
        super().__init__(parent)
        self.title(title)
        self.geometry("500x300")
        self.result = None
        
        # Center the dialog
        self.transient(parent)
        self.grab_set()
        
        # UI
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="Command Name:", font=('Segoe UI', 10, 'bold')).pack(anchor=tk.W)
        self.entry_cmd = ttk.Entry(frame, width=40)
        self.entry_cmd.insert(0, initial_cmd)
        self.entry_cmd.pack(fill=tk.X, pady=(5, 15))
        
        ttk.Label(frame, text="Response:", font=('Segoe UI', 10, 'bold')).pack(anchor=tk.W)
        self.entry_resp = scrolledtext.ScrolledText(frame, height=5, font=('Segoe UI', 9))
        self.entry_resp.insert('1.0', initial_resp)
        self.entry_resp.pack(fill=tk.BOTH, expand=True, pady=(5, 15))
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X)
        
        ttk.Button(btn_frame, text="Cancel", command=self.cancel).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Save", command=self.save).pack(side=tk.RIGHT)
        
        # Wait for window
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.entry_cmd.focus_set()
        self.wait_window(self)

    def save(self):
        cmd = self.entry_cmd.get().strip()
        resp = self.entry_resp.get('1.0', tk.END).strip()
        
        if not cmd:
            messagebox.showwarning("Validation", "Command name cannot be empty.", parent=self)
            return
        if not resp:
            messagebox.showwarning("Validation", "Response cannot be empty.", parent=self)
            return
            
        self.result = (cmd, resp)
        self.destroy()

    def cancel(self):
        self.destroy()

class PermissionEditorDialog(tk.Toplevel):
    def __init__(self, parent, command, current_roles):
        super().__init__(parent)
        self.title(f"Permissions: {command}")
        self.geometry("300x400")
        self.result = None
        
        self.transient(parent)
        self.grab_set()
        
        ttk.Label(self, text=f"Allowed Roles for {command}", font=('Segoe UI', 10, 'bold')).pack(pady=10)
        
        self.roles_vars = {}
        all_roles = ["everyone", "subscriber", "vip", "moderator", "broadcaster"]
        
        for role in all_roles:
            var = tk.BooleanVar(value=role in current_roles)
            cb = ttk.Checkbutton(self, text=role.capitalize(), variable=var)
            cb.pack(anchor=tk.W, padx=20, pady=2)
            self.roles_vars[role] = var
            
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, pady=20)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=10)
        ttk.Button(btn_frame, text="Save", command=self.save).pack(side=tk.RIGHT)
        
        # Make dialog modal and wait for it to close
        self.wait_window()
        
    def save(self):
        selected = [r for r, v in self.roles_vars.items() if v.get()]
        self.result = selected
        self.destroy()

class TimerEditorDialog(tk.Toplevel):
    def __init__(self, parent, title, initial_data=None):
        super().__init__(parent)
        self.title(title)
        self.geometry("400x500")
        self.result = None
        
        self.transient(parent)
        self.grab_set()
        
        # Defaults
        self.name = ""
        self.msg = ""
        self.interval = 15
        self.lines = 2
        
        if initial_data:
            self.name = initial_data.get('name', '')
            self.msg = initial_data.get('message', '')
            self.interval = initial_data.get('interval', 15)
            self.lines = initial_data.get('lines', 2)
            
        self.setup_ui()
        
        # Center dialog
        self.geometry("+%d+%d" % (parent.winfo_rootx() + 50, parent.winfo_rooty() + 50))
        
        self.wait_window()

    def setup_ui(self):
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        # Name
        ttk.Label(frame, text="Timer Name (ID):", font=('Segoe UI', 9, 'bold')).pack(anchor=tk.W)
        self.entry_name = ttk.Entry(frame)
        self.entry_name.insert(0, self.name)
        # If editing existing, maybe disable name editing? Or allow rename loop?
        # Let's allow edit, logic will handle rename.
        self.entry_name.pack(fill=tk.X, pady=(2, 10))

        # Message
        ttk.Label(frame, text="Message:", font=('Segoe UI', 9, 'bold')).pack(anchor=tk.W)
        self.text_msg = scrolledtext.ScrolledText(frame, height=8, font=('Segoe UI', 9))
        self.text_msg.insert("1.0", self.msg)
        self.text_msg.pack(fill=tk.BOTH, expand=True, pady=(2, 10))

        # Interval
        ttk.Label(frame, text="Interval (minutes):", font=('Segoe UI', 9, 'bold')).pack(anchor=tk.W)
        self.spin_interval = ttk.Spinbox(frame, from_=1, to=9999)
        self.spin_interval.set(self.interval)
        self.spin_interval.pack(fill=tk.X, pady=(2, 10))

        # Lines
        ttk.Label(frame, text="Minimum Chat Lines:", font=('Segoe UI', 9, 'bold')).pack(anchor=tk.W)
        self.spin_lines = ttk.Spinbox(frame, from_=0, to=9999)
        self.spin_lines.set(self.lines)
        self.spin_lines.pack(fill=tk.X, pady=(2, 20))

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Save", command=self.save).pack(side=tk.RIGHT)

    def save(self):
        name = self.entry_name.get().strip()
        msg = self.text_msg.get("1.0", tk.END).strip()
        
        if not name:
            messagebox.showwarning("Validation", "Timer name cannot be empty.", parent=self)
            return
        if not msg:
            messagebox.showwarning("Validation", "Message cannot be empty.", parent=self)
            return
            
        try:
            interval = int(self.spin_interval.get())
            lines = int(self.spin_lines.get())
        except ValueError:
            messagebox.showwarning("Validation", "Interval and Lines must be integers.", parent=self)
            return

        self.result = {
            "name": name,
            "message": msg,
            "interval": interval,
            "lines": lines
        }
        self.destroy()

class BotGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("botthehekli control panel")
        self.root.geometry("900x700")
        
        # --- THEME & DESIGN ---
        self.style = ttk.Style()
        try:
            self.style.theme_use('vista')
        except:
            self.style.theme_use('default')
            
        # --- STATE ---
        self.bot = None
        self.bot_thread = None
        self.bot_running = False
        self.log_queue = queue.Queue()
        self.settings = self.load_settings()
        self.tray_icon = None
        self.is_window_visible = True
        
        # --- LOG REDIRECTION ---
        self.redirector = RedirectText(self.log_queue)
        sys.stdout = self.redirector
        sys.stderr = self.redirector
        
        # --- UI SETUP ---
        self.setup_ui()
        
        # --- INITIALIZATION ---
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.update_logs()
        self.setup_tray_icon() # Persistent tray icon
        self.check_auto_start()

    def check_auth(self):
        """Check valid tokens; launch generator if failed. Returns True if valid."""
        try:
            valid = asyncio.run(TokenManager().validate_and_refresh_tokens())
            if not valid:
                msg = "Bot tokens are invalid or missing.\n\nThe 'Token Generator' will now launch.\nPlease follow the instructions to generate new tokens.\n\nThe Control Panel will restart automatically once you are done."
                messagebox.showwarning("Authentication Failure", msg)
                self.launch_token_generator()
                return False
            return True
        except Exception as e:
            print(f"Auth check failed: {e}")
            return False

    def launch_token_generator(self):
        """Launch token generator script and restart GUI when done"""
        # Path to token generator script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        gen_dir = os.path.join(script_dir, 'token_generator')
        
        # We use a chained command in a new terminal:
        # 1. cd to generator dir
        # 2. run batch file (which runs python logic)
        # 3. restart this gui
        
        # Note: We use 'start /wait' to ensure the first part completes before restarting python gui.py
        # But since run_token_generator.bat has a 'pause', the user controls when it exits.
        
        cmd = f'start "Token Generator" cmd /c "cd /d "{gen_dir}" && call run_token_generator.bat && cd /d "{script_dir}" && python gui.py"'
        
        subprocess.Popen(cmd, shell=True)
        self.exit_app()

    def setup_ui(self):
        # Main Notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Create Tabs
        self.create_dashboard_tab()
        self.create_commands_tab()
        self.create_aliases_tab()
        self.create_permissions_tab()
        self.create_cooldowns_tab()
        self.create_counts_tab()
        self.create_responses_tab()
        self.create_music_tab()
        self.create_timers_tab()
        self.create_settings_tab()
        
        # Status Bar
        self.status_var = tk.StringVar(value="Status: Stopped")
        self.status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    # ==================== DATA HELPERS ====================
    def load_json(self, filepath):
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data if isinstance(data, (dict, list)) else {}
            except:
                return {}
        return {}

    def save_json(self, filepath, data):
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    
    def load_settings(self):
        s = self.load_json(SETTINGS_FILE)
        if not isinstance(s, dict): return {}
        return s
    
    def save_settings(self):
        self.save_json(SETTINGS_FILE, self.settings)

    # ==================== DASHBOARD ====================
    def create_dashboard_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Dashboard")
        
        # Bot Status
        status_frame = ttk.LabelFrame(tab, text="Bot Status", padding=10)
        status_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.lbl_status = ttk.Label(status_frame, text="Status: Stopped", font=('Segoe UI', 12, 'bold'))
        self.lbl_status.pack(side=tk.LEFT, padx=5)
        
        # Buttons
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.btn_start = ttk.Button(btn_frame, text="Start Bot", command=self.start_bot)
        self.btn_start.pack(side=tk.LEFT, padx=10)
        
        self.btn_stop = ttk.Button(btn_frame, text="Stop Bot", command=self.stop_bot, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(btn_frame, text="Check Updates", command=self.check_updates).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(btn_frame, text="Exit Bot", command=self.exit_app).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Minimize to Tray", command=self.minimize_to_tray).pack(side=tk.RIGHT, padx=5)
        
        # Logs
        log_frame = ttk.LabelFrame(tab, text="Bot Logs", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, state='disabled', height=20, font=('Consolas', 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def start_bot(self):
        if not self.bot_running:
            # Disable button immediately to prevent double-click
            self.btn_start.config(state=tk.DISABLED)
            self.lbl_status.config(text="Status: Starting...")
            
            try:
                self.bot_thread = threading.Thread(target=self._run_bot_thread, daemon=True)
                self.bot_thread.start()
                self.bot_running = True
                
                self.btn_stop.config(state=tk.NORMAL)
                self.status_var.set("Status: Running")
                self.lbl_status.config(text="Status: Running")
            except Exception as e:
                print(f"Error starting bot: {e}")
                self.reset_ui_stopped()
                messagebox.showerror("Error", str(e))

    def _run_bot_thread(self):
        """Run bot in a separate thread with its own event loop."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 1. Auth Check (Background)
            print("Verifying tokens...")
            valid = loop.run_until_complete(TokenManager().validate_and_refresh_tokens())
            
            if not valid:
                self.root.after(0, self.handle_auth_failure)
                loop.close()
                return

            # 2. Run Bot
            self.bot = Bot()
            self.bot.run()
        except Exception as e:
            print(f"Bot thread error: {e}")
            self.root.after(0, self.reset_ui_stopped)

    def handle_auth_failure(self):
        """Handle auth failure on main thread."""
        self.reset_ui_stopped()
        msg = "Bot tokens are invalid or missing.\n\nThe 'Token Generator' will now launch.\nPlease follow the instructions to generate new tokens.\n\nThe Control Panel will restart automatically once you are done."
        messagebox.showwarning("Authentication Failure", msg)
        self.launch_token_generator()

    def reset_ui_stopped(self):
        """Reset UI to stopped state."""
        self.bot_running = False
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.status_var.set("Status: Stopped")
        self.lbl_status.config(text="Status: Stopped")
    
    def stop_bot(self):
        if self.bot_running:
            try:
                if self.bot:
                    self.bot.stop()
                self.bot_running = False
                self.btn_start.config(state=tk.NORMAL)
                self.btn_stop.config(state=tk.DISABLED)
                self.status_var.set("Status: Stopped")
                self.lbl_status.config(text="Status: Stopped")
                print("Bot stopped.")
            except Exception as e:
                print(f"Error stopping bot: {e}")

    def check_updates(self):
        """Check for updates using updater.py --check"""
        try:
            print("Checking for updates...")
            # Run updater.py --check
            # Use subprocess to capture output
            cmd = ["python", "updater.py", "--check"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            output = result.stdout.strip()
            
            if "UPDATE_AVAILABLE" in output:
                # Parse count if needed: UPDATE_AVAILABLE:5
                count = "several"
                if ":" in output:
                    count = output.split(":")[1]
                    
                print(f"Update available! ({count} commits behind)")
                
                # Ask user
                if messagebox.askyesno("Update Available", f"An update is available ({count} commits).\n\nDo you want to update now?\nThe bot will restart."):
                    self.perform_update()
            elif "UPDATE_NONE" in output:
                print("Bot is up to date.")
                messagebox.showinfo("Update Check", "Bot is up to date.")
            else:
                print(f"Update check finished with unexpected output: {output}")
                
        except Exception as e:
            print(f"Error checking updates: {e}")
            messagebox.showerror("Update Error", str(e))

    def perform_update(self):
        """Launch updater to perform actual update"""
        try:
            print("Launching updater...")
            # We use Popen and passing PID so updater can kill us/wait
            # But since we are the GUI, we might want to close gracefully?
            # actually if we pass PID of this process, updater kills it.
            
            cmd = ["python", "updater.py", "--pid", str(os.getpid())]
            subprocess.Popen(cmd)
            
            # Application presumably dies now or shortly
        except Exception as e:
            print(f"Error launching updater: {e}")

    def update_logs(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_text.config(state='normal')
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state='disabled')
        self.root.after(100, self.update_logs)

    def check_auto_start(self):
        if self.settings.get('auto_start_bot'):
            self.root.after(1000, self.start_bot)
        if self.settings.get('start_minimized'):
            self.minimize_to_tray()

    # ==================== SYSTEM TRAY ====================
    def setup_tray_icon(self):
        """Create and start the tray icon immediately."""
        if self.tray_icon: return

        # Create a basic image (White square on dark bg)
        image = Image.new('RGB', (64, 64), color=(30, 30, 30))
        d = ImageDraw.Draw(image)
        d.rectangle([16,16,48,48], fill=(255, 255, 255))
        
        def get_toggle_text(item):
            # User requested reversal: "Show" when visible (Status?), "Hide" when hidden.
            return "Show" if self.is_window_visible else "Hide"

        menu = pystray.Menu(
            pystray.MenuItem(get_toggle_text, self.toggle_window, default=True),
            pystray.MenuItem('Exit', self.exit_app)
        )
        
        self.tray_icon = pystray.Icon("botthehekli", image, "botthehekli", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def minimize_to_tray(self):
        """Hide window; icon is already running."""
        self.root.withdraw()
        self.is_window_visible = False

    def show_window(self, icon=None, item=None):
        """Show window; do NOT stop icon."""
        self.root.after(0, self._restore_window)
        
    def _restore_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.is_window_visible = True

    def toggle_window(self, icon=None, item=None):
        # Force toggle based on current flag
        if self.is_window_visible:
            self.root.after(0, self.minimize_to_tray)
        else:
            self.show_window()

    def on_close(self):
        if self.settings.get('minimize_to_tray_on_close', False):
            self.minimize_to_tray()
        else:
            self.exit_app()

    def exit_app(self, icon=None, item=None):
        if self.bot_running:
            self.stop_bot()
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.destroy()
        sys.exit(0)

    def create_commands_tab(self):
        self.bg_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.bg_frame, text="Commands")
        
        # Tools
        tool_frame = ttk.Frame(self.bg_frame)
        tool_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(tool_frame, text="Add Command", command=self.add_command).pack(side=tk.LEFT)
        ttk.Button(tool_frame, text="Edit Selected", command=self.edit_command).pack(side=tk.LEFT, padx=5)
        ttk.Button(tool_frame, text="Delete Selected", command=self.delete_command).pack(side=tk.LEFT)
        ttk.Button(tool_frame, text="Refresh", command=self.refresh_commands).pack(side=tk.RIGHT)
        
        # Table
        cols = ("Command", "Response", "Role", "Cooldown")
        self.tree_cmds = ttk.Treeview(self.bg_frame, columns=cols, show='headings', selectmode='browse')
        self.tree_cmds.heading("Command", text="Command")
        self.tree_cmds.heading("Response", text="Response")
        self.tree_cmds.heading("Role", text="Role")
        self.tree_cmds.heading("Cooldown", text="Cooldown")
        
        self.tree_cmds.column("Command", width=120)
        self.tree_cmds.column("Response", width=300)
        self.tree_cmds.column("Role", width=80)
        self.tree_cmds.column("Cooldown", width=80)
        
        self.tree_cmds.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.tree_cmds.bind("<Double-1>", lambda e: self.edit_command())
        
        self.refresh_commands()
        
    def refresh_commands(self):
        for i in self.tree_cmds.get_children():
            self.tree_cmds.delete(i)
        
        # Load custom commands
        cmds = self.load_json(COMMANDS_FILE)
        # Load cooldowns
        cds = self.load_json(COOLDOWNS_FILE)
        
        # Sort using migration logic safely if not already done
        for c in sorted(cmds.keys()):
            data = cmds[c]
            # MIGRATION COMPATIBILITY: invalid legacy string check
            if isinstance(data, str):
                resp = data
                role = "everyone"
            else:
                resp = data.get('response', '')
                role = data.get('ul', 'everyone')
            
            cd = cds.get(c, 0)
            self.tree_cmds.insert('', tk.END, values=(c, resp, role, cd))

    def add_command(self):
        """Add a new command via dialog"""
        dlg = CommandEditorDialog(self.root, "Add Command")
        if dlg.result:
            cmd, resp = dlg.result
            
            # Save
            cmds = self.load_json(COMMANDS_FILE)
            cmds[cmd] = {"response": resp, "ul": "everyone", "type": "custom"}
            self.save_json(COMMANDS_FILE, cmds)
            self.refresh_commands()
            
    def edit_command(self):
        """Edit selected"""
        sel = self.tree_cmds.selection()
        if not sel: return
        item = self.tree_cmds.item(sel[0])
        old_cmd = item['values'][0]
        old_resp = item['values'][1]
        
        dlg = CommandEditorDialog(self.root, "Edit Command", old_cmd, old_resp)
        if dlg.result:
            new_cmd, new_resp = dlg.result
            
            cmds = self.load_json(COMMANDS_FILE)
            
            # If renamed, delete old
            if new_cmd != old_cmd and old_cmd in cmds:
                del cmds[old_cmd]
            
            cmds[new_cmd] = {"response": new_resp, "ul": "everyone", "type": "custom"} # preserve role? simplifed for now
            self.save_json(COMMANDS_FILE, cmds)
            self.refresh_commands()
            
    def delete_command(self):
        sel = self.tree_cmds.selection()
        if not sel: return
        cmd = self.tree_cmds.item(sel[0])['values'][0]
        if messagebox.askyesno("Confirm", f"Delete command {cmd}?"):
            cmds = self.load_json(COMMANDS_FILE)
            if cmd in cmds:
                del cmds[cmd]
                self.save_json(COMMANDS_FILE, cmds)
                self.refresh_commands()

    # ==================== ALIASES ====================
    # ==================== ALIASES ====================
    def create_aliases_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Aliases")
        
        # Nested Notebook
        sub_notebook = ttk.Notebook(tab)
        sub_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Tab 1: Command Aliases
        f_cmd = ttk.Frame(sub_notebook)
        sub_notebook.add(f_cmd, text="Command Aliases")
        self.create_command_aliases_panel(f_cmd)
        
        # Tab 2: Game Aliases
        f_game = ttk.Frame(sub_notebook)
        sub_notebook.add(f_game, text="Game Aliases")
        self.create_game_aliases_panel(f_game)

    def create_command_aliases_panel(self, parent):
        tf = ttk.Frame(parent)
        tf.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(tf, text="Add/Edit Alias", command=self.add_cmd_alias).pack(side=tk.LEFT)
        ttk.Button(tf, text="Delete Entry", command=self.del_cmd_alias).pack(side=tk.LEFT, padx=5)
        ttk.Button(tf, text="Refresh", command=self.refresh_cmd_aliases).pack(side=tk.RIGHT)
        
        # Treeview: Main Command | Aliases
        cols = ("Main Command", "Aliases")
        self.tree_ca = ttk.Treeview(parent, columns=cols, show='headings')
        self.tree_ca.heading("Main Command", text="Main Command")
        self.tree_ca.heading("Aliases", text="Aliases (comma sep)")
        self.tree_ca.column("Main Command", width=150)
        self.tree_ca.column("Aliases", width=400)
        self.tree_ca.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.tree_ca.bind("<Double-1>", lambda e: self.add_cmd_alias()) # reuse for edit
        
        self.refresh_cmd_aliases()

    def create_game_aliases_panel(self, parent):
        tf = ttk.Frame(parent)
        tf.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(tf, text="Add Alias", command=self.add_game_alias).pack(side=tk.LEFT)
        ttk.Button(tf, text="Delete Selected", command=self.del_game_alias).pack(side=tk.LEFT, padx=5)
        ttk.Button(tf, text="Refresh", command=self.refresh_game_aliases).pack(side=tk.RIGHT)
        
        cols = ("Short Code", "Game Name")
        self.tree_ga = ttk.Treeview(parent, columns=cols, show='headings')
        self.tree_ga.heading("Short Code", text="Short Code")
        self.tree_ga.heading("Game Name", text="Game Name")
        self.tree_ga.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.refresh_game_aliases()

    # --- Command Aliases Logic ---
    def refresh_cmd_aliases(self):
        for i in self.tree_ca.get_children():
            self.tree_ca.delete(i)
        data = self.load_json(COMMAND_ALIASES_FILE)
        for cmd, aliases in data.items():
            if isinstance(aliases, list):
                alias_str = ", ".join(aliases)
            else:
                alias_str = str(aliases)
            self.tree_ca.insert('', tk.END, values=(cmd, alias_str))

    def add_cmd_alias(self):
        # Determine if editing existing
        sel = self.tree_ca.selection()
        init_cmd = ""
        init_alias = ""
        if sel:
            item = self.tree_ca.item(sel[0])
            init_cmd = item['values'][0]
            init_alias = str(item['values'][1])

        # Dialog
        cmd = simpledialog.askstring("Command Alias", "Enter Main Command (e.g. !donate):", initialvalue=init_cmd, parent=self.root)
        if not cmd: return
        if not cmd.startswith('!'): cmd = '!' + cmd
        
        aliases_raw = simpledialog.askstring("Command Alias", "Enter Aliases (comma separated, e.g. !tip, !money):", initialvalue=init_alias, parent=self.root)
        if not aliases_raw: return
        
        # Process aliases
        alias_list = [a.strip() for a in aliases_raw.split(',') if a.strip()]
        # Ensure prefixes
        alias_list = [(a if a.startswith('!') else '!' + a) for a in alias_list]
        
        data = self.load_json(COMMAND_ALIASES_FILE)
        data[cmd] = alias_list
        self.save_json(COMMAND_ALIASES_FILE, data)
        self.refresh_cmd_aliases()
        
        if self.bot_running and self.bot:
            threading.Thread(target=self.bot.export_web_data).start()
        
    def del_cmd_alias(self):
        sel = self.tree_ca.selection()
        if not sel: return
        cmd = self.tree_ca.item(sel[0])['values'][0]
        if messagebox.askyesno("Delete", f"Delete aliases for {cmd}?"):
            data = self.load_json(COMMAND_ALIASES_FILE)
            if cmd in data:
                del data[cmd]
                self.save_json(COMMAND_ALIASES_FILE, data)
                self.refresh_cmd_aliases()
                
                if self.bot_running and self.bot:
                    threading.Thread(target=self.bot.export_web_data).start()

    # --- Game Aliases Logic ---
    def refresh_game_aliases(self):
        for i in self.tree_ga.get_children():
            self.tree_ga.delete(i)
        data = self.load_json(ALIASES_FILE)
        for a, t in data.items():
            self.tree_ga.insert('', tk.END, values=(a, t))

    def add_game_alias(self):
        alias = simpledialog.askstring("Game Alias", "Enter short code (e.g. val):", parent=self.root)
        if not alias: return
        target = simpledialog.askstring("Game Alias", "Enter full game name (e.g. Valorant):", parent=self.root)
        if not target: return
        
        data = self.load_json(ALIASES_FILE)
        data[alias] = target
        self.save_json(ALIASES_FILE, data)
        self.refresh_game_aliases()

    def del_game_alias(self):
        sel = self.tree_ga.selection()
        if not sel: return
        alias = self.tree_ga.item(sel[0])['values'][0]
        if messagebox.askyesno("Delete", f"Delete game alias {alias}?"):
            data = self.load_json(ALIASES_FILE)
            if alias in data:
                del data[alias]
                self.save_json(ALIASES_FILE, data)
                self.refresh_game_aliases()

    # ==================== PERMISSIONS ====================
    def create_permissions_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Permissions")
        
        tf = ttk.Frame(tab)
        tf.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(tf, text="Edit Permissions", command=self.edit_permission).pack(side=tk.LEFT)
        ttk.Button(tf, text="Refresh", command=self.refresh_permissions).pack(side=tk.RIGHT)
        
        self.tree_perm = ttk.Treeview(tab, columns=("Command", "Allowed Roles"), show='headings', selectmode='browse')
        self.tree_perm.heading("Command", text="Command")
        self.tree_perm.heading("Allowed Roles", text="Allowed Roles")
        self.tree_perm.column("Command", width=120)
        self.tree_perm.column("Allowed Roles", width=400)
        self.tree_perm.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.tree_perm.bind("<Double-1>", lambda e: self.edit_permission())
        
        self.refresh_permissions()

    def refresh_permissions(self):
        for i in self.tree_perm.get_children():
            self.tree_perm.delete(i)
        data = self.load_json(PERMISSIONS_FILE)
        for cmd, roles in sorted(data.items()):
            role_str = ", ".join(roles)
            self.tree_perm.insert('', tk.END, values=(cmd, role_str))
            
    def edit_permission(self):
        sel = self.tree_perm.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Please select a command to edit its permissions.", parent=self.root)
            return
        item = self.tree_perm.item(sel[0])
        cmd = item['values'][0]
        
        # Load current
        data = self.load_json(PERMISSIONS_FILE)
        current = data.get(cmd, [])
        
        dlg = PermissionEditorDialog(self.root, cmd, current)
        if dlg.result is not None:
            data[cmd] = dlg.result
            self.save_json(PERMISSIONS_FILE, data)
            self.refresh_permissions()
            
            if self.bot_running and self.bot:
                 threading.Thread(target=self.bot.export_web_data).start()
            
            # Notify user about bot status
            if self.bot_running:
                messagebox.showinfo("Saved", f"Permissions for {cmd} updated!\n\nChanges will take effect immediately (auto-reloaded).", parent=self.root)
            else:
                messagebox.showinfo("Saved", f"Permissions for {cmd} updated!\n\nStart the bot to apply changes.", parent=self.root)

    # ==================== COOLDOWNS ====================
    def create_cooldowns_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Cooldowns")
        
        tf = ttk.Frame(tab)
        tf.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(tf, text="Set Cooldown", command=self.edit_cooldown).pack(side=tk.LEFT)
        ttk.Button(tf, text="Remove Cooldown", command=self.delete_cooldown).pack(side=tk.LEFT, padx=5)
        ttk.Button(tf, text="Refresh", command=self.refresh_cooldowns).pack(side=tk.RIGHT)
        
        self.tree_cd = ttk.Treeview(tab, columns=("Command", "Seconds"), show='headings')
        self.tree_cd.heading("Command", text="Command")
        self.tree_cd.heading("Seconds", text="Seconds")
        self.tree_cd.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.refresh_cooldowns()

    def refresh_cooldowns(self):
        for i in self.tree_cd.get_children():
            self.tree_cd.delete(i)
        cds = self.load_json(COOLDOWNS_FILE)
        for c, s in cds.items():
            self.tree_cd.insert('', tk.END, values=(c, s))
            
    def edit_cooldown(self):
        cmd = simpledialog.askstring("Cooldown", "Enter command (e.g. !test):")
        if not cmd: return
        if not cmd.startswith('!'): cmd = '!' + cmd
        
        sec = simpledialog.askinteger("Cooldown", "Enter cooldown (seconds):")
        if sec is None: return
        
        cds = self.load_json(COOLDOWNS_FILE)
        cds[cmd] = sec
        self.save_json(COOLDOWNS_FILE, cds)
        self.refresh_cooldowns()
        
    def delete_cooldown(self):
        sel = self.tree_cd.selection()
        if not sel: return
        cmd = self.tree_cd.item(sel[0])['values'][0]
        cds = self.load_json(COOLDOWNS_FILE)
        if cmd in cds:
            del cds[cmd]
            self.save_json(COOLDOWNS_FILE, cds)
            self.refresh_cooldowns()

    # ==================== TIMERS ====================
    def create_timers_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Timers")
        
        # Tools
        tf = ttk.Frame(tab)
        tf.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(tf, text="Add Timer", command=self.add_timer).pack(side=tk.LEFT)
        ttk.Button(tf, text="Edit Selected", command=self.edit_timer).pack(side=tk.LEFT, padx=5)
        ttk.Button(tf, text="Delete Selected", command=self.delete_timer).pack(side=tk.LEFT)
        ttk.Button(tf, text="Refresh", command=self.refresh_timers).pack(side=tk.RIGHT)
        
        # Table
        cols = ("Name", "Message", "Interval (m)", "Lines")
        self.tree_timers = ttk.Treeview(tab, columns=cols, show='headings', selectmode='browse')
        self.tree_timers.heading("Name", text="Name")
        self.tree_timers.heading("Message", text="Message")
        self.tree_timers.heading("Interval (m)", text="Interval (m)")
        self.tree_timers.heading("Lines", text="Lines")
        
        self.tree_timers.column("Name", width=100)
        self.tree_timers.column("Message", width=300)
        self.tree_timers.column("Interval (m)", width=80)
        self.tree_timers.column("Lines", width=50)
        
        self.tree_timers.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.tree_timers.bind("<Double-1>", lambda e: self.edit_timer())
        
        self.refresh_timers()

    # ==================== COUNTS ====================
    def create_counts_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Counts")
        
        tf = ttk.Frame(tab)
        tf.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(tf, text="Add/Edit Count", command=self.edit_count).pack(side=tk.LEFT)
        ttk.Button(tf, text="Delete Selected", command=self.delete_count).pack(side=tk.LEFT, padx=5)
        ttk.Button(tf, text="Refresh", command=self.refresh_counts).pack(side=tk.RIGHT)
        
        self.tree_counts = ttk.Treeview(tab, columns=("Name", "Value"), show='headings')
        self.tree_counts.heading("Name", text="Name")
        self.tree_counts.heading("Value", text="Value")
        self.tree_counts.column("Name", width=150)
        self.tree_counts.column("Value", width=100)
        
        self.tree_counts.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.tree_counts.bind("<Double-1>", lambda e: self.edit_count())
        
        self.refresh_counts()

    def refresh_counts(self):
        for i in self.tree_counts.get_children():
            self.tree_counts.delete(i)
        
        counts = self.load_json(COUNTS_FILE)
        for name, val in sorted(counts.items()):
            self.tree_counts.insert('', tk.END, values=(name, val))

    def edit_count(self):
        # Determine if editing existing
        sel = self.tree_counts.selection()
        init_name = ""
        init_val = 0
        
        if sel:
            item = self.tree_counts.item(sel[0])
            init_name = item['values'][0]
            try:
                init_val = int(item['values'][1])
            except: pass
            
        name = simpledialog.askstring("Edit Count", "Counter Name (e.g. deaths):", initialvalue=init_name, parent=self.root)
        if not name: return
        
        val = simpledialog.askinteger("Edit Count", f"Value for '{name}':", initialvalue=init_val, parent=self.root)
        if val is None: return
        
        counts = self.load_json(COUNTS_FILE)
        
        # If renaming (and old name exists), delete old ONLY if we selected one
        if sel and init_name and init_name != name and init_name in counts:
            del counts[init_name]
            
        counts[name] = val
        self.save_json(COUNTS_FILE, counts)
        self.refresh_counts()

    def delete_count(self):
        sel = self.tree_counts.selection()
        if not sel: return
        name = self.tree_counts.item(sel[0])['values'][0]
        
        if messagebox.askyesno("Confirm", f"Delete counter '{name}'?"):
            counts = self.load_json(COUNTS_FILE)
            if name in counts:
                del counts[name]
                self.save_json(COUNTS_FILE, counts)
                self.refresh_counts()
        
        self.refresh_timers()

    def refresh_timers(self):
        for i in self.tree_timers.get_children():
            self.tree_timers.delete(i)
        
        # timers.json is a list of dicts: [{"name":..., "message":..., ...}]
        # But load_json returns {}, we need to handle that or import TIMERS_FILE
        timers_data = []
        if os.path.exists(TIMERS_FILE):
             try:
                with open(TIMERS_FILE, 'r', encoding='utf-8') as f:
                    timers_data = json.load(f)
             except: pass
        
        if not isinstance(timers_data, list): timers_data = []
        
        for t in timers_data:
            self.tree_timers.insert('', tk.END, values=(
                t.get('name', ''),
                t.get('message', ''),
                t.get('interval', 15),
                t.get('lines', 2)
            ))

    def add_timer(self):
        dlg = TimerEditorDialog(self.root, "Add Timer")
        if dlg.result:
            new_data = dlg.result
            
            # Load existing to check duplicates
            timers_data = self._load_timers_file()
            
            # Check duplicate name
            for t in timers_data:
                if t.get('name') == new_data['name']:
                    messagebox.showerror("Error", f"Timer '{new_data['name']}' already exists.")
                    return

            timers_data.append(new_data)
            self._save_timers_file(timers_data)
            self.refresh_timers()

    def edit_timer(self):
        sel = self.tree_timers.selection()
        if not sel: return
        
        # Get current data from tree/file
        # We rely on the name as the key
        item = self.tree_timers.item(sel[0])
        current_name = item['values'][0]
        
        timers_data = self._load_timers_file()
        target_timer = next((t for t in timers_data if t.get('name') == current_name), None)
        
        if not target_timer:
            messagebox.showerror("Error", "Could not find timer data.")
            return
            
        dlg = TimerEditorDialog(self.root, "Edit Timer", initial_data=target_timer)
        if dlg.result:
            new_data = dlg.result
            
            # If name changed, we need to handle that
            # Remove the old entry
            timers_data = [t for t in timers_data if t.get('name') != current_name]
            
            # If name changed, check if new name collides with another EXISTING timer
            if new_data['name'] != current_name:
                collision = any(t for t in timers_data if t.get('name') == new_data['name'])
                if collision:
                    messagebox.showerror("Error", f"Timer name '{new_data['name']}' is taken.")
                    return
            
            timers_data.append(new_data)
            self._save_timers_file(timers_data)
            self.refresh_timers()

    def delete_timer(self):
        sel = self.tree_timers.selection()
        if not sel: return
        name = self.tree_timers.item(sel[0])['values'][0]
        
        if messagebox.askyesno("Confirm", f"Delete timer '{name}'?"):
            timers_data = self._load_timers_file()
            timers_data = [t for t in timers_data if t.get('name') != name]
            self._save_timers_file(timers_data)
            self.refresh_timers()

    def _load_timers_file(self):
        if os.path.exists(TIMERS_FILE):
             try:
                with open(TIMERS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list): return data
             except: pass
        return []

    def _save_timers_file(self, data):
        with open(TIMERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)

    # ==================== RESPONSES ====================
    def create_responses_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Responses")
        
        # Split view: List | Editor
        paned = ttk.PanedWindow(tab, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left: List
        frame_list = ttk.LabelFrame(paned, text="Templates")
        paned.add(frame_list, weight=1)
        
        ttk.Button(frame_list, text="Refresh", command=self.refresh_responses).pack(fill=tk.X)
        self.list_resp = tk.Listbox(frame_list, width=30) # Wider to show descriptions
        self.list_resp.pack(fill=tk.BOTH, expand=True)
        self.list_resp.bind("<<ListboxSelect>>", self.on_resp_select)
        
        # Right: Editor
        frame_edit = ttk.LabelFrame(paned, text="Edit Template")
        paned.add(frame_edit, weight=2)
        
        # Header: Key + Enabled Toggle
        header_frame = ttk.Frame(frame_edit)
        header_frame.pack(fill=tk.X, padx=5, pady=2)
        
        self.lbl_resp_key = ttk.Label(header_frame, text="Key: -", font=('Consolas', 9))
        self.lbl_resp_key.pack(side=tk.LEFT)
        
        self.resp_enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(header_frame, text="Enabled", variable=self.resp_enabled_var).pack(side=tk.RIGHT)
        
        self.text_resp_edit = scrolledtext.ScrolledText(frame_edit, height=10, font=('Segoe UI', 10))
        self.text_resp_edit.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        ttk.Button(frame_edit, text="Save Changes", command=self.save_resp).pack(anchor=tk.E, padx=5, pady=5)
        
        self.refresh_responses()

    def refresh_responses(self):
        self.list_resp.delete(0, tk.END)
        self.responses_data = self.load_json(RESPONSES_FILE) # Load raw
        self.resp_keys = list(self.responses_data.keys()) # Store keys mapping
        
        # Display readable names if available
        for k in self.resp_keys:
            val = self.responses_data[k]
            # Handle both string (legacy) and dict (new)
            if isinstance(val, dict):
                display = val.get("description", k)
            else:
                display = k
            self.list_resp.insert(tk.END, display)
            
    def on_resp_select(self, event):
        sel = self.list_resp.curselection()
        if not sel: return
        idx = sel[0]
        if idx < len(self.resp_keys):
            key = self.resp_keys[idx]
            val = self.responses_data.get(key, "")
            
            self.lbl_resp_key.config(text=f"Key: {key}")
            self.text_resp_edit.delete("1.0", tk.END)
            
            # Load template content
            if isinstance(val, dict):
                content = val.get("template", "")
                enabled = val.get("enabled", True)
            else:
                content = str(val)
                enabled = True
            
            self.text_resp_edit.insert("1.0", content)
            self.resp_enabled_var.set(enabled)
            self.current_resp_key = key
        
    def save_resp(self):
        if hasattr(self, 'current_resp_key') and self.current_resp_key:
            val = self.text_resp_edit.get("1.0", tk.END).strip()
            # Preserve description/structure if possible
            current = self.responses_data[self.current_resp_key]
            
            if isinstance(current, dict):
                current["template"] = val
                current["enabled"] = self.resp_enabled_var.get()
                self.responses_data[self.current_resp_key] = current
            else:
                # Convert to dict structure to support enabled flag
                self.responses_data[self.current_resp_key] = {
                    "template": val,
                    "description": self.current_resp_key, # default desc
                    "enabled": self.resp_enabled_var.get()
                }
                
            self.save_json(RESPONSES_FILE, self.responses_data)
            messagebox.showinfo("Saved", f"Updated {self.current_resp_key}")

            messagebox.showinfo("Saved", f"Updated {self.current_resp_key}")

    # ==================== MUSIC SERVICES ====================
    def create_music_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Music Services")

        # --- Active Service ---
        svc_frame = ttk.LabelFrame(tab, text="Active Music Service", padding=10)
        svc_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.var_music_service = tk.StringVar(value=self.settings.get('active_music_service', 'spotify'))
        
        f_radios = ttk.Frame(svc_frame)
        f_radios.pack(fill=tk.X)
        ttk.Radiobutton(f_radios, text="Spotify (Default)", variable=self.var_music_service, value="spotify").pack(side=tk.LEFT, padx=(0, 20))
        ttk.Radiobutton(f_radios, text="Cider (Apple Music)", variable=self.var_music_service, value="cider").pack(side=tk.LEFT)
        
        ttk.Label(svc_frame, text="Controls destination for !sr and channel point requests.", font=("Segoe UI", 8, "italic")).pack(anchor=tk.W, pady=(5,0))

        # --- Notebook for Service Configs ---
        # We use a nested notebook or just frames. Let's use Frames in a PanedWindow or just stacked LabelFrames.
        # Given space, let's use a Notebook for "Service Config" to keep it clean, OR just stacked frames.
        # Let's try stacked frames for visibility.
        
        # --- Common Request Settings ---
        req_settings = ttk.LabelFrame(tab, text="General Request Rules", padding=10)
        req_settings.pack(fill=tk.X, padx=10, pady=5)
        
        self.var_disable_offline = tk.BooleanVar()
        self.var_auto_refund = tk.BooleanVar()
        self.var_auto_fulfill = tk.BooleanVar()
        self.var_requests_enabled = tk.BooleanVar() # Global toggle? Or Spotify specific? It was Spotify specific. Let's make it global logic?
        # Actually checking code: spotify_requests_enabled is checked in !sr.
        # Let's rename it visually to "Enable Requests (Global)" or keep it.
        
        c1 = ttk.Checkbutton(req_settings, text="Enable Song Requests (!sr)", variable=self.var_requests_enabled)
        c1.grid(row=0, column=0, sticky=tk.W, padx=5)
        
        c2 = ttk.Checkbutton(req_settings, text="Disable when offline", variable=self.var_disable_offline)
        c2.grid(row=0, column=1, sticky=tk.W, padx=5)
        
        c3 = ttk.Checkbutton(req_settings, text="Auto-refund on failure", variable=self.var_auto_refund)
        c3.grid(row=1, column=0, sticky=tk.W, padx=5)
        
        c4 = ttk.Checkbutton(req_settings, text="Auto-fulfill on success", variable=self.var_auto_fulfill)
        c4.grid(row=1, column=1, sticky=tk.W, padx=5)

        # --- Service Configuration Area ---
        # We can use a small notebook here for "Spotify Config" vs "Cider Config" to save vertical space
        config_nb = ttk.Notebook(tab)
        config_nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 1. Spotify Config Tab
        f_spot = ttk.Frame(config_nb, padding=10)
        config_nb.add(f_spot, text="Spotify Config")
        
        ttk.Label(f_spot, text="Client ID:").grid(row=0, column=0, sticky=tk.W)
        self.entry_spot_id = ttk.Entry(f_spot, width=35)
        self.entry_spot_id.grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(f_spot, text="Client Secret:").grid(row=1, column=0, sticky=tk.W)
        self.entry_spot_sec = ttk.Entry(f_spot, width=35, show="*")
        self.entry_spot_sec.grid(row=1, column=1, padx=5, pady=2)
        
        ttk.Separator(f_spot, orient='horizontal').grid(row=2, column=0, columnspan=2, sticky='ew', pady=10)
        
        ttk.Label(f_spot, text="Playlist URL:").grid(row=3, column=0, sticky=tk.W)
        self.entry_playlist = ttk.Entry(f_spot, width=35)
        self.entry_playlist.grid(row=3, column=1, padx=5, pady=2)
        
        self.var_add_playlist = tk.BooleanVar()
        ttk.Checkbutton(f_spot, text="Add requested songs to playlist", variable=self.var_add_playlist).grid(row=4, column=1, sticky=tk.W, pady=2)
        
        # 2. Cider Config Tab
        f_cider = ttk.Frame(config_nb, padding=10)
        config_nb.add(f_cider, text="Cider Config")
        
        ttk.Label(f_cider, text="Host URL:").grid(row=0, column=0, sticky=tk.W)
        self.entry_cider_host = ttk.Entry(f_cider, width=35)
        self.entry_cider_host.grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(f_cider, text="Auth Token:").grid(row=1, column=0, sticky=tk.W)
        self.entry_cider_token = ttk.Entry(f_cider, width=35, show="*")
        self.entry_cider_token.grid(row=1, column=1, padx=5, pady=2)
        
        ttk.Label(f_cider, text="Note: Enable 'External Application Access' in Cider.", font=("Segoe UI", 8)).grid(row=2, column=0, columnspan=2, pady=10, sticky=tk.W)
        
        # --- Save Button ---
        ttk.Button(tab, text="Save All Music Settings", command=self.save_music_settings).pack(pady=10)
        
        # Load
        self.load_music_settings()

    def load_music_settings(self):
        # 1. Env Vars (Spotify & Cider)
        env_vars = {}
        if os.path.exists(ENV_FILE):
             try:
                 with open(ENV_FILE, 'r') as f:
                     for line in f:
                         if '=' in line and not line.strip().startswith('#'):
                             k, v = line.strip().split('=', 1)
                             env_vars[k] = v.strip()
             except: pass
             
        # Spotify
        self.entry_spot_id.delete(0, tk.END)
        self.entry_spot_id.insert(0, env_vars.get('SPOTIFY_CLIENT_ID', ''))
        self.entry_spot_sec.delete(0, tk.END)
        self.entry_spot_sec.insert(0, env_vars.get('SPOTIFY_CLIENT_SECRET', ''))
        
        # Cider
        self.entry_cider_host.delete(0, tk.END)
        self.entry_cider_host.insert(0, env_vars.get('CIDER_HOST', 'http://localhost:10767'))
        self.entry_cider_token.delete(0, tk.END)
        self.entry_cider_token.insert(0, env_vars.get('CIDER_TOKEN', ''))
        
        # 2. JSON Settings
        self.entry_playlist.delete(0, tk.END)
        self.entry_playlist.insert(0, self.settings.get('spotify_playlist_url', ''))
        
        self.var_add_playlist.set(self.settings.get('history_to_playlist', False))
        self.var_disable_offline.set(self.settings.get('disable_requests_offline', False))
        self.var_auto_refund.set(self.settings.get('auto_refund_on_error', False)) # Defaulted to False/True based on prev
        self.var_auto_fulfill.set(self.settings.get('auto_fulfill_on_success', False))
        self.var_requests_enabled.set(self.settings.get('spotify_requests_enabled', True))
        
        # Active Service
        self.var_music_service.set(self.settings.get('active_music_service', 'spotify'))

    def save_music_settings(self):
        # 1. Update Env File
        env_vars = {}
        if os.path.exists(ENV_FILE):
            try:
                with open(ENV_FILE, 'r') as f:
                    for line in f:
                        if '=' in line:
                            k, v = line.strip().split('=', 1)
                            env_vars[k] = v.strip()
            except: pass
            
        # Spotify Env
        env_vars['SPOTIFY_CLIENT_ID'] = self.entry_spot_id.get().strip()
        env_vars['SPOTIFY_CLIENT_SECRET'] = self.entry_spot_sec.get().strip()
        
        # Cider Env
        c_host = self.entry_cider_host.get().strip()
        if not c_host: c_host = "http://localhost:10767"
        env_vars['CIDER_HOST'] = c_host
        env_vars['CIDER_TOKEN'] = self.entry_cider_token.get().strip()
        
        with open(ENV_FILE, 'w') as f:
            for k, v in env_vars.items():
                f.write(f"{k}={v}\n")
                
        # Update os.environ
        for k, v in env_vars.items():
            os.environ[k] = v
            
        # 2. Update JSON Settings
        self.settings['active_music_service'] = self.var_music_service.get()
        self.settings['spotify_playlist_url'] = self.entry_playlist.get().strip()
        self.settings['history_to_playlist'] = self.var_add_playlist.get()
        self.settings['disable_requests_offline'] = self.var_disable_offline.get()
        self.settings['auto_refund_on_error'] = self.var_auto_refund.get()
        self.settings['auto_fulfill_on_success'] = self.var_auto_fulfill.get()
        self.settings['spotify_requests_enabled'] = self.var_requests_enabled.get()
        
        self.save_settings()
        
        messagebox.showinfo("Saved", "Music settings saved!", parent=self.root)

    # ==================== SETTINGS ====================
    def create_settings_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Settings")
        
        opts = ttk.LabelFrame(tab, text="Startup Options", padding=10)
        opts.pack(fill=tk.X, padx=10, pady=10)
        
        self.var_autostart = tk.BooleanVar(value=self.settings.get('auto_start_bot', False))
        self.var_min_start = tk.BooleanVar(value=self.settings.get('start_minimized', False))
        self.var_min_close = tk.BooleanVar(value=self.settings.get('minimize_to_tray_on_close', False))
        
        ttk.Checkbutton(opts, text="Auto-start bot on launch", variable=self.var_autostart).pack(anchor=tk.W)
        ttk.Checkbutton(opts, text="Start minimized to tray", variable=self.var_min_start).pack(anchor=tk.W)
        ttk.Checkbutton(opts, text="Minimize to tray on close", variable=self.var_min_close).pack(anchor=tk.W)
        
        # Auth / Maintenance
        maint = ttk.LabelFrame(tab, text="Maintenance", padding=10)
        maint.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(maint, text="Launch Token Generator", command=self.confirm_launch_generator).pack(anchor=tk.W)
        ttk.Button(maint, text="Open .env File", command=lambda: os.startfile(ENV_FILE)).pack(anchor=tk.W)
        
        # Gist Sync Settings
        gist_frame = ttk.LabelFrame(tab, text="Website Sync (GitHub Gist)", padding=10)
        gist_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(gist_frame, text="GitHub Token (gist scope)").pack(anchor=tk.W)
        self.entry_github_token = ttk.Entry(gist_frame, show="*")
        self.entry_github_token.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(gist_frame, text="Gist ID").pack(anchor=tk.W)
        self.entry_gist_id = ttk.Entry(gist_frame)
        self.entry_gist_id.pack(fill=tk.X)
        
        # Load env vars
        env = load_env_file()
        if env.get('GITHUB_TOKEN'):
            self.entry_github_token.insert(0, env.get('GITHUB_TOKEN'))
        if env.get('GIST_ID'):
            self.entry_gist_id.insert(0, env.get('GIST_ID'))
        
        ttk.Button(gist_frame, text="Force Sync Now", command=self.force_sync_gist).pack(pady=5)
        
        ttk.Button(tab, text="Save Settings", command=self.save_general_settings).pack(pady=10)

    def confirm_launch_generator(self):
        if messagebox.askyesno("Launch Token Generator", "The bot must close to run the token generator.\nIt will restart automatically after you finish.\n\nContinue?"):
            self.stop_bot()
            self.launch_token_generator()

    def save_general_settings(self):
        self.settings['auto_start_bot'] = self.var_autostart.get()
        self.settings['start_minimized'] = self.var_min_start.get()
        self.settings['minimize_to_tray_on_close'] = self.var_min_close.get()
        # active_music_service is now saved in Music tab
        self.save_settings()
        
        # Save Gist credentials to .env
        env_vars = {}
        token = self.entry_github_token.get().strip()
        gist_id = self.entry_gist_id.get().strip()
        
        if token: env_vars['GITHUB_TOKEN'] = token
        if gist_id: env_vars['GIST_ID'] = gist_id
        
        if env_vars:
            update_env_file(env_vars)
            print("✅ Gist credentials updated")
        
        messagebox.showinfo("Saved", "Settings saved successfully!", parent=self.root)

    def force_sync_gist(self):
        if not self.bot or not self.bot_running:
            messagebox.showwarning("Warning", "Bot must be running to sync commands.", parent=self.root)
            return
            
        threading.Thread(target=self.bot.export_web_data).start()
        messagebox.showinfo("Sync Started", "Gist sync has been triggered.\nCheck the logs for '✅ Gist synced successfully' or error details.", parent=self.root)

    def sort_and_migrate_commands(self):
        """Sort commands alphabetically and migrate legacy string formats to dicts."""
        data = self.load_json(COMMANDS_FILE)
        if hasattr(data, 'items'):
            new_data = {}
            # Sort by key
            for key in sorted(data.keys()):
                val = data[key]
                # Migration: Convert string to dict if needed
                if isinstance(val, str):
                    new_data[key] = {"response": val, "ul": "everyone", "type": "custom"}
                else:
                    new_data[key] = val
            self.save_json(COMMANDS_FILE, new_data)

    def run(self):
        self.sort_and_migrate_commands() # Auto-sort on launch
        self.root.mainloop()

if __name__ == "__main__":
    try:
        app = BotGUI()
        app.run()
    except Exception as e:
        import traceback
        import datetime
        
        # Log to file
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        error_details = traceback.format_exc()
        error_msg = f"[{timestamp}] CRITICAL STARTUP ERROR:\n{error_details}\n{'-'*50}\n"
        
        with open("crash_log.txt", "a", encoding='utf-8') as f:
            f.write(error_msg)
            
        # Error Dialog
        try:
            # Create a minimal root if needed for the messagebox
            if 'tk' not in sys.modules:
                import tkinter as tk
            if 'messagebox' not in sys.modules:
                from tkinter import messagebox
                
            # We try to use the existing root if logical, but safe to create new hidden one for the error
            err_root = tk.Tk()
            err_root.withdraw()
            messagebox.showerror("Startup Error", f"The application failed to start.\n\nError: {e}\n\nDetails saved to crash_log.txt")
            err_root.destroy()
        except:
            pass # Fallback if GUI fails completely
