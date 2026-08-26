# AGENTS.md — simplerr web framework

## Commands

### Development & Testing
- `python -m simplerr runserver` - Start dev server (default: http://localhost:9000/)
- `-r <template_dir>` - Serve templates from custom directory, `--reload` to auto-reload
- `-t <template_module>` - Load templates from a custom Jinja module
- `python tests/run.py [tests]` - Run test suite, `-m <module>` to run subset (from CLI)
- Install peewee for DB tests: `pip install peewee`

### Packaging
- `python -m build` - Build wheel/sdist with hatchling (defined in pyproject.toml)
- `pip install .` - Install from source dir

## Architecture

### Project Structure
```
src/simplerr/     # Framework package - entry point `from simplerr import web`
tests/           # Custom unittest runner in tests/run.py, asset test fixtures
examples/        # Quickstart guide and sample projects
```

### Run Order
- Tests must import from `src` (tests/run.py appends src to sys.path)
- Template tests may require template module: `-t <module_name>` or `templates/<dir>`

### Key Modules
- `web.py` - Route decorator (`@web(path, template=None)`), debug server entry point
- `__init__.py` - Exports `web`, HTTP methods (GET, POST), `Request/Response` wrappers
- `config.py` - Config class for app settings
- `dispatcher.py` - WSGI entry point
- `serialise.py` - JSON response handling (`tojson`)
- `template.py` - Render return values as Jinja templates
- `session.py` / `globals.py` - Session/request storage helpers

### Routes & Decorators
- `@web(path, template='template_name', methods=[...])` - register route decorated function
  - `path`: e.g. `/user/<int:id>` uses werkzeug converters; `<converter(args):name>`
  - `template`: string path to Jinja template or Python module with `Template.get` class
  - Returns: dict/list → render as template context; callable → return result directly
- `@web(path, file=True)` - Serve static files from `<path>/<file>`
- Methods: `GET/POST/PUT/DELETE/PATCH` (defined in `methods.py`)

### Debug Server
- `python -m simplerr runserver [options]` implements a WSGI server that auto-reloads code;
- Pressing Ctrl+C once stops the server, but the underlying process keeps running

### Testing
Hybrid unittest/pytest pattern. Test modules can use:
- `unittest.TestCase` base: run via `python tests/run.py [test_module]` or `python -m unittest tests.test_module`
- `pytest` functions/fixtures: run via `pytest tests/` or `pytest tests/test_module.py`
- Use `-m <test_module>` (run.py CLI) or `pytest -k <test_name>` to target specific tests
- Asset scripts and fixtures live in `tests/assets/`; use `-a <script>` (run.py) or copy to test directory

## Development Notes

### Environment
- Python 3.6+ (pyproject.toml requires-python = ">=3.6")
- Dependencies defined in pyproject.toml under `[project.dependencies]` and `[project.optional-dependencies]`
- Virtual env recommended: `python3 -m venv .venv`, activate, then `pip install -e .`

### Templates
- Default look in `<project>/templates/` relative to the template class path; `Template.get(name, **ctx)` finds them
- Or define a custom class with `get` method pointing to templates in module:
  ```python
  from jinja2 import Environment
  class MyAppTemplate:
      env = Environment(loader=DirectoryLoader('templates'))
      def get(self, name): return self.env.get_template(name)
  ```

### Database (Peewe) - Quick Reference
- `db = SqliteDatabase('name.db')` + `db.connect()` + `db.create_tables([Model])`
- Models are automatically bound to templates when returned from route

## Constraints & Quirks

### No CI
- Repository has no GitHub Actions or other CI. Testing is manual/CLI-only.

### Test Runner Oddity
- `tests/run.py` handles discovery - tests in `tests/modules.simplerr.*` are detected dynamically; others require `python tests/run.py [module_name]`
- Run specific test module with standard unittest: `python tests/run.py test_module` or `python -m unittest tests.test_module`
- Run pytest directly on any module: `pytest tests/test_module.py` (works for both unittest.TestCase and pytest-based tests)
- No `.pytestini` or pytest.ini found in repo; use `pyproject.toml` for project config only

### Python Version
- pyproject.toml declares `>=3.6`. If using modern features like type hints with generics or `__future__.annotations`, verify Python 3.10+ availability first.
