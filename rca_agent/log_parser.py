"""Parse server exception tracebacks from application logs."""
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class Frame:
    """Represents a single stack frame from a traceback."""

    file: str
    line: int
    func: str
    code: str


@dataclass
class ServerTrace:
    """Represents an unhandled HTTP exception and its full traceback."""

    method: str
    path: str
    exception: str
    frames: List[Frame]
    raw: str

    def app_frame(self, repo_dir: Path | str) -> Optional[Frame]:
        """Return the innermost frame whose realpath lies inside the repo directory."""
        repo_real = os.path.realpath(str(repo_dir))
        for frame in reversed(self.frames):
            frame_real = os.path.realpath(os.path.abspath(frame.file))
            try:
                if os.path.commonpath([repo_real, frame_real]) == repo_real:
                    return frame
            except ValueError:
                continue
        return None


def parse_server_log(text: str) -> List[ServerTrace]:
    """Parse application log text and extract all ServerTrace objects."""
    traces: List[ServerTrace] = []
    lines = text.splitlines()
    i = 0
    n = len(lines)

    header_pattern = re.compile(r"Exception on (\S+) \[([A-Z]+)\]")
    frame_pattern = re.compile(r'^\s*File "([^"]+)", line (\d+), in (.*)$')

    while i < n:
        line = lines[i]
        match = header_pattern.search(line)
        if match:
            path = match.group(1)
            method = match.group(2)
            raw_lines = [line]
            frames: List[Frame] = []
            exception_str = ""

            i += 1
            while i < n and "Traceback" not in lines[i]:
                raw_lines.append(lines[i])
                i += 1

            if i < n and "Traceback" in lines[i]:
                raw_lines.append(lines[i])
                i += 1

            while i < n:
                curr = lines[i]
                if not curr.strip():
                    raw_lines.append(curr)
                    i += 1
                    continue

                if not curr.startswith(" ") and not curr.startswith("\t"):
                    exception_str = curr.strip()
                    raw_lines.append(curr)
                    i += 1
                    break

                raw_lines.append(curr)
                f_match = frame_pattern.match(curr)
                if f_match:
                    f_file = f_match.group(1)
                    f_line = int(f_match.group(2))
                    f_func = f_match.group(3).strip()
                    code_line = ""

                    i += 1
                    while i < n and lines[i].startswith(" ") and not frame_pattern.match(lines[i]):
                        candidate = lines[i]
                        raw_lines.append(candidate)
                        stripped = candidate.strip()
                        # Skip Python 3.11+ caret/tilde highlight lines
                        if stripped and not all(c in "~^ \t" for c in stripped):
                            code_line = stripped
                        i += 1
                    frames.append(Frame(file=f_file, line=f_line, func=f_func, code=code_line))
                    continue
                else:
                    i += 1

            raw_trace = "\n".join(raw_lines)
            traces.append(
                ServerTrace(
                    method=method,
                    path=path,
                    exception=exception_str,
                    frames=frames,
                    raw=raw_trace,
                )
            )
        else:
            i += 1

    return traces
