from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StageWork:
    stage: str
    remaining_units: float
    observed_units_per_second: float | None
    historical_units_per_second: float | None


def update_ema(previous: float | None, observed: float, alpha: float = 0.35) -> float:
    if previous is None:
        return observed
    return alpha * observed + (1 - alpha) * previous


def estimate_completion_seconds(queue_delay_seconds: float, stages: list[StageWork]) -> tuple[int, str]:
    seconds = queue_delay_seconds
    low_confidence = False
    for stage in stages:
        throughput = stage.observed_units_per_second or stage.historical_units_per_second
        if not throughput or throughput <= 0:
            low_confidence = True
            throughput = max(1.0, stage.remaining_units / 60)
        seconds += stage.remaining_units / throughput
    confidence = "Low" if low_confidence else "Medium" if len(stages) > 2 else "High"
    return int(seconds), confidence
