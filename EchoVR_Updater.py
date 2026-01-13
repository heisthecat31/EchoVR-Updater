import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import shutil
import subprocess
import threading
import urllib.request
import zipfile
import json
import time
import stat  # Needed for handling read-only files

# --- CONFIGURATION ---
REPO_URL = "https://github.com/heisthecat31/EchoVR-Updater/releases/download/Ignoreme/input-pcvr.zip"
SETTINGS_DIR = "Settings"
CONFIG_FILE = "config.json"
TOOL_NAME = "evrFileTools.exe"
INPUT_DIR_NAME = "input-pcvr"
EXTRACTED_DIR_NAME = "pcvr-extracted"
OUTPUT_DIR_NAME = "output-both"

class EchoUpdaterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("EchoVR Auto-Updater")
        self.root.geometry("600x550") # Made slightly taller for extra button
        self.root.resizable(False, False)
        self.root.configure(bg="#1a1a1a")
        
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("TProgressbar", thickness=20, troughcolor='#333333', background='#4cd964')
        
        # Get absolute base directory
        if getattr(sys, 'frozen', False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))

        self.settings_path = os.path.join(self.base_dir, SETTINGS_DIR)
        self.config_file = os.path.join(self.settings_path, CONFIG_FILE)
        
        self.data_folder = None
        self.last_backup_folder = None
        self.package_name = None
        self.cancel_process = False
        
        self.load_config()
        self.setup_ui()
        self.check_tools()
        self.update_restore_button_state()

    def load_config(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    
                    # Load Data Folder
                    stored_path = config.get('data_folder')
                    if stored_path and os.path.exists(stored_path):
                        self.data_folder = stored_path
                        
                    # Load Last Backup Folder
                    backup_path = config.get('last_backup_folder')
                    if backup_path and os.path.exists(backup_path):
                        self.last_backup_folder = backup_path
                        
        except Exception as e:
            print(f"Failed to load config: {e}")

    def save_config(self):
        try:
            if not os.path.exists(self.settings_path):
                os.makedirs(self.settings_path)
            
            data = {
                'data_folder': self.data_folder,
                'last_backup_folder': self.last_backup_folder
            }
            
            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Failed to save config: {e}")

    def setup_ui(self):
        header_frame = tk.Frame(self.root, bg="#1a1a1a")
        header_frame.pack(fill=tk.X, pady=20)
        
        tk.Label(header_frame, text="ECHO VR UPDATER", font=("Segoe UI", 20, "bold"), fg="white", bg="#1a1a1a").pack()
        tk.Label(header_frame, text="PCVR Edition", font=("Segoe UI", 10), fg="#888888", bg="#1a1a1a").pack()

        self.main_frame = tk.Frame(self.root, bg="#1a1a1a")
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=20)

        self.status_label = tk.Label(self.main_frame, text="Ready to update", font=("Segoe UI", 11), fg="#cccccc", bg="#1a1a1a")
        self.status_label.pack(pady=(10, 5))

        self.progress = ttk.Progressbar(self.main_frame, orient="horizontal", length=400, mode="determinate")
        self.progress.pack(pady=10)

        # UPDATE BUTTON
        btn_text = "DOWNLOAD LATEST UPDATES"
        if self.data_folder:
            btn_text += " (Game Folder Detected)"

        self.action_btn = tk.Button(self.main_frame, text=btn_text, command=self.start_update_process, 
                                    bg="#007aff", fg="white", font=("Segoe UI", 12, "bold"), 
                                    relief=tk.FLAT, padx=20, pady=10, cursor="hand2")
        self.action_btn.pack(pady=(10, 5))

        # RESTORE BUTTON
        self.restore_btn = tk.Button(self.main_frame, text="RESTORE FROM BACKUP", command=self.start_restore_process, 
                                    bg="#d9534f", fg="white", font=("Segoe UI", 10, "bold"), 
                                    relief=tk.FLAT, padx=15, pady=5, cursor="hand2")
        self.restore_btn.pack(pady=(5, 20))

        log_frame = tk.Frame(self.main_frame, bg="#1a1a1a")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, font=("Consolas", 9), bg="#222222", fg="#eeeeee", relief=tk.FLAT)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def update_restore_button_state(self):
        if self.last_backup_folder and os.path.exists(self.last_backup_folder):
            self.restore_btn.config(state=tk.NORMAL, text="RESTORE FROM BACKUP")
        else:
            self.restore_btn.config(state=tk.DISABLED, text="NO BACKUP FOUND")

    def log(self, message):
        """Thread-safe logging to the text box."""
        self.log_text.insert(tk.END, f"> {message}\n")
        self.log_text.see(tk.END)
        self.status_label.config(text=message)
        print(message)

    def log_safe(self, msg):
        """Helper to log from background threads using main thread event loop."""
        self.root.after(0, lambda: self.log(msg))
        # Update progress bar safely
        self.root.after(0, lambda: self.progress.step(5))

    def get_tool_path(self):
        return os.path.join(self.settings_path, TOOL_NAME)

    def get_absolute_path(self, folder_name):
        return os.path.join(self.base_dir, folder_name)

    def check_tools(self):
        path = self.get_tool_path()
        if not os.path.exists(path):
            messagebox.showerror("Missing Tool", f"Could not find {TOOL_NAME}\nExpected at: {path}")
            self.action_btn.config(state=tk.DISABLED)
            self.log(f"Error: Tool missing at {path}")
        else:
            self.log(f"Tool found: {path}")

    def run_hidden_command(self, cmd):
        """Runs a subprocess without a visible console window."""
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        
        try:
            return subprocess.run(
                cmd, 
                startupinfo=startupinfo,
                capture_output=True, 
                text=True, 
                cwd=self.base_dir, 
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        except Exception as e:
            return None

    def start_update_process(self):
        self.action_btn.config(state=tk.DISABLED)
        self.restore_btn.config(state=tk.DISABLED)
        self.cancel_process = False
        threading.Thread(target=self.process_thread, daemon=True).start()

    # ---------------------------------------------------------
    # RESTORE FUNCTIONALITY
    # ---------------------------------------------------------
    def start_restore_process(self):
        if not self.data_folder or not os.path.exists(self.data_folder):
            messagebox.showerror("Error", "Game folder is not known. Cannot restore.")
            return

        msg = f"This will overwrite your current game files with files from:\n{self.last_backup_folder}\n\nAre you sure?"
        if messagebox.askyesno("Confirm Restore", msg):
            self.action_btn.config(state=tk.DISABLED)
            self.restore_btn.config(state=tk.DISABLED)
            threading.Thread(target=self.restore_worker, daemon=True).start()

    def restore_worker(self):
        try:
            self.log_safe("Starting restoration...")
            self.root.after(0, lambda: self.progress.configure(value=10))
            time.sleep(1)

            # 1. Clear Current
            self.log_safe("Clearing current files...")
            
            def remove_readonly(func, path, excinfo):
                os.chmod(path, stat.S_IWRITE)
                func(path)

            target_pkg = os.path.join(self.data_folder, "packages")
            target_mnf = os.path.join(self.data_folder, "manifests")

            if os.path.exists(target_pkg): shutil.rmtree(target_pkg, onerror=remove_readonly)
            if os.path.exists(target_mnf): shutil.rmtree(target_mnf, onerror=remove_readonly)

            self.root.after(0, lambda: self.progress.configure(value=40))

            # 2. Copy Backup
            self.log_safe("Restoring backup files...")
            
            src_pkg = os.path.join(self.last_backup_folder, "packages")
            src_mnf = os.path.join(self.last_backup_folder, "manifests")

            if os.path.exists(src_pkg):
                shutil.copytree(src_pkg, target_pkg)
            
            if os.path.exists(src_mnf):
                shutil.copytree(src_mnf, target_mnf)

            self.root.after(0, lambda: self.progress.configure(value=100))
            self.log_safe("Restoration Complete!")
            self.root.after(0, lambda: messagebox.showinfo("Success", "Game restored successfully."))
            self.root.after(0, self.reset_ui)

        except Exception as e:
            self.log_safe(f"Restore Error: {e}")
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
            self.root.after(0, self.reset_ui)

    # ---------------------------------------------------------
    # PHASE 1: DOWNLOAD & PROCESS (Background Thread)
    # ---------------------------------------------------------
    def process_thread(self):
        abs_input_path = self.get_absolute_path(INPUT_DIR_NAME)
        abs_extracted_path = self.get_absolute_path(EXTRACTED_DIR_NAME)
        abs_output_path = self.get_absolute_path(OUTPUT_DIR_NAME)
        tool_path = self.get_tool_path()

        try:
            # 1. DOWNLOAD
            self.log_safe("Step 1/5: Downloading updates...")
            self.root.after(0, lambda: self.progress.configure(value=10))
            
            zip_path = os.path.join(self.base_dir, "input-pcvr.zip")
            try:
                urllib.request.urlretrieve(REPO_URL, zip_path)
            except Exception as e:
                raise Exception(f"Download failed: {e}")
            
            self.log_safe("Extracting updates...")
            if os.path.exists(abs_input_path):
                shutil.rmtree(abs_input_path)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(self.base_dir)
            
            try: os.remove(zip_path) 
            except: pass
            
            if not os.path.exists(abs_input_path):
                raise Exception(f"Extraction failed: {abs_input_path} not found.")

            # 2. CHECK DATA FOLDER
            if not self.data_folder:
                self.log_safe("Step 2/5: Waiting for folder selection...")
                self.root.after(0, self.prompt_data_folder)
                
                while self.data_folder is None:
                    time.sleep(0.5)
                    if self.cancel_process:
                        self.root.after(0, self.reset_ui)
                        return
            else:
                self.log_safe(f"Using saved Game Folder: {self.data_folder}")

            self.root.after(0, lambda: self.progress.configure(value=30))
            
            manifests_path = os.path.join(self.data_folder, "manifests")
            self.package_name = self.find_package(manifests_path)
            if not self.package_name:
                raise Exception("Could not find valid EchoVR package.")
            
            self.log_safe(f"Target Package: {self.package_name}")

            # 3. EXTRACTION CHECK
            self.log_safe("Step 3/5: Checking game cache...")
            
            has_extracted_files = False
            if os.path.exists(abs_extracted_path):
                if len(os.listdir(abs_extracted_path)) > 0:
                    has_extracted_files = True

            if has_extracted_files:
                self.log_safe(f"Cache found in '{EXTRACTED_DIR_NAME}'. Using existing files.")
                self.root.after(0, lambda: self.progress.configure(value=60))
            else:
                self.log_safe(f"Cache empty. Extracting textures (This takes a while)...")
                if os.path.exists(abs_extracted_path):
                    shutil.rmtree(abs_extracted_path)
                os.makedirs(abs_extracted_path)

                cmd_extract = [
                    tool_path,
                    "-mode", "extract",
                    "-packageName", self.package_name,
                    "-dataDir", self.data_folder,
                    "-outputDir", abs_extracted_path,
                    "-texturesonly"
                ]
                
                res = self.run_hidden_command(cmd_extract)
                if res.returncode != 0:
                    raise Exception(f"Extraction failed: {res.stderr}")
                self.root.after(0, lambda: self.progress.configure(value=60))

            # 4. REPACK
            self.log_safe("Step 4/5: Repacking with new updates...")
            
            if os.path.exists(abs_output_path):
                shutil.rmtree(abs_output_path)
            
            cmd_repack = [
                tool_path,
                "-mode", "replace",
                "-packageName", self.package_name,
                "-dataDir", self.data_folder,
                "-inputDir", abs_input_path,
                "-outputDir", abs_output_path
            ]
            
            res = self.run_hidden_command(cmd_repack)
            if res.returncode != 0:
                print(f"Command failed: {cmd_repack}")
                raise Exception(f"Repacking failed: {res.stderr}")

            self.root.after(0, lambda: self.progress.configure(value=80))

            # 5. TRIGGER INSTALLATION UI
            self.log_safe("Step 5/5: Preparing installation...")
            self.root.after(0, lambda: self.prompt_backup_and_install_ui(abs_output_path, abs_input_path))

        except Exception as e:
            self.log_safe(f"ERROR: {str(e)}")
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
            self.root.after(0, self.reset_ui)

    def find_package(self, manifests_path):
        if not os.path.exists(manifests_path): return None
        common_name = "48037dc70b0ecab2"
        if os.path.exists(os.path.join(manifests_path, common_name)):
            return common_name
        for f in os.listdir(manifests_path):
            if os.path.isfile(os.path.join(manifests_path, f)):
                return f
        return None

    def prompt_data_folder(self):
        messagebox.showinfo("Select Folder", "Please select your EchoVR '_data' folder.\n\nWill look like ready-at-dawn-echo-arena\\_data\\5932408047\\rad15\\win10")
        path = filedialog.askdirectory(title="Select EchoVR _data Folder")
        if path:
            if os.path.exists(os.path.join(path, "manifests")) and os.path.exists(os.path.join(path, "packages")):
                self.data_folder = path
                self.save_config()
            else:
                messagebox.showerror("Invalid Folder", "Selected folder does not contain 'manifests' and 'packages'.")
                self.cancel_process = True
        else:
            self.cancel_process = True

    # ---------------------------------------------------------
    # PHASE 2: UI PROMPT (Main Thread)
    # ---------------------------------------------------------
    def prompt_backup_and_install_ui(self, output_path, input_path):
        do_backup = messagebox.askyesno("Create Backup?", "Do you want to create a backup of your current game files before updating?")
        
        backup_path_selected = None
        if do_backup:
            backup_dir = filedialog.askdirectory(title="Select Backup Location")
            if backup_dir:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                backup_path_selected = os.path.join(backup_dir, f"EchoBackup_{timestamp}")
            else:
                if not messagebox.askyesno("Backup Cancelled", "You cancelled the backup selection.\n\nProceed with update WITHOUT backup?"):
                    self.reset_ui()
                    return

        threading.Thread(target=self.install_worker, args=(output_path, input_path, backup_path_selected)).start()

    # ---------------------------------------------------------
    # PHASE 3: INSTALLATION (Background Thread)
    # ---------------------------------------------------------
    def install_worker(self, output_path, input_path, backup_path):
        try:
            self.log_safe("Finalizing repack... (Waiting 2s)")
            time.sleep(2)

            if backup_path:
                self.log_safe(f"Backing up to: {os.path.basename(backup_path)}...")
                shutil.copytree(self.data_folder, backup_path, ignore_dangling_symlinks=True)
                self.log_safe("Backup complete.")
                
                # SAVE BACKUP LOCATION TO CONFIG
                self.last_backup_folder = backup_path
                self.save_config()

            self.log_safe("Pushing files...")
            
            def safe_install_files(src_dir, dst_dir):
                if not os.path.exists(src_dir):
                    return

                if not os.path.exists(dst_dir):
                    os.makedirs(dst_dir)

                files = os.listdir(src_dir)
                
                for index, filename in enumerate(files):
                    src_file = os.path.join(src_dir, filename)
                    dst_file = os.path.join(dst_dir, filename)
                    
                    if os.path.isfile(src_file):
                        if index % 5 == 0: 
                             self.root.after(0, lambda: self.progress.step(5))
                        
                        if os.path.exists(dst_file):
                            try:
                                os.chmod(dst_file, stat.S_IWRITE)
                            except:
                                pass

                        shutil.copy2(src_file, dst_file)

            safe_install_files(os.path.join(output_path, "packages"), os.path.join(self.data_folder, "packages"))
            safe_install_files(os.path.join(output_path, "manifests"), os.path.join(self.data_folder, "manifests"))

            self.log_safe("Cleaning up temporary files...")
            time.sleep(1)
            if os.path.exists(output_path):
                shutil.rmtree(output_path)

            self.log_safe("Installation Complete!")
            self.root.after(0, lambda: self.prompt_final_cleanup_ui(input_path))

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Install Error", f"Failed during installation:\n{e}"))
            self.root.after(0, self.reset_ui)

    def prompt_final_cleanup_ui(self, input_path):
        self.progress['value'] = 100
        do_cleanup = messagebox.askyesno("Cleanup", "Update complete!\n\nDo you want to delete the downloaded updates (input-pcvr) to save space?")
        
        if do_cleanup:
            self.log("Removing input files...")
            try:
                if os.path.exists(input_path): shutil.rmtree(input_path)
            except: pass
        
        messagebox.showinfo("Success", "EchoVR has been updated successfully!")
        self.reset_ui()

    def reset_ui(self):
        self.action_btn.config(state=tk.NORMAL)
        self.update_restore_button_state()
        self.progress['value'] = 0
        if self.data_folder:
             self.action_btn.config(text="DOWNLOAD LATEST UPDATES (Game Folder Detected)")
        else:
             self.action_btn.config(text="DOWNLOAD LATEST UPDATES")

if __name__ == "__main__":
    root = tk.Tk()
    app = EchoUpdaterApp(root)
    root.mainloop()