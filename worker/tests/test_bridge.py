import asyncio

from marvin.adapters.permissions import PermissionBroker
from marvin.bridge import Segment, Timeline, TurnAssembler, WakeDetector, render_prompt


def seg(speaker, text, start, dur=2.0, final=True):
    return Segment(start=start, end=start + dur, speaker=speaker, text=text, final=final)


class TestWakeDetector:
    d = WakeDetector()

    def test_name_at_start(self):
        m = self.d.detect("Marvin, how does the retry backoff work?")
        assert m and m.position == "start" and m.question == "how does the retry backoff work"

    def test_name_at_end(self):
        m = self.d.detect("what do you think about that Marvin")
        assert m and m.position == "end" and m.question == "what do you think about that"

    def test_stt_misspellings(self):
        for spelling in ("Marvyn", "Marven", "marvin", "Marvel"):
            assert self.d.detect(f"{spelling} run the tests") is not None

    def test_fuzzy(self):
        assert self.d.detect("Marvinn, run the tests") is not None

    def test_third_person_mid_sentence_does_not_trigger(self):
        assert self.d.detect("I think we should ask Marvin about it after the meeting is over") is None

    def test_plain_talk_does_not_trigger(self):
        assert self.d.detect("the retry logic lives in the client module") is None
        assert self.d.detect("") is None


class TestTimelineAndTurns:
    def test_out_of_order_insert_and_render(self):
        tl = Timeline(t0=0.0)
        tl.add(seg("Gil", "second", 5.0))
        tl.add(seg("Ana", "first", 1.0))
        assert [s.text for s in tl.all()] == ["first", "second"]
        assert tl.render(tl.all()) == "[00:01] Ana: first\n[00:05] Gil: second"

    def test_interim_segments_are_ignored(self):
        tl = Timeline(t0=0.0)
        tl.add(seg("Gil", "partial", 1.0, final=False))
        assert len(tl) == 0

    def test_turn_carries_context_since_last_turn(self):
        tl = Timeline(t0=0.0)
        ta = TurnAssembler(tl)
        assert ta.on_segment(seg("Ana", "the retries are exponential", 1.0)) is None
        assert ta.on_segment(seg("Gil", "but capped at five I think", 4.0)) is None
        turn = ta.on_segment(seg("Gil", "Marvin is that right", 7.0))
        assert turn is not None
        assert turn.asked_by == "Gil"
        assert [s.text for s in turn.context] == ["the retries are exponential", "but capped at five I think"]
        # next turn only sees what came after
        ta.on_segment(seg("Ana", "ok next topic", 12.0))
        turn2 = ta.on_segment(seg("Ana", "Marvin run the tests", 15.0))
        assert [s.text for s in turn2.context] == ["ok next topic"]

    def test_long_silence_is_not_truncated(self):
        # An hour of talk without the wake word still reaches the agent whole; a cap is opt-in.
        tl = Timeline(t0=0.0)
        ta = TurnAssembler(tl)
        ta.on_segment(seg("Ana", "hour-old remark", 10.0))
        ta.on_segment(seg("Gil", "recent remark", 3600.0))
        turn = ta.on_segment(seg("Gil", "Marvin what do you think", 3605.0))
        assert [s.text for s in turn.context] == ["hour-old remark", "recent remark"]
        capped = TurnAssembler(Timeline(t0=0.0), max_context_s=60)
        capped.on_segment(seg("Ana", "hour-old remark", 10.0))
        capped.on_segment(seg("Gil", "recent remark", 3600.0))
        turn = capped.on_segment(seg("Gil", "Marvin what do you think", 3605.0))
        assert [s.text for s in turn.context] == ["recent remark"]

    def test_name_alone_waits_for_the_rest(self):
        # Silero VAD often ends the utterance after "Marvin,"; that must not become a turn.
        tl = Timeline(t0=0.0)
        ta = TurnAssembler(tl)
        assert ta.on_segment(seg("Gil", "Marvin.", 1.0, dur=0.4)) is None
        turn = ta.on_segment(seg("Gil", "what does this repo do", 1.8))
        assert turn is not None
        assert turn.asked_by == "Gil"
        assert turn.question == "what does this repo do"
        assert [s.text for s in turn.context] == ["Marvin."]

    def test_name_alone_expires(self):
        tl = Timeline(t0=0.0)
        ta = TurnAssembler(tl, wake_hold_s=2.0)
        assert ta.on_segment(seg("Gil", "Marvin.", 1.0, dur=0.4)) is None
        assert ta.on_segment(seg("Gil", "what about this", 10.0)) is None

    def test_other_speaker_cancels_name_hold(self):
        tl = Timeline(t0=0.0)
        ta = TurnAssembler(tl)
        assert ta.on_segment(seg("Gil", "Marvin.", 1.0, dur=0.4)) is None
        assert ta.on_segment(seg("Ana", "meanwhile the tests failed", 1.6)) is None
        assert ta.on_segment(seg("Gil", "what about this", 2.0)) is None

    def test_same_utterance_still_strips_the_name(self):
        tl = Timeline(t0=0.0)
        ta = TurnAssembler(tl)
        turn = ta.on_segment(seg("Gil", "Marvin, how does the retry backoff work?", 1.0))
        assert turn is not None
        assert turn.question == "how does the retry backoff work"

    def test_prompt_rendering(self):
        tl = Timeline(t0=0.0)
        ta = TurnAssembler(tl)
        ta.on_segment(seg("Ana", "the retries are exponential", 1.0))
        turn = ta.on_segment(seg("Gil", "Marvin is that right", 7.0))
        prompt = render_prompt(turn, tl)
        assert "[00:01] Ana: the retries are exponential" in prompt
        assert 'Gil is now addressing you: "is that right"' in prompt


class TestPermissionBroker:
    def test_ask_and_resolve(self):
        async def run():
            seen = []

            async def notify(req):
                seen.append(req)

            broker = PermissionBroker(notify, timeout_s=5)
            task = asyncio.create_task(broker.ask("Bash", {"command": "ls"}))
            await asyncio.sleep(0)
            assert len(seen) == 1 and broker.pending[0].tool == "Bash"
            assert broker.resolve(seen[0].id, True)
            assert await task is True
            assert broker.pending == []
            assert broker.resolve("nope", True) is False

        asyncio.run(run())

    def test_timeout_denies(self):
        async def run():
            async def notify(req):
                pass

            broker = PermissionBroker(notify, timeout_s=0.01)
            assert await broker.ask("Bash", {"command": "rm -rf /"}) is False

        asyncio.run(run())
