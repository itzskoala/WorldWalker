#fitbit_steps.py
# The primary walking-progress metric - a continuous count, unlike
# exercise's discrete workout sessions. See docs/prompt_log/.

from services.fitbit_pydantic_schema import StepsData
from services.fitbitMetrics.fitbit_metric_strategy import FitbitMetric


class StepsMetric(FitbitMetric):
    def __init__(self, api_response: dict):
        self.api_response = api_response

    def metric_obj(self) -> StepsData:
        return StepsData(**self.api_response)
