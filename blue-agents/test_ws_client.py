#!/usr/bin/env python3
"""
Quick test script to check if agents are broadcasting data to the WebSocket
"""
import asyncio
import websockets
import json

async def test_ws():
    uri = "ws://localhost:3344/receive"
    print(f"🔌 Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected! Waiting for messages...")
            
            # Listen for 10 messages
            for i in range(10):
                message = await websocket.recv()
                data = json.loads(message)
                
                if 'metadata' in data and 'user' in data.get('metadata', {}):
                    agent = data['metadata']['user']
                    coords = data.get('coords', [])
                    events = data.get('metadata', {}).get('recent_events', [])
                    
                    print(f"\n📡 Message {i+1}:")
                    print(f"   Agent: {agent}")
                    print(f"   Coords: {len(coords)} points")
                    if coords:
                        print(f"   Last position: {coords[-1]}")
                    print(f"   Events: {len(events)} - {[e.get('type') for e in events]}")
                else:
                    print(f"\n📊 Stats message: {list(data.keys())}")
                    
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_ws())
