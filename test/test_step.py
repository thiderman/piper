from piper.step import Step

import mock


class TestStepExecute(object):
    def setup_method(self, method):
        self.step = Step('key', {})

    def test_execute(self):
        self.step.pre = mock.MagicMock()
        self.step.run = mock.MagicMock()
        self.step.post = mock.MagicMock()

        self.step.execute()

        self.step.pre.assert_called_once_with()
        self.step.run.assert_called_once_with()
        self.step.post.assert_called_once_with()


class TestStepValidate(object):
    def setup_method(self, method):
        self.step = Step('key', {})

    @mock.patch('jsonschema.validate')
    def test_validate(self, jv):
        self.step.validate()
        jv.assert_called_once_with(self.step.config.data, self.step.schema)
