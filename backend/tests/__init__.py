"""Makes `tests` a package so conftest is imported exactly once.

Without this, pytest imports the conftest by path as top-level `conftest`, while
`from tests.conftest import ...` in a test module imports it a second time under
a different name. The two copies define *different* class objects, so a
`pytest.raises(LiveApiCallAttempted)` cannot catch the exception the guard
raises — same name, same file, unequal types.
"""
