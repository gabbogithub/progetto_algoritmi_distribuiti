from pykeepass import PyKeePass, create_database
from pykeepass.exceptions import CredentialsError
import questionary
from questionary import prompt, ValidationError, Validator
from prettytable import PrettyTable, TableStyle
from pathlib import Path
from itertools import zip_longest
from database.db_local import DBLocal
from .context import ContextApp

class NameValidator(Validator):
    def validate(self, document):
        input_text = document.text.strip()

        if not input_text.endswith(".kdbx"):
            suggestion = input_text + ".kdbx"
            raise ValidationError(
                message=f"Missing '.kdbx' extension. Did you mean '{suggestion}'?",
                cursor_position=len(document.text),
            )

        try:
            file_path = Path(input_text).expanduser().resolve()
        except Exception:
             raise ValidationError(
                message="Could not expand or resolve the path",
                cursor_position=len(document.text),
            )

        if file_path.exists():
            raise ValidationError(
                message="There already exists a file with that name",
                cursor_position=len(document.text),
            )  # Move cursor to end

class ListValidator(Validator):
    def __init__(self, ctx):
        self.ctx = ctx

    def validate(self, document):
        try:
            candidate_db_path = Path(document.text).expanduser().resolve()
        except Exception:
             raise ValidationError(
                message="Could not expand or resolve the path",
                cursor_position=len(document.text),
            )

        if not candidate_db_path.exists():
            raise ValidationError(
                message="The specified file does not exist",
                cursor_position=len(document.text),
            )

        if candidate_db_path.suffix.lower() != ".kdbx":
            raise ValidationError(
                message="File must have a .kdbx extension",
                cursor_position=len(document.text),
            )

        for open_db in self.ctx.local_dbs:
            try:
                open_db_path = Path(open_db.get_filename()).expanduser().resolve()
                if candidate_db_path.samefile(open_db_path):
                    raise ValidationError(
                        message="This database is already open",
                        cursor_position=len(document.text),
                    )
            except FileNotFoundError:
                # This can happen if an open DB was moved/deleted.
                continue

def database_selection(ctx: ContextApp):
    local_choices = [
        f"[Local {i + 1}] {db.get_name()} ({db.get_filename()})"
        for i, db in enumerate(ctx.local_dbs)
    ]
    remote_choices = [
        f"[Remote {i + 1}] {db.get_name()} ({db.get_filename()})"
        for i, db in enumerate(ctx.remote_dbs)
    ]

    all_choices = local_choices + remote_choices

    if not all_choices:
        print("There are no open databases!")
        return (None, None)

    selected = questionary.autocomplete(
        "Start typing to select the database:",
        choices=all_choices,
        validate=lambda val: val in all_choices or "Please select a valid option",
        ignore_case=True,
        match_middle=True,
    ).ask()

    if selected is None:
        return (None, None)

    confirmation = questionary.confirm("Did you select the right database?").ask()
    if not confirmation:
        return (None, None)

    return (local_choices.index(selected), "l") if selected in local_choices else (remote_choices.index(selected), "r")

def create_database(ctx: ContextApp) -> None:
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
        path = Path(results["db_path"].strip()).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        ctx.local_dbs.append(DBLocal.create_db(path, results["db_passwd"], results["db_name"]))

def open_database(ctx: ContextApp) -> None:
    questions = [
            {
                "type": "path",
                "name": "db_path",
                "message": "Insert the database path",
                "validate": ListValidator(ctx),
                },
            {
                "type": "password",
                "name": "db_passwd",
                "message": "Insert the database password",
                },
            ]
    results = prompt(questions)
    if results:
        try:
            ctx.local_dbs.append(DBLocal(Path(results["db_path"]).expanduser().resolve(), results["db_passwd"]))
        except CredentialsError:
            print("Incorrect credentials")


def list_databases(ctx: ContextApp) -> None:
    table = PrettyTable()
    table.field_names = ["N.", "Name", "Filepath"]
    table.title = "Local databases"
    table.add_rows([[i, db.get_name(), Path(db.get_filename()).expanduser().resolve()] for i, db in enumerate(ctx.local_dbs, 1)])
    table.set_style(TableStyle.SINGLE_BORDER)
    local_lines = table.get_string().splitlines()

    table.clear_rows()
    table.title = "Remote databases"
    table.add_rows([[i, db.get_name(), Path(db.get_filename()).expanduser().resolve()] for i, db in enumerate(ctx.remote_dbs, 1)])
    remote_lines = table.get_string().splitlines()
    
    filling = len(local_lines[0]) if len(local_lines) < len(remote_lines) else len(remote_lines[0])
    # Pad lines so both tables have the same number of rows
    for line1, line2 in zip_longest(local_lines,
                                    remote_lines, 
                                    fillvalue=" " * filling):
        print(f"{line1}   {line2}")
    
def add_group(ctx: ContextApp) -> None:
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

def add_entry(ctx: ContextApp) -> None:
    pass

def delete_group(ctx: ContextApp) -> None:
    pass

def delete_entry(ctx: ContextApp) -> None:
    pass

def save_changes(ctx: ContextApp) -> None:
    pass

def close_local_db(ctx: ContextApp):
    idx, db_type = database_selection(ctx)
    if db_type == "l":
        db_to_close = ctx.local_dbs.pop(idx)
        print(f"Closed local database: {db_to_close.get_name()}")

    else:
        # TODO add logic to handle the transition from online to offline database
        db_to_close = ctx.remote_dbs.pop(idx)
        print(f"Closed remote database: {db_to_close.get_name()}")
