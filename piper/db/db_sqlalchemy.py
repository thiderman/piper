import os
import datetime
import socket
import contextlib
import json
import logbook

from piper import utils

from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import create_engine
from sqlalchemy import update
from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import relationship

from piper.db import core as db


Base = declarative_base()
Session = sessionmaker()


class SQLAlchemyManager(object):
    def __init__(self, db):
        self.db = db

        self.log = logbook.Logger(self.__class__.__name__)

    def get_or_create(self, session, model, keys=(), **kwargs):
        """
        Get or create an object.

        A filter is done on the model with `kwargs`. If `keys` are specified,
        only those keys will be used to do the filtering.

        """

        filter = kwargs
        if keys:
            filter = dict((k, v) for k, v in kwargs.items() if k in keys)

        instance = session.query(model).filter_by(**filter).first()
        if not instance:
            instance = model(**kwargs)
            session.add(instance)

        return instance

    @contextlib.contextmanager
    def in_session(self):
        """
        Context manager that yields SQLA Session() objects.

        Currently implemented by storing the session on the database for the
        duration of the topmost context. That means that all subsequent
        calls to this will just re-use the upper context. This will lead to
        simple code that ensures just one transaction per operation, but it
        also removes thread safety.

        """

        if self.db._session is not None:
            self.log.debug('Re-using session `{0}`'.format(self.db._session))
            yield self.db._session
            return

        session = Session()
        self.log.debug('Creating new session `{0}`'.format(session))

        # Store the session on the database singleton.
        self.db._session = session

        try:
            yield session
            self.log.debug('Committing session `{0}`'.format(session))
            session.commit()
        except:
            session.rollback()
            raise
        finally:
            self.log.debug('Closing session `{0}`'.format(session))
            session.close()
            self.db._session = None


class Agent(Base):
    __tablename__ = 'agent'

    id = Column(Integer(), primary_key=True)
    fqdn = Column(String(255))
    name = Column(String(255))
    active = Column(Boolean())
    busy = Column(Boolean())
    registered = Column(Boolean())
    properties = relationship('Property')
    created = Column(DateTime(), default=utils.now)
    last_seen = Column(DateTime(), default=utils.now)


class AgentManager(SQLAlchemyManager, db.AgentManager):
    def get(self):
        with self.in_session() as session:
            name = socket.gethostname()
            agent = self.get_or_create(
                session,
                Agent,
                keys=('fqdn',),
                name=name,
                fqdn=name,  # XXX
                active=True,
                busy=False,
                registered=False,
            )

            return agent

    def lock(self, build):
        self.set_lock(build, True)

    def unlock(self, build):
        self.set_lock(build, False)

    def set_lock(self, build, locked):
        with self.in_session() as session:
            agent = session.query(Build).get(build.ref.id).agent
            agent.busy = locked

            session.add(agent)


class Build(Base):
    __tablename__ = 'build'

    id = Column(Integer(), primary_key=True)
    agent_id = Column(Integer(), ForeignKey('agent.id'))
    project_id = Column(Integer(), ForeignKey('project.id'))
    config_id = Column(Integer(), ForeignKey('config.id'))

    agent = relationship('Agent', backref='builds')
    project = relationship('Project', backref='builds')
    config = relationship('Config', backref='builds')

    user = Column(String(255))
    success = Column(Boolean())
    crashed = Column(Boolean())
    status = Column(String(255))
    started = Column(DateTime())
    ended = Column(DateTime())
    updated = Column(DateTime(), default=utils.now)
    created = Column(DateTime(), default=utils.now)


class BuildManager(SQLAlchemyManager, db.BuildManager):
    def add(self, build):
        with self.in_session() as session:
            instance = Build(
                agent=self.db.agent.get(),
                project=self.db.project.get(build),
                config=self.db.config.register(build),
                user=os.getenv('USER'),
                **build.default_db_kwargs()
            )

            # Flush the object to save it.
            # Refresh it so that it get autogenerated fields (id
            # Expunge it so that it can be used by other sessions.
            session.add(instance)
            session.flush()
            session.refresh(instance)
            session.expunge(instance)

            return instance

    def update(self, build, **extra):
        with self.in_session() as session:
            values = build.default_db_kwargs()
            values.update(extra)

            stmt = update(Build).where(Build.id == build.ref.id).values(values)
            session.execute(stmt)

    def get(self, build_id):
        with self.in_session() as session:
            build = session.query(Build).get(build_id)
            if build is not None:
                # Aight, so this is obviously bad and wrong.
                # How do load in one query? Halp!
                build.agent.properties
                build.project.vcs

                session.expunge_all()
            return build

    def all(self):
        with self.in_session() as session:
            builds = session.query(Build).all()
            for build in builds:  # pragma: nocover
                build.agent.properties
                build.project.vcs

            session.expunge_all()
            return builds


class Config(Base):
    __tablename__ = 'config'

    id = Column(Integer(), primary_key=True)
    project = relationship('Project', backref='configs')
    project_id = Column(Integer(), ForeignKey('project.id'))
    json = Column(Text())
    created = Column(DateTime(), default=utils.now)


class ConfigManager(SQLAlchemyManager, db.ConfigManager):
    def register(self, build, project=None):
        with self.in_session() as session:
            if project is None:
                project = self.db.project.get(build)

            return self.get_or_create(
                session,
                Config,
                project=project,
                json=json.dumps(build.config.raw),
            )


