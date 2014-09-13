import mock

from piper.build import Build
from piper.utils import DotDict
from test.utils import BASE_CONFIG


class BuildTestBase(object):
    def setup_method(self, method):
        self.build = Build(mock.Mock(), mock.MagicMock())
        self.base_config = BASE_CONFIG


class TestBuildSetup(BuildTestBase):
    def setup_method(self, method):
        self.methods = (
            'load_classes',
            'set_version',
            'configure_env',
            'configure_steps',
            'configure_job',
            'setup_env',
        )

        super(TestBuildSetup, self).setup_method(method)

    def test_setup_calls(self):
        for method in self.methods:
            setattr(self.build, method, mock.Mock())

        self.build.setup()

        for method in self.methods:
            getattr(self.build, method).assert_called_once_with()


class TestBuildRun(BuildTestBase):
    def setup_method(self, method):
        self.methods = ('setup', 'execute', 'teardown')

        super(TestBuildRun, self).setup_method(method)
        self.build.version = mock.Mock()

        for method in self.methods:
            setattr(self.build, method, mock.Mock())

    def test_run_calls(self):
        self.build.run()

        for method in self.methods:
            getattr(self.build, method).assert_called_once_with()

    def test_run_returns_boolean_success(self):
        self.build.success = False
        ret = self.build.run()
        assert ret is False

        self.build.success = True
        ret = self.build.run()
        assert ret is True


class TestBuildLoadClasses(BuildTestBase):
    def setup_method(self, method):
        super(TestBuildLoadClasses, self).setup_method(method)
        self.build.config = DotDict(self.base_config)

        self.version = 'piper.version.GitVersion'
        self.step = 'piper.step.CommandLineStep'
        self.env = 'piper.env.EnvBase'

    @mock.patch('piper.build.dynamic_load')
    def test_load_classes(self, dl):
        self.build.load_classes()

        calls = (
            mock.call(self.version),
            mock.call(self.step),
            mock.call(self.env)
        )
        assert dl.has_calls(calls, any_order=True)
        assert self.build.classes[self.version] is dl.return_value
        assert self.build.classes[self.step] is dl.return_value
        assert self.build.classes[self.env] is dl.return_value


class TestBuildSetVersion(object):
    def setup_method(self, method):
        self.version = '0.0.0.0.0.0.0.0.1-beta'
        self.cls = mock.Mock()
        self.cls_key = 'mandowar.FearOfTheDark'

        self.build = Build(mock.Mock(), mock.Mock())
        self.build.classes = {self.cls_key: self.cls}
        self.build.config = DotDict({
            'version': {
                'class': self.cls_key,
            },
        })

    def test_set_version(self):
        self.build.set_version()

        self.cls.assert_called_once_with(
            self.build.ns,
            self.build.config.version
        )
        self.cls.return_value.validate.assert_called_once_with()


class TestBuildConfigureEnv(object):
    def setup_method(self, method):
        self.env_key = 'local'
        self.cls_key = 'unisonic.KingForADay'
        self.cls = mock.Mock()

        self.build = Build(mock.Mock(env=self.env_key), mock.Mock())
        self.build.classes = {self.cls_key: self.cls}
        self.build.config = DotDict({
            'envs': {
                'local': {
                    'class': self.cls_key,
                }
            },
        })

    def test_configure_env(self):
        self.build.configure_env()

        self.cls.assert_called_once_with(
            self.build.ns,
            self.build.config.envs[self.env_key]
        )
        self.cls.return_value.validate.assert_called_once_with()


class TestBuildConfigureSteps(object):
    def setup_method(self, method):
        self.step_key = 'local'
        self.config = {
            'steps': {
                'bang': {
                    'class': 'edguy.police.LoveTyger',
                },
                'boom': {
                    'class': 'bethhart.light.LiftsUUp',
                }
            },
        }

        self.build = Build(mock.Mock(job=self.step_key), mock.Mock())
        for key in self.config['steps']:
            cls = self.config['steps'][key]['class']
            self.build.classes[cls] = mock.Mock()

        self.build.config = DotDict(self.config)

    def test_configure_steps(self):
        self.build.configure_steps()

        for key in self.config['steps']:
            cls_key = self.config['steps'][key]['class']

            cls = self.build.classes[cls_key]
            cls.assert_called_once_with(
                self.build.ns,
                self.build.config.steps[key],
                key
            )
            cls.return_value.validate.assert_called_once_with()


