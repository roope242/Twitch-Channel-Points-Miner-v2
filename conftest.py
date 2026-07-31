# Present so `pytest` works from the repo root, not only `python -m pytest`.
# The package is not pip-installed for the tests, and only the module form puts
# the working directory on sys.path -- without this file the bare `pytest`
# command dies at collection with ModuleNotFoundError.