class Project(Base):
    __tablename__ = 'project'

    id = Column(Integer(), primary_key=True)
    name = Column(String(255))
    vcs = relationship('VCS')
    vcs_id = Column(Integer(), ForeignKey('vcs.id'))
    created = Column(DateTime(), default=utils.now)


class ProjectManager(SQLAlchemyManager, db.ProjectManager):
    def get(self, build):
        with self.in_session() as session:
            project = self.get_or_create(
                session,
                Project,
                name=build.vcs.get_project_name(),
                vcs=self.db.vcs.get(build),
            )

            return project


class VCS(Base):
    __tablename__ = 'vcs'

    id = Column(Integer(), primary_key=True)
    name = Column(String(255))
    root_url = Column(String(255))
    created = Column(DateTime(), default=utils.now)


class VCSManager(SQLAlchemyManager, db.VCSManager):
    def get(self, build):
        with self.in_session() as session:
            vcs = self.get_or_create(
                session,
                VCS,
                keys=('root_url',),
                root_url=build.vcs.root_url,
                name=build.vcs.name,
            )

        return vcs


class Property(Base):
    __tablename__ = 'property'

    id = Column(Integer(), primary_key=True)
    agent = relationship('Agent')
    agent_id = Column(Integer(), ForeignKey('agent.id'))
    namespace = relationship('PropertyNamespace')
    namespace_id = Column(Integer(), ForeignKey('property_namespace.id'))
    key = Column(String(255))
    value = Column(String(255))
    created = Column(DateTime(), default=utils.now)


class PropertyManager(SQLAlchemyManager, db.PropertyManager):
    def update(self, classes):
        self.log.info('Updating properties')
        self.log.debug(classes)

        with self.in_session() as session:
            agent = self.db.agent.get()

            # Clear existing properties.
            query = session.query(Property).filter(Property.agent == agent)
            query.delete()
            self.log.debug('Cleared old properties')

            for prop_class in classes:
                prop_source = prop_class.source
                prop_source.log.info('Loading properties')
                prop_source.ns = self.db.property_namespace.get(
                    prop_source.namespace
                )

                for prop in prop_source.generate():
                    prop_source.log.debug(str(prop))

                    obj = Property(**prop.to_kwargs(
                        agent=agent,
                        namespace=prop_source.ns,
                    ))
                    session.add(obj)

                prop_source.log.info('Properties loaded')

            self.log.info('Property updating complete')


class PropertyNamespace(Base):
    __tablename__ = 'property_namespace'

    id = Column(Integer(), primary_key=True)
    properties = relationship('Property')
    name = Column(String(255))
    created = Column(DateTime(), default=utils.now)


class PropertyNamespaceManager(SQLAlchemyManager, db.PropertyNamespaceManager):
    def get(self, name):
        with self.in_session() as session:
            return self.get_or_create(session, PropertyNamespace, name=name)


class SQLAlchemyDB(db.Database):
    tables = {
        Agent: AgentManager,
        Build: BuildManager,
        Config: ConfigManager,
        Project: ProjectManager,
        VCS: VCSManager,
        Property: PropertyManager,
        PropertyNamespace: PropertyNamespaceManager,
    }

    sqlite = 'sqlite:///'
    _session = None

    def setup(self, config):
        self._config = config
        self.engine = create_engine(config.raw['db']['host'])
        Session.configure(bind=self.engine)

        self.setup_managers()

    def init(self, config):
        host = config.raw['db']['host']
        assert host is not None, 'No database configured'

        if host.startswith(self.sqlite):
            self.handle_sqlite(host)

        self.log.info('Creating tables for {0}'.format(host))
        self.create_tables(host, echo=config.verbose)

    def setup_managers(self):
        for cls, man in self.tables.items():
            table = cls.__tablename__
            self.log.debug(
                'Creating manager {0} as db.{1}'.format(man.__name__, table)
            )

            # Initialize the manager with this db as first argument. That way
            # they can all access each other in a clean way.
            instance = man(self)
            setattr(self, table, instance)

    def handle_sqlite(self, host):
        target = os.path.dirname(host.replace(self.sqlite, ''))
        if target and not os.path.exists(target):
            self.log.debug('Creating SQLite dir {0}'.format(target))
            utils.mkdir(target)

    def create_tables(self, host, echo=False):
        engine = create_engine(host, echo=echo)
        self.log.debug('Engine created')

        Session.configure(bind=engine)
        self.log.debug('Session configured')

        for table in self.tables:
            self.log.debug('Creating table `{0}`'.format(table.__tablename__))
            table.metadata.bind = engine
            table.metadata.create_all()

        self.log.info('Database initialization complete.')

    @property
    def json_settings(self):  # pragma: nocover
        return {
            'cls': AlchemyEncoder,
            'check_circular': False,
        }


class AlchemyEncoder(json.JSONEncoder):  # pragma: nocover
    cache = utils.LimitedSizeDict(size_limit=1000)

    def default(self, obj):
        if isinstance(obj.__class__, DeclarativeMeta):
            if obj in self.cache:
                return self.cache[obj]

            fields = {}
            for field in dir(obj):
                if not field.startswith('_') and field != 'metadata' \
                        and not field.endswith('_id'):
                    fields[field] = obj.__getattribute__(field)

            self.cache[obj] = fields
            return fields

        elif isinstance(obj, datetime.datetime):
            return str(obj.isoformat())

        return json.JSONEncoder.default(self, obj)
