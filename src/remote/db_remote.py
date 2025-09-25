from typing import Self
from base64 import b64decode
from time import time
import ipaddress
import socket
from Pyro5.core import URI
from Pyro5.server import Daemon, expose, oneway
from Pyro5.api import Proxy, current_context
from Pyro5.errors import CommunicationError, NamingError
from pykeepass import Entry, Group
from database.db_interface import DBInterface
from database.db_local import DBLocal
from context.context import ContextApp
from .remote_data_structures import Notification, ReturnCode, StatusCode, OperationData

class DBRemote(DBInterface):

    def __init__(self, leader_uri_str: str, context: ContextApp) -> None:
        # Try to connect to make sure that the remote object is active.
        leader_uri = URI(leader_uri_str)
        proxy = Proxy(leader_uri)
        proxy._pyroBind() # Forces the connection to the remote object.
        self._leader = proxy
        cert = proxy._pyroConnection.sock.getpeercert()
        subject = dict(x[0] for x in cert["subject"])
        self._leader_cn = subject.get("commonName")
        self._leader_uri = leader_uri_str
        self._db_local = None
        self._followers_uris = None # TODO implement access to followers as property
        self._uri = None
        self._db_path = None
        self._password = None
        self._ctx = context
        self._local_id = None

    @property
    def uri(self) -> str | None:
        return self._uri

    @uri.setter
    def uri(self, value: str) -> None:
        if self._uri is not None:
            raise AttributeError("URI has already been set and cannot be modified.")
        self._uri = value

    @property
    def local_id(self) -> int | None:
        return self._local_id

    @local_id.setter
    def local_id(self, value: int) -> None:
        if self._local_id is not None:
            raise AttributeError("Local ID has already been set and cannot be modified.")
        self._local_id = value

    @property
    def leader_uri(self) -> str:
        return self._leader_uri

    @classmethod
    def create_and_register(cls, leader_uri: str, context: ContextApp, password: str, path: str) -> Self | None:
        uri = None
        try:
            remote_db = cls(leader_uri, context)
            uri = str(context.daemon.register(remote_db))
            remote_db.uri = uri
            remote_db._db_path = path
            remote_db._password = password

            return_code, _ = remote_db._leader.login(password, uri)
            return_code = ReturnCode(return_code)
            match return_code:
                case ReturnCode.OK:
                    remote_db.print_message("You have joined the remote database!")
                    return remote_db
                case ReturnCode.ERROR:
                    remote_db.print_message("An error occured while trying to join the remote database!")
                    context.daemon.unregister(remote_db)
                    return None
                case ReturnCode.BANNED:
                    remote_db.print_message("You have been banned!")
                    context.daemon.unregister(remote_db)
                    return None
                case _:
                    remote_db.print_message("An unidentified error occured")
                    return None
        except (CommunicationError, NamingError):
            if uri:
                context.daemon.unregister(remote_db)
            return None
    
    def add_entry(self, destination_group: list[str], title: str, username: str, passwd: str) -> bool:
        try:
            return_code, status_code = self._leader.propose_add_entry(destination_group, title, username, passwd, self.uri)
            return self._process_return_code(return_code, status_code)
        except (CommunicationError, NamingError):
            self.print_message("Error when trying to communicate with the leader!")
            return False

    def add_group(self, parent_group: list[str], group_name: str) -> bool:
        try:
            return_code, status_code = self._leader.propose_add_group(parent_group, group_name, self.uri)
            return self._process_return_code(return_code, status_code)
        except (CommunicationError, NamingError):
            self.print_message("Error when trying to communicate with the leader!")
            return False
    
    def delete_entry(self, entry_path: list[str]) -> bool:
        try:
            return_code, status_code = self._leader.propose_delete_entry(entry_path, self.uri)
            return self._process_return_code(return_code, status_code)
        except (CommunicationError, NamingError):
            self.print_message("Error when trying to communicate with the leader!")
            return False
    
    def delete_group(self, path: list[str]) -> bool:
        try:
            return_code, status_code = self._leader.propose_delete_group(path, self.uri)
            return self._process_return_code(return_code, status_code)
        except (CommunicationError, NamingError):
            self.print_message("Error when trying to communicate with the leader!")
            return False
    
    def _process_return_code(self, return_code: ReturnCode, status_code: StatusCode) -> bool:
        return_code = ReturnCode(return_code)
        status_code = StatusCode(status_code)
        match return_code:
            case ReturnCode.OK:
                self.print_message("The request is being processed by the leader")
                return True
            case ReturnCode.ERROR:
                match status_code:
                    case StatusCode.DATABASE_CHANGE:
                        self.print_message("There is already a request being processed")
                    case StatusCode.FOLLOWER_CHANGE:
                        self.print_message("Someone is trying to join the database")
                    case StatusCode.FREE:
                        self.print_message("The database should be free, try again to request the change")
                return False
            case ReturnCode.BANNED:
                self.print_message("You have been banned!")
                return False
    
    @expose
    def add_uri(self, uri: str) -> bool:
        if not self._cn_check():
            return False
        
        self._followers_uris.add(uri)
        self.print_message(f"A new follower was added to database {self.get_name()}")
        return True
    
    @expose
    def remove_uris(self, uris: set[str]) -> bool:
        if not self._cn_check():
            return False
        
        self._followers_uris -= set(uris)
        self.print_message(f"Dead followers were removed from the database {self.get_name()}")
        return True
    
    @expose
    def receive_uris(self, uris: set[str]) -> bool:
        if not self._cn_check():
            return False
        self._followers_uris = set(uris) # Necessary cast to set, otherwise the received data is a tuple
        return True

    @expose
    def receive_db(self, db_data: bytes) -> bool:
        if not self._cn_check():
            return False
        
        decoded_data = b64decode(db_data["data"])
        with open(self._db_path, "wb") as f:
            f.write(decoded_data)
        self._db_local = DBLocal(self._db_path, self._password)
        return True
    
    def print_message(self, message: str):
        self._ctx.print_message(message)

    @oneway
    def remote_print_message(self, message: str) -> None:
        if self._cn_check():
            self._ctx.print_message(message)

    @oneway
    def add_notification(self, message: str, timestamp: float, proposition_id: int) -> None:
        notification_message = f"- {message} for database {self.get_name()}"
        self._ctx.add_notification(Notification(notification_message, timestamp, proposition_id, self.local_id))
        self.print_message(f"A new notification regarding database {self.get_name()} was added!")

    @expose
    def remote_add_entry(self, data: OperationData) -> bool:
        if not self._cn_check():
            return False
        self._db_local.add_entry(data["destination_group"], data["title"], data["username"], data["passwd"])
        self.print_message(f"A new entry was added to database {self.get_name()}")
        return True
    
    @expose
    def remote_add_group(self, data: OperationData) -> bool:
        if not self._cn_check():
            return False
        self._db_local.add_group(data["parent_group"], data["group_name"])
        self.print_message(f"A new group was added to database {self.get_name()}")
        return True
    
    @expose
    def remote_delete_entry(self, data: OperationData) -> bool:
        if not self._cn_check():
            return False
        self._db_local.delete_entry(data["entry_path"])
        self.print_message(f"An entry was deleted from database {self.get_name()}")
        return True
    
    @expose
    def remote_delete_group(self, data: OperationData) -> bool:
        if not self._cn_check():
            return False
        self._db_local.delete_group(data["path"])
        self.print_message(f"A group was deleted from database {self.get_name()}")
        return True

    def answer_notification(self, vote: bool, notification: Notification) -> bool:
        if time() > notification.timestamp:
            return False
        return self._leader.cast_vote(vote, self.uri, notification.proposition_id)
    
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
