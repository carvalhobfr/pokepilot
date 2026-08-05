import asyncio
import base64
import io
import os
import time
import websockets
import json

import gymnasium as gym
from PIL import Image

X_POS_ADDRESS, Y_POS_ADDRESS = 0xD362, 0xD361
MAP_N_ADDRESS = 0xD35E

class StreamWrapper(gym.Wrapper):
    def __init__(self, env, stream_metadata=None):
        super().__init__(env)
        # Point to local visualization server
        self.ws_address = "ws://localhost:3344/broadcast"
        self.stream_metadata = stream_metadata or {}
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.websocket = None
        self.loop.run_until_complete(
            self.establish_wc_connection()
        )
        self.upload_interval = max(
            int(os.getenv("POKEAI_STREAM_INTERVAL", self.stream_metadata.get("stream_interval", 30))),
            1,
        )
        self.battle_interval = max(
            int(os.getenv("POKEAI_BATTLE_STREAM_INTERVAL", 24)),
            1,
        )
        self.frame_format = os.getenv("POKEAI_BATTLE_FRAME_FORMAT", "webp").lower()
        # Publish the first real emulator snapshot on the first step so the
        # dashboard does not look empty during PPO warm-up at 1x speed.
        self.steam_step_counter = self.upload_interval
        self.env = env
        self.coord_list = []
        if hasattr(env, "pyboy"):
            self.emulator = env.pyboy
        elif hasattr(env, "game"):
            self.emulator = env.game
        else:
            raise Exception("Could not find emulator!")

    def step(self, action):

        x_pos = self.emulator.memory[X_POS_ADDRESS]
        y_pos = self.emulator.memory[Y_POS_ADDRESS]
        map_n = self.emulator.memory[MAP_N_ADDRESS]
        self.coord_list.append([x_pos, y_pos, map_n])

        currently_in_battle = self.emulator.memory[0xD057] != 0
        if self.steam_step_counter >= (
            self.battle_interval if currently_in_battle else self.upload_interval
        ):
            metadata = dict(self.stream_metadata)
            metadata["extra"] = f"coords: {len(getattr(self.env, 'seen_coords', {}))}"
            metadata["last_update"] = time.time()

            # Keep the UI driven by the real emulator state instead of the
            # static metadata created when the environment starts.
            try:
                metadata["map_id"] = self.env.read_m(MAP_N_ADDRESS)
                metadata["coords_current"] = [
                    self.env.read_m(X_POS_ADDRESS),
                    self.env.read_m(Y_POS_ADDRESS),
                ]
                metadata["badges"] = bin(self.env.read_m(0xD356)).count("1")
                metadata["pokedex_owned"] = (
                    self.env._pokedex_owned_count()
                    if hasattr(self.env, "_pokedex_owned_count") else 0
                )
                metadata["pokedex_seen"] = (
                    self.env._pokedex_seen_count()
                    if hasattr(self.env, "_pokedex_seen_count") else 0
                )
                metadata["step_count"] = getattr(
                    self.env,
                    "journey_total_steps",
                    getattr(self.env, "step_count", 0),
                )
                metadata["current_task"] = getattr(self.env, "current_task", "")
                metadata["runtime_control"] = {
                    "paused": bool(getattr(self.env, "agent_paused", False)),
                    "speed": float(getattr(self.env, "playback_speed", 1.0)),
                }
                if hasattr(self.env, "get_journey_snapshot"):
                    metadata["journey"] = self.env.get_journey_snapshot()
                if hasattr(self.env, "decision_log_path"):
                    metadata["decision_log"] = str(self.env.decision_log_path)
            except Exception:
                pass
            
            # Inject Party Info if available
            if hasattr(self.env, "get_party_info"):
                try:
                    metadata["party"] = self.env.get_party_info()
                except:
                    metadata["party"] = []
            else:
                metadata["party"] = []

            # Battle state is sampled from emulator memory and sent on every
            # update so the dashboard can open/refresh/close its modal.
            battle_info = None
            if hasattr(self.env, "_get_battle_info"):
                try:
                    battle_info = self.env._get_battle_info()
                except Exception:
                    battle_info = None
            metadata["battle_info"] = battle_info or {"is_battle": False}
            metadata["status"] = "battle" if battle_info else "running"
            metadata["battle_frame"] = (
                self._encode_battle_frame() if battle_info else None
            )
            metadata["build"] = {
                "personality": metadata.get("personality", "Unknown"),
                "starter": metadata.get("starter", "Unknown"),
                "traits": {
                    "meta_score": metadata.get("meta_score", 50),
                    "exploration": metadata.get("exploration", 50),
                    "collector": metadata.get("collector", 50),
                    "mission_focus": metadata.get("mission_focus", 50),
                },
                "policy": "PPO navigation + real RAM telemetry",
                "battle_strategy": "wild capture policy + type effectiveness + move power",
                "capture_controller": metadata.get("capture_controller", "wild_auto"),
                "guide": metadata.get("guide", "Pokemon Blue detonado até Brock"),
                "guide_path": metadata.get("guide_path", "docs/cidades/1/brock.json"),
                "team": metadata["party"],
                "active_pokemon": (
                    battle_info.get("active_pokemon")
                    if battle_info
                    else None
                ),
            }
            
            # Inject Recent Events if available
            recent_events = []
            if hasattr(self.env, "recent_events"):
                try:
                    recent_events = self.env.recent_events
                except Exception as e:
                    print(f"[StreamWrapper] Error getting recent_events: {e}")
            
            # Always include recent_events in metadata (even if empty)
            metadata["recent_events"] = recent_events
            
            self.loop.run_until_complete(
                self.broadcast_ws_message(
                    json.dumps(
                        {
                          "metadata": metadata,
                          "coords": self.coord_list
                        }
                    )
                )
            )
            self.steam_step_counter = 0
            self.coord_list = []

        self.steam_step_counter += 1

        return self.env.step(action)

    def _encode_battle_frame(self):
        """Encode the current PyBoy screen only while the agent is battling."""
        try:
            frame = self.env.render(reduce_res=False)
            if frame.ndim == 3 and frame.shape[2] == 1:
                frame = frame[:, :, 0]
            elif frame.ndim == 3:
                frame = frame[:, :, :3]

            image = Image.fromarray(frame.astype("uint8"))
            output = io.BytesIO()
            if self.frame_format == "png":
                image.save(output, format="PNG", optimize=False, compress_level=1)
                mime = "image/png"
            else:
                # WebP is substantially smaller than base64 PNG for these
                # tiny battle frames and is supported by modern browsers.
                image.save(output, format="WEBP", quality=65, method=0)
                mime = "image/webp"
            encoded = base64.b64encode(output.getvalue()).decode("ascii")
            return f"data:{mime};base64,{encoded}"
        except Exception:
            return None

    async def broadcast_ws_message(self, message):
        if self.websocket is None:
            await self.establish_wc_connection()
        if self.websocket is not None:
            try:
                await self.websocket.send(message)
            except websockets.exceptions.WebSocketException as e:
                self.websocket = None

    async def establish_wc_connection(self):
        try:
            self.websocket = await websockets.connect(self.ws_address)
        except:
            self.websocket = None

    def close(self):
        """Close the optional stream and the emulator without leaking a loop."""
        try:
            if self.websocket is not None:
                self.loop.run_until_complete(self.websocket.close())
        except Exception:
            pass
        finally:
            self.websocket = None
            try:
                self.loop.close()
            except Exception:
                pass
        return self.env.close()
