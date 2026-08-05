import argparse
import os
import sys
from dotenv import load_dotenv
from src.emulator import Emulator
from src.agent import RandomAgent

load_dotenv()

def main():
    parser = argparse.ArgumentParser(description="PokeAI Blue - AI playing Pokemon Blue")
    parser.add_argument("--rom", type=str, default="roms/Pokemon Blue.gb", help="Path to the ROM file")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    parser.add_argument("--frames", type=int, default=0, help="Number of frames to run (0 for infinite)")
    parser.add_argument("--agent", type=str, default="random", choices=["random", "scripted"], help="Agent type to use")
    parser.add_argument("--name", type=str, default="AARON", help="Player name")
    parser.add_argument("--save-dir", type=str, default="runs", help="Directory to save states")
    parser.add_argument("--load-state", type=str, default=None, help="Load from checkpoint state file")
    
    args = parser.parse_args()

    if not os.path.exists(args.rom):
        print(f"Error: ROM file not found at {args.rom}")
        print("Please place 'Pokemon Blue.gb' in the 'roms' directory or specify the path with --rom")
        sys.exit(1)
        
    # Create save directory if it doesn't exist
    os.makedirs(args.save_dir, exist_ok=True)

    print(f"Starting PokeAI with ROM: {args.rom}")
    print(f"Agent: {args.agent}, Name: {args.name}")
    
    # Initialize Emulator
    emulator = Emulator(args.rom, headless=args.headless)
    
    # Load checkpoint if specified
    if args.load_state:
        if os.path.exists(args.load_state):
            print(f"Loading checkpoint from: {args.load_state}")
            emulator.load_state(args.load_state)
        else:
            print(f"Warning: Checkpoint file not found: {args.load_state}")
            print("Starting from beginning...")
    
    # Initialize Agent
    if args.agent == "scripted":
        from src.scripted_agent import ScriptedAgent
        # TODO: Make this path configurable or smarter
        agent = ScriptedAgent("docs/cidades/1/badge1.json", emulator=emulator, player_name=args.name, save_dir=args.save_dir)
    else:
        agent = RandomAgent()
    
    try:
        frame_count = 0
        while args.frames == 0 or frame_count < args.frames:
            # Get current state
            state = emulator.get_state()
            
            # Agent decides action
            action = agent.get_action(state)
            
            # Emulator performs action
            emulator.step(action)
            
            frame_count += 1
            
            if frame_count % 600 == 0: # Print every ~10 seconds
                print(f"Running... Frame: {frame_count}")
                if args.agent == "scripted":
                     # Print some memory info to prove it works
                     pos = state["game_state"]["pos"]
                     print(f"Player Pos: {pos}")
                
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        emulator.stop()

if __name__ == "__main__":
    main()
