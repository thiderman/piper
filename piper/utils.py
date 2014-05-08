class DotDict(object):
    """
    Immutable dict-like objects accessible by dot notation

    Used because the amount of configuration access is very high and just using
    dots instead of the dict notation feels good.

    """

    def __init__(self, data):
        self.data = data

    def __repr__(self):  # pragma: nocover
        return '<DotDict {}>'.format(self.data)

    def __getattr__(self, key):
        val = self.data[key]

        if isinstance(val, dict):
            val = DotDict(val)

        return val


def dynamic_load(target):
    """
    Dynamically import a class and return it

    This is used by the core parts of the main configuration file since
    one of the main features is to let the user specify which class to use.

    """

    split = target.split('.')
    module_name = '.'.join(split[:-1])
    class_name = split[-1]

    mod = __import__(module_name, fromlist=[class_name])
    return getattr(mod, class_name)
