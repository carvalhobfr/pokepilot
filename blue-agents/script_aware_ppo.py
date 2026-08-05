"""PPO guardrails for a hybrid scripted/learned environment."""

from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback


class ScriptAwarePPO(PPO):
    """Skip policy updates for rollouts containing overridden actions.

    Stable-Baselines stores the action sampled by PPO, while HybridGymEnv may
    execute a quest, battle, manual or pause action instead. Training on that
    rollout would assign the resulting reward to an action that never happened.
    Until a masked rollout buffer is introduced, skipping the mixed rollout is
    conservative and correct: gameplay continues, but invalid data cannot alter
    the shared brain.
    """

    _rollout_has_overridden_actions = False

    def train(self) -> None:
        skipped = bool(self._rollout_has_overridden_actions)
        self.logger.record("train/scripted_rollout_skipped", int(skipped))
        if skipped:
            return
        super().train()


class ScriptedTransitionGuard(BaseCallback):
    """Mark a rollout whenever an environment executes a non-PPO action."""

    def _on_rollout_start(self) -> None:
        self.model._rollout_has_overridden_actions = False

    def _on_step(self) -> bool:
        infos = self.locals.get("infos") or []
        if any(not info.get("trainable_transition", True) for info in infos):
            self.model._rollout_has_overridden_actions = True
        return True
