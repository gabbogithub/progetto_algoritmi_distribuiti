from typing import Self
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import time, sleep
from uuid import uuid4
from Pyro5.server import Daemon, expose, oneway
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
        self._followers_id = {} # followers IDs
        self._uri = None # leader URI
        self._is_leader = True
        self._ctx = context
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._operation_lock = Lock()
        self._vote_lock = Lock()
        self._followers_lock = Lock()
        self._leader_lock = Lock()
        self._current_proposition = None
        self._status = StatusCode.FREE

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
    
    def add_entry(self, destination_group: list[str], title: str, username: str, passwd: str) -> bool:
        if not self._operation_lock.acquire(timeout=5):
            self._process_status_code(self._status, False)
            return False
        
        self._status = StatusCode.DATABASE_CHANGE
        self._executor.submit(self.propose_change, Operation.ADD_ENTRY, {"destination_group": destination_group, "title": title, "username": username, "passwd": passwd}, self.uri)
        self._process_status_code(self._status, True)
        return True

    def add_group(self, parent_group: list[str], group_name: str) -> bool:
        if not self._operation_lock.acquire(timeout=5):
            self._process_status_code(self._status, False)
            return False
        
        self._status = StatusCode.DATABASE_CHANGE
        self._executor.submit(self.propose_change, Operation.ADD_GROUP, {"parent_group": parent_group, "group_name": group_name}, self.uri)
        self._process_status_code(self._status, True)
   
        return True
    
    def delete_entry(self, entry_path: list[str]) -> bool:
        if not self._operation_lock.acquire(timeout=5):
            self._process_status_code(self._status, False)
            return False
        
        self._status = StatusCode.DATABASE_CHANGE
        self._executor.submit(self.propose_change, Operation.DELETE_ENTRY, {"entry_path": entry_path}, self.uri)
        self._process_status_code(self._status, True)

        return True
    
    def delete_group(self, path: list[str]) -> bool:
        if not self._operation_lock.acquire(timeout=5):
            self._process_status_code(self._status, False)
            return False
        
        self._status = StatusCode.DATABASE_CHANGE
        self._executor.submit(self.propose_change, Operation.DELETE_GROUP, {"path": path}, self.uri)
        self._process_status_code(self._status, True)
        
        return True
    
    def _process_status_code(self, status_code: StatusCode, lock_acquired: bool) -> None:
        if lock_acquired:
            self.print_message("You request is being processed")
        else:
            match status_code:
                case StatusCode.FOLLOWER_CHANGE:
                    self.print_message("I was unable to proceed with the request because someone is trying to join the database")
                case StatusCode.DATABASE_CHANGE:
                    self.print_message("I was unable to proceed with the request because there is already a pending request")
                case StatusCode.FREE:
                    self.print_message("I was unable to proceed with the request but the database should be free, try again")
    
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
            unique_id = uuid4().int
            dead_followers = set()
            has_failure = False

            with open(self.get_filename(), "rb") as f:
                db_data = f.read()
            if not proxy.receive_db(db_data):
                return (ReturnCode.ERROR, self._status)
            with self._followers_lock:
                uris_ids_snapshot = self._followers_id.copy() # Because other threads might modify the dictionary while I iterate.
                uris_cns_snapshot = self._followers_cn.copy()
            if not proxy.receive_uris(uris_ids_snapshot, uris_cns_snapshot):
                return (ReturnCode.ERROR, self._status)
            if not proxy.set_unique_id(unique_id):
                return (ReturnCode.ERROR, self._status)
            proxy._pyroRelease()

            # Inform the followers that a new one is joining.
            with self._followers_lock:
                uris_snapshot = list(self._followers_cn.keys())
            for follower_uri in uris_snapshot:
                with Proxy(URI(follower_uri)) as follower_proxy:
                    follower_proxy._pyroTimeout = 5.0 # Wait at most 5 seconds to establish a connection, 
                                                      # otherwise the follower is overwhelmed with connections and can't respond.
                    try:
                        if not follower_proxy.add_uri(uri, unique_id, caller_cn):
                            has_failure = True
                    except (CommunicationError, NamingError):
                        dead_followers.add(follower_uri)
            
            self._followers_cleanup(dead_followers)

        except (CommunicationError, NamingError):
            return (ReturnCode.ERROR, self._status)
            
        with self._followers_lock:
            self._followers_cn[uri] = caller_cn
            self._followers_id[uri] = unique_id
        self._status = StatusCode.FREE
        self._operation_lock.release()
    
        if has_failure:
            self.print_message(f"A client was added to database {self.get_name()} but some of the followers couldn't add them")
        else:
            self.print_message(f"A client was added to database {self.get_name()}")

        return (ReturnCode.OK, self._status)
    
    @expose
    def propose_add_entry(self, destination_group: list[str], title: str, username: str, passwd: str, uri: str) -> tuple[ReturnCode, StatusCode]:
        if not self._cn_check():
            return (ReturnCode.ERROR, self._status)
        
        if not self._operation_lock.acquire(timeout=5):
            return (ReturnCode.ERROR, self._status)
        
        self._status = StatusCode.DATABASE_CHANGE
        self._executor.submit(self.propose_change, Operation.ADD_ENTRY, {"destination_group": destination_group, "title": title, "username": username, "passwd": passwd}, uri)
        return (ReturnCode.OK, self._status)
    
    @expose
    def propose_add_group(self, parent_group: list[str], group_name: str, uri: str) -> tuple[ReturnCode, StatusCode]:
        if not self._cn_check():
            return (ReturnCode.ERROR, self._status)

        if not self._operation_lock.acquire(timeout=5):
            return (ReturnCode.ERROR, self._status)
        
        self._status = StatusCode.DATABASE_CHANGE
        self._executor.submit(self.propose_change, Operation.ADD_GROUP, {"parent_group": parent_group, "group_name": group_name}, uri)
        return (ReturnCode.OK, self._status)

    @expose
    def propose_delete_entry(self, entry_path: list[str], uri: str) -> tuple[ReturnCode, StatusCode]:
        if not self._cn_check():
            return (ReturnCode.ERROR, self._status)

        if not self._operation_lock.acquire(timeout=5):
            return (ReturnCode.ERROR, self._status)
        
        self._status = StatusCode.DATABASE_CHANGE
        self._executor.submit(self.propose_change, Operation.DELETE_ENTRY, {"entry_path": entry_path}, uri)
        return (ReturnCode.OK, self._status)

    @expose
    def propose_delete_group(self, path: list[str], uri: str) -> tuple[ReturnCode, StatusCode]:
        if not self._cn_check():
            return (ReturnCode.ERROR, self._status)

        if not self._operation_lock.acquire(timeout=5):
            return (ReturnCode.ERROR, self._status)
        
        self._status = StatusCode.DATABASE_CHANGE
        self._executor.submit(self.propose_change, Operation.DELETE_GROUP, {"path": path}, uri)
        return (ReturnCode.OK, self._status)
    
    def propose_change(self, operation: Operation, data: OperationData, uri: str) -> None:
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
                    self._operation_lock.release()
                    return
                
        proposition_id = uuid4().int
        with self._vote_lock:
            self._current_proposition = {
                        "votes": [True],
                        "voters": {uri},
                        "deadlines": {},
                        "proposition_id": proposition_id
                    }
        with self._followers_lock:
            followers_uris = (follower_uri for follower_uri in self._followers_cn.keys() if follower_uri != uri)

        for follower_uri in followers_uris:
            with Proxy(URI(follower_uri)) as follower_proxy:
                follower_proxy._pyroTimeout = 5.0 # Wait at most 5 seconds to establish a connection, 
                                                  # otherwise the follower is overwhelmed with connections and can't respond.
                try:
                    follower_proxy._pyroBind()
                    with self._vote_lock:
                        deadline = time() + 30
                        self._current_proposition["deadlines"][follower_uri] = deadline
                    follower_proxy.add_notification(notification_message, deadline, proposition_id)
                except (CommunicationError, NamingError):
                    self.print_message(f"A follower was unreachable during a change proposition for database {self.get_name()}")
                except Exception as e:
                    print(e)

        if uri != self.uri:
            deadline = time() + 30
            with self._vote_lock:
                self._current_proposition["deadlines"][self.uri] = deadline
            self.add_notification(notification_message, deadline, proposition_id)
        
        sleep(30) # Wait for answers

        # The decision is approved if at least the ceiling half the followers + leader has approved the change.
        # - ( (-n1) // n2) is a trick to perform a ceiling division instead of a floor division.
        decision = True if sum(self._current_proposition["votes"]) >= -( (-(len(self._followers_cn)+1)) // 2) else False
        decision_message_template = f"Database change \'{notification_message}\' has been "
        decision_message = decision_message_template + "approved" if decision else decision_message_template + "denied"

        with self._followers_lock:
            uris_snapshot = list(self._followers_cn.keys()) # Because other threads might modify the dictionary while I iterate.
        for follower_uri in uris_snapshot:
            with Proxy(URI(follower_uri)) as follower_proxy:
                follower_proxy._pyroTimeout = 5.0 # Wait at most 5 seconds to establish a connection, 
                                                  # otherwise the follower is overwhelmed with connections and can't respond.
                try:
                    follower_proxy.remote_print_message(decision_message)
                except (CommunicationError, NamingError):
                    pass
                except Exception as e:
                    print(e)
        
        self.print_message(decision_message)

        if decision:
            dead_followers = set()
            follower_method = None
            leader_method = None
            match operation:
                case Operation.ADD_ENTRY:
                    follower_method = "remote_add_entry"
                    leader_method = "local_add_entry"
                case Operation.ADD_GROUP:
                    follower_method = "remote_add_group"
                    leader_method = "local_add_group"
                case Operation.DELETE_ENTRY:
                    follower_method = "remote_delete_entry"
                    leader_method = "local_delete_entry"
                case Operation.DELETE_GROUP:
                    follower_method = "remote_delete_group"
                    leader_method = "local_delete_group"

            with self._followers_lock:
                uris_snapshot = list(self._followers_cn.keys())
            for follower_uri in uris_snapshot:
                with Proxy(URI(follower_uri)) as follower_proxy:
                    follower_proxy._pyroTimeout = 5.0 # Wait at most 5 seconds to establish a connection, 
                                                      # otherwise the follower is overwhelmed with connections and can't respond.
                    try:
                        method = getattr(follower_proxy, follower_method)
                        method(data)
                    except (CommunicationError, NamingError):
                        dead_followers.add(follower_uri)
                    except AttributeError:
                        self.print_message("I tried to call a method that doesn't exist on the client")

            try:
                method = getattr(self, leader_method)
                method(data)
            except AttributeError:
                self.print_message("I tried to call a method that doesn't exist on the leader")

            self._followers_cleanup(dead_followers)

        self._status = StatusCode.FREE
        with self._vote_lock:
            self._current_proposition = None
        self._operation_lock.release()

    def local_add_entry(self, data: OperationData) -> None:
        # Add a try catch because the approved change could raise an exception if ill-formed
        try:
            self._db_local.add_entry(data["destination_group"], data["title"], data["username"], data["passwd"])
            self.print_message(f"A new entry was added to database {self.get_name()}")
        except Exception:
            self.print_message(f"An error occured while trying to add a new entry to database {self.get_name()}")
    
    def local_add_group(self, data: OperationData) -> None:
        try:
            self._db_local.add_group(data["parent_group"], data["group_name"])
            self.print_message(f"A new group was added to database {self.get_name()}")
        except Exception:
            self.print_message(f"An error occured while trying to add a new group to database {self.get_name()}")
    
    def local_delete_entry(self, data: OperationData) -> None:
        try:
            self._db_local.delete_entry(data["entry_path"])
            self.print_message(f"An entry was deleted from database {self.get_name()}")
        except Exception:
            self.print_message(f"An error occured while trying to delete an entry of database {self.get_name()}")
    
    def local_delete_group(self, data: OperationData) -> None:
        try:
            self._db_local.delete_group(data["path"])
            self.print_message(f"A group was deleted from database {self.get_name()}")
        except Exception:
            self.print_message(f"An error occured while trying to delete a group of database {self.get_name()}")

    @expose
    @oneway
    def leave_database(self) -> None:
        if not self._cn_check():
            return
        cn_name = self._get_caller_cn()
        with self._followers_lock:
            uri = next((k for k, v in self._followers_cn.items() if v == cn_name), None)
            removed = False
            try:
                del self._followers_cn[uri]
                del self._followers_id[uri]
                removed = True
            except AttributeError:
                pass
            if removed:
                self.print_message("A follower has left the database")
            uri_set = {uri} # Need to adapt the URI into a set because that's what the remove method requires.
            dead_followers = set()
            for follower_uri in self._followers_cn:
                with Proxy(URI(follower_uri)) as follower_proxy:
                    follower_proxy._pyroTimeout = 5.0 # Wait at most 5 seconds to establish a connection,
                                                        # otherwise the follower is overwhelmed with connections and can't respond.
                    try:
                        follower_proxy.remove_uris(uri_set)
                    except (CommunicationError, NamingError):
                        dead_followers.add(follower_uri)

        self._followers_cleanup(dead_followers)


    def _followers_cleanup(self, dead_followers: set[str]) -> None:
        # Cleanup dead followers.
        while len(dead_followers) > 0:
            new_dead_followers = set() # Other followers could stop responding, so we delete them too.
                                        # The loop will eventually end because in the worst case every follower is removed.
            removed = False
            with self._followers_lock:
                for dead_follower in dead_followers:
                    try:
                        del self._followers_cn[dead_follower]
                        del self._followers_id[dead_follower]
                        removed = True
                    except KeyError:
                        pass
                if removed:
                    self.print_message(f"Dead followers were removed from database {self.get_name()}")

                uris_snapshot = list(self._followers_cn.keys())
            for follower_uri in uris_snapshot:
                    with Proxy(URI(follower_uri)) as follower_proxy:
                        follower_proxy._pyroTimeout = 5.0
                        try:
                            follower_proxy.remove_uris(dead_followers)
                        except (CommunicationError, NamingError):
                            new_dead_followers.add(follower_uri)

            dead_followers = new_dead_followers

    def _cn_check(self) -> bool:
        """Checks if the client that is making a call has a common name in the allowed list"""
        client_cn = self._get_caller_cn()
        with self._followers_lock:
            return client_cn in self._followers_cn.values()
    
    def _get_caller_cn(self) -> str:
        """Return the Common Name of the caller"""
        cert = current_context.client.getpeercert()
        subject = dict(x[0] for x in cert["subject"])
        return subject.get("commonName")
    
    @expose
    def cast_vote(self, vote: bool, uri: str, proposition_id: int) -> bool:
        if not self._cn_check():
            return False
        with self._vote_lock:
            if (
                not self._current_proposition
                or self._current_proposition["proposition_id"] != proposition_id
                or uri in self._current_proposition["voters"]
                or time() > self._current_proposition["deadlines"][uri]
            ):
                return False

            self._current_proposition["voters"].add(uri)
            self._current_proposition["votes"].append(vote)
        return True
    
    @expose
    def ping(self) -> bool:
        with self._leader_lock:
            return self._is_leader
    
    def close_database(self) -> DBLocal:
        self.print_message("I'm notifying the followers of your decision")
        with self._leader_lock:
            self._is_leader = False
        with self._followers_lock:
            uris_snapshot = list(self._followers_cn.keys())
        for follower_uri in uris_snapshot:
            try:
                with Proxy(follower_uri) as proxy:
                    proxy._pyroTimeout = 5.0
                    proxy.start_election()
            except (CommunicationError, NamingError):
                continue
            except Exception as e:
                print(e)
                continue
        return self._db_local
    
    def add_notification(self, message: str, timestamp: float, proposition_id: int) -> None:
        notification_message = f"- {message} for database {self.get_name()}"
        self._ctx.add_notification(Notification(notification_message, timestamp, proposition_id, self.local_id))
        self.print_message(f"A new notification regarding database {self.get_name()} was added!")

    def answer_notification(self, vote: bool, notification: Notification) -> bool:
        with self._vote_lock:
            if (
                not self._current_proposition
                or self._current_proposition["proposition_id"] != notification.proposition_id
                or self.uri in self._current_proposition["voters"]
                or time() > self._current_proposition["deadlines"][self.uri]
            ):
                return False

            self._current_proposition["voters"].add(self.uri)
            self._current_proposition["votes"].append(vote)
        return True
    
    def print_message(self, message: str) -> None:
        self._ctx.print_message(message)
    
    def unregister_object(self) -> None:
        self._ctx.daemon.unregister(self)
    
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
