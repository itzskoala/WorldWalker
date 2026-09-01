#events.py

#The base publisher class includes subscription management code and notification methods.

class Events:
    """Represents what is being observed"""

    def __init__(self):
        #these are like our subscriber list
        self._observers = []


    def notifySubscribers(self, eventType, listener):

        """Alert the observers"""

        for observer in self._observers:
            if listener != observer:
                observer.update(self)

    def unsubscribe(self, eventType, listener):
        try:
            self._observers.remove(listener)
        except ValueError:
            pass

    def subscribe(self, eventType, listener): #subscribe and unsubscribe for specfici events
        if listener not in self.observers:
            self._observers.append(listener)


        

