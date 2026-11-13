#workout_calibration.py

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkoutCalibration:
    stride_m: float
    speed_m_per_s: float
