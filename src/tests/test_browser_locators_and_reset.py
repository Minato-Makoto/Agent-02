from builtin_tools import browser_tools


class _FakeLocator:
    def __init__(self, page, label):
        self._page = page
        self._label = label

    @property
    def first(self):
        return self

    def click(self, timeout=None):
        self._page.events.append(("click", self._label, timeout))

    def fill(self, text, timeout=None):
        self._page.events.append(("fill", self._label, text, timeout))

    def wait_for(self, state="visible", timeout=None):
        self._page.events.append(("wait_for", self._label, state, timeout))


class _FakePage:
    def __init__(self):
        self.events = []
        self.url = "about:blank"

    def locator(self, selector):
        return _FakeLocator(self, f"selector:{selector}")

    def get_by_role(self, role, **kwargs):
        return _FakeLocator(self, f"role:{role}:{kwargs.get('name', '')}")

    def get_by_text(self, text):
        return _FakeLocator(self, f"text:{text}")

    def get_by_label(self, name):
        return _FakeLocator(self, f"label:{name}")


def test_browser_click_and_wait_support_user_facing_locators(monkeypatch):
    page = _FakePage()
    monkeypatch.setattr(browser_tools.BrowserManager, "get_page", staticmethod(lambda: page))

    click_result = browser_tools._click({"role": "button", "name": "Submit"})
    wait_result = browser_tools._wait({"text": "Done", "timeout": 321})

    assert click_result.success is True
    assert wait_result.success is True
    assert any(event[0] == "click" and "role:button:Submit" in event[1] for event in page.events)
    assert any(event[0] == "wait_for" and "text:Done" in event[1] for event in page.events)


def test_browser_type_supports_role_and_text_alias(monkeypatch):
    page = _FakePage()
    monkeypatch.setattr(browser_tools.BrowserManager, "get_page", staticmethod(lambda: page))

    result = browser_tools._type({"role": "textbox", "name": "Email", "text": "user@example.com"})
    assert result.success is True
    assert any(event[0] == "fill" and event[2] == "user@example.com" for event in page.events)


def test_browser_reset_context_tool(monkeypatch):
    class _ResetPage:
        url = "about:blank"

    monkeypatch.setattr(
        browser_tools.BrowserManager,
        "reset_context",
        staticmethod(lambda: _ResetPage()),
    )

    result = browser_tools._reset_context({})
    assert result.success is True
    assert result.output["status"] == "reset"
