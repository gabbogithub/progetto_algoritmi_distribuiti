from collections.abc import ItemsView
import socket
from zeroconf import Zeroconf, ServiceInfo, ServiceBrowser
import time

SERVICE_TYPE = "_uri._tcp.local."

class ContinuousListener:
    """Keeps track of discovered services in real time."""
    def __init__(self, ip: str, port: str) -> None:
        self._ip = socket.inet_aton(socket.gethostbyname(ip))
        self._port = int(port)
        self._services = {}
        # set used to avoid adding to the services variable my own services and already used ones
        self._ignored_services = set()

    def add_service(self, zeroconf: Zeroconf, service_type: str, name: str) -> None:
        """Adds new services to a dictionary to keep track of them"""
        info = zeroconf.get_service_info(service_type, name)
        if not info:
            return
        uri = info.properties.get(b'uri', b'').decode('utf-8')
        ip_address = info.parsed_addresses()[0]
        if uri not in self._ignored_services:
            self._services[name] = (uri, ip_address, info.port)

    def remove_service(self, _zeroconf: Zeroconf, _service_type: str, name: str) -> None:
        """Removes from the services dictionaries one that is no longer available"""
        if name in self._services:
            del self._services[name]

    def update_service(self, zeroconf, service_type, name):
        """Mandatory method for a listener"""
        pass

    def add_ignored_service(self, uri: str) -> None:
        self._ignored_services.add(uri)

    def remove_ignored_service(self, uri: str) -> None:
        self._ignored_services.remove(uri)

    def get_services_information(self) -> ItemsView[str, tuple[str, str, int]]:
        return self._services.items()


class UriAdvertiser:
    """Handles service registration."""
    def __init__(self, zeroconf: Zeroconf, ip: str, port: str) -> None:
        self.zeroconf = zeroconf
        self._ip = socket.inet_aton(socket.gethostbyname(ip))
        self._port = int(port)
        self._services = {}

    def register_uri(self, name: str, uri: str) -> None:
        """Registers a URI with the specified name"""
        props = {'uri': uri.encode('utf-8')}
        service_name = f"{name}._uri._tcp.local."
        info = ServiceInfo(
            SERVICE_TYPE,
            service_name,
            addresses=[self._ip],
            port=self._port,
            properties=props
        )
        self.zeroconf.register_service(info, allow_name_change=True)
        self._services[name] = info
    
    def unregister_uri(self, name: str) -> None:
        """Unregisters a URI with the specified name"""
        try:
            service = self._services.pop(name)
            self.zeroconf.unregister_service(service)
        except KeyError:
            pass

    def get_services(self) -> dict[str, ServiceInfo]:
        """Returns a list with the active services"""
        return self._services