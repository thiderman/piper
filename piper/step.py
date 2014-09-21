import logbook

from piper.abc import DynamicItem


class StepBase(DynamicItem):
    """
    Abstract base class of an execution step.

    """

    def __init__(self, ns, config, key):
        super(StepBase, self).__init__(ns, config)

        self.index = ('x', 'y')
        self.key = key
        self.success = None
        self.log = logbook.Logger(key)

    def __repr__(self):  # pragma: nocover
        return "<{0} {1}>".format(self.__class__.__name__, self.key)

    def set_index(self, cur, tot):
        """
        Store the order of the step running and set up the logger accordingly.

        """

        self.index = (cur, tot)
        self.log_key = '{0} ({1}/{2})'.format(
            self.key, self.index[0], self.index[1]
        )
        self.log = logbook.Logger(self.log_key)

    def get_command(self):
        """
        The main entry point.

        This is what Env()s are supposed to run.

        """

        raise NotImplementedError()


class CommandLineStep(StepBase):
    """
    Step that simply runs a command line from the configuration file.

    KISS.

    """

    @property
    def schema(self):
        if not hasattr(self, '_schema'):
            self._schema = super(CommandLineStep, self).schema
            self._schema['required'].append('command')
            self._schema['properties']['command'] = {
                'description': 'Command line to execute.',
                'type': 'string',
            }

        return self._schema

    def get_command(self):
        return self.config.command
