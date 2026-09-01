#fitbit_user_data.py

from services.fitbit_pydantic_schema import UserData
from services.fitbitMetrics.fitbit_metric_strategy import FitbitMetric

#api_response is a single flat user-profile event dict, e.g.
#{"dataType": "user", "user_id": ..., "gender": ..., ...}

class UserMetric(FitbitMetric):
    def __init__(self, api_response: dict):
        self.api_response = api_response

    def metric_obj(self) -> UserData:
        return UserData(**self.api_response)
