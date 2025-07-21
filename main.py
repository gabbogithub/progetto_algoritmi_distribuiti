from pykeepass import PyKeePass, create_database
from client.db_local import DBLocal
import questionary
from questionary import prompt, ValidationError, Validator
from sys import exit
from prettytable import PrettyTable, TableStyle
from pathlib import Path

local_dbs = []
remote_dbs = []

class NameValidator(Validator):
    def validate(self, document):
        file_path = Path(document.text)
        if file_path.exists():
            raise ValidationError(
                message="There already exists a file with that name",
                cursor_position=len(document.text),
            )  # Move cursor to end

class ListValidator(Validator):
    # TODO controlla che il file esista
    def validate(self, document):
        open_db_path = Path(document.text)
        if not open_db_path.exists():
            return
        for db in local_dbs:
            if open_db_path.same_file(Path(db.get_filename())):
                raise ValidationError(
                    message="This database is already open",
                    cursor_position=len(document.text),
                )  # Move cursor to end

def create_database() -> None:
    questions = [
            {
                "type": "path",
                "name": "db_path",
                "message": "Insert the database file name",
                "validate": NameValidator
                },
            {
                "type": "text",
                "name": "db_name",
                "message": "Insert the database name",
                },
            {
                "type": "password",
                "name": "db_passwd",
                "message": "Insert the database password",
                },
            ]
    results = prompt(questions)
    if results:
        local_dbs.append(DBLocal.create_db(results["db_path"], results["db_passwd"], results["db_name"]))

def open_database() -> None:
    questions = [
            {
                "type": "path",
                "name": "db_path",
                "message": "Insert the database path",
                "validate": ListValidator,
                },
            {
                "type": "password",
                "name": "db_passwd",
                "message": "Insert the database password",
                },
            ]
    results = prompt(questions)
    if results:
        local_dbs.append(DBLocal(results["db_path"], results["db_passwd"]))

def list_databases() -> None:
    table = PrettyTable()
    table.field_names = ["N.", "Name", "Filename"]
    table.title = "Local databases"
    table.add_rows([[i, db.get_name(), db.get_filename()] for i, db in enumerate(local_dbs, 1)])
    table.set_style(TableStyle.SINGLE_BORDER)
    print(table)

    table.clear_rows()
    table.title = "Remote databases"
    table.add_rows([[i, db.get_name(), db.get_filename()] for i, db in enumerate(remote_dbs, 1)])
    print(table)


def add_group() -> None:
    questions = [
            {
                "type": "path",
                "name": "db_path",
                "message": "Insert the database path",
                },
            {
                "type": "password",
                "name": "db_passwd",
                "message": "Insert the database password",
                },  
            ]
    results = prompt(questions)
    if results:
        db = DBLocal(results["db_path"], results["db_passwd"])
        questions = [
                {
                    "type": "text",
                    "name": "parent_group",
                    "message": "Insert the parent group",
                    },
                {
                    "type": "text",
                    "name": "group_name",
                    "message": "Insert the name of the new group",
                    },  
                ]
        results = prompt(questions)
        if results:
            try:
                db.add_group(results["parent_group"].split("/"), results["group_name"])
            except ValueError:
                questionary.print("The inserted names were not correct!")

def add_entry() -> None:
    pass

def delete_group() -> None:
    pass

def delete_entry() -> None:
    pass

def save_changes() -> None:
    questions = [
            {
                "type": "path",
                "name": "db_path",
                "message": "Insert the database path",
                },
            {
                "type": "password",
                "name": "db_passwd",
                "message": "Insert the database password",
                },  
            ]
    results = prompt(questions)
    if results:
        db = DBLocal(results["db_path"], results["db_passwd"])
        db.save_changes()

def close_local_db():
    pass

def exit_loop() -> None:
    confirmation = questionary.confirm("Are you sure you want to exit?").ask()
    if confirmation:
        exit(0)

def main():

    actions = {
                "Create database": create_database,
                "Open local database": open_database,
                "List databases": list_databases,
                "Add group": add_group,
                "Add entry": add_entry,
                "Delete group": delete_group,
                "Delete entry": delete_entry,
                "Save changes": save_changes,
                "Close local database": close_local_db,
                "Exit": exit_loop,
                }

    while True:
        action = questionary.select(
            "What do you want to do?",
            choices=actions.keys()).ask()

        actions.get(action, exit)()

if __name__ == "__main__":
    main()
