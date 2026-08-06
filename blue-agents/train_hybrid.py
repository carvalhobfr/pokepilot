"""
Hybrid Training Script - Combines RL + LLM

Runs multiple parallel environments:
- RL handles exploration and navigation
- LLM handles important battles  
- Streams all agents to shared map visualization
- Each agent has unique personality traits
"""

import argparse
import multiprocessing
import os
try:
    multiprocessing.set_start_method('spawn', force=True)
except RuntimeError:
    pass

from pathlib import Path
from hybrid_agent import HybridGymEnv
from stream_agent_wrapper import StreamWrapper
from stable_baselines3.common.utils import set_random_seed
from stable_baselines3.common.callbacks import CheckpointCallback, CallbackList
from script_aware_ppo import ScriptAwarePPO as PPO, ScriptedTransitionGuard
from tensorboard_callback import TensorboardCallback
from rom_identity import require_blue
from journey_roster import load_or_create_roster
from archetypes import archetype_for_slot, get_archetype


def configure_torch(requested_device):
    """Configure PyTorch for a small PPO workload on Apple Silicon."""
    import torch

    thread_count = max(int(os.getenv("POKEAI_TORCH_THREADS", "4")), 1)
    try:
        torch.set_num_threads(thread_count)
        torch.set_num_interop_threads(1)
    except RuntimeError:
        # A worker may already have started; the default remains valid.
        pass

    mps_available = bool(
        getattr(torch.backends, "mps", None)
        and torch.backends.mps.is_available()
    )
    if requested_device == "mps":
        if not mps_available:
            raise RuntimeError(
                "--device mps foi solicitado, mas MPS não está disponível neste runtime"
            )
        return "mps"
    if requested_device == "auto":
        # PPO with small batches is commonly faster on CPU. Opt into MPS only
        # after benchmarking this machine with POKEAI_USE_MPS=1.
        if os.getenv("POKEAI_USE_MPS", "0") == "1" and mps_available:
            return "mps"
        return "cpu"
    return requested_device


