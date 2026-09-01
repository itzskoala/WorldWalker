# tests/test_fitbit_metrics.py
# Each strategy class: a real-shaped dataPoint dict in -> correct Pydantic
# object out, aliases (camelCase -> snake_case) land on the right fields.
# Shapes are lifted from developers.google.com/health/reference/rest/v4/
# users.dataTypes.dataPoints

from services.fitbitMetrics.fitbit_steps import StepsMetric
from services.fitbitMetrics.fitbit_sleep import SleepMetric
from services.fitbitMetrics.fitbit_exercise import ExerciseMetric
from services.fitbitMetrics.fitbit_heart_rate import HeartRateMetric
from services.fitbit_pydantic_schema import StepsData, SleepData, ExerciseData, HeartRateData


def test_steps_metric_splices_aliased_fields():
    point = {
        "interval": {
            "startTime": "2026-09-01T15:01:23Z",
            "endTime": "2026-09-01T16:01:23Z",
        },
        "count": "1250",  # Google sends this as a string
    }
    obj = StepsMetric(point).metric_obj()
    assert isinstance(obj, StepsData)
    assert obj.count == 1250
    assert obj.interval.start_time == "2026-09-01T15:01:23Z"


def test_sleep_metric_splices_aliased_fields():
    point = {
        "interval": {
            "startTime": "2026-08-31T23:00:00Z",
            "endTime": "2026-09-01T07:00:00Z",
        },
        "type": "STAGES",
        "summary": {"minutesAsleep": "480", "minutesAwake": "30"},
    }
    obj = SleepMetric(point).metric_obj()
    assert isinstance(obj, SleepData)
    assert obj.summary.minutes_asleep == 480
    assert obj.summary.minutes_awake == 30


def test_exercise_metric_splices_aliased_fields():
    point = {
        "interval": {
            "startTime": "2026-08-11T20:40:32Z",
            "endTime": "2026-08-11T21:41:05.600Z",
        },
        "exerciseType": "WALKING",
        "displayName": "Walk",
        "metricsSummary": {
            "caloriesKcal": 542,
            "distanceMillimeters": "3248500",
            "steps": "4699",
            "averageHeartRateBeatsPerMinute": "126",
        },
    }
    obj = ExerciseMetric(point).metric_obj()
    assert isinstance(obj, ExerciseData)
    assert obj.exercise_type == "WALKING"
    assert obj.metrics_summary.steps == 4699
    assert obj.metrics_summary.average_heart_rate_bpm == 126


def test_heart_rate_metric_splices_aliased_fields():
    point = {
        "sampleTime": {"physicalTime": "2026-09-01T08:15:00Z"},
        "beatsPerMinute": "72",
        "metadata": {"motionContext": "ACTIVE", "sensorLocation": "WRIST"},
    }
    obj = HeartRateMetric(point).metric_obj()
    assert isinstance(obj, HeartRateData)
    assert obj.bpm == 72
    assert obj.sample_time.physical_time == "2026-09-01T08:15:00Z"
