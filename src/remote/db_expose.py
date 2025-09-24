from typing import Self
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import time, sleep
from uuid import uuid4
from Pyro5.server import Daemon, expose
from Pyro5.errors import CommunicationError, NamingError
from Pyro5.core import URI
from Pyro5.api import Proxy, current_context
from pykeepass import Entry, Group
from database.db_interface import DBInterface
from database.db_local import DBLocal
from context.context import ContextApp
from .remote_data_structures import StatusCode, Operation, OperationData, ReturnCode, Notification

class DBExpose(DBInterface):

    def __init__(self, db_local: DBLocal, context: ContextApp) -> None:
        self._db_local = db_local
        self._followers_cn = {} # followers Common Names
        self._uri = None # leader URI
        self._ctx = context
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._operation_lock = Lock()
        self._vote_lock = Lock()
        self._current_proposal = None
        self._status = StatusCode.FREE
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
        return self._db_local.local_id

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
        return set(self._followers_cn.keys())

    @expose
    def login(self, password: str, uri: str) -> tuple[ReturnCode, StatusCode]:
        """Check if the client knows the password. This allows to modify the shared database"""
        if not self._operation_lock.acquire(timeout=5):
            return (ReturnCode.ERROR, self._status)

        self._status = StatusCode.FOLLOWER_CHANGE

        if not password == self.get_password():
            return (ReturnCode.ERROR, self._status)
        
        caller_cn = self._get_caller_cn()
        client_uri = URI(uri)
        proxy = Proxy(client_uri)

        try:
            proxy._pyroBind()
            dead_followers = set()
            has_failure = False

            # Inform the followers that a new one is joining.
            for follower_uri in self._followers_cn:
                with Proxy(URI(follower_uri)) as follower_proxy:
                    follower_proxy._pyroTimeout = 5.0 # Wait at most 5 seconds to establish a connection, 
                                                      # otherwise the follower is overwhelmed with connections and can't respond.
                    try:
                        if not follower_proxy.add_uri(uri):
                            has_failure = True
                    except (CommunicationError, NameError):
                        dead_followers.add(follower_uri)

            # Cleanup dead followers.
            while len(dead_followers) > 0:
                new_dead_followers = set() # Other followers could stop responding, so we delete them too.
                                           # The loop will eventually end because in the worst case every follower is removed.
                for dead_follower in dead_followers:
                    del self._followers_cn[dead_follower]
    
                for follower_uri in self._followers_cn:
                    with Proxy(URI(follower_uri)) as follower_proxy:
                        follower_proxy._pyroTimeout = 5.0
                        try:
                            follower_proxy.remove_uris(dead_followers)
                        except (CommunicationError, NameError):
                            new_dead_followers.add(follower_uri)
                dead_followers = new_dead_followers

            with open(self.get_filename(), "rb") as f:
                db_data = f.read()
            if not proxy.receive_db(db_data):
                return (ReturnCode.ERROR, self._status)
            if not proxy.receive_uris(set(self._followers_cn.keys())):
                return (ReturnCode.ERROR, self._status)
            proxy._pyroRelease()
        except (CommunicationError, NameError):
            return (ReturnCode.ERROR, self._status)
            
        self._followers_cn[uri] = caller_cn
        self._status = StatusCode.FREE
        self._operation_lock.release()
    
        if has_failure:
            self.print_message(f"A client was added to database {self.get_name()} but some of the followers couldn't add them")
        else:
            self.print_message(f"A client was added to database {self.get_name()}")

        return (ReturnCode.OK, self._status)
    
    @expose
    def propose_add_entry(self, destination_group: list[str], title: str, username: str, passwd: str, uri: str) -> tuple[ReturnCode, StatusCode]:
        # Remember to check if the requester is in the cn list.
        if not self._operation_lock.acquire(timeout=5):
            return (ReturnCode.ERROR, self._status)
        
        self._status = StatusCode.DATABASE_CHANGE
        self._executor.submit(self.propose_change, Operation.ADD_ENTRY, {"destination_group": destination_group, "title": title, "username": username, "passwd": passwd}, uri)
        return (ReturnCode.OK, self._status)
    
    @expose
    def propose_add_group(self, parent_group: list[str], group_name: str, uri: str) -> tuple[ReturnCode, StatusCode]:
        if not self._operation_lock.acquire(timeout=5):
            return (ReturnCode.ERROR, self._status)
        
        self._status = StatusCode.DATABASE_CHANGE
        self._executor.submit(self.propose_change, Operation.ADD_GROUP, {"parent_group": parent_group, "group_name": group_name}, uri)
        return (ReturnCode.OK, self._status)

    @expose
    def propose_delete_entry(self, entry_path: list[str], uri: str) -> tuple[ReturnCode, StatusCode]:
        if not self._operation_lock.acquire(timeout=5):
            return (ReturnCode.ERROR, self._status)
        
        self._status = StatusCode.DATABASE_CHANGE
        self._executor.submit(self.propose_change, Operation.DELETE_ENTRY, {"entry_path": entry_path}, uri)
        return (ReturnCode.OK, self._status)

    @expose
    def propose_delete_group(self, path: list[str], uri: str) -> tuple[ReturnCode, StatusCode]:
        if not self._operation_lock.acquire(timeout=5):
            return (ReturnCode.ERROR, self._status)
        
        self._status = StatusCode.DATABASE_CHANGE
        self._executor.submit(self.propose_change, Operation.DELETE_GROUP, {"path": path}, uri)
        return (ReturnCode.OK, self._status)
    
    def propose_change(self, operation: Operation, data: OperationData, uri: str) -> None:
        # Maybe add a flag inside every db remote after they receive the notification or a version number in order to understand if someone is in un inconsistent state when the leader
        # closes the exposed db while a change request is taking place.
        notification_message = ""
        match operation:
            case Operation.ADD_ENTRY:
                notification_message = f"Entry addition titled {data["username"]} with username {data["username"]} and password {data["passwd"]} in path {'/'.join(data["destination_group"])}"
            case Operation.ADD_GROUP:
                notification_message = f"Group addition named {data["group_name"]} in parent group {'/'.join(data["parent_group"])}"
            case Operation.DELETE_ENTRY:
                notification_message = f"Entity elimination with path {'/'.join(data["entry_path"])}"
            case Operation.DELETE_GROUP:
                notification_message = f"Group elimination with path {'/'.join(data["path"])}"
            case _:
                with Proxy(URI(uri)) as proxy:
                    proxy._pyroTimeout = 5.0
                    proxy.remote_print_message("The specified operation is not supported")
                    return
                
        proposition_id = uuid4().int
        # TODO Remember to remove the requester (because they are obviously in favor)
        self._current_proposal = {
                    "votes": [],
                    "voters": set(),
                    "deadlines": None
                }
        followers_uris = (follower_uri for follower_uri in self._followers_cn.keys() if follower_uri != uri)
        for follower_uri in followers_uris:
            with Proxy(URI(follower_uri)) as follower_proxy:
                follower_proxy._pyroTimeout = 5.0 # Wait at most 5 seconds to establish a connection, 
                                                  # otherwise the follower is overwhelmed with connections and can't respond.
                try:
                    follower_proxy.add_notification(notification_message, time(), proposition_id)
                except (CommunicationError, NameError):
                    self.print_message(f"A follower was unreachable during a change proposition for database {self.get_name()}")

        if uri != self.uri:
            self.add_notification(notification_message, time(), proposition_id)
        
        sleep(30) # Wait for answers

        self._status = StatusCode.FREE
        self._current_proposal = None
        self._operation_lock.release()
        
    def _cn_check(self) -> bool:
        """Checks if the client that is making a call has a common name in the allowed list"""
        client_cn = self._get_caller_cn()
        return client_cn in self._followers_cn.values()
    
    def _get_caller_cn(self) -> str:
        """Return the Common Name of the caller"""
        cert = current_context.client.getpeercert()
        subject = dict(x[0] for x in cert["subject"])
        return subject.get("commonName")
    
    @expose
    def cast_vote(self, vote: bool) -> bool:
        return True  
    
    def add_notification(self, message: str, timestamp: float, proposition_id: int) -> None:
        notification_message = f"- {message} for database {self.get_name()}"
        self._ctx.add_notification(Notification(notification_message, timestamp, proposition_id, self.local_id))
        self.print_message(f"A new notification regarding database {self.get_name()} was added!")
    
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
