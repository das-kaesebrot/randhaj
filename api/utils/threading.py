from threading import Lock
from time import sleep


class ThreadingUtils:
    @staticmethod
    def wait_and_acquire_lock(lock: Lock):
        while lock.locked():
            sleep(0.001)
        lock.acquire()
