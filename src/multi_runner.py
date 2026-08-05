import subprocess
import time
import os
from datetime import datetime

def main():
    # Create a timestamped directory for this batch of runs
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_dir = os.path.abspath(f"runs/{timestamp}")
    os.makedirs(save_dir, exist_ok=True)
    
    print(f"Starting multi-simulation run. Saving to: {save_dir}")
    
    # Define runs
    runs = [
        {"name": "AARON", "log": f"{save_dir}/aaron.log"},
        {"name": "BARON", "log": f"{save_dir}/baron.log"}
    ]
    
    processes = []
    
    for run in runs:
        print(f"Launching agent {run['name']}...")
        
        # Command to run main.py
        cmd = [
            "python3", "-m", "src.main",
            "--agent", "scripted",
            "--name", run["name"],
            "--save-dir", save_dir,
            "--headless" # Run headless to avoid window conflicts
        ]
        
        # Open log file
        log_file = open(run["log"], "w")
        
        # Start process
        p = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
        processes.append({"process": p, "log_file": log_file, "name": run["name"]})
        
        time.sleep(2) # Stagger starts slightly
        
    print("All agents running. Monitoring...")
    
    try:
        while True:
            all_done = True
            for p_data in processes:
                if p_data["process"].poll() is None:
                    all_done = False
                else:
                    print(f"Agent {p_data['name']} finished with code {p_data['process'].returncode}")
            
            if all_done:
                break
                
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\nStopping all agents...")
        for p_data in processes:
            p_data["process"].terminate()
            
    finally:
        # Close log files
        for p_data in processes:
            p_data["log_file"].close()
            
    print("Multi-simulation finished.")

if __name__ == "__main__":
    main()
