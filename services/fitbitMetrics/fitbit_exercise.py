#fitbit_exercise.py

from services.fitbit_pydantic_schema import ExerciseData
from services.fitbitMetrics.fitbit_metric_strategy import FitbitMetric

#api_response is a single flat exercise event dict, e.g.
#{"dataType": "exercise", "startTime": ..., "steps": 4699, ...}

class ExerciseMetric(FitbitMetric):
    def __init__(self, api_response: dict):
        self.api_response = api_response

    def metric_obj(self) -> ExerciseData:
        return ExerciseData(**self.api_response)
