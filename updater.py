
import os
import sys
import shutil
import time
import subprocess
import datetime
import psutil
import requests
import zipfile
import io

REPO_OWNER = "heklii"
REPO_NAME = "botthehekli-public"
BRANCH = "main"

# Configuration
# Assuming we are running from the bot's root directory
BACKUP_DIR = ".backup"
FILES_TO_BACKUP = ["*.py", "*.json", "assets", ".env"] # Glob patterns handled manually or via simple check
REQUIREMENTS_FILE = "requirements.txt"
MAIN_SCRIPT = "main.py"
BOT_PROCESS_NAME = "python.exe" # Might be too generic, better to pass PID or use marker

def log(msg):
    print(f"[UPDATER] {msg}")

def create_backup():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, timestamp)
    
    if not os.path.exists(backup_path):
        os.makedirs(backup_path)
        
    log(f"Creating backup at {backup_path}...")
    
    # Simple file copy
    for item in os.listdir('.'):
        if item.startswith('.') or item == "__pycache__" or item == "venv" or item == "node_modules":
            continue
            
        # Copy files
        if os.path.isfile(item):
            shutil.copy2(item, backup_path)
        # Copy specific directories
        elif os.path.isdir(item) and item in ['assets', 'data', 'commands_page']:
             shutil.copytree(item, os.path.join(backup_path, item))
             
    log("Backup complete.")

def get_remote_commit_sha():
    """Fetch the latest commit SHA from GitHub API."""
    try:
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits/{BRANCH}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data['sha']
    except Exception as e:
        log(f"Failed to fetch remote SHA: {e}")
        return None

def get_local_version():
    """Get local version (SHA). First check git, then version.txt."""
    # 1. Try Git
    try:
        if os.path.exists(".git"):
            return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except:
        pass
        
    # 2. Try version.txt
    if os.path.exists("version.txt"):
        try:
            with open("version.txt", "r") as f:
                return f.read().strip()
        except:
            pass
            
    return None

def update_from_zip():
    """Download and extract ZIP from GitHub, preserving data."""
    log("Starting ZIP update...")
    try:
        # 1. Download ZIP
        url = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/archive/{BRANCH}.zip"
        log(f"Downloading {url}...")
        resp = requests.get(url)
        resp.raise_for_status()
        
        # 2. Extract to temp
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            # GitHub zips put everything in a root folder e.g. "manual-bot-main/"
            root_folder = z.namelist()[0]
            
            for member in z.namelist():
                # Remove root folder from path
                rel_path = member[len(root_folder):]
                if not rel_path or rel_path.endswith('/'):
                    continue
                    
                # SAFEGUARDS: Skip protected files
                if rel_path == ".env": continue
                if rel_path.startswith("data/"): continue # SKIP DATA FOLDER ENTIRELY to preserve user jsons
                if rel_path == "crash_log.txt": continue
                
                # Write file
                target_path = os.path.join(os.getcwd(), rel_path)
                
                # Ensure dir exists
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                
                with z.open(member) as source, open(target_path, "wb") as target:
                    shutil.copyfileobj(source, target)
                    
        # 3. Write version.txt
        sha = get_remote_commit_sha()
        if sha:
            with open("version.txt", "w") as f:
                f.write(sha)
                
        log("ZIP update finished successfully.")
        return True
        
    except Exception as e:
        log(f"Error during ZIP update: {e}")
        return False

