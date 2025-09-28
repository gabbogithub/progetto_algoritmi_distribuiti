from typing import Self
from threading import Lock
from time import sleep
from base64 import b64decode
from time import time, sleep
from Pyro5.core import URI
from Pyro5.server import expose, oneway
from Pyro5.api import Proxy, current_context
from Pyro5.errors import CommunicationError, NamingError, PyroError
from pykeepass import Entry, Group
from database.db_interface import DBInterface
from database.db_local import DBLocal
from context.context import ContextApp
from .db_expose import DBExpose
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
        self._followers_ids = {} # dictionary with the URIs and the IDs of the other followers.
        self._followers_cns = {} # dictionary holding the URIs and Common Names of the other followers.
        self._uri = None
        self._db_path = None
        self._password = None
        self._ctx = context
        self._local_id = None # ID assigned by the context class.
        self._unique_id = None # ID assigned by the leader.
        self._election_lock = Lock()
        self._leader_lock = Lock() # Lock used to signal that a leader election is taking place.

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
        self._db_local.local_id = value

    @property
    def unique_id(self) -> int | None:
        return self._unique_id

    @unique_id.setter
    def unique_id(self, value: int) -> None:
        if self._unique_id is not None:
            raise AttributeError("Unique ID has already been set and cannot be modified.")
        self._unique_id = value

    @property
    def leader_uri(self) -> str:
        return self._leader_uri
    
    @leader_uri.setter
    def leader_uri(self, value: str | None) -> None:
        self._leader_uri = value

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
        if self._election_lock.locked():
            return False
        try:
            self._leader._pyroClaimOwnership()
            return_code, status_code = self._leader.propose_add_entry(destination_group, title, username, passwd, self.uri)
            return self._process_return_code(return_code, status_code)
        except (CommunicationError, NamingError, PyroError):
            self.print_message("Error when trying to communicate with the leader!")
            return False

    def add_group(self, parent_group: list[str], group_name: str) -> bool:
        if self._election_lock.locked():
            return False
        try:
            self._leader._pyroClaimOwnership()
            return_code, status_code = self._leader.propose_add_group(parent_group, group_name, self.uri)
            return self._process_return_code(return_code, status_code)
        except (CommunicationError, NamingError, PyroError):
            self.print_message("Error when trying to communicate with the leader!")
            return False
    
    def delete_entry(self, entry_path: list[str]) -> bool:
        if self._election_lock.locked():
            return False
        try:
            self._leader._pyroClaimOwnership()
            return_code, status_code = self._leader.propose_delete_entry(entry_path, self.uri)
            return self._process_return_code(return_code, status_code)
        except (CommunicationError, NamingError, PyroError):
            self.print_message("Error when trying to communicate with the leader!")
            return False
    
    def delete_group(self, path: list[str]) -> bool:
        if self._election_lock.locked():
            return False
        try:
            self._leader._pyroClaimOwnership()
            return_code, status_code = self._leader.propose_delete_group(path, self.uri)
            return self._process_return_code(return_code, status_code)
        except (CommunicationError, NamingError, PyroError):
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
    def add_uri(self, uri: str, unique_id: int, cn: str) -> bool:
        if not self._cn_check():
            return False
        
        self._followers_ids[uri] = unique_id
        self._followers_cns[uri] = cn
        self.print_message(f"A new follower was added to database {self.get_name()}")
        return True
    
    @expose
    def remove_uris(self, uris: set[str]) -> bool:
        if not self._cn_check():
            return False
        
        before_len = len(self._followers_ids)
        for uri in uris:
            self._followers_ids.pop(uri, None)
            self._followers_cns.pop(uri, None)
        if before_len != len(self._followers_ids):
            self.print_message(f"Some followers were removed from the database {self.get_name()}")
        return True
    
    @expose
    def receive_uris(self, ids: dict[str, int], cns: dict[str, int]) -> bool:
        if not self._cn_check():
            return False
        self._followers_ids = ids
        self._followers_cns = cns
        return True

    @expose
    def receive_db(self, db_data: bytes) -> bool:
        if not self._cn_check():
            return False
        
        decoded_data = b64decode(db_data["data"])
        with open(self._db_path, "wb") as f:
            f.write(decoded_data)
        self._db_local = DBLocal(self._db_path, self._password)
        if self.local_id:
            self._db_local.local_id = self.local_id
        return True
    
    @expose
    def set_unique_id(self, id: int) -> bool:
        try:
            self.unique_id = id
            return True
        except AttributeError:
            return False
    
    def print_message(self, message: str):
        self._ctx.print_message(message)

    @expose
    @oneway
    def remote_print_message(self, message: str) -> None:
        if self._cn_check():
            self._ctx.print_message(message)

    @expose
    @oneway
    def add_notification(self, message: str, timestamp: float, proposition_id: int) -> None:
        notification_message = f"- {message} for database {self.get_name()}"
        self._ctx.add_notification(Notification(notification_message, timestamp, proposition_id, self.local_id))
        self.print_message(f"A new notification regarding database {self.get_name()} was added!")

    @expose
    def remote_add_entry(self, data: OperationData) -> bool:
        if not self._cn_check():
            return False
        try:
            self._db_local.add_entry(data["destination_group"], data["title"], data["username"], data["passwd"])
            self.print_message(f"A new entry was added to database {self.get_name()}")
        except Exception:
            self.print_message(f"An error occured while trying to add a new entry to database {self.get_name()}")
            return False
        return True
    
    @expose
    def remote_add_group(self, data: OperationData) -> bool:
        if not self._cn_check():
            return False
        try:
            self._db_local.add_group(data["parent_group"], data["group_name"])
            self.print_message(f"A new group was added to database {self.get_name()}")
        except Exception:
            self.print_message(f"An error occured while trying to add a new group to database {self.get_name()}")
            return False
        return True
    
    @expose
    def remote_delete_entry(self, data: OperationData) -> bool:
        if not self._cn_check():
            return False
        try:
            self._db_local.delete_entry(data["entry_path"])
            self.print_message(f"An entry was deleted from database {self.get_name()}")
        except Exception:
            self.print_message(f"An error occured while trying to delete an entry of database {self.get_name()}")
        return True
    
    @expose
    def remote_delete_group(self, data: OperationData) -> bool:
        if not self._cn_check():
            return False
        try:
            self._db_local.delete_group(data["path"])
            self.print_message(f"A group was deleted from database {self.get_name()}")
        except Exception:
            self.print_message(f"An error occured while trying to delete a group of database {self.get_name()}")
        return True
    
    @expose
    @oneway
    def start_election(self) -> None:
        # Only start election if the leader URI is still set and the leader is unreachable or responds negatively to the ping.
        with self._leader_lock:
            if self.leader_uri:
                try:
                    self._leader._pyroClaimOwnership()
                    self._leader._pyroTimeout = 5.0
                    if self._leader.ping():
                        self._leader._pyroTimeout = None
                        return
                except (CommunicationError, NamingError, PyroError):
                    pass 
                except Exception as e:
                    print(e)
                    return


        if not self._election_lock.acquire(blocking=False):
            # Election already started.
            return
        
        self.print_message(f"Starting leader election for database {self.get_name()}")
        with self._leader_lock:
            self._ctx.unregister_ignored_service(self.leader_uri)
            self.leader_uri = None
            self._leader = None
            self._leader_cn = None
        tries_number = 5 # Number of times to try to elect a leader, after that the db disconnects.
        dead_followers = set()
        while tries_number > 0:
            # Exclude followers with an ID lower than mine and that were unable to answer in the previous rounds.
            higher_follower_uris = [follower_uri for (follower_uri, follower_id) in self._followers_ids.items() if ((follower_uri not in dead_followers) and (follower_id > self.unique_id))]
            got_response = False
            for follower_uri in higher_follower_uris:
                # Probing the higher nodes.
                with Proxy(URI(follower_uri)) as follower_proxy:
                    follower_proxy._pyroTimeout = 5.0 # Wait at most 5 seconds to establish a connection, 
                                                # otherwise the follower is overwhelmed with connections and can't respond.
                    try:
                        if follower_proxy.ping():
                            got_response = True
                        follower_proxy.start_election()
                    except (CommunicationError, NamingError, PyroError):
                        dead_followers.add(follower_uri)
                    except Exception as e:
                        print(e)

            if got_response:
                # Wait for the new leader message.
                self.print_message(f"A new leader should be announced shortly for database {self.get_name()}")
                start = time()
                # Wait for at most a minute before redoing the probing.
                while time() - start < 60:
                    with self._leader_lock:
                        if self.leader_uri is not None:
                            self._election_lock.release()
                            self.print_message(f"A new leader has been elected for database {self.get_name()}")
                            return
                    sleep(5)
                tries_number -= 1

            else:
                # No higher node responded so I am the new leader.
                expose_db = DBExpose.create_and_register(self._db_local, self._ctx)
                expose_db._operation_lock.acquire() # This will be useful if someone tries to start an operation while the leader election process hasn't ended for all the followers.
                expose_db._status = StatusCode.DATABASE_CHANGE
                new_dead_followers = set()
                with open(self.get_filename(), "rb") as f:
                    db_data = f.read()
                if len(dead_followers) > 0:
                    self.print_message("Dead followers were removed during the leader election process")
                expose_db._followers_cn = {follower_uri:follower_cn for (follower_uri, follower_cn) in self._followers_cns.items() if follower_uri not in dead_followers}
                expose_db._followers_id = {follower_uri:follower_id for (follower_uri, follower_id) in self._followers_ids.items() if follower_uri not in dead_followers}
                dead_followers.add(self.uri) # Up until now we were followers like the others, so we need to remove our URI from their dictionaries.
                for follower_uri in expose_db._followers_cn:
                    # Probing the higher nodes.
                    with Proxy(URI(follower_uri)) as follower_proxy:
                        follower_proxy._pyroTimeout = 5.0
                        try:
                            if not follower_proxy.new_leader(self.unique_id, expose_db.uri):
                                new_dead_followers.add(follower_uri)
                            if not follower_proxy.receive_db(db_data):
                                new_dead_followers.add(follower_uri)
                            if not follower_proxy.remove_uris(dead_followers):
                                new_dead_followers.add(follower_uri)
                        except (CommunicationError, NamingError, PyroError):
                            new_dead_followers.add(follower_uri)
                        except Exception as e:
                            print(e)

                # Clean up eventual nodes that disconnected during the new leader declaration.
                dead_followers = new_dead_followers
                while len(dead_followers) > 0:
                    new_dead_followers = set()
                    removed = False
                    with expose_db._followers_lock:
                        for dead_follower in dead_followers:
                            try:
                                del expose_db._followers_cn[dead_follower]
                                del expose_db._followers_id[dead_follower]
                                removed = True
                            except KeyError:
                                pass
                        if removed:
                            expose_db.print_message(f"Dead followers were removed from database {self.get_name()}")
                        uris_snapshot = list(expose_db._followers_cn.keys())

                    for follower_uri in uris_snapshot:
                        with Proxy(URI(follower_uri)) as follower_proxy:
                            follower_proxy._pyroTimeout = 5.0
                            try:
                                follower_proxy.remove_uris(dead_followers)
                            except (CommunicationError, NamingError, PyroError):
                                new_dead_followers.add(follower_uri)

                    dead_followers = new_dead_followers

                self._ctx.daemon.unregister(self)
                expose_db._status = StatusCode.FREE
                expose_db._operation_lock.release()
                self._ctx.register_ignored_service(expose_db.uri)
                self._ctx.register_uri(expose_db.get_name(), expose_db.uri)
                try:
                    expose_db.local_id = self.local_id
                    expose_db._db_local.local_id = self.local_id
                except AttributeError:
                    pass
                self._ctx.replace_database(expose_db.local_id, expose_db)
                self._election_lock.release()
                self.print_message(f"You became the new leader for database {self.get_name()}")
                return

        self.print_message(f"The leader election process failed. Database {self.get_name()} will be disconnected")
        self._ctx.replace_database(self.local_id, self._db_local) 

    @expose
    def new_leader(self, unique_id: int, leader_uri: str) -> bool:
        # Accept someone as the leader if an election is taking place and if their ID is bigger than yours.
        # These controls are used to prevent a random rogue follower from becoming the leader for a follower.
        if self._election_lock.locked() and unique_id > self.unique_id:
            # Try to connect with the new leader. If a connection cannot be established, continue with the leader election.
            leader_proxy = Proxy(URI(leader_uri))
            try:
                leader_proxy._pyroBind()
                with self._leader_lock:
                    self._leader_uri = leader_uri
                    self._leader = leader_proxy
                    self._ctx.register_ignored_service(leader_uri)
                cert = current_context.client.getpeercert()
                subject = dict(x[0] for x in cert["subject"])
                self._leader_cn = subject.get("commonName")
                return True
            except (ConnectionError, NamingError, PyroError):
                return False
        return False
            

    @expose
    def ping(self) -> bool:
        return True

    def answer_notification(self, vote: bool, notification: Notification) -> bool:
        if time() > notification.timestamp:
            return False
        self._leader._pyroClaimOwnership()
        return self._leader.cast_vote(vote, self.uri, notification.proposition_id)
    
    def leave_db(self) -> DBLocal:
        try:
            self._leader._pyroClaimOwnership()
            self._leader.leave_database()
            self._leader._pyroRelease()
        except (CommunicationError, NamingError, PyroError):
            self.print_message("Error when trying to communicate with the leader!")
        
        return self._db_local

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
    