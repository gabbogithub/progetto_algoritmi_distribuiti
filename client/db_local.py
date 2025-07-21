from typing import Self
from pykeepass import PyKeePass, create_database

class DBLocal():

    def __init__(self, path: str, passwd: str) -> None:
        self._kp_db = PyKeePass(path, passwd)

    @classmethod
    def create_db(cls, path: str, passwd: str) -> Self:
        create_database(path, passwd)
        return cls(path, passwd)

    def reset_db(self, path: str, passwd: str) -> None:
        self._kp_db = create_database(path, passwd)

    def add_entry(self, destination_group, title: str, username: str, passwd: str):
        group = self._kp_db.find_groups(path=destination_group, first=True)
        if group is None:
            raise KeyError("The group for the entry doesn't exist!")
        
        if self._kp_db.find_entries(group=group, title=title, first=True) is not None:
            raise KeyError("The entry under the specified group, with the specified title already exists!")
        
        self._kp_db.add_entry(group, title, username, passwd)

    def add_group(self, parent_group: list[str], group_name: str) -> None:
        parent = self._kp_db.find_groups(path=parent_group, first=True)

        if parent is None:
            raise ValueError(f"The parent group does not exist!")

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
    
    def change_name(self, new_name: str) -> None:
        self._kp_db.database_name = new_name

    def get_entries(self):
        return self._kp_db.entries
    
    def save_changes(self) -> None:
        self._kp_db.save()
