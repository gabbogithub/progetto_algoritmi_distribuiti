from collections.abc import ItemsView
import threading
from Pyro5.server import Daemon
from database.db_interface import DBInterface

class ContextApp():
    """Context class that holds essential values used by different compontents
    of the application."""
    def __init__(self):
        self._dbs = {}
        self._counter = 0
        self.daemon = Daemon()

    def start_daemon_loop(self) -> None:
        """Starts the Pyro5 daemon in a separate thread."""
        threading.Thread(target=self.daemon.requestLoop, daemon=True).start()

    def add_database(self, db: DBInterface) -> None:
        """Adds a new database to the context and returns its unique ID."""
        self._counter += 1
        self._dbs[self._counter] = db

    def remove_database(self, db_id: int) -> DBInterface | None:
        """Removes a database by its ID and returns it."""
        return self._dbs.pop(db_id, None)
    
    def replace_database(self, db_id: int, new_db: DBInterface) -> None:
        """Replaces the database at the given ID with the one passed as argument."""
        self._dbs[db_id] = new_db

    def get_database(self, db_id: int) -> DBInterface | None:
        """Retrieves a database by its ID."""
        return self._dbs.get(db_id)
    
    def get_indexes_databases(self) -> ItemsView[int, DBInterface]:
        """Return all the dbs and their indexes"""
        return self._dbs.items()