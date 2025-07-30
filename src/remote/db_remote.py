from typing import Self
from Pyro5.core import URI
from Pyro5.server import Daemon, expose
from Pyro5.api import Proxy
from Pyro5.errors import CommunicationError, NamingError, TimeoutError, ConnectionClosedError
from database.db_interface import DBInterface
from database.db_local import DBLocal

class DBExpose(DBInterface):

    def __init__(self, db_local: DBLocal, leader_uri: URI) -> None:
        self._db_local = db_local
        self._followers = [] # TODO implement access to followers as property
        self._leader = None

        # Try to connect to make sure that the remote object is active
        try:
            proxy = Proxy(leader_uri)
            proxy._pyroBind()  # Forces connection to the remote object
            self._leader = proxy
        except CommunicationError as e:
            print(f"Could not connect to the remote object: {e}")
        except NamingError as e:
            print(f"Problem with name resolution: {e}")

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
    def create_and_register(cls, db_local: DBLocal, leader_uri: URI, daemon: Daemon) -> Self:
        remote_db = cls(db_local, leader_uri)
        uri = daemon.register(remote_db)
        remote_db.uri = uri
        print(uri)
        # TODO request addition to the followers list of the leader.
        # TODO request list of URIs belonging to the other followers.
        return remote_db

    @expose
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