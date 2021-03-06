import asyncio
import blessings
import json
import logbook
import types

from aiohttp import web
from piper.db.core import LazyDatabaseMixin
from piper import config


class ApiCLI(LazyDatabaseMixin):
    _modules = None
    config_class = config.AgentConfig

    def __init__(self, config):
        self.config = config

        self.log = logbook.Logger(self.__class__.__name__)

    def compose(self, parser):  # pragma: nocover
        api = parser.add_parser('api', help='Control the REST API')

        sub = api.add_subparsers(help='API commands', dest="api_command")
        sub.add_parser('start', help='Start the API')

        return 'api', self.run

    @property
    def modules(self):  # pragma: nocover
        """
        Get a tuple of the modules that should be in the API.

        This should probably be programmatically built rather than statically.

        """

        if self._modules is not None:
            return self._modules

        from piper.agent import AgentAPI
        from piper.build import BuildAPI

        return (
            AgentAPI(self.config),
            BuildAPI(self.config),
        )

    @asyncio.coroutine
    def setup_loop(self, loop):
        app = web.Application(loop=loop)

        for mod in self.modules:
            mod.setup(app)

        srv = yield from loop.create_server(
            app.make_handler(),
            self.config.raw['api']['address'],
            self.config.raw['api']['port'],
        )

        self.log.info(
            "Server started at http://{address}:{port}".format(
                **self.config.raw['api']
            )
        )
        return srv

    def setup(self):  # pragma: nocover
        loop = asyncio.get_event_loop()
        setup_future = self.setup_loop(loop)
        loop.run_until_complete(setup_future)
        return loop

    def run(self, ns):
        loop = self.setup()
        loop.run_forever()


class RESTful(LazyDatabaseMixin):
    """
    Abstract class pertaining to a RESTful API endpoint for aiohttp.

    Anything that inherits for this has to set `self.routes` to be a tuple like
    .. code-block::
       routes = (
          ("POST", "/foo", self.post),
          ("GET", "/foo", self.get),
       )

    When :func:`setup` is ran, the routes will be added to the aiohttp app.
    See :class:`piper.build.BuildAPI` for an example implementation.

    """

    def __init__(self, config):
        self.config = config

        self.t = blessings.Terminal()
        self.log = logbook.Logger(self.__class__.__name__)

    def setup(self, app):
        """
        Register the routes to the application.

        Will decorate all methods with :func:`endpoint`

        """

        for method, route, function in self.routes:
            app.router.add_route(
                method,
                route,
                self.endpoint(function, method, route),
            )

    def endpoint(self, func, method, route):
        """
        Decorator method that takes care of calling and post processing
        responses.

        """

        def wrap(*args, **kwargs):
            uri = route.format(**args[0].match_info)
            self.log.debug(
                '{t.bold_black}>>{t.white} {method} {t.normal}{uri}'.format(
                    method=method,
                    uri=uri,
                    t=self.t
                )
            )

            body = func(*args, **kwargs)
            code = 200

            # POST requests will need to read from asyncio interfaces, and thus
            # their handler functions will need to `yield from` and return
            # generator objects. If this is the case, we need to yield from
            # them to get the actual body out of there.
            if isinstance(body, types.GeneratorType):  # pragma: nocover
                body = yield from body

            # TODO: Add JSONschema validation
            if isinstance(body, tuple):
                # If the result was a 2-tuple, use the second item as the
                # status code.
                body, code = body

            s = '{t.bold_black}<<{t.white} {method} {t.normal}{uri}: {code}'
            self.log.info(
                s.format(
                    method=method,
                    uri=uri,
                    code=code,
                    t=self.t
                )
            )
            return self.encode_response(body, code)

        return asyncio.coroutine(wrap)

    def encode_response(self, body, code):
        # TODO: Add **headers argument

        body = json.dumps(
            body,
            indent=2,
            sort_keys=True,
            default=date_handler,
        )

        response = web.Response(
            body=body.encode(),
            status=code,
            headers={'content-type': 'application/json'}
        )

        return response

    def extract_json(self, request):  # pragma: nocover
        """
        Read the POST body of the request, decode it as JSON and return it.

        :return: JSON-loaded dict of the POST body

        """

        content = yield from request.content.read()
        body = content.decode('utf-8')

        self.log.debug(body)
        data = json.loads(body)
        return data


def date_handler(obj):  # pragma: nocover
    """
    This is why we cannot have nice things.
    https://stackoverflow.com/questions/455580/

    """

    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    elif isinstance(obj, ...):
        return ...
    else:
        raise TypeError(
            'Object of type %s with value of %s is not JSON serializable' % (
                type(obj), repr(obj)
            )
        )
