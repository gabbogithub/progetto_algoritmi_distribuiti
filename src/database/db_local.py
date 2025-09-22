from typing import Self
from pykeepass import PyKeePass, create_database, Entry, Group
from .db_interface import DBInterface

class DBLocal(DBInterface):

    def __init__(self, path: str, passwd: str) -> None:
        self._kp_db = PyKeePass(path, passwd)
        self._local_id = None

    @property
    def local_id(self) -> int | None:
        return self._local_id

    @local_id.setter
    def local_id(self, value: int) -> None:
        if self._local_id is not None:
            raise AttributeError("Local ID has already been set and cannot be modified.")
        self._local_id = value

    @classmethod
    def create_db(cls, path: str, passwd: str, name: str) -> Self:
        db = create_database(path, passwd)
        db.database_name = name
        db.save()
        return cls(path, passwd)

    def reset_db(self, path: str, passwd: str) -> None:
        self._kp_db = create_database(path, passwd)

    def add_entry(self, destination_group, title: str, username: str, passwd: str) -> None:
        group = self._kp_db.find_groups(path=destination_group, first=True)
        if group is None:
            raise KeyError("The group for the entry doesn't exist!")
        
        if self._kp_db.find_entries(group=group, title=title, first=True, recursive=False) is not None:
            raise KeyError("The entry under the specified group, with the specified title already exists!")
        
        self._kp_db.add_entry(group, title, username, passwd)

    def add_group(self, parent_group: list[str], group_name: str) -> None:
        parent = self._kp_db.find_groups(path=parent_group, first=True)

        if parent is None:
            raise ValueError("The parent group does not exist!")

        if self._kp_db.find_groups(group=parent, name=group_name, first=True, recursive=False) is not None:
            raise ValueError("The group is already present in the parent group!")

        self._kp_db.add_group(parent, group_name) 

    def delete_entry(self, entry_path: list[str]) -> None:
        entry = self._kp_db.find_entries(path=entry_path, first=True)
        if entry is None:
            raise KeyError("The entry doesn't exist!")

        self._kp_db.delete_entry(entry)

    def delete_group(self, path: list[str]) -> None:
        group = self._kp_db.find_groups(path=path, first=True) 
        if group is None:
            raise KeyError("The group doesn't exist!")

        self._kp_db.delete_group(group)
    
    def set_name(self, name: str) -> None:
        self._kp_db.database_name = name
    
    def get_name(self) -> str:
        return self._kp_db.database_name

    def get_password(self) -> str:
        return self._kp_db.password

    def get_filename(self) -> str:
        return self._kp_db.filename

    def get_entries(self) -> list[Entry]:
        return self._kp_db.entries

    def get_groups(self) -> list[Group]:
        return self._kp_db.groups
    
    def save_changes(self) -> None:
        self._kp_db.save()
