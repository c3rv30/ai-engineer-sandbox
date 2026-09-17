import pytest


def pytest_collection_modifyitems(config, items):
    evals_dir = config.rootpath / "tests" / "evals"
    for item in items:
        if item.path.is_relative_to(evals_dir):
            item.add_marker(pytest.mark.eval)
