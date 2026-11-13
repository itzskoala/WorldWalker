#steps.py

from backend.services.health_pydantic_schema import StepsData
from backend.services.health_metrics.health_metric_strategy import HealthMetric


class StepsMetric(HealthMetric):
    def __init__(self, api_response: dict):
        self.api_response = api_response

    def metric_obj(self) -> StepsData:
        return StepsData(**self.api_response)
