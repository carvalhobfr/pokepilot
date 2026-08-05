"""
Map Visualization - Live multi-agent display
Adapted from PokemonRedExperiments stream_agent_wrapper.py

Shows all running agents on a 2D map in real-time.
"""

import json
import time
from pathlib import Path
import numpy as np
from datetime import datetime


class MapVisualizer:
    """
    Collects position data from multiple running agents and displays on a shared map.
    """
    
    def __init__(self, output_dir="runs/map_viz"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.agents = {}  # {agent_name: {pos, map_id, color, last_update}}
        self.position_history = []  # List of all positions for trails
        
    def update_agent(self, agent_name, map_id, x, y, color="#00ff00"):
        """Update agent position"""
        timestamp = datetime.now().isoformat()
        
        self.agents[agent_name] = {
            "pos": (x, y),
            "map_id": map_id,
            "color": color,
            "last_update": timestamp
        }
        
        # Add to history for trails
        self.position_history.append({
            "agent": agent_name,
            "map_id": map_id,
            "x": x,
            "y": y,
            "timestamp": timestamp
        })
        
    def get_agents_on_map(self, map_id):
        """Get all agents currently on a specific map"""
        return {
            name: data 
            for name, data in self.agents.items() 
            if data["map_id"] == map_id
        }
    
    def save_snapshot(self, filename="agents_snapshot.json"):
        """Save current state to JSON"""
        filepath = self.output_dir / filename
        with open(filepath, 'w') as f:
            json.dump({
                "agents": self.agents,
                "timestamp": datetime.now().isoformat()
            }, f, indent=2)
        return filepath
    
    def save_history(self, filename="position_history.json"):
        """Save full position history"""
        filepath = self.output_dir / filename
        with open(filepath, 'w') as f:
            json.dump(self.position_history, f, indent=2)
        return filepath
    
    def generate_html_view(self, map_id=0, map_width=20, map_height=18):
        """
        Generate HTML visualization of agents on map.
        Creates a simple grid-based view.
        """
        agents_on_map = self.get_agents_on_map(map_id)
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Pokemon AI - Map {map_id} View</title>
    <style>
        body {{
            background: #1a1a1a;
            color: #fff;
            font-family: 'Courier New', monospace;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 20px;
        }}
        .map-container {{
            background: #2a2a2a;
            border: 3px solid #4a4a4a;
            padding: 20px;
            border-radius: 10px;
        }}
        .map-grid {{
            display: grid;
            grid-template-columns: repeat({map_width}, 30px);
            grid-template-rows: repeat({map_height}, 30px);
            gap: 1px;
            background: #333;
        }}
        .cell {{
            background: #2a2a2a;
            border: 1px solid #444;
            position: relative;
        }}
        .agent {{
            width: 100%;
            height: 100%;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            font-weight: bold;
        }}
        .info {{
            margin-top: 20px;
            padding: 15px;
            background: #2a2a2a;
            border-radius: 5px;
            min-width: 400px;
        }}
        .agent-list {{
            display: flex;
            flex-direction: column;
            gap: 10px;
        }}
        .agent-info {{
            padding: 10px;
            background: #333;
            border-left: 4px solid;
            border-radius: 3px;
        }}
        h1, h2 {{
            text-align: center;
            color: #4CAF50;
        }}
    </style>
</head>
<body>
    <h1>🗺️ Pokemon Blue AI - Map {map_id} (Pallet Town)</h1>
    
    <div class="map-container">
        <div class="map-grid">
"""
        
        # Generate grid
        for y in range(map_height):
            for x in range(map_width):
                # Check if any agent is at this position
                agent_here = None
                for name, data in agents_on_map.items():
                    if data["pos"] == (x, y):
                        agent_here = (name, data)
                        break
                
                if agent_here:
                    name, data = agent_here
                    html += f'<div class="cell"><div class="agent" style="background: {data["color"]};" title="{name}">{name[0]}</div></div>'
                else:
                    html += '<div class="cell"></div>'
        
        html += """
        </div>
    </div>
    
    <div class="info">
        <h2>Active Agents</h2>
        <div class="agent-list">
"""
        
        # Agent list
        for name, data in agents_on_map.items():
            html += f"""
            <div class="agent-info" style="border-color: {data['color']}">
                <strong>{name}</strong><br>
                Position: ({data['pos'][0]}, {data['pos'][1]})<br>
                Map: {data['map_id']}<br>
                Last Update: {data['last_update']}
            </div>
"""
        
        html += """
        </div>
    </div>
    
    <script>
        // Auto-refresh every 2 seconds
        setTimeout(() => location.reload(), 2000);
    </script>
</body>
</html>
"""
        
        filepath = self.output_dir / f"map_{map_id}_view.html"
        with open(filepath, 'w') as f:
            f.write(html)
        
        print(f"Generated map view: file://{filepath.absolute()}")
        return filepath


# Example usage
if __name__ == "__main__":
    viz = MapVisualizer()
    
    # Simulate agent updates
    viz.update_agent("AARON", map_id=0, x=5, y=3, color="#00ff00")
    viz.update_agent("BARON", map_id=0, x=7, y=5, color="#ff0000")
    viz.update_agent("CARON", map_id=0, x=3, y=8, color="#0000ff")
    
    # Generate visualization
    viz.generate_html_view(map_id=0)
    viz.save_snapshot()
    viz.save_history()
    
    print("Map visualization created! Open the HTML file in your browser.")
