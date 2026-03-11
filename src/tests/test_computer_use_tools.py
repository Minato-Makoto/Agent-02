from pathlib import Path

from builtin_tools import computer_use_tools


class _FakeImage:
    def save(self, path):
        with open(path, "wb") as handle:
            handle.write(b"fake-image")


class _FakePyAuto:
    def __init__(self):
        self.moves = []
        self.clicks = []
        self.writes = []
        self.keys = []
        self.scrolls = []

    @staticmethod
    def size():
        return (1024, 768)

    @staticmethod
    def screenshot(region=None):
        del region
        return _FakeImage()

    def moveTo(self, x, y, duration=0):
        self.moves.append((x, y, duration))

    def click(self, x=None, y=None, button="left", clicks=1, interval=0):
        self.clicks.append((x, y, button, clicks, interval))

    def write(self, text, interval=0):
        self.writes.append((text, interval))

    def press(self, key):
        self.keys.append(("press", key))

    def keyDown(self, key):
        self.keys.append(("down", key))

    def keyUp(self, key):
        self.keys.append(("up", key))

    def scroll(self, amount):
        self.scrolls.append(amount)


def test_desktop_tools_happy_path(monkeypatch, tmp_path):
    fake = _FakePyAuto()
    monkeypatch.setenv("AGENTFORGE_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("AGENTFORGE_DESKTOP_CONTROL", "1")
    monkeypatch.setattr(computer_use_tools, "_import_pyautogui", lambda: (fake, None))

    screenshot = computer_use_tools._desktop_screenshot({})
    assert screenshot.success is True
    assert Path(screenshot.output["path"]).exists()

    moved = computer_use_tools._desktop_move_mouse({"x": 10, "y": 20})
    assert moved.success is True
    clicked = computer_use_tools._desktop_click({"x": 10, "y": 20, "button": "left", "clicks": 2})
    assert clicked.success is True
    typed = computer_use_tools._desktop_type({"text": "hello"})
    assert typed.success is True
    keyed = computer_use_tools._desktop_key({"key": "a", "modifiers": ["ctrl"]})
    assert keyed.success is True
    scrolled = computer_use_tools._desktop_scroll({"amount": -120})
    assert scrolled.success is True


def test_desktop_tools_block_when_disabled(monkeypatch):
    monkeypatch.setenv("AGENTFORGE_DESKTOP_CONTROL", "0")
    result = computer_use_tools._desktop_click({"x": 1, "y": 1})
    assert result.success is False
    assert "disabled" in result.error.lower()


def test_desktop_click_validates_bounds(monkeypatch):
    fake = _FakePyAuto()
    monkeypatch.setenv("AGENTFORGE_DESKTOP_CONTROL", "1")
    monkeypatch.setattr(computer_use_tools, "_import_pyautogui", lambda: (fake, None))
    result = computer_use_tools._desktop_click({"x": 9999, "y": 20})
    assert result.success is False
    assert "out of bounds" in result.error.lower()

