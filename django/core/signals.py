from django.dispatch import Signal

request_started = Signal()
request_finished = Signal()
got_request_exception = Signal(providing_args=["request"])

def log_exception(*args, **kwargs):
    import logging
    logging.exception('Exception in request:')
got_request_exception.connect(log_exception)
