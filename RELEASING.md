# Releasing RowLint

This guide is for maintainers publishing a new package version. CI validates
changes and builds packages; it does not publish automatically.

The commands below use **0.1.1** as an example of a new patch release. Substitute
the intended version everywhere, including the Git tag and installation checks.
Use the same terminal session throughout so the temporary directory variables
remain available. The shell examples are for macOS or Linux.

## Prepare the release

1. Update `[project].version` in `pyproject.toml` on a release branch.
   `rowlint.__version__` reads installed package metadata, so the version is
   maintained in `pyproject.toml`.
2. Update the README and prepare release notes describing changes and limitations.
   README changes appear on PyPI when a new distribution is built and uploaded.
3. Reinstall the editable project to refresh its version metadata, then run the
   checks in [CONTRIBUTING.md](CONTRIBUTING.md#checks).
4. Open a pull request against `main`, wait for CI to pass, and merge it.

Every published package update, including a README update, needs a new version.
PyPI and TestPyPI do not allow replacing an uploaded distribution filename.

## Tag the merged release commit

Update your checkout and confirm it is clean and contains the intended version:

```bash
git switch main
git pull --ff-only origin main
git status --short --branch
python -m pip install -e '.[dev,parquet,polars]'
python -m rowlint --version
```

Wait for CI on the merged commit to pass. Tag that commit and push the tag:

```bash
git tag -a v0.1.1 -m "RowLint 0.1.1 release"
git push origin v0.1.1
```

Build the release from this clean, tagged commit. Keep existing release tags
pointing at their original commits.

## Build and check the distributions

Create a fresh output directory to keep artifacts from different releases apart:

```bash
rowlint_repo_dir="$PWD"
rowlint_release_dist="$(mktemp -d)"
python -m build --outdir "$rowlint_release_dist"
python -m twine check --strict "$rowlint_release_dist"/*
python scripts/smoke_install.py "$rowlint_release_dist"/*.whl "$rowlint_release_dist"/*.tar.gz
```

The smoke script installs the wheel and source archive in separate fresh
virtual environments and tests outside the source checkout. It requires
network access to install dependencies. Keep the two checked artifacts for
both uploads and the GitHub release assets.

## Upload to TestPyPI

Sign in to [TestPyPI](https://test.pypi.org/), verify your account, and create an
[API token](https://test.pypi.org/manage/account/#api-tokens). TestPyPI accounts
and tokens are separate from those on PyPI. For the first upload of a new
project, use an account-wide token; once the project exists, a project-scoped
token can be used.

```bash
python -m twine upload --repository testpypi --username __token__ "$rowlint_release_dist"/*
```

Paste the TestPyPI token at the password prompt, including its `pypi-` prefix.
Check the [TestPyPI project page](https://test.pypi.org/project/rowlint/).

Verify the published package in a fresh environment. Install dependencies from
PyPI first, then download RowLint specifically from TestPyPI:

```bash
rowlint_test_dir="$(mktemp -d)"
python -m venv "$rowlint_test_dir/venv"
"$rowlint_test_dir/venv/bin/python" -m pip install --index-url https://pypi.org/simple/ 'pandas>=2.2,<4' 'PyYAML>=6,<7'
"$rowlint_test_dir/venv/bin/python" -m pip install --index-url https://test.pypi.org/simple/ --no-deps rowlint==0.1.1
"$rowlint_test_dir/venv/bin/python" -m pip check
cd "$rowlint_test_dir"
"$rowlint_test_dir/venv/bin/rowlint" --version
"$rowlint_test_dir/venv/bin/rowlint" "$rowlint_repo_dir/data.csv"
cd "$rowlint_repo_dir"
```

Confirm the version is `rowlint 0.1.1` and the sample dataset is profiled
successfully. Running outside the checkout ensures the installed package is
being used. Each command above is a complete line; copy it without adding
backslashes between arguments.

If verification requires a package change, prepare a new version and tag,
rebuild, and repeat TestPyPI verification before publishing to PyPI.

## Publish to PyPI

Sign in to [PyPI](https://pypi.org/), verify your account, complete its two-factor
setup, and create a [PyPI API token](https://pypi.org/manage/account/#api-tokens).
Use that token for the following upload:

```bash
python -m twine upload --username __token__ "$rowlint_release_dist"/*
```

Upload the exact files tested on TestPyPI. Check the
[PyPI project page](https://pypi.org/project/rowlint/), then verify an installation
from PyPI in another fresh environment:

```bash
rowlint_pypi_dir="$(mktemp -d)"
python -m venv "$rowlint_pypi_dir/venv"
"$rowlint_pypi_dir/venv/bin/python" -m pip install --index-url https://pypi.org/simple/ rowlint==0.1.1
"$rowlint_pypi_dir/venv/bin/python" -m pip check
cd "$rowlint_pypi_dir"
"$rowlint_pypi_dir/venv/bin/rowlint" --version
"$rowlint_pypi_dir/venv/bin/rowlint" "$rowlint_repo_dir/data.csv"
cd "$rowlint_repo_dir"
```

## Create the GitHub release

Create a release at [GitHub Releases](https://github.com/dotserver/rowlint/releases)
using the existing `v0.1.1` tag. Include a short description of the changes,
installation instructions, relevant limitations, and a link to the PyPI page.
Optionally attach the same wheel and source archive from
`$rowlint_release_dist` as release assets.

Further guidance: [Python packaging tutorial](https://packaging.python.org/en/latest/tutorials/packaging-projects/)
and [GitHub release documentation](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).
