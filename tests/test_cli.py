import importlib
import sys
import types


def _import_app(monkeypatch):
    class _StubEnchant:
        class errors:
            class DictNotFoundError(Exception):
                pass

        @staticmethod
        def Dict(lang):
            return types.SimpleNamespace(check=lambda _w: True, suggest=lambda _w: [])

    sys.modules.setdefault("enchant", _StubEnchant())
    return importlib.import_module("fimpad.app")


class DummyApp:
    def __init__(self):
        self.opened = []
        self.mainloop_called = False

    def open_files(self, paths):
        self.opened.append(list(paths))

    def mainloop(self):
        self.mainloop_called = True


def test_main_opens_provided_paths(tmp_path, monkeypatch):
    app_module = _import_app(monkeypatch)
    target = tmp_path / "sample.txt"
    target.write_text("hello")

    app_instance: DummyApp | None = None

    def factory() -> DummyApp:
        nonlocal app_instance
        app_instance = DummyApp()
        return app_instance

    app_module.main([str(target)], app_factory=factory)

    assert app_instance is not None
    assert app_instance.opened == [[str(target)]]
    assert app_instance.mainloop_called


def test_main_skips_open_when_no_paths(monkeypatch):
    app_module = _import_app(monkeypatch)
    app_instance: DummyApp | None = None

    def factory() -> DummyApp:
        nonlocal app_instance
        app_instance = DummyApp()
        return app_instance

    app_module.main([], app_factory=factory)

    assert app_instance is not None
    assert app_instance.opened == []
    assert app_instance.mainloop_called
