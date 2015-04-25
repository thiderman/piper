import sys
from setuptools import setup
from setuptools.command.test import test as TestCommand


# http://stackoverflow.com/questions/11472810/#14405269
install_requires = (
    'Flask-RESTful>=0.3.2,<1.0.0a0',
    'Logbook>=0.9.0,<1.0.0a0',
    'PyYAML>=3.11,<4.0a0',
    'SQLAlchemy==0.9.7',  # Purposefully on hold
    'ago>=0.0.6,<1.0.0a0',
    'blessings>=1.6,<2.0.0a0',
    'facterpy>=0.1,<1.0a0',
    'jsonschema>=2.3.0,<3.0.0a0',
    'six>=1.9.0,<2.0.0a0',
)

tests_require = (
    'mock',
    'pytest-cov',
    'tox',
)


class PyTest(TestCommand):
    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = [
            'test',
            '-v',
            '--cov=piper',
            '--cov-report=xml',
            '--cov-report=term-missing',
            '--result-log=pytest-results.log'
        ]
        self.test_suite = True

    def run_tests(self):
        import pytest
        errno = pytest.main(self.test_args)
        sys.exit(errno)


class PyTestIntegration(PyTest):
    def finalize_options(self):
        super(PyTestIntegration, self).finalize_options()
        # Only run tests from classes that match "Integration"
        self.test_args.append('-k Integration')


class PyTestUnit(PyTest):
    def finalize_options(self):
        super(PyTestUnit, self).finalize_options()
        # Only run tests from classes that do not match "Integration"
        self.test_args.append('-k not Integration')


setup(
    name='piper',
    version='0.0.1',
    url='https://github.com/thiderman/piper',
    author='Lowe Thiderman',
    author_email='lowe.thiderman@gmail.com',
    description=('Manifest-based build pipeline system'),
    license='MIT',
    packages=['piper'],
    install_requires=install_requires,
    tests_require=tests_require,
    zip_safe=False,
    entry_points={
        'console_scripts': [
            'piper = piper.cli.cmd_piper:entry',
            'piperd = piper.cli.cmd_piperd:entry',
        ],
    },
    cmdclass={
        'test': PyTest,
        'integration': PyTestIntegration,
        'unit': PyTestUnit,
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Operating System :: Unix',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 2.7',
        'Topic :: Software Development :: Build Tools',
    ],
)
