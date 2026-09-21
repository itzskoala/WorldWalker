#fitbit_pydantic_schema.py
#
# Field shapes match the REAL Google Health API dataPoint responses
# (https://developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints),
# not the classic Fitbit Web API. Google serializes some numeric fields as
# strings (protobuf int64 convention) - Pydantic v2 auto-coerces those
# numeric strings into int/float, so fields below are typed as their real
# numeric type rather than str.

from pydantic import BaseModel, Field
from typing import Optional, Literal


class TimeInterval(BaseModel):
    start_time: str = Field(alias="startTime")
    end_time: str = Field(alias="endTime")


class SampleTime(BaseModel):
    physical_time: str = Field(alias="physicalTime")


class StepsData(BaseModel):
    """https://developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints#steps"""
    dataType: Literal["steps"] = "steps"
    interval: TimeInterval
    count: int


class HeartRateData(BaseModel):
    """.../users.dataTypes.dataPoints#heartrate"""
    dataType: Literal["heart-rate"] = "heart-rate"
    sample_time: SampleTime = Field(alias="sampleTime")
    bpm: int = Field(alias="beatsPerMinute")


class SleepSummary(BaseModel):
    minutes_asleep: int = Field(alias="minutesAsleep")
    minutes_awake: Optional[int] = Field(default=None, alias="minutesAwake")


class SleepData(BaseModel):
    """.../users.dataTypes.dataPoints#sleep"""
    dataType: Literal["sleep"] = "sleep"
    interval: TimeInterval
    summary: SleepSummary


class ExerciseMetricsSummary(BaseModel):
    calories_kcal: Optional[float] = Field(default=None, alias="caloriesKcal")
    distance_millimeters: Optional[float] = Field(default=None, alias="distanceMillimeters")
    steps: Optional[int] = Field(default=None)
    average_heart_rate_bpm: Optional[int] = Field(default=None, alias="averageHeartRateBeatsPerMinute")
    # Real device-measured pace for this workout (e.g. GPS-tracked) - when
    # present, more accurate than deriving speed from distance/duration
    # ourselves, and the only way to get a distance at all when a workout
    # reports neither distance_millimeters nor steps.
    average_speed_mm_per_s: Optional[float] = Field(default=None, alias="averageSpeedMillimetersPerSecond")
    average_pace_s_per_m: Optional[float] = Field(default=None, alias="averagePaceSecondsPerMeter")


class ExerciseData(BaseModel):
    """.../users.dataTypes.dataPoints#exercise"""
    dataType: Literal["exercise"] = "exercise"
    interval: TimeInterval
    exercise_type: str = Field(alias="exerciseType")
    metrics_summary: ExerciseMetricsSummary = Field(alias="metricsSummary")


class UserData(BaseModel):
    """Profile pull (services.google_health.client.get_profile), not
    webhook-driven. Stride lengths confirmed live: real per-user values
    from Profile > Google Health settings > Activity > Stride Length,
    per activity type (not a single unisex figure).

    member_since is unconfirmed/likely wrong - a live pull actually
    returned membershipStartDate as {year, month, day}, not a memberSince
    string; unused today, so left as-is rather than guessed again."""
    dataType: Literal["user"] = "user"
    age: Optional[int] = None
    member_since: Optional[str] = Field(default=None, alias="memberSince")
    walking_stride_length_mm: Optional[float] = Field(default=None, alias="userConfiguredWalkingStrideLengthMm")
    running_stride_length_mm: Optional[float] = Field(default=None, alias="userConfiguredRunningStrideLengthMm")