class TestBuildConfigureJob(object):
    def setup_method(self, method):
        self.job_key = 'mmmbop'
        self.step_keys = ('bidubidappa', 'dubop', 'schuwappa')
        self.steps = (mock.Mock(), mock.Mock(), mock.Mock())

        for step in self.steps:
            step.config.depends = None

        self.config = {
            'jobs': {
                self.job_key: self.step_keys,
            },
        }

    def get_build(self, config):
        build = Build(mock.Mock(job=self.job_key), DotDict(config))
        build.steps = dict(zip(self.step_keys, self.steps))
        return build

    def test_configure_job(self):
        self.build = self.get_build(self.config)
        self.build.configure_job()

        for x, _ in enumerate(self.step_keys):
            assert self.build.order[x] is self.steps[x]

    def test_configure_job_with_dependency(self):
        """
        Set so that we only have a list with the second item, and set so that
        it depends on the first. This should add the first item to the ordered
        list even though it's not otherwise specified.

        """

        self.steps[1].config.depends = self.step_keys[0]
        self.build = self.get_build({
            'jobs': {
                self.job_key: self.step_keys[1:2],
            },
        })

        self.build.configure_job()

        assert len(self.build.order) == 2
        assert self.build.order[0] is self.steps[0]
        assert self.build.order[1] is self.steps[1]

    def test_configure_job_with_multiple_dependencies(self):
        """
        Set so that we see that a step with multiple dependencies gets all of
        them set.

        """

        # Let the third step depend on the two earlier ones, and let the job
        # configuration only specify the third step.
        self.steps[2].config.depends = self.step_keys[0:2]
        self.build = self.get_build({
            'jobs': {
                self.job_key: (self.step_keys[2],),
            },
        })

        self.build.configure_job()

        assert len(self.build.order) == 3
        assert self.build.order[0] is self.steps[0]
        assert self.build.order[1] is self.steps[1]
        assert self.build.order[2] is self.steps[2]

    def test_configure_job_with_nested_dependencies(self):
        """
        See so that a dependency chain gets resolved properly.

        """

        # Make the third step depend on the second step, and let the second
        # step depend on the first one. Whew.
        self.steps[2].config.depends = self.step_keys[1]
        self.steps[1].config.depends = self.step_keys[0]
        self.build = self.get_build({
            'jobs': {
                self.job_key: (self.step_keys[2],),
            },
        })

        self.build.configure_job()

        assert len(self.build.order) == 3
        assert self.build.order[0] is self.steps[0]
        assert self.build.order[1] is self.steps[1]
        assert self.build.order[2] is self.steps[2]

    def test_configure_job_with_nested_dependencies_out_of_order(self):
        """
        See so that a dependency chain gets resolved properly, even when the
        steps are defined in a different order.

        """
        # Make the third step depend on the first step, and let the first
        # step depend on the second one. Whew x2.
        self.steps[2].config.depends = self.step_keys[0]
        self.steps[0].config.depends = self.step_keys[1]
        self.build = self.get_build({
            'jobs': {
                self.job_key: (self.step_keys[2],),
            },
        })

        self.build.configure_job()

        assert len(self.build.order) == 3
        assert self.build.order[0] is self.steps[1]
        assert self.build.order[1] is self.steps[0]
        assert self.build.order[2] is self.steps[2]


class TestBuildExecute(object):
    def setup_method(self, method):
        self.build = Build(mock.Mock(), mock.Mock())
        self.build.order = [mock.Mock() for _ in range(3)]
        self.build.env = mock.Mock()

    def test_all_successful(self):
        self.build.execute()

        calls = [mock.call(step) for step in self.build.order]
        assert self.build.env.execute.call_args_list == calls
        assert self.build.success is True

    def test_execution_stops_by_failed_step(self):
        self.build.order[1].success = False
        self.build.env.execute.side_effect = (
            mock.Mock(),
            mock.Mock(success=False),
        )
        self.build.execute()

        calls = [mock.call(step) for step in self.build.order[:2]]
        assert self.build.env.execute.call_args_list == calls
        assert self.build.success is False


class TestBuildSetupEnv(BuildTestBase):
    def setup_method(self, method):
        super(TestBuildSetupEnv, self).setup_method(method)
        self.build.env = mock.Mock()

    def test_setup_env(self):
        self.build.setup_env()
        self.build.env.setup.assert_called_once_with()


class TestBuildTeardown(BuildTestBase):
    def setup_method(self, method):
        super(TestBuildTeardown, self).setup_method(method)
        self.build.env = mock.Mock()

    def test_teardown(self):
        self.build.teardown_env = mock.Mock()
        self.build.teardown()
        self.build.teardown_env.assert_called_once_with()

    def test_teardown_env(self):
        self.build.teardown_env()
        self.build.env.teardown.assert_called_once_with()
