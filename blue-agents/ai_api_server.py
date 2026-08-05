"""
Simple HTTP API for on-demand AI strategy consultation
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import json
from pathlib import Path
from ai_strategy import get_ai_strategy

app = Flask(__name__)
CORS(app)  # Allow requests from React dashboard

@app.route('/api/ask-ai', methods=['POST'])
def ask_ai():
    """
    Endpoint for AI strategy consultation
    
    POST body:
    {
        "agent_name": "GARON",
        "agent_state": {
            "map_id": 40,
            "badges": 0,
            "party": [...],
            ...
        }
    }
    """
    try:
        data = request.get_json()
        agent_name = data.get('agent_name')
        agent_state =data.get('agent_state', {})
        
        if not agent_name:
            return jsonify({'error': 'Missing agent_name'}), 400
        
        print(f"🤖 AI Strategy Request for: {agent_name}")
        
        # Call AI strategy function
        response = get_ai_strategy(agent_name, agent_state)
        
        return jsonify({
            'success': True,
            'agent_name': agent_name,
            'strategy': response
        })
    
    except Exception as e:
        print(f"❌ Error in /api/ask-ai: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

@app.route('/api/reset-agent/<agent_name>', methods=['POST'])
def reset_agent(agent_name):
    """
    Reset an agent by deleting its save file
    """
    try:
        import os
        import glob
        
        # Find and delete all save files for this agent
        # Server runs in blue-agents/, so files are in current directory
        save_pattern = f"{agent_name}*.state"
        deleted = []
        
        for file_path in glob.glob(save_pattern):
            os.remove(file_path)
            deleted.append(file_path)
        
        print(f"🗑️ Reset {agent_name}: Deleted {len(deleted)} save files")
        
        return jsonify({
            'success': True,
            'agent_name': agent_name,
            'deleted_files': deleted
        })
    
    except Exception as e:
        print(f"❌ Error in /api/reset-agent: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/list-checkpoints/<agent_name>', methods=['GET'])
def list_checkpoints(agent_name):
    """
    List all available checkpoint files for an agent
    """
    try:
        import glob
        import os
        
        checkpoints = []
        # Server runs in blue-agents/, so files are in current directory
        save_pattern = f"{agent_name}*.state"
        
        for file_path in glob.glob(save_pattern):
            file_stat = os.stat(file_path)
            checkpoints.append({
                'file': os.path.basename(file_path),
                'size': file_stat.st_size,
                'modified': file_stat.st_mtime
            })
        
        # Sort by modification time (newest first)
        checkpoints.sort(key=lambda x: x['modified'], reverse=True)
        
        return jsonify({
            'success': True,
            'agent_name': agent_name,
            'checkpoints': checkpoints
        })
    
    except Exception as e:
        print(f"❌ Error in /api/list-checkpoints: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("🚀 Starting AI Strategy API Server on http://localhost:5002")
    app.run(host='0.0.0.0', port=5002, debug=False)
