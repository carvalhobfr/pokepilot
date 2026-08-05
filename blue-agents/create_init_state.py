from pyboy import PyBoy
import os

def create_init_state():
    print("🎮 Creating new init.state...")
    # Initialize PyBoy with the ROM
    pyboy = PyBoy('../roms/Pokemon Blue.gb', window="headless")
    pyboy.set_emulation_speed(0)
    
    # Run for a few frames to initialize
    for _ in range(100):
        pyboy.tick()
        
    # Save the state
    with open('init.state', 'wb') as f:
        pyboy.save_state(f)
        
    print("✅ init.state created successfully!")
    pyboy.stop()

if __name__ == "__main__":
    create_init_state()