def make_hybrid_env(rank, env_conf, seed=0):
    """
    Create hybrid environment with unique personality per agent.
    
    Personality System (4 attributes, 0-100 each):
    - Meta Score: Strategic thinking (100=optimal, 0=chaotic)
    - Exploration: Map discovery drive (100=explorer, 0=focused)
    - Collector: Pokemon catching desire (100=completist, 0=minimalist)
    - Mission Focus: Story progression priority (100=laser-focused, 0=free-spirit)
    
    Balancing Rules:
    - No agent can have all attributes < 30
    - Each agent must have at least 1 attribute > 70
    - Total of 4 attributes must be between 180-280
    """
    
    # Agent names
    agent_names = [
        "AARON", "BARON", "CARON", "DARON",
        "EARON", "FARON", "GARON", "HARON"
    ]
    
    # Color palette
    colors = [
        "#ff6b00",  # AARON - Orange-Red
        "#ff0000",  # BARON - Red  
        "#0000ff",  # CARON - Blue
        "#ffff00",  # DARON - Yellow
        "#ff00ff",  # EARON - Purple
        "#00ffff",  # FARON - Cyan
        "#ff8800",  # GARON - Orange
        "#8800ff",  # HARON - Violet
    ]
    
    def _init():
        import random

        slot = env_conf["slot_roster"][rank]
        agent_name = str(slot["agent_name"])
        identity_index = int(slot.get("identity_index", rank))
        idx = int(slot.get("profile_index", identity_index)) % len(agent_names)

        # A fixed archetype beats a rolled personality when the point is to
        # compare playing styles: the roll once pushed a trainer below every
        # capture threshold, and a whole run looked like a policy bug.
        archetype_name = archetype_for_slot(slot)
        archetype = get_archetype(archetype_name)

        traits = archetype["traits"]
        meta_score = traits["meta_score"]
        exploration = traits["exploration"]
        collector = traits["collector"]
        mission_focus = traits["mission_focus"]

        # Clone config and add personality
        local_conf = env_conf.copy()
        local_conf['agent_name'] = agent_name
        local_conf['starter_preference'] = archetype["starter_preference"]
        local_conf['meta_score'] = meta_score
        local_conf['exploration'] = exploration
        local_conf['collector'] = collector
        local_conf['mission_focus'] = mission_focus
        local_conf['personality'] = archetype["label"]
        local_conf['archetype'] = archetype_name
        local_conf['capture_stance'] = archetype["capture_stance"]
        local_conf['route_role'] = str(slot.get("route_role", "follower"))
        trainer_dir = Path(env_conf["trainer_root"]) / agent_name
        local_conf['trainer_dir'] = str(trainer_dir)
        local_conf['ram_path'] = str(trainer_dir / "current.sav")
        
        # Hard mode bonus for chaos agents (meta < 40)
        is_chaos_mode = meta_score < 40
        local_conf['hard_mode_bonus'] = is_chaos_mode
        
        # Everyone leaves the bedroom together. The staggered start was pure
        # decoration — each bot drives its own emulator, so nothing in Oak's
        # errand or anywhere else depends on it — and it made the four runs
        # incomparable from the first step, which is the opposite of the point.
        # POKEAI_STAGGER_START=1 brings the old random delay back.
        delay_frames = 0
        if os.getenv("POKEAI_STAGGER_START", "0") == "1":
            import random
            delay_frames = random.randint(0, 600)
        local_conf['delay_steps'] = delay_frames
        local_conf['agent_index'] = rank  # Stable runtime slot for ranking/comparison
        local_conf['profile_index'] = idx
        local_conf['identity_index'] = identity_index
        
        if delay_frames:
            print(f"⏱️  Slot {rank}: {agent_name} começa {delay_frames/60:.1f}s depois")
        
        env = StreamWrapper(
            HybridGymEnv(local_conf),
            stream_metadata = {
                "user": agent_name,
                "env_id": rank,
                "color": colors[idx],
                "extra": f"Hybrid RL+LLM Agent #{rank}",
                "starter": ["Bulbasaur", "Charmander", "Squirtle"][archetype["starter_preference"]],
                "hard_mode": is_chaos_mode,
                "meta_score": meta_score,
                "exploration": exploration,
                "collector": collector,
                "mission_focus": mission_focus,
                "personality": archetype["label"],
                "route_role": local_conf['route_role'],
                "guide": "Pokemon Blue: QuestGraph real até Mewtwo",
                "guide_path": "knowledge/quests/main_quest_graph.json",
                "mode": "real_emulator",
                "rom": local_conf.get("rom_identity", {}),
                "save_path": local_conf["ram_path"],
                "capture_controller": "wild_auto_one_attempt",
                "trainer_profile": {
                    "id": agent_name.lower(),
                    "name": agent_name,
                    "personality": archetype["label"],
                    "starter": ["Bulbasaur", "Charmander", "Squirtle"][archetype["starter_preference"]],
                    "traits": {
                        "meta_score": meta_score,
                        "exploration": exploration,
                        "collector": collector,
                        "mission_focus": mission_focus,
                    },
                },
                "sprite_id": str(idx)
            }
        )
        env.reset(seed=(seed + rank))
        return env
    
    set_random_seed(seed)
    return _init


