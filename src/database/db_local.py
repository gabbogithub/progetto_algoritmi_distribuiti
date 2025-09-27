from typing import Self
from threading import Lock
from pykeepass import PyKeePass, create_database, Entry, Group
from .db_interface import DBInterface

class DBLocal(DBInterface):

    def __init__(self, path: str, passwd: str) -> None:
        self._kp_db = PyKeePass(path, passwd)
        self._local_id = None
        self._db_lock = Lock()

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
        with self._db_lock:
            group = self._kp_db.find_groups(path=destination_group, first=True)
            if group is None:
                raise KeyError("The group for the entry doesn't exist!")
            
            if self._kp_db.find_entries(group=group, title=title, first=True, recursive=False) is not None:
                raise KeyError("The entry under the specified group, with the specified title already exists!")
            
            self._kp_db.add_entry(group, title, username, passwd)
            self._kp_db.save()

    def add_group(self, parent_group: list[str], group_name: str) -> None:
        with self._db_lock:
            parent = self._kp_db.find_groups(path=parent_group, first=True)

            if parent is None:
                raise ValueError("The parent group does not exist!")

            if self._kp_db.find_groups(group=parent, name=group_name, first=True, recursive=False) is not None:
                raise ValueError("The group is already present in the parent group!")

            self._kp_db.add_group(parent, group_name) 
            self._kp_db.save()

    def delete_entry(self, entry_path: list[str]) -> None:
        with self._db_lock:
            entry = self._kp_db.find_entries(path=entry_path, first=True)
            if entry is None:
                raise KeyError("The entry doesn't exist!")

            self._kp_db.delete_entry(entry)
            self._kp_db.save()

    def delete_group(self, path: list[str]) -> None:
        with self._db_lock:
            group = self._kp_db.find_groups(path=path, first=True) 
            if group is None:
                raise KeyError("The group doesn't exist!")

            self._kp_db.delete_group(group)
            self._kp_db.save()
    
    def set_name(self, name: str) -> None:
        with self._db_lock:
            self._kp_db.database_name = name
            self._kp_db.save()
    
    def get_name(self) -> str:
        with self._db_lock:
            return self._kp_db.database_name

    def get_password(self) -> str:
        with self._db_lock:
            return self._kp_db.password

    def get_filename(self) -> str:
        with self._db_lock:
            return self._kp_db.filename

    def get_entries(self) -> list[Entry]:
        with self._db_lock:
            return self._kp_db.entries

    def get_groups(self) -> list[Group]:
        with self._db_lock:
            return self._kp_db.groups
    