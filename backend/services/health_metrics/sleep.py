#sleep.py

from backend.services.health_pydantic_schema import SleepData
from backend.services.health_metrics.health_metric_strategy import HealthMetric


class SleepMetric(HealthMetric):
    def __init__(self, api_response: dict):
        self.api_response = api_response

    def metric_obj(self) -> SleepData:
        return SleepData(**self.api_response)
