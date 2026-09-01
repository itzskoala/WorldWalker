#fitbit_sleep.py

from services.fitbit_pydantic_schema import SleepData
from services.fitbitMetrics.fitbit_metric_strategy import FitbitMetric

#api_response is a single flat sleep event dict, e.g.
#{"dataType": "sleep", "dateOfSleep": "2026-05-12", "startTime": ..., ...}

class SleepMetric(FitbitMetric):
    def __init__(self, api_response: dict):
        self.api_response = api_response

    def metric_obj(self) -> SleepData:
        return SleepData(**self.api_response)
