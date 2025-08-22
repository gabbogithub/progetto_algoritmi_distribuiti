from typing import Self
import ipaddress
from Pyro5.server import Daemon, expose
from Pyro5.core import URI
from Pyro5.api import current_context
from pykeepass import Entry, Group
from database.db_interface import DBInterface
from database.db_local import DBLocal

class DBExpose(DBInterface):

    def __init__(self, db_local: DBLocal) -> None:
        self._db_local = db_local
        self._followers = [] # followers proxy objects
        self._ips = set() # followers IPs TODO implement access to followers as property
        self._uris = set() # followers URIs
        self._uri = None # leader URI

    @property
    def uri(self) -> str | None:
        return self._uri

    @uri.setter
    def uri(self, value: str) -> None:
        if self._uri is not None:
            raise AttributeError("URI has already been set and cannot be modified.")
        self._uri = value

    @classmethod
    def create_and_register(cls, db_local: DBLocal, daemon: Daemon) -> Self:
        obj = cls(db_local)
        uri = daemon.register(obj)
        obj.uri = str(uri)
        return obj
    
    @expose
    def add_entry(self, destination_group, title, username, passwd) -> bool:
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
    
    @expose
    def send_database(self) -> bytes | None:
        if not self._ip_check():
            return None
        with open(self.get_filename(), "rb") as f:
            return f.read()
    
    @expose
    def send_followers_uris(self) -> set:
        if not self._ip_check():
            return set()
        return self._uris

    @expose
    def login(self, password: str, uri: str) -> bool:
        """Check if client knows the password. This allows to modify the shared database"""
        if password == self.get_password():
            client_ip = current_context.client_sock_addr[0]
            ip_int = int(ipaddress.IPv4Address(client_ip))
            self._ips.add(ip_int)
            self._uris.add(uri)
            return True
        
        return False
    
    def _ip_check(self) -> bool:
        """Checks if the ip making a call is in the allowed list"""

        client_ip = current_context.client_sock_addr[0]
        ip_int = int(ipaddress.IPv4Address(client_ip))
        return ip_int in self._ips
    
    def unregister_object(self, daemon: Daemon) -> None:
        daemon.unregister(self)
    
    def get_name(self) -> str:
        return self._db_local.get_name()

    def get_password(self) -> str:
        return self._db_local.get_password()
    
    def get_filename(self) -> str:
        return self._db_local.get_filename()
    
    
    def get_entries(self) -> list[Entry]:
        return self._db_local.get_entries()
    
    def get_groups(self) -> list[Group]:
        return self._db_local.get_groups()
    
    def save_changes(self) -> None:
        self._db_local.save_changes()
