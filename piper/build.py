import ago
import logbook
import requests

from piper import config
from piper import logging
from piper import utils
from piper.api import RESTful
from piper.db.core import LazyDatabaseMixin
from piper.vcs import GitVCS


class Build(LazyDatabaseMixin):
    """
    The main pipeline runner.

    This class loads the configurations, sets up all other components,
    executes them in whatever order they are supposed to happen in, collects
    data about the state of the pipeline and persists it, and finally tears
    down the components that needs tearing down.

    """

    FIELDS_TO_DB = (
        # Main fields
        'id',
        'agent',
        'config',

        # Booleans
        'success',
        'crashed',

        # String fields
        'status',

        # Timestamps
        'started',
        'ended',
        'created',
    )

    def __init__(self, config):
        self.config = config

        self.vcs = GitVCS('github', 'git@github.com')

        self.id = None
        self.version = None
        self.steps = {}
        self.order = []
        self.started = None
        self.success = None
        self.crashed = False
        self.status = None

        self.pipeline = None
        self.env = None

        self.log = logbook.Logger(self.__class__.__name__)

    def run(self, pipeline, env):
        """
        Main entry point

        This is run when starting the script from the command line.
        Returns boolean success.

        """

        self.pipeline = pipeline
        self.env = env

        self.log.info('Setting up {0}...'.format(self.pipeline))
        self.started = utils.now()

        self.setup()
        self.execute()
        self.teardown()
        self.finish()

        return self.success

    def finish(self):
        self.ended = utils.now()

        verb = 'finished successfully in'
        if not self.success:
            verb = 'failed after'

        ts = ago.human(
            self.ended - self.started,
            precision=5,
            past_tense='%s {0}' % verb  # hee hee
        )
        self.log.info('{0} {1}'.format(self.version, ts))

        self.log_handler.pop_application()

    def setup(self):
        """
        Performs all setup steps

        This is basically an umbrella function that runs setup for all the
        things that the class needs to run a fully configured execute().

        """

        # self.add_build()
        self.set_logfile()
        self.set_version()

        self.configure_env()
        self.configure_steps()
        self.configure_pipeline()

        self.setup_env()

    def queue(self, pipeline, env):
        """
        Use the API to enqueue a build.

        """

        self.pipeline = pipeline
        self.env = env

        self.log.info('Adding to queue: {0} {1}'.format(pipeline, env))
        app_conf = config.get_app_config()

        url = '{0}/builds/'.format(app_conf['masters'][0])

        requests.post(url, json=self.config.raw)

    def set_logfile(self):
        """
        Set the log file to store the build log in.

        """

        self.log_key = '{0} {1}'.format(
            self.__class__.__name__,
            self.id[:7] if self.id else '',
        )
        self.log = logbook.Logger(self.log_key)

        self.logfile = 'logs/piper/{0}.log'.format(self.id)
        self.log_handler = logging.get_file_logger(self.logfile)
        self.log_handler.push_application()

    def set_version(self):
        """
        Set the version for this pipeline

        """

        self.log.debug('Determining version...')
        ver_config = self.config.raw['version']
        cls = self.config.classes[ver_config['class']]

        self.version = cls(self, ver_config)
        self.version.validate()
        self.log.info(str(self.version))

    def configure_env(self):
        """
        Configures the environment according to its config file.

        """

        self.log.debug('Loading environment...')
        env_config = self.config.raw['envs'][self.env]
        cls = self.config.classes[env_config['class']]

        self.env = cls(self, env_config)
        self.log.debug('Validating env config...')
        self.env.validate()
        self.env.log.debug('Environment configured.')

    def configure_steps(self):
        """
        Configures the steps according to their config sections.

        """

        for step_key, step_config in self.config.raw['steps'].items():
            cls = self.config.classes[step_config['class']]

            step = cls(self, step_config, step_key)
            step.log.debug('Validating config...')
            step.validate()
            step.log.debug('Step configured.')
            self.steps[step_key] = step

    def configure_pipeline(self):
        """
        Places steps in proper order according to the pipeline.

        """

        for step_key in self.config.raw['pipelines'][self.pipeline]:
            step = self.steps[step_key]
            self.order.append(step)

        self.log.debug('Step order configured.')
        self.log.info('Steps: ' + ', '.join(map(repr, self.order)))

    def setup_env(self):
        """
        Execute setup steps of the env

        """

        self.env.log.debug('Setting up env...')
        self.env.setup()

    def execute(self):
        """
        Runs the steps and determines whether to continue or not.

        Of all the things to happen in this application, this is probably
        the most important part!

        """

        total = len(self.order)
        self.log.info('Running {0}...'.format(self.pipeline))

        for x, step in enumerate(self.order, start=1):
            step.set_index(x, total)

            # Update db status to show that we are running this build
            self.status = '{0}/{1}: {2}'.format(x, total, step.key)
            # self.db.build.update(self)

            step.log.info('Running...')
            proc = self.env.execute(step)

            if proc.success:
                step.log.info('Step complete.')
            else:
                # If the success is not positive, bail and stop running.
                step.log.error('Step failed.')
                self.log.error('{0} failed.'.format(self.pipeline))
                self.success = False
                break

        self.status = ''
        # As long as we did not break out of the loop above, the build is
        # to be deemed successful.
        if self.success is not False:
            self.success = True

    def teardown(self):
        self.teardown_env()

    def teardown_env(self):
        """
        Execute teardown step of the env

        """

        self.env.log.debug('Tearing down env...')
        self.env.teardown()


class ExecCLI:
    config_class = config.BuildConfig

    def __init__(self, config):
        self.config = config

    def compose(self, parser):  # pragma: nocover
        cli = parser.add_parser('exec', help='Execute a pipeline locally')

        cli.add_argument(
            'pipeline',
            nargs='?',
            default='build',
            help='The pipeline to execute',
        )

        cli.add_argument(
            'env',
            nargs='?',
            default='local',
            help='The environment to execute in',
        )

        return 'exec', self.run

    def run(self, ns):
        success = Build(self.config).run(ns.pipeline, ns.env)

        return 0 if success else 1


class BuildCLI:
    config_class = config.BuildConfig

    def __init__(self, config):
        self.config = config

    def compose(self, parser):  # pragma: nocover
        cli = parser.add_parser('build', help='Build on an agent')

        cli.add_argument(
            'pipeline',
            nargs='?',
            default='build',
            help='The pipeline to execute',
        )

        cli.add_argument(
            'env',
            nargs='?',
            default='local',
            help='The environment to execute in',
        )

        return 'build', self.run

    def run(self, ns):
        success = Build(self.config).queue(ns.pipeline, ns.env)

        return 0 if success else 1


class BuildAPI(RESTful):
    """
    API endpoint for CRUD operations on builds.

    """

    def __init__(self, config):
        super().__init__(config)
        self.routes = (
            ('GET', '/builds/{id}', self.get),
            ('POST', '/builds/', self.create),
        )

    def get(self, request):
        """
        Get one build.

        """

        id = request.match_info.get('id')
        build = self.db.build.get(id)

        if build is None:
            return {}, 404

        return build

    def create(self, request):
        """
        Put a build into the database.

        :returns: id of created object

        """

        config = yield from self.extract_json(request)

        build = Build(config)
        build.created = utils.now()  # TODO: Should be in Build()?

        id = self.db.build.add(build)

        self.log.info('Build {0} added.'.format(id))
        ret = {
            'id': id,
        }
        return ret, 201
