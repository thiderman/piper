import piper
import logbook

import mock


class TestPiper(object):
    @mock.patch('piper.Piper')
    @mock.patch('sys.argv')
    def test_main_entry_point(self, argv, Piper):
        piper.main()

        assert Piper.call_count == 1
        Piper.return_value.run.assert_called_once_with()

    @mock.patch('piper.Piper')
    @mock.patch('piper.build_parser')
    def test_debug_argument_sets_debug_log_level(self, bp, Piper):
        bp.return_value.parse_args.return_value.debug = True
        piper.main()

        assert Piper.call_count == 1
        assert piper.handler.level == logbook.DEBUG
        Piper.return_value.run.assert_called_once_with()
