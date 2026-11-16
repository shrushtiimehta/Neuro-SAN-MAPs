# Copyright © 2025-2026 Cognizant Technology Solutions Corp, www.cognizant.com.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# END COPYRIGHT

from pathlib import Path

import pytest
from neuro_san.message.types.chat_message_type import ChatMessageType

from neuro_san_studio.conversation_logging import ConversationThinkingFileMessageProcessor
from neuro_san_studio.conversation_logging import convert_thinking_directory


def _message(message_type: str, text: str) -> dict:
    return {
        "type": message_type,
        "text": text,
        "origin": [{"tool": "planner", "instantiation_index": 1}],
    }


def test_live_processor_omits_system_messages(tmp_path: Path) -> None:
    output_dir = tmp_path / "thinking-dir-small"
    output_dir.mkdir()
    processor = ConversationThinkingFileMessageProcessor(str(tmp_path / "unused.txt"), str(output_dir))

    processor.process_message(_message("SYSTEM", "private instructions"), ChatMessageType.SYSTEM)
    processor.process_message(_message("AGENT", "duplicate tool chatter"), ChatMessageType.AGENT)
    processor.process_message(_message("HUMAN", "please inspect the run"), ChatMessageType.HUMAN)
    processor.process_message(_message("AI", "the run looks healthy"), ChatMessageType.AI)

    transcript = (output_dir / "planner").read_text(encoding="utf-8")
    assert "private instructions" not in transcript
    assert "duplicate tool chatter" not in transcript
    assert "[SYSTEM]" not in transcript
    assert "[AGENT]" not in transcript
    assert "[HUMAN]" in transcript
    assert "please inspect the run" in transcript
    assert "[AI]" in transcript
    assert "the run looks healthy" in transcript


def test_directory_conversion_removes_only_system_blocks(tmp_path: Path) -> None:
    source = tmp_path / "thinking_dir"
    destination = tmp_path / "thinking-dir-small"
    source.mkdir()
    original = """Agent: planner

[SYSTEM] @ 2026-09-21 12:00:00:
private instructions
with multiple lines

[HUMAN] @ 2026-09-21 12:00:01:
hello; the literal text [SYSTEM] remains when it is conversation data

[AGENT_TOOL_RESULT (result from status)] @ 2026-09-21 12:00:02:
duplicate tool output

[AGENT_FRAMEWORK] @ 2026-09-21 12:00:02:
duplicate AI answer and accumulated chat_context

[AI] @ 2026-09-21 12:00:03:
goodbye
"""
    (source / "planner").write_text(original, encoding="utf-8")

    stats = convert_thinking_directory(source, destination)

    converted = (destination / "planner").read_text(encoding="utf-8")
    assert (source / "planner").read_text(encoding="utf-8") == original
    assert "private instructions" not in converted
    assert "[SYSTEM] @" not in converted
    assert "[HUMAN]" in converted
    assert "[AGENT_TOOL_RESULT" not in converted
    assert "[AGENT_FRAMEWORK" not in converted
    assert "duplicate tool output" not in converted
    assert "the literal text [SYSTEM] remains" in converted
    assert "[AI]" in converted
    assert stats.files == 1
    assert stats.system_messages_removed == 1
    assert stats.other_messages_removed == 2
    assert stats.conversation_messages_written == 2
    assert stats.bytes_written < stats.bytes_read


def test_directory_conversion_omits_tool_only_files(tmp_path: Path) -> None:
    source = tmp_path / "thinking_dir"
    destination = tmp_path / "thinking-dir-small"
    source.mkdir()
    (source / "planner.state_read").write_text(
        """Agent: planner.state_read

[AGENT] @ 2026-09-21 12:00:00:
Received arguments
""",
        encoding="utf-8",
    )

    stats = convert_thinking_directory(source, destination)

    assert list(destination.iterdir()) == []
    assert stats.files == 0
    assert stats.other_messages_removed == 1


def test_directory_conversion_refuses_existing_destination(tmp_path: Path) -> None:
    source = tmp_path / "thinking_dir"
    destination = tmp_path / "thinking-dir-small"
    source.mkdir()
    destination.mkdir()

    with pytest.raises(FileExistsError):
        convert_thinking_directory(source, destination)


def test_directory_conversion_can_atomically_replace_destination(tmp_path: Path) -> None:
    source = tmp_path / "thinking_dir"
    destination = tmp_path / "thinking-dir-small"
    source.mkdir()
    destination.mkdir()
    (destination / "stale").write_text("old duplicate-heavy output", encoding="utf-8")
    (source / "planner").write_text(
        """Agent: planner

[HUMAN] @ 2026-09-21 12:00:00:
new conversation
""",
        encoding="utf-8",
    )

    convert_thinking_directory(source, destination, replace=True)

    assert not (destination / "stale").exists()
    assert "new conversation" in (destination / "planner").read_text(encoding="utf-8")
