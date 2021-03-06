import os
import yaml
import logbook
import jsonschema

from xdg import BaseDirectory
from piper.utils import dynamic_load


DB_SCHEMA = {
    'description': 'Database configuration',
    'type': 'object',
    'required': ['class', 'host'],
    'properties': {
        'class': {
            'description': 'The piper.db class to use as DB abstraction',
            'type': 'string',
        },
        'host': {
            'description': 'The host to connect to',
            'type': 'string',
        },
        'user': {
            'description': 'The username used for authentication',
            'type': ['string', 'null'],
        },
        'password': {
            'description': 'The passord used for authentication',
            'type': ['string', 'null'],
        },
    },
}


class ConfigError(Exception):
    pass


class Config:
    def __init__(self, filename=None, raw=None):
        args = (filename, raw)
        assert any(args), 'Need to specify `filename` or `raw`'
        assert not all(args), 'Cannot specify both ' + \
            '`filename` and `raw` at the same time'

        self.filename = filename
        self.raw = raw

        self.classes = {}

        self.log = logbook.Logger(self.__class__.__name__)

    def load(self):
        self.log.debug('Loading configuration')

        if self.filename:
            self.load_config()
        else:
            self.log.debug('Using provided raw configuration.')

        # self.validate_config()
        self.load_classes()
        return self

    def load_config(self):
        """
        Parses the configuration file and dies in flames if there are errors.

        """

        if not os.path.isfile(self.filename):
            err = 'Config file not found in $PWD. Aborting.'
            self.log.error(err)
            raise ConfigError(err)

        with open(self.filename) as config:
            file_data = config.read()

            try:
                self.raw = yaml.safe_load(file_data)

            except yaml.parser.ParserError as exc:
                self.log.error(exc)
                err = 'Invalid YAML in {0}. Aborting.'.format(self.filename)
                self.log.error(err)
                raise ConfigError(err)

        self.log.debug('Configuration file loaded.')

    def collect_classes(self):
        """
        Return a set of all class package strings in the configuration tree.

        """

        def traverse(data):
            for key, value in data.items():
                if key in ('class', 'classes'):
                    yield value
                elif isinstance(value, dict):
                    yield from traverse(value)

        return set(traverse(self.raw))

    def load_classes(self):
        self.log.debug("Loading classes...")

        for cls in self.collect_classes():
            self.log.debug("Loading class '{0}()'".format(cls))
            self.classes[cls] = dynamic_load(cls)

        self.log.debug("Class loading done.")

    def validate_config(self):
        self.log.debug('Validating...')
        jsonschema.validate(self.raw, self.schema)

    def merge_namespace(self, ns):
        """
        Take an argparse namespace and merge whatever it had directly in to the
        configuration object.

        Before this, we used to shuffle around both, to mostly the same use.

        """

        self.log.debug('Merging argparse namespace')
        for key in filter(lambda x: not x.startswith('_'), dir(ns)):
            attr = getattr(ns, key)
            setattr(self, key, attr)

    def get_database(self):
        return self.classes[self.raw['db']['class']]()


class BuildConfig(Config):
    schema = {
        "$schema": "http://json-schema.org/draft-04/schema",
        'type': 'object',
        'additionalProperties': False,
        'required': ['version', 'envs', 'steps', 'pipelines'],
        'properties': {
            'version': {
                'description':
                    'Versioning setup for this project. This sets up what '
                    'commands to run to determine the version of the pipeline '
                    'being executed',
                'type': 'object',
            },
            'envs': {
                'description': 'The env configuration for this build.',
                'type': 'object',
                'additionalProperties': {
                    'type': 'object',
                },
            },
            'steps': {
                'description': 'Definitions of executable build steps.',
                'type': 'object',
            },
            'pipelines': {
                'description': 'Runnable collections of steps.',
                'type': 'object',
                'additionalProperties': {
                    'type': 'array',
                    'items': {'type': 'string'},
                },
            },
            'db': DB_SCHEMA,
            'pipeline': {
                'description': 'The key of the pipeline to execute.',
                'type': 'string',
            },
        },
    }

    def __init__(self, filename=None, raw=None):
        if raw is None and filename is None:
            filename = 'piper.yml'

        super(BuildConfig, self).__init__(filename, raw)


class AgentConfig(Config):
    schema = {
        "$schema": "http://json-schema.org/draft-04/schema",
        'type': 'object',
        'additionalProperties': False,
        'required': ['agent', 'db'],
        'properties': {
            'agent': {
                'description': 'Agent configuration',
                'type': 'object',
                'additionalProperties': False,
                'required': ['id', 'fqdn', 'active'],
                'properties': {
                    'id': {
                        'description':
                            'Agent identifier',
                        'type': 'string',
                    },
                    'fqdn': {
                        'description':
                            'Fully qualified domain name, used for network '
                            'operations.',
                        'type': 'string',
                    },
                    'active': {
                        'description':
                            'Decides if the agent is to be used for building '
                            'or not. Inactive agents are connected and '
                            'visible, but will not be considered for any '
                            'tasks.',
                        'type': 'boolean',
                    },
                },
            },
            'db': DB_SCHEMA,
            'api': {
                'description': 'API configuration',
                'type': 'object',
                'additionalProperties': False,
                'required': ['address', 'port'],
                'properties': {
                    'address': {
                        'description': 'Address to bind to',
                        'type': 'string',
                    },
                    'port': {
                        'description': 'Port to listen on',
                        'type': 'integer',
                    },
                },
            },
        },
    }

    def __init__(self, filename=None):
        if not filename:
            filename = 'piperd.yml'

        super(AgentConfig, self).__init__(filename)


def get_app_config():  # pragma: nocover
    """
    Gets a dict with the global configuration files set in the XDG dirs.

    """

    # NOTE: This is very quick and dirty and should be baked into the
    # configuration ecosystem of piper at a later point.

    ret = {}
    files = [f for f in BaseDirectory.load_config_paths('piper', 'piper.yml')]
    files.reverse()

    for conf in files:
        with open(conf) as f:
            data = yaml.safe_load(f.read())
            ret.update(data)

    return ret
