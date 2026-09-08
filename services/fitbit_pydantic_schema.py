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
    """Profile pull (services.google_health_client.get_profile), not
    webhook-driven - see that function's docstring. Documented fields are
    limited to age + membership start date; NOT the classic Fitbit
    gender/height/weight fields.

    stride_length_m: this IS real per-user data - the Google Health app
    lets a user calibrate it under Profile > Google Health settings >
    Activity > Stride Length (default estimated from height/weight/sex,
    overridable with a measured value). Not confirmed to be exposed by the
    v4 REST API's documented fields yet, though (getProfile only documents
    age/memberSince, per get_profile()'s docstring) - needs a live
    get_profile() probe to check for an undocumented field before this can
    populate for real. Stays None until then; travel_logic falls back to a
    gender average."""
    dataType: Literal["user"] = "user"
    age: Optional[int] = None
    member_since: Optional[str] = Field(default=None, alias="memberSince")
    stride_length_m: Optional[float] = None
