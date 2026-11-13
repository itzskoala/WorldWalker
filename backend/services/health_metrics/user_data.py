#user_data.py

from backend.services.health_pydantic_schema import UserData
from backend.services.health_metrics.health_metric_strategy import HealthMetric


class UserMetric(HealthMetric):
    def __init__(self, api_response: dict):
        self.api_response = api_response

    def metric_obj(self) -> UserData:
        return UserData(**self.api_response)
