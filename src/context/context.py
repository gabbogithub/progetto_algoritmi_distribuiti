from collections.abc import ItemsView
import threading
from Pyro5.server import Daemon
from zeroconf import Zeroconf, ServiceBrowser
from database.db_interface import DBInterface
from remote.mdns_services import ContinuousListener, UriAdvertiser, SERVICE_TYPE
from remote.pyro_tls import CertValidatingDaemon

class ContextApp():
    """Context class that holds essential values used by different compontents
    of the application."""
    def __init__(self):
        self._dbs = {}
        self._counter = 0
        self.daemon = CertValidatingDaemon()
        self._zeroconf = Zeroconf()
        ip, port = self.daemon.locationStr.split(":")
        self._listener = ContinuousListener(ip, port)
        self._advertiser = UriAdvertiser(self._zeroconf, ip, port)
        # Start continuous browsing in background without having to call any method
        self._browser = ServiceBrowser(self._zeroconf, SERVICE_TYPE, self._listener)

    def start_daemon_loop(self) -> None:
        """Starts the Pyro5 daemon in a separate thread."""
        threading.Thread(target=self.daemon.requestLoop, daemon=True).start()

    def add_database(self, db: DBInterface) -> None:
        """Adds a new database to the context and returns its unique ID."""
        self._counter += 1
        self._dbs[self._counter] = db

    def remove_database(self, db_id: int) -> DBInterface | None:
        """Removes a database by its ID and returns it."""
        return self._dbs.pop(db_id, None)
    
    def replace_database(self, db_id: int, new_db: DBInterface) -> None:
        """Replaces the database at the given ID with the one passed as argument."""
        self._dbs[db_id] = new_db

    def get_database(self, db_id: int) -> DBInterface | None:
        """Retrieves a database by its ID."""
        return self._dbs.get(db_id)
    
    def get_indexes_databases(self) -> ItemsView[int, DBInterface]:
        """Return all the dbs and their indexes."""
        return self._dbs.items()
    
    def register_uri(self, name: str, uri: str) -> None:
        """Registers a URI with the specified name inside the mDNS service"""
        self._advertiser.register_uri(name, uri)

    def unregister_uri(self, name: str) -> None:
        """Unregisters a URI with the specified name inside the mDNS service"""
        self._advertiser.unregister_uri(name)

    def register_ignored_service(self, uri: str) -> None:
        """Register a URI that will be ignored by the mDNS service"""
        self._listener.add_ignored_service(uri)

    def unregister_ignored_service(self, uri: str) -> None:
        """Unregister a URI that was ignored by the mDNS service"""
        self._listener.remove_ignored_service(uri)

    def add_service_from_db_name(self, name: str) -> None:
        service_name = name + "." + SERVICE_TYPE     
        self._listener.add_service(self._zeroconf, SERVICE_TYPE, service_name)

    def remove_service(self, name: str) -> None:
        self._listener.remove_service(self._zeroconf, SERVICE_TYPE, name)

    def get_services_information(self) -> ItemsView[str, tuple[str, str, int]]:
        """Returns the registered URIs and their associated names"""
        return self._listener.get_services_information()
    
    def close_mdns_service(self) -> None:
        """Terminates the mDNS service"""
        self._zeroconf.close()

    def get_listener(self) -> ContinuousListener:
        return self._listener
    
    def get_advertiser(self) -> UriAdvertiser:
        return self._advertiser