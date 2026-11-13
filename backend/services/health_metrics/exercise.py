#exercise.py

from backend.services.health_pydantic_schema import ExerciseData
from backend.services.health_metrics.health_metric_strategy import HealthMetric


class ExerciseMetric(HealthMetric):
    def __init__(self, api_response: dict):
        self.api_response = api_response

    def metric_obj(self) -> ExerciseData:
        return ExerciseData(**self.api_response)
