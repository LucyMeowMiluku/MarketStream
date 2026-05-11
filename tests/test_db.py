from storage.db import get_engine, _session_factory


class TestGetEngine:
    def test_returns_engine(self):
        engine = get_engine()
        assert engine is not None

    def test_caches_engine(self):
        e1 = get_engine()
        e2 = get_engine()
        assert e1 is e2


class TestSessionFactory:
    def test_caches_factory(self):
        f1 = _session_factory()
        f2 = _session_factory()
        assert f1 is f2

    def test_factory_is_callable(self):
        factory = _session_factory()
        assert callable(factory)
