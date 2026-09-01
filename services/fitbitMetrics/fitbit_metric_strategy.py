#fitbit_metric_strategy.py
from abc import ABC, abstractmethod
'''

// The strategy interface declares operations common to all
// supported versions of some algorithm. The context uses this
// interface to call the algorithm defined by the concrete
// strategies.
so the facade will call this? / intake.py?

'''

class FitbitMetric(ABC):
    @abstractmethod
    def metric_obj(self):
        """Convert the raw event dict into a Pydantic object."""
        pass


# class interface Strategy is
#     method execute(a, b)

