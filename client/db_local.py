from typing import Self
from pykeepass import PyKeePass, create_database

class DBLocal():

    def __init__(self, path: str, passwd: str) -> None:
        self._pk_db = PyKeePass(path, passwd)

    @classmethod
    def create_db(cls, path: str, passwd: str) -> Self:
        create_database(path, passwd)
        return cls(path, passwd)

    def reset_db(self, path: str, passwd: str) -> None:
        self._pk_db = PyKeePass(path, passwd)

    def add_entry(self):
        pass

    def add_group(self, parent_group: str, group_name: str) -> None:
        self._pk_db.add_group(parent_group, group_name)
        self._pk_db.save()

    def delete_entry(self):
        pass

    def delete_group(self):
        pass
    
    def change_name(self, new_name: str) -> None:
        self._pk_db.database_name = new_name
        self._pk_db.save()

    def get_entries(self):
        return self._pk_db.entries
