from typing import Self
from base64 import b64decode
from Pyro5.core import URI
from Pyro5.server import Daemon, expose
from Pyro5.api import Proxy
from Pyro5.errors import CommunicationError, NamingError
from pykeepass import Entry, Group
from database.db_interface import DBInterface
from database.db_local import DBLocal

class DBRemote(DBInterface):

    def __init__(self, leader_uri: URI) -> None:
        # Try to connect to make sure that the remote object is active.
        proxy = Proxy(leader_uri)
        proxy._pyroBind()  # Forces connection to the remote object.
        self._leader = proxy
        local_db_data = self._leader.send_database()
        decoded_data = b64decode(local_db_data["data"])
        # TODO after adding mDNS, use the name of the exposed db to create the filename
        # or ask the user where they want to save it.
        with open("tmp/tmp.kdbx", "wb") as f:
            f.write(decoded_data)
        # TODO add password as a parameter, this is provided by the user because he needs to
        # know it in order to connect
        self._db_local = DBLocal("tmp/tmp.kdbx", passwd="prova")
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
    def create_and_register(cls, leader_uri: URI, daemon: Daemon) -> Self:
        remote_db = cls(leader_uri)
        uri = daemon.register(remote_db)
        remote_db.uri = uri
        print(uri)
        # TODO request addition to the followers list of the leader.
        # TODO request list of URIs belonging to the other followers.
        return remote_db

    
    def add_entry(self, destination_group, title, username, passwd) -> bool:
        try:
            self._leader.add_entry(destination_group, title, username, passwd)
            self._db_local.add_entry(destination_group, title, username, passwd)
        except:
            return False
        
        return True

    def add_group(self, parent_group: list[str], group_name: str) -> bool:
        try:
            self._db_local.add_group(parent_group, group_name)
        except:
            return False
        return True
    
    def delete_entry(self, entry_path: list[str]) -> bool:
        try:
            self._db_local.delete_entry(entry_path)
        except:
            return False
        return True
    
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