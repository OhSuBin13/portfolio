import sqlite3
from typing import Annotated, get_args, get_origin

from portfolio_app.api import get_db
from portfolio_app.api.dependencies import Db


def test_db_dependency_alias_uses_get_db():
    connection_type, dependency = get_args(Db)

    assert get_origin(Db) is Annotated
    assert connection_type is sqlite3.Connection
    assert dependency.dependency is get_db