def parse_args():
    parser = argparse.ArgumentParser(description="Train local PokeAI agents with PPO")
    parser.add_argument(
        "--agents",
        type=int,
        default=int(os.getenv("POKEAI_NUM_AGENTS", "2")),
        help="Number of parallel agents (default: 2, safer for fanless Macs)",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=int(os.getenv("POKEAI_EPISODE_STEPS", "4096")),
        help="Rollout length per environment (default: 4096)",
    )
    parser.add_argument(
        "--total-multiplier",
        type=int,
        default=int(os.getenv("POKEAI_TOTAL_MULTIPLIER", "1")),
        help="How many rollout batches to train (default: 1)",
    )
    parser.add_argument(
        "--state",
        choices=["fresh", "pokedex"],
        default=os.getenv("POKEAI_START_STATE", "fresh"),
        help="Start from the real beginning or the prepared Pokedex state",
    )
    parser.add_argument(
        "--rom",
        default=os.getenv("POKEAI_ROM", "PokemonBlue.gb"),
        help="ROM filename inside roms/ or an absolute path (default: PokemonBlue.gb)",
    )
    parser.add_argument(
        "--fresh-model",
        action="store_true",
        help="Ignore existing PPO checkpoints",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume each agent from its autosave/milestone state",
    )
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "mps"],
        default=os.getenv("POKEAI_DEVICE", "auto"),
        help="Torch device; auto keeps PPO on CPU unless POKEAI_USE_MPS=1",
    )
    parser.add_argument(
        "--collect-stats",
        action="store_true",
        help="Keep per-step diagnostic dictionaries (slower, for profiling)",
    )
    parser.add_argument(
        "--rollout-steps",
        type=int,
        default=int(os.getenv("POKEAI_ROLLOUT_STEPS", "128")),
        help="PPO rollout length per environment (default: 128)",
    )
    parser.add_argument(
        "--state-update-interval",
        type=int,
        default=int(os.getenv("POKEAI_STATE_UPDATE_INTERVAL", "250")),
        help="How often to persist JSON agent state (default: 250 steps)",
    )
    parser.add_argument(
        "--verbose-model",
        action="store_true",
        help="Print the full PPO architecture (hidden by default for readable logs)",
    )
    parser.add_argument(
        "--roster",
        default=os.getenv("POKEAI_ROSTER", "tasks/slot_roster.json"),
        help="Persistent runtime-slot roster (default: tasks/slot_roster.json)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    agent_root = Path(__file__).resolve().parent

    # Configuration
    use_wandb_logging = False
    ep_length = max(args.steps, 64)
    sess_id = "v2_repro_runs"
    sess_path = agent_root / "v2_repro_runs"
    sess_path.mkdir(exist_ok=True)
    
    num_cpu = max(args.agents, 1)
    requested_roster = Path(args.roster).expanduser()
    roster_path = (
        requested_roster
        if requested_roster.is_absolute()
        else agent_root / requested_roster
    )
    # Running fewer agents than the roster has is a smaller run, not a smaller
    # roster. Resizing here retired three trainers and handed their slots to
    # freshly named ones — the short validation command in the handoff quietly
    # replaced BARON, CARON and DARON with EARON, FARON and GARON. Growing the
    # roster stays an explicit act (`run_journeys.py --slots`).
    roster = load_or_create_roster(
        roster_path, slot_count=None if roster_path.exists() else num_cpu
    )
    if num_cpu > len(roster["slots"]):
        roster = load_or_create_roster(roster_path, slot_count=num_cpu)
    if num_cpu > len(roster["slots"]):
        raise ValueError(
            f"Requested {num_cpu} agents, but the roster only produced "
            f"{len(roster['slots'])} slots"
        )
    active_slots = roster["slots"][:num_cpu]
    device = configure_torch(args.device)
    state_name = "init.state" if args.state == "fresh" else "has_pokedex_nballs.state"
    state_path = project_root / "states" / state_name
    requested_rom = Path(args.rom).expanduser()
    rom_path = requested_rom if requested_rom.is_absolute() else project_root / "roms" / requested_rom

    if not state_path.exists():
        raise FileNotFoundError(f"Start state not found: {state_path}")
    if not rom_path.exists():
        raise FileNotFoundError(f"ROM not found: {rom_path}")
    rom_identity = require_blue(rom_path)

    env_config = {
        'headless': True,
        'save_final_state': True,
        'early_stop': False,
        'action_freq': 24,
        'init_state': str(state_path),
        'max_steps': ep_length,
        'print_rewards': False,
        'collect_stats': args.collect_stats,
        'save_video': False,
        'fast_video': True,
        'session_path': sess_path,
        'gb_path': str(rom_path),
        'rom_identity': rom_identity.as_dict(),
        'trainer_root': str(project_root / "trainers"),
        'debug': False,
        'reward_scale': 0.5,
        'explore_weight': 0.25,
        'resume_state': args.resume,
        'persist_journey': True,
        'agent_count': num_cpu,
        'slot_roster': active_slots,
        'state_update_interval': max(args.state_update_interval, 1),
        'control_poll_interval': 30,
        'save_interval': 180,
    }
    
    print("="*60)
    print("HYBRID RL+LLM TRAINING - PERSONALITY SYSTEM")
    print("="*60)
    print(f"Agents: {num_cpu}")
    print("Runtime slots: " + ", ".join(
        f"{slot['slot']}={slot['agent_name']}" for slot in active_slots
    ))
    print(f"ROM: {rom_identity.title} ({rom_identity.sha1[:12]}…)")
    print(f"Torch device: {device}")
    print(f"Torch threads: {os.getenv('POKEAI_TORCH_THREADS', '4')}")
    print(f"Episode Length: {ep_length}")
    print(f"Personality Traits: Meta, Exploration, Collector, Mission Focus")
    print(f"Session: {sess_path}")
    print("="*60)
    
    # Create vectorized environment (multiple parallel agents)
    print(f"\nCreating {num_cpu} parallel environments with unique personalities...")
    # Use DummyVecEnv to avoid macOS multiprocessing/numpy crash
    from stable_baselines3.common.vec_env import DummyVecEnv
    env = DummyVecEnv([make_hybrid_env(i, env_config) for i in range(num_cpu)])
    
    # Checkpoint saving
    checkpoint_callback = CheckpointCallback(
        save_freq=2048 * 10, 
        save_path=sess_path,
        name_prefix="hybrid_poke"
    )
    
    callbacks = [
        ScriptedTransitionGuard(),
        checkpoint_callback,
        TensorboardCallback(sess_path),
    ]
    
    # Optional: WandB logging
    if use_wandb_logging:
        import wandb
        from wandb.integration.sb3 import WandbCallback
        wandb.tensorboard.patch(root_logdir=str(sess_path))
        run = wandb.init(
            project="pokemon-hybrid-train",
            id=sess_id,
            name="hybrid-llm-rl-personality",
            config=env_config,
            sync_tensorboard=True,
            monitor_gym=True,
            save_code=True,
        )
        callbacks.append(WandbCallback())
    
    # Auto-load latest checkpoint from this consolidated project.
    latest_policy = sess_path / "latest_policy.zip"
    checkpoints = sorted(sess_path.glob("hybrid_poke_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    resume_candidate = latest_policy if latest_policy.exists() else (checkpoints[0] if checkpoints else None)
    checkpoint_file = str(resume_candidate)[:-4] if resume_candidate and not args.fresh_model else ""
    
    train_steps_batch = min(max(args.rollout_steps, 64), ep_length)
    
    model = None
    if checkpoint_file:
        print(f"\n🔄 Found checkpoint: {checkpoint_file}")
        try:
            model = PPO.load(checkpoint_file, env=env, device=device)
            # PPO.load rebuilds runtime buffers for the supplied VecEnv. Never
            # mutate n_envs fields in place: that changes counters without
            # resizing the backing arrays when the slot count changes.
            train_steps_batch = model.n_steps
        except Exception as exc:
            print(f"⚠️ Existing checkpoint is incompatible with the corrected observation space: {exc}")
            print("✨ Starting a fresh policy.")

    if model is None:
        print("\n✨ Starting FRESH training session (no checkpoints found)")
        model = PPO(
            "MultiInputPolicy",
            env,
            verbose=1,
            n_steps=train_steps_batch,
            batch_size=min(512, train_steps_batch * num_cpu),
            n_epochs=1,
            gamma=0.997,
            ent_coef=0.01,
            tensorboard_log=sess_path,
            policy_kwargs={"share_features_extractor": True},
            device=device,
        )
    
    if args.verbose_model:
        print("\nModel Architecture:")
        print(model.policy)
    
    # Train!
    total_steps = ep_length * num_cpu * max(args.total_multiplier, 1)
    print(f"\nStarting training for {total_steps:,} total steps...")
    print("View progress: tensorboard --logdir", sess_path)
    print("\n" + "="*60)
    
    interrupted = False
    try:
        model.learn(
            total_timesteps=total_steps,
            callback=CallbackList(callbacks),
            tb_log_name="hybrid_poke_ppo"
        )
    except KeyboardInterrupt:
        interrupted = True
        print("\n🛑 Training interrupted; persisting policy and emulator slots...")
    finally:
        try:
            model.save(sess_path / "latest_policy")
            print(f"\n💾 Latest shared policy: {latest_policy}")
        finally:
            env.close()

    print("\n" + "="*60)
    print("Training stopped safely." if interrupted else "Training complete!")
    print("="*60)
    
    if use_wandb_logging:
        run.finish()
