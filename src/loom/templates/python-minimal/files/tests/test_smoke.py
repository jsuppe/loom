"""Smoke test — verify the package imports.

Replace with real tests as you write them. Loom's `loom spec --test`
will write additional skeletons alongside this one when you capture
specs.
"""
from {{ app_name }} import __version__


def test_package_imports():
    assert __version__ == "0.0.1"
