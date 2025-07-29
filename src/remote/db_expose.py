from typing import Self
from Pyro5.server import Daemon, expose
from Pyro5.core import URI
from pykeepass import Entry, Group
from database.db_interface import DBInterface
from database.db_local import DBLocal

class DBExpose(DBInterface):

    def __init__(self, db_local: DBLocal) -> None:
        self._db_local = db_local
        self._followers = [] # TODO implement access to followers as property
        self._uri = None

    @property
    def uri(self) -> URI | None:
        return self._uri

    @uri.setter
    def uri(self, value: URI) -> None:
        if self._uri is not None:
            raise AttributeError("URI has already been set and cannot be modified.")
        self._uri = value

    @classmethod
    def create_and_register(cls, db_local: DBLocal, daemon: Daemon) -> Self:
        obj = cls(db_local)
        uri = daemon.register(obj)
        obj.uri = uri
        print()
    
    def add_entry(self, destination_group, title, username, passwd) -> None:
        try:
            self._db_local.add_entry(destination_group, title, username, passwd)
        except:
            return False
        
        return True

    @expose
    def add_group(self, parent_group: list[str], group_name: str) -> bool:
        try:
            self._db_local.add_group(parent_group, group_name)
        except:
            return False
        return True
    
    @expose
    def delete_entry(self, entry_path: list[str]) -> bool:
        try:
            self._db_local.delete_entry(entry_path)
        except:
            return False
        return True
    
    @expose
    def delete_group(self, path: list[str]) -> bool:
        try:
            self._db_local.delete_group(path)
        except:
            return False
        return True
    
    def get_name(self) -> str:
        return self._db_local.get_name()
    
    def get_filename(self) -> str:
        return self._db_local.get_filename()
    
    
    def get_entries(self) -> list[Entry]:
        return self._db_local.get_entries()
    
    def get_groups(self) -> list[Group]:
        return self._db_local.get_groups()
    
    def save_changes(self) -> None:
        self._db_local.save_changes()