#health_pydantic_schema.py

from pydantic import BaseModel, Field
from typing import Optional, Literal


class TimeInterval(BaseModel):
    start_time: str = Field(alias="startTime")
    end_time: str = Field(alias="endTime")


class SampleTime(BaseModel):
    physical_time: str = Field(alias="physicalTime")


class StepsData(BaseModel):
    dataType: Literal["steps"] = "steps"
    interval: TimeInterval
    count: int


class HeartRateData(BaseModel):
    dataType: Literal["heart-rate"] = "heart-rate"
    sample_time: SampleTime = Field(alias="sampleTime")
    bpm: int = Field(alias="beatsPerMinute")


class SleepSummary(BaseModel):
    minutes_asleep: int = Field(alias="minutesAsleep")
    minutes_awake: Optional[int] = Field(default=None, alias="minutesAwake")


class SleepData(BaseModel):
    dataType: Literal["sleep"] = "sleep"
    interval: TimeInterval
    summary: SleepSummary


class ExerciseMetricsSummary(BaseModel):
    calories_kcal: Optional[float] = Field(default=None, alias="caloriesKcal")
    distance_millimeters: Optional[float] = Field(default=None, alias="distanceMillimeters")
    steps: Optional[int] = Field(default=None)
    average_heart_rate_bpm: Optional[int] = Field(default=None, alias="averageHeartRateBeatsPerMinute")
    average_speed_mm_per_s: Optional[float] = Field(default=None, alias="averageSpeedMillimetersPerSecond")
    average_pace_s_per_m: Optional[float] = Field(default=None, alias="averagePaceSecondsPerMeter")


class ExerciseData(BaseModel):
    dataType: Literal["exercise"] = "exercise"
    interval: TimeInterval
    exercise_type: str = Field(alias="exerciseType")
    metrics_summary: ExerciseMetricsSummary = Field(alias="metricsSummary")


class UserData(BaseModel):
    dataType: Literal["user"] = "user"
    age: Optional[int] = None
    member_since: Optional[str] = Field(default=None, alias="memberSince")
    walking_stride_length_mm: Optional[float] = Field(default=None, alias="userConfiguredWalkingStrideLengthMm")
    running_stride_length_mm: Optional[float] = Field(default=None, alias="userConfiguredRunningStrideLengthMm")
