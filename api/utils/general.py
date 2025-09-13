# Hello there
class GeneralUtils:
    def __init__(self):
        pass

    @staticmethod
    def clamp(val, lower_bound, upper_bound):
        if not val:
            return

        return min(max(val, lower_bound), upper_bound)
