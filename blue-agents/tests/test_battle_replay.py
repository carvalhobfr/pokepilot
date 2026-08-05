import json
import unittest

from stream_agent_wrapper import REPLAY_MAX_FRAMES, StreamWrapper


class FakeEnv:
    def __init__(self, viewers=1, speed=1.0):
        self.viewer_count = viewers
        self.playback_speed = speed


class ReplayRecordingTests(unittest.TestCase):
    """Nobody can follow four bots fighting live; a replay is the answer.

    Recording costs nothing extra — the frames are the ones the arena already
    encodes — but only while somebody could plausibly watch them.
    """

    def make_wrapper(self, viewers=1, speed=1.0):
        wrapper = StreamWrapper.__new__(StreamWrapper)
        wrapper.env = FakeEnv(viewers, speed)
        wrapper.stream_metadata = {"user": "AARON"}
        wrapper.replay_frames = []
        wrapper.replay_started_at = None
        wrapper.replay_enemy = None
        wrapper.replay_sequence = 0
        wrapper.sent = []
        wrapper.loop = type("FakeLoop", (), {
            "run_until_complete": staticmethod(lambda coro: coro),
        })()
        wrapper.broadcast_ws_message = lambda message: wrapper.sent.append(message)
        return wrapper

    @staticmethod
    def battle(species=41):
        return {"is_battle": True, "enemy_species_id": species}

    def test_a_finished_battle_is_published_once_with_its_frames(self):
        wrapper = self.make_wrapper()
        for index in range(3):
            wrapper._record_replay_frame(self.battle(), f"data:image/webp;base64,{index}")
        self.assertEqual([], wrapper.sent, "nada é enviado no meio da luta")

        wrapper._record_replay_frame(None, None)
        self.assertEqual(1, len(wrapper.sent))
        replay = json.loads(wrapper.sent[0])["battle_replay"]
        self.assertEqual("AARON", replay["agent"])
        self.assertEqual(41, replay["enemy_species_id"])
        self.assertEqual(3, len(replay["frames"]))
        self.assertEqual([], wrapper.replay_frames, "o buffer reinicia para a próxima")

    def test_a_second_flush_with_nothing_buffered_sends_nothing(self):
        wrapper = self.make_wrapper()
        wrapper._record_replay_frame(None, None)
        self.assertEqual([], wrapper.sent)

    def test_with_the_dashboard_closed_nothing_is_recorded(self):
        # Frames encoded for nobody are pure waste; the panel being open is the
        # only honest signal that somebody might watch.
        wrapper = self.make_wrapper(viewers=0)
        wrapper._record_replay_frame(self.battle(), "data:image/webp;base64,x")
        wrapper._record_replay_frame(None, None)
        self.assertEqual([], wrapper.sent)

    def test_above_two_times_speed_nothing_is_recorded(self):
        # At training speed the run produces battles faster than anyone could
        # watch them, and the buffer would only burn memory.
        wrapper = self.make_wrapper(speed=0.0)
        wrapper._record_replay_frame(self.battle(), "data:image/webp;base64,x")
        wrapper._record_replay_frame(None, None)
        self.assertEqual([], wrapper.sent)

    def test_the_buffer_keeps_the_end_of_a_long_battle(self):
        # A fight is decided at the end, so the tail is what a replay must hold.
        wrapper = self.make_wrapper()
        for index in range(REPLAY_MAX_FRAMES + 10):
            wrapper._record_replay_frame(self.battle(), f"frame-{index}")
        wrapper._record_replay_frame(None, None)
        frames = json.loads(wrapper.sent[0])["battle_replay"]["frames"]
        self.assertEqual(REPLAY_MAX_FRAMES, len(frames))
        self.assertEqual(f"frame-{REPLAY_MAX_FRAMES + 9}", frames[-1])

    def test_a_broadcast_failure_never_interrupts_the_journey(self):
        wrapper = self.make_wrapper()

        def explode(_message):
            raise RuntimeError("relay caiu")

        wrapper.broadcast_ws_message = explode
        wrapper._record_replay_frame(self.battle(), "frame")
        wrapper._record_replay_frame(None, None)  # não pode levantar


if __name__ == "__main__":
    unittest.main()
