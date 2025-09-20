from typing import Self
from base64 import b64decode
import ipaddress
import socket
from Pyro5.core import URI
from Pyro5.server import Daemon, expose
from Pyro5.api import Proxy, current_context
from Pyro5.errors import CommunicationError, NamingError
from pykeepass import Entry, Group
from database.db_interface import DBInterface
from database.db_local import DBLocal
from context.context import ContextApp

class DBRemote(DBInterface):

    def __init__(self, leader_uri_str: str, context: ContextApp) -> None:
        # Try to connect to make sure that the remote object is active.
        leader_uri = URI(leader_uri_str)
        proxy = Proxy(leader_uri)
        try:
            proxy._pyroBind() # Forces the connection to the remote object.
        except Exception as e:
            print(str(e))
            return False
        self._leader = proxy
        cert = proxy._pyroConnection.sock.getpeercert()
        subject = dict(x[0] for x in cert["subject"])
        self._leader_cn = subject.get("commonName")
        self._leader_uri = leader_uri_str
        self._db_local = None
        self._followers_uris = None # TODO implement access to followers as property
        self._uri = None
        self._ctx = context

    @property
    def uri(self) -> str | None:
        return self._uri

    @uri.setter
    def uri(self, value: str) -> None:
        if self._uri is not None:
            raise AttributeError("URI has already been set and cannot be modified.")
        self._uri = value

    @property
    def leader_uri(self) -> str:
        return self._leader_uri

    @classmethod
    def create_and_register(cls, leader_uri: str, context: ContextApp, password: str, path: str) -> Self | None:
        try:
            remote_db = cls(leader_uri, context)
        except (CommunicationError, NamingError):
            return None

        uri = str(context.daemon.register(remote_db))
        remote_db.uri = uri

        if not remote_db._leader.login(password, uri):
            context.daemon.unregister(remote_db)
            return None
        
        local_db_data = remote_db._leader.send_database()
        decoded_data = b64decode(local_db_data["data"])
        with open(path, "wb") as f:
            f.write(decoded_data)
        remote_db._db_local = DBLocal(path, password)
        remote_db._followers_uris = remote_db._leader.send_followers_uris()
        remote_db._followers_uris.remove(uri)
        return remote_db

    
    def add_entry(self, destination_group, title, username, passwd) -> bool:
        try:
            self._leader.add_entry(destination_group, title, username, passwd)
            self._db_local.add_entry(destination_group, title, username, passwd)
        except Exception as e:
            print(f"{e}")
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
    
    @expose
    def add_uri(self, uri: str) -> bool:
        if not self._cn_check():
            return False
        self._followers_uris.add(uri)
        self.print_message(f"A new follower was added to database {self.get_name()}")
        return True
    
    def print_message(self, message: str) -> None:
        self._ctx.print_message(message)
    
    def _cn_check(self) -> bool:
        """Checks if the client that is making a call has a common name in the allowed list"""
        client_cn = self._get_caller_cn()
        return client_cn == self._leader_cn
    
    def _get_caller_cn(self) -> str:
        """Return the Common Name of the caller"""
        cert = current_context.client.getpeercert()
        subject = dict(x[0] for x in cert["subject"])
        return subject.get("commonName")
    
    def set_name(self, name: str) -> None:
        self._db_local.set_name(name)
    
    def get_name(self) -> str:
        return self._db_local.get_name()

    def get_password(self) -> str:
        return self.db_local.get_password()
    
    def get_filename(self) -> str:
        return self._db_local.get_filename()
    
    
    def get_entries(self) -> list[Entry]:
        return self._db_local.get_entries()
    
    def get_groups(self) -> list[Group]:
        return self._db_local.get_groups()
    
    def save_changes(self) -> None:
        self._db_local.save_changes()
