#!/usr/bin/env python3
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

"""Convert existing thinking logs into compact, conversation-only transcripts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make direct ``python scripts/convert_thinking_logs.py`` execution work in the
# same way as ``python -m scripts.convert_thinking_logs``.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from neuro_san_studio.conversation_logging import convert_thinking_directory  # noqa: E402


def _human_size(byte_count: int) -> str:
    value = float(byte_count)
    for suffix in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024.0 or suffix == "TiB":
            return f"{value:.1f} {suffix}"
        value /= 1024.0
    raise AssertionError("unreachable")


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy only HUMAN and AI turns from Neuro SAN thinking logs.")
    parser.add_argument("source", nargs="?", type=Path, default=Path("logs/thinking_dir"))
    parser.add_argument("destination", nargs="?", type=Path, default=Path("logs/thinking-dir-small"))
    parser.add_argument(
        "--replace",
        action="store_true",
        help="atomically replace the destination if it already exists",
    )
    args = parser.parse_args()

    stats = convert_thinking_directory(args.source, args.destination, replace=args.replace)
    print(
        f"Wrote {stats.conversation_messages_written} conversation turns "
        f"across {stats.files} files to {args.destination}; "
        f"omitted {stats.system_messages_removed} system and "
        f"{stats.other_messages_removed} redundant/non-conversation messages; "
        f"size {_human_size(stats.bytes_read)} -> {_human_size(stats.bytes_written)}"
    )


if __name__ == "__main__":
    main()
