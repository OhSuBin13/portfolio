import tomllib
from pathlib import Path


def test_backend_package_includes_runtime_schema_sql() -> None:
    pyproject_path = Path(__file__).parents[1] / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    assert pyproject["build-system"]["build-backend"] == "setuptools.build_meta"
    assert any(
        requirement.startswith("setuptools")
        for requirement in pyproject["build-system"]["requires"]
    )
    assert (
        "schema.sql"
        in pyproject["tool"]["setuptools"]["package-data"]["portfolio_app"]
    )
