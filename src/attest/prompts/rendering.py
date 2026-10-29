from __future__ import annotations

from ..trajectory import Trajectory


def tool_call_lines(traj: Trajectory, *, output_chars: int | None = None) -> str:
    lines: list[str] = []
    for index, call in traj.tool_calls():
        line = f"{index}: {call.name}({call.arguments})"
        if output_chars is not None:
            line += f" -> {call.output[:output_chars]}"
        lines.append(line)
    return "\n".join(lines)
