from typing import Self
import ipaddress
from Pyro5.server import Daemon, expose
from Pyro5.errors import CommunicationError, NamingError
from Pyro5.core import URI
from Pyro5.api import Proxy, current_context
from pykeepass import Entry, Group
from database.db_interface import DBInterface
from database.db_local import DBLocal
from context.context import ContextApp

class DBExpose(DBInterface):

    def __init__(self, db_local: DBLocal, context: ContextApp) -> None:
        self._db_local = db_local
        self._followers_cn = set() # followers Common Names
        self._followers_uris = set() # followers URIs
        self._uri = None # leader URI
        self._ctx = context

    @property
    def uri(self) -> str | None:
        return self._uri

    @uri.setter
    def uri(self, value: str) -> None:
        if self._uri is not None:
            raise AttributeError("URI has already been set and cannot be modified.")
        self._uri = value

    @classmethod
    def create_and_register(cls, db_local: DBLocal, context: ContextApp) -> Self:
        obj = cls(db_local, context)
        uri = context.daemon.register(obj)
        obj.uri = str(uri)
        return obj
    
    @expose
    def add_entry(self, destination_group: list[str], title: str, username: str, passwd: str) -> bool:
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
        if not self._cn_check():
            return None
        with open(self.get_filename(), "rb") as f:
            return f.read()
    
    @expose
    def send_followers_uris(self) -> set[str]:
        if not self._cn_check():
            return set()
        return self._followers_uris

    @expose
    def login(self, password: str, uri: str) -> bool:
        """Check if the client knows the password. This allows to modify the shared database"""
        if not password == self.get_password():
            return False
        
        caller_cn = self._get_caller_cn()
        client_uri = URI(uri)
        proxy = Proxy(client_uri)

        try:
            proxy._pyroBind()
            has_failure = False
            # TODO handle the case where one of the followers disconnected but it's still in the followers list
            for follower_uri in self._followers_uris:
                with Proxy(URI(follower_uri)) as follower_proxy:
                    follower_proxy._pyroTimeout = 5.0
                    try:
                        if not follower_proxy.add_uri(uri):
                            has_failure = True
                    except CommunicationError:
                        pass
            self._followers_cn.add(caller_cn)
            self._followers_uris.add(uri)
            proxy._pyroRelease()
        except Exception as e:
            self.print_message(f"Something went wrong: {e}")
            return False
    
        if has_failure:
            self.print_message(f"A client was added to database {self.get_name()} but one of the followers couldn't add them")
        else:
            self.print_message(f"A client was added to database {self.get_name()}")

        return True
        
    def _cn_check(self) -> bool:
        """Checks if the client that is making a call has a common name in the allowed list"""
        client_cn = self._get_caller_cn()
        return client_cn in self._followers_cn
    
    def _get_caller_cn(self) -> str:
        """Return the Common Name of the caller"""
        cert = current_context.client.getpeercert()
        subject = dict(x[0] for x in cert["subject"])
        return subject.get("commonName")
    
    def print_message(self, message: str) -> None:
        self._ctx.print_message(message)
    
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
