from piper import build
from piper import config
from piper.cli.cli import CLI


def entry(args=None):
    cli = CLI(
        'piper',
        (build.ExecCLI, build.BuildCLI),
        config.BuildConfig,
        args=args
    )
    return cli.entry()
