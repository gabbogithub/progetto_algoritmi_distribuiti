from abc import ABC, abstractmethod
from pykeepass import Entry, Group

class DBInterface(ABC):

    @abstractmethod
    def add_entry(self, destination_group: list[str], title: str, username: str, passwd: str) -> None:
        pass
    
    @abstractmethod
    def add_group(self, parent_group: list[str], group_name: str) -> None:
        pass
    
    @abstractmethod
    def delete_entry(self, entry_path: list[str]) -> None:
        pass
    
    @abstractmethod
    def delete_group(self, path: list[str]) -> None:
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        pass

    @abstractmethod
    def get_password(self) -> str:
        pass
    
    @abstractmethod
    def get_filename(self) -> str:
        pass
    
    @abstractmethod
    def get_entries(self) -> list[Entry]:
        pass
    
    @abstractmethod
    def get_groups(self) -> list[Group]:
        pass
