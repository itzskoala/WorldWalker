#health_metric_strategy.py

from abc import ABC, abstractmethod


class HealthMetric(ABC):
    @abstractmethod
    def metric_obj(self):
        pass
