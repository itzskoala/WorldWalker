#fitbit_heart_rate.py

from services.fitbit_pydantic_schema import HeartRateData
from services.fitbitMetrics.fitbit_metric_strategy import FitbitMetric

#api_response is a single flat heart-rate event dict, e.g.
#{"dataType": "heart_rate", "time": ..., "value": 72}

class HeartRateMetric(FitbitMetric):
    def __init__(self, api_response: dict):
        self.api_response = api_response

    def metric_obj(self) -> HeartRateData:
        return HeartRateData(**self.api_response)
