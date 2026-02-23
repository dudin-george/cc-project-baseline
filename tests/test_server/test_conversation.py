"""Tests for conversation JSONL persistence."""

from mycroft.shared.protocol import StepId
from mycroft.server.state.conversation import (
    append_message,
    load_messages,
    delete_conversation,
    tail_messages,
)


class TestConversation:
    def test_append_and_load(self, tmp_path):
        append_message(tmp_path, StepId.IDEA_SCOPING, {"role": "user", "content": "hi"})
        msgs = load_messages(tmp_path, StepId.IDEA_SCOPING)
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"

    def test_append_multiple(self, tmp_path):
        for i in range(5):
            append_message(tmp_path, StepId.IDEA_SCOPING, {"role": "user", "content": f"msg {i}"})
        msgs = load_messages(tmp_path, StepId.IDEA_SCOPING)
        assert len(msgs) == 5

    def test_load_empty(self, tmp_path):
        msgs = load_messages(tmp_path, StepId.IDEA_SCOPING)
        assert msgs == []

    def test_separate_steps(self, tmp_path):
        append_message(tmp_path, StepId.IDEA_SCOPING, {"role": "user", "content": "idea"})
        append_message(tmp_path, StepId.USE_CASES_MANUAL, {"role": "user", "content": "uc"})
        assert len(load_messages(tmp_path, StepId.IDEA_SCOPING)) == 1
        assert len(load_messages(tmp_path, StepId.USE_CASES_MANUAL)) == 1

    def test_delete(self, tmp_path):
        append_message(tmp_path, StepId.IDEA_SCOPING, {"role": "user", "content": "hi"})
        delete_conversation(tmp_path, StepId.IDEA_SCOPING)
        assert load_messages(tmp_path, StepId.IDEA_SCOPING) == []

    def test_delete_nonexistent(self, tmp_path):
        # Should not raise
        delete_conversation(tmp_path, StepId.IDEA_SCOPING)

    def test_tail_fewer_than_count(self, tmp_path):
        for i in range(3):
            append_message(tmp_path, StepId.IDEA_SCOPING, {"n": i})
        tail = tail_messages(tmp_path, StepId.IDEA_SCOPING, count=10)
        assert len(tail) == 3

    def test_tail_more_than_count(self, tmp_path):
        for i in range(50):
            append_message(tmp_path, StepId.IDEA_SCOPING, {"n": i})
        tail = tail_messages(tmp_path, StepId.IDEA_SCOPING, count=5)
        assert len(tail) == 5
        assert tail[0]["n"] == 45
        assert tail[-1]["n"] == 49
