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

"""Compact, conversation-only copies of Neuro SAN thinking logs."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import BinaryIO

from neuro_san.client.thinking_file_message_processor import ThinkingFileMessageProcessor
from neuro_san.message.types.chat_message_type import ChatMessageType

# ThinkingFileMessageProcessor emits headers such as:
#   [SYSTEM] @ 2026-09-19 06:23:17:
#   [AGENT_TOOL_RESULT (result from state_read)] @ 2026-09-19 06:23:18:
# Require the timestamp as well as the bracketed type so prompt content that merely
# mentions "[SYSTEM]" is not mistaken for a log boundary.
_MESSAGE_HEADER = re.compile(
    rb"^\[(?P<type>[A-Z_]+)(?:[^\]]*)\] @ "
    rb"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}:\r?\n$"
)
_CONVERSATION_MESSAGE_TYPES = frozenset({ChatMessageType.HUMAN, ChatMessageType.AI})
_CONVERSATION_HEADER_TYPES = frozenset({b"HUMAN", b"AI"})


class ConversationThinkingFileMessageProcessor(ThinkingFileMessageProcessor):
    """Write only the non-redundant HUMAN and AI sides of conversations."""

    def process_message(self, chat_message_dict: dict[str, Any], message_type: ChatMessageType):
        """Ignore system, framework, tool, accounting, and progress records."""
        normalized_type = ChatMessageType.from_response_type(message_type)
        if normalized_type not in _CONVERSATION_MESSAGE_TYPES:
            return
        super().process_message(chat_message_dict, normalized_type)


@dataclass(frozen=True)
class ConversionStats:
    """Summary returned after converting a thinking-log directory."""

    files: int = 0
    system_messages_removed: int = 0
    other_messages_removed: int = 0
    conversation_messages_written: int = 0
    bytes_read: int = 0
    bytes_written: int = 0

    def __add__(self, other: "ConversionStats") -> "ConversionStats":
        return ConversionStats(
            files=self.files + other.files,
            system_messages_removed=self.system_messages_removed + other.system_messages_removed,
            other_messages_removed=self.other_messages_removed + other.other_messages_removed,
            conversation_messages_written=(self.conversation_messages_written + other.conversation_messages_written),
            bytes_read=self.bytes_read + other.bytes_read,
            bytes_written=self.bytes_written + other.bytes_written,
        )


def filter_thinking_stream(source: BinaryIO, destination: BinaryIO) -> ConversionStats:
    """Copy only complete ``[HUMAN]`` and ``[AI]`` message blocks.

    Processing is line-oriented and bounded by the longest individual line, which
    keeps conversion practical for multi-gigabyte transcript directories.
    """
    keep_message = False
    system_messages_removed = 0
    other_messages_removed = 0
    conversation_messages_written = 0
    bytes_read = 0
    bytes_written = 0
    preamble = bytearray()
    found_first_header = False
    wrote_preamble = False

    for line in source:
        bytes_read += len(line)
        header = _MESSAGE_HEADER.match(line)
        if header is not None:
            found_first_header = True
            header_type = header.group("type")
            keep_message = header_type in _CONVERSATION_HEADER_TYPES
            if keep_message:
                conversation_messages_written += 1
                if not wrote_preamble:
                    destination.write(preamble)
                    bytes_written += len(preamble)
                    wrote_preamble = True
            elif header_type == b"SYSTEM":
                system_messages_removed += 1
            else:
                other_messages_removed += 1
        elif not found_first_header:
            preamble.extend(line)
            continue

        if keep_message:
            destination.write(line)
            bytes_written += len(line)

    return ConversionStats(
        files=int(conversation_messages_written > 0),
        system_messages_removed=system_messages_removed,
        other_messages_removed=other_messages_removed,
        conversation_messages_written=conversation_messages_written,
        bytes_read=bytes_read,
        bytes_written=bytes_written,
    )


def convert_thinking_directory(
    source_dir: Path | str,
    destination_dir: Path | str,
    *,
    replace: bool = False,
) -> ConversionStats:
    """Create an atomic, conversation-only copy of a thinking-log directory.

    The source is never modified. Existing destinations are refused unless
    ``replace`` is explicitly enabled; replacement still builds the new tree
    completely before swapping it into place.
    """
    source = Path(source_dir).resolve()
    destination = Path(destination_dir).resolve()

    if not source.is_dir():
        raise ValueError(f"Thinking-log source is not a directory: {source}")
    if destination.exists() and not replace:
        raise FileExistsError(f"Destination already exists: {destination}")
    if destination == source or source in destination.parents:
        raise ValueError("Destination must be outside the source thinking-log directory")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    totals = ConversionStats()

    try:
        for source_path in sorted(source.rglob("*")):
            relative_path = source_path.relative_to(source)
            destination_path = temporary / relative_path

            if source_path.is_dir():
                destination_path.mkdir(parents=True, exist_ok=True)
                continue
            if not source_path.is_file():
                raise ValueError(f"Unsupported non-file entry in thinking directory: {source_path}")

            destination_path.parent.mkdir(parents=True, exist_ok=True)
            with source_path.open("rb") as source_file, destination_path.open("wb") as destination_file:
                file_stats = filter_thinking_stream(source_file, destination_file)
                totals += file_stats
            if file_stats.files == 0:
                destination_path.unlink()
                continue
            shutil.copystat(source_path, destination_path)

        if destination.exists():
            backup = Path(tempfile.mkdtemp(prefix=f".{destination.name}.old.", dir=destination.parent))
            backup.rmdir()
            os.replace(destination, backup)
            try:
                os.replace(temporary, destination)
            except BaseException:
                os.replace(backup, destination)
                raise
            shutil.rmtree(backup)
        else:
            os.replace(temporary, destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    return totals
