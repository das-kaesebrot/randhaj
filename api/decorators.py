from functools import wraps
from threading import Lock
from .utils import ThreadingUtils

def wait_lock(lock: Lock):
    def _wait_lock_inner(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            ThreadingUtils.wait_and_acquire_lock(lock)
            return_value = func(*args, **kwargs)
            lock.release()
            return return_value            
        return wrapper
    return _wait_lock_inner