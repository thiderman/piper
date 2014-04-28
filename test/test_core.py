import mock

from piper.core import Piper

from test.utils import builtin


class PiperTestBase(object):
    def setup_method(self, method):
        self.piper = Piper()


class TestPiperSetup(PiperTestBase):
    def test_setup_calls(self):
        self.piper.load_config = mock.MagicMock()

        self.piper.setup()

        self.piper.load_config.assert_called_once_with()


class TestPiperConfigLoader(PiperTestBase):
    def setup_method(self, method):
        self.data = 'lel: 10\ntest: wizard\n\n'
        super(TestPiperConfigLoader, self).setup_method(method)

    @mock.patch('sys.exit')
    @mock.patch('os.path.isfile')
    def test_load_config_no_file(self, isfile, exit):
        isfile.return_value = False
        self.piper.load_config()

        exit.assert_called_once_with(127)

    @mock.patch('yaml.safe_load')
    @mock.patch('os.path.isfile')
    def test_load_config(self, isfile, sl):
        isfile.return_value = True
        fake = mock.mock_open(read_data=str(self.data))

        with mock.patch(builtin('open'), fake):
            self.piper.load_config()

        sl.assert_called_once_with(fake.return_value)