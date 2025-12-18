import os
import sys
import time
import subprocess
from core.installs.ffmpeg_installer import check_and_install_ffmpeg

def main():
    check_and_install_ffmpeg()

    while True:
        print("\n[RUNNER] Starting main.py...")
        process = subprocess.Popen([sys.executable, "main.py"])
        
        try:
            process.wait()
        except KeyboardInterrupt:
            print("\n[RUNNER] Stopping bot...")
            process.terminate()
            
            try:
                subprocess.run("taskkill /F /T /PID " + str(process.pid), shell=True, stderr=subprocess.DEVNULL)
            except: pass
            
            break

        exit_code = process.returncode
        print("[RUNNER] Bot crashed (code " + str(exit_code) + "). Restarting in 5 sec...")
        time.sleep(5)

if __name__ == "__main__":
    main()