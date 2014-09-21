import mock

from piper.api.build import Build


class TestBuildGet(object):
    def setup_method(self, method):
        self.build = Build()
        self.build.db = mock.Mock()
        self.build_id = 871263487612384761243  # ?

    def test_found(self):
        ret = self.build.get(self.build_id)

        assert ret is self.build.db.get_build.return_value
        self.build.db.get_build.assert_called_once_with(self.build_id)

    def test_not_found(self):
        self.build.db.get_build.return_value = None

        ret, code = self.build.get(1)
        assert ret == {}
        assert code == 404
