# Publishing to PyPI

This package ships **Python backend + CLI** only. The React frontend remains in the Git repository (install via `setup_env.sh` / `npm`).

## Prerequisites

```bash
pip install build twine
# or: pip install -e ".[dev]"
```

Register accounts:

- Test PyPI: https://test.pypi.org/account/register/
- Production PyPI: https://pypi.org/account/register/

Create `~/.pypirc` or use `twine` prompts / API tokens (recommended).

## Build

From repository root:

```bash
# Optional: refresh core/_bundled from repo config/ + data/
python scripts/sync_bundled.py

rm -rf dist/ build/ *.egg-info dataevolver.egg-info
python -m build
```

Artifacts:

- `dist/dataevolver-0.1.0-py3-none-any.whl`
- `dist/dataevolver-0.1.0.tar.gz`

Inspect the wheel (optional):

```bash
unzip -l dist/dataevolver-*.whl | head -40
```

## Upload to Test PyPI

**两种方式都可以**（二选一即可）：

1. **命令行（推荐）** — 用 `twine` 上传本地 `dist/` 里的包，适合重复发布、CI：
   ```bash
   python -m twine upload --repository testpypi dist/*
   ```
   首次会提示输入用户名、密码；更稳妥的是到 [test.pypi.org → Account settings → API tokens](https://test.pypi.org/manage/account/token/) 创建 token，用户名填 `__token__`，密码填 `pypi-...`。

2. **网页手动上传** — 登录 [test.pypi.org](https://test.pypi.org/) → 「Your projects」→ 「Upload a package」→ 选择 `dist/*.whl` 或 `.tar.gz`。适合只发一两次、不想配 token 的情况。

文档里写的是方式 1；不是必须命令行，只是维护者更常用。

Install from Test PyPI:

```bash
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ dataevolver
```

Smoke test in a fresh directory:

```bash
mkdir /tmp/de-pypi-test && cd /tmp/de-pypi-test
dataevolver init
dataevolver --help
dataevolver-server --help  # or: python -m run_server --help
```

Configure `config/api_keys.json`, then run a minimal workflow if desired.

## Upload to production PyPI

After Test PyPI validation:

```bash
python -m twine upload dist/*
```

## Version bumps

1. Edit `version` in `pyproject.toml`
2. Rebuild and upload new artifacts
3. Tag the git release (optional): `git tag v0.1.1`

## What gets published

| Included | Excluded |
|----------|----------|
| `core/`, `subsystems/`, `web/`, `cli/` | `frontend/` |
| `core/_bundled/` default config & operator registry | `data/` runtime artifacts |
| `run_server.py`, entry points | `assets/` paper figures |
| `examples/operator_template.json` | `tmp/` sample datasets |

## End-user workflow (PyPI)

```bash
pip install dataevolver
mkdir my_project && cd my_project
dataevolver init
# edit config/api_config.json & config/api_keys.json
dataevolver session-start demo --raw ... --seed ...
dataevolver workflow advance-all demo --max-steps 32
```

For Web UI, clone the GitHub repo and run `bash setup_env.sh` (requires Node.js).
