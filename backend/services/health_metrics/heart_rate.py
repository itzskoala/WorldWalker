#heart_rate.py

from backend.services.health_pydantic_schema import HeartRateData
from backend.services.health_metrics.health_metric_strategy import HealthMetric


class HeartRateMetric(HealthMetric):
    def __init__(self, api_response: dict):
        self.api_response = api_response

    def metric_obj(self) -> HeartRateData:
        return HeartRateData(**self.api_response)
