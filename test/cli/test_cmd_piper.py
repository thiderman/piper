from piper import agent
from piper import api
from piper import build
from piper import config
from piper.db import core as db
from piper.cli import cmd_piper
from piper.cli.cli import CLI

import mock


class TestEntry:
    @mock.patch('piper.cli.cmd_piper.CLI')
    def test_calls(self, clibase):
        self.mock = mock.Mock()
        classes = (
            build.BuildCLI,
            build.ExecCLI,
            agent.AgentCLI,
            api.ApiCLI,
            db.DbCLI,
        )

        cmd_piper.entry(self.mock)
        clibase.assert_called_once_with(
            'piper',
            classes,
            config.BuildConfig,
            args=self.mock
        )
        clibase.return_value.entry.assert_called_once_with()

    @mock.patch('piper.cli.cmd_piper.CLI')
    def test_return_value(self, clibase):
        ret = cmd_piper.entry()
        assert ret is clibase.return_value.entry.return_value


class TestEntryIntegration:
    """
    Test randomly selected points of entry to make sure that the mechanisms
    seem to work.

    """

    def test_db_init(self):
        args = ['db', 'init']
        cli = CLI('piper', (db.DbCLI,), config.BuildConfig, args=args)

        db.DbCLI.db = mock.Mock()
        ret = cli.entry()

        assert ret == 0
        assert db.DbCLI.db.init.call_count == 1

    @mock.patch('piper.build.Build.run')
    def test_exec(self, run):
        args = ['exec']
        cli = CLI('piper', (build.ExecCLI,), config.BuildConfig, args=args)

        cli.entry()
        run.assert_called_once_with('build', 'local')