def update_from_git():
    log("Pulling from Git...")
    try:
        # Check if git exists
        subprocess.check_call(["git", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Pull
        result = subprocess.run(["git", "pull"], capture_output=True, text=True)
        if result.returncode == 0:
            log(f"Git Pull Success: {result.stdout.strip()}")
            return True
        else:
            log(f"Git Pull Failed: {result.stderr}")
            return False
            
    except FileNotFoundError:
        log("Error: Git not found in PATH.")
        return False
    except Exception as e:
        log(f"Error during git pull: {e}")
        return False

def check_updates():
    """Check for updates (Git or API)."""
    log("Checking for updates...")
    
    # Method A: Git
    if os.path.exists(".git"):
        try:
            subprocess.check_call(["git", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "fetch"], check=True, capture_output=True)
            result = subprocess.run(["git", "rev-list", "--count", "HEAD..origin/main"], capture_output=True, text=True)
            if result.returncode == 0:
                count = int(result.stdout.strip())
                if count > 0:
                    print(f"UPDATE_AVAILABLE:{count}")
                    return True
                else:
                    print("UPDATE_NONE")
                    return False
        except Exception as e:
            log(f"Git check failed: {e}")
            # Fallthrough to API check
            
    # Method B: API vs Local Version
    remote = get_remote_commit_sha()
    local = get_local_version()
    
    if remote and local and remote != local:
        print("UPDATE_AVAILABLE:unknown")
        return True
    elif remote and not local:
        # No local version? Assume update available or just fresh install.
        print("UPDATE_AVAILABLE:new_install")
        return True
    else:
        print("UPDATE_NONE")
        return False

def check_dependencies():
    log("Checking dependencies...")
    if os.path.exists(REQUIREMENTS_FILE):
        try:
             subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", REQUIREMENTS_FILE])
             log("Dependencies installed/verified.")
        except Exception as e:
            log(f"Error installing dependencies: {e}")

def restart_bot(current_pid):
    log(f"Restarting bot (PID: {current_pid})...")
    
    # 1. Kill the current bot process if provided
    if current_pid:
        try:
            parent = psutil.Process(int(current_pid))
            for child in parent.children(recursive=True):
                child.terminate()
            parent.terminate()
            log("Terminated old process.")
        except psutil.NoSuchProcess:
            log("Old process already gone.")
        except Exception as e:
            log(f"Error terminating process: {e}")
            
    # 2. Exit with specific code to tell batch wrapper to restart
    # We are the updater, running as a subprocess or separate process.
    # If we were called by the bot, the bot is already waiting or dead.
    # If the bot is running via a batch loop that checks exit code, we don't need to spawn new one,
    # we just need to make sure the OLD one exits with the right code (if we were the parent?)
    # BUT, this script is likely called via `subprocess.Popen` from the bot.
    # So if we kill the bot (parent), we might die too unless detached.
    
    # Better approach for Batch Loop:
    # 1. Bot calls Updater.
    # 2. Updater does work.
    # 3. Updater finishes.
    # 4. Bot (waiting for updater) sees success.
    # 5. Bot exits with code 42.
    # 6. Batch loop sees 42 -> restarts.
    
    # So we don't kill here. We just return success.
    log("Update complete. Exiting updater.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", help="PID of the running bot to kill/restart (if not using batch loop mode)")
    parser.add_argument("--git", action="store_true", help="Force Update via Git")
    parser.add_argument("--zip", action="store_true", help="Force Update via ZIP")
    parser.add_argument("--dry-run", action="store_true", help="Test run without changes")
    parser.add_argument("--check", action="store_true", help="Check for updates only")
    
    args = parser.parse_args()
    
    if args.check:
        check_updates()
        sys.exit(0)
    
    if args.dry_run:
        log("DRY RUN: No changes will be made.")
        create_backup()
        sys.exit(0)
        
    try:
        create_backup()
        
        updated = False
        
        # Decide method
        has_git = False
        try:
            subprocess.check_call(["git", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(".git"):
                has_git = True
        except: pass
        
        if args.zip:
            updated = update_from_zip()
        elif args.git or has_git:
            updated = update_from_git()
            if not updated and not has_git:
                log("Git update failed, falling back to ZIP...")
                updated = update_from_zip()
        else:
            # Default fallback
            updated = update_from_zip()
            
        if updated:
            check_dependencies()
            log("Update successful.")
            # We return 0. The calling bot should handle the restart signal.
        else:
            log("Update failed or no changes.")
            sys.exit(1)
            
    except Exception as e:
        log(f"Critical Updater Error: {e}")
        sys.exit(1)
