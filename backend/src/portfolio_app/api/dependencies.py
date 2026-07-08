import sqlite3
from typing import Annotated

from fastapi import Depends

from portfolio_app.api import get_db

Db = Annotated[sqlite3.Connection, Depends(get_db)]
