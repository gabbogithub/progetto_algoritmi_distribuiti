from pykeepass.exceptions import CredentialsError
import questionary
from questionary import prompt, ValidationError, Validator, Choice
from prettytable import PrettyTable, TableStyle
from pathlib import Path
from itertools import zip_longest
from database.db_local import DBLocal
from database.db_interface import DBInterface
from context.context import ContextApp

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

        for _, open_db in self.ctx.get_indexes_databases():
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

def database_selection(ctx: ContextApp) -> int:
    """Prompts the user to select a database and returns the associated index"""
    choices = {}
    for db_id, db in ctx.get_indexes_databases():
        db_type_str = "Local" if isinstance(db, DBLocal) else "Remote"
        display_name = f"[{db_type_str}] {db.get_name()} ({db_id})"
        choices[display_name] = db_id

    if not choices:
        print("There are no open databases!")
        return -1
    
    while True:
        selected_display_name = questionary.autocomplete(
            "Start typing to select the database:",
            choices=choices.keys(),
            ignore_case=True,
            match_middle=True,
        ).ask()

        if selected_display_name is None:
        # User cancelled the operation
            return -1
        
        selected_id = choices[selected_display_name]

        confirmation = questionary.confirm(f"You selected '{selected_display_name}'. Is this correct?").ask()

        if confirmation:
            return selected_id

def create_database(ctx: ContextApp) -> None:
    questions = [
            {
                "type": "path",
                "name": "db_path",
                "message": "Insert the database file name:",
                "validate": NameValidator
                },
            {
                "type": "text",
                "name": "db_name",
                "message": "Insert the database name:",
                },
            {
                "type": "password",
                "name": "db_passwd",
                "message": "Insert the database password:",
                },
            ]
    results = prompt(questions)
    if results:
        path = Path(results["db_path"].strip()).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        db = DBLocal.create_db(path, results["db_passwd"], results["db_name"])
        ctx.add_database(db)

def open_database(ctx: ContextApp) -> None:
    questions = [
            {
                "type": "path",
                "name": "db_path",
                "message": "Insert the database path:",
                "validate": ListValidator(ctx),
                },
            {
                "type": "password",
                "name": "db_passwd",
                "message": "Insert the database password:",
                },
            ]
    results = prompt(questions)
    if results:
        try:
            ctx.add_database(DBLocal(Path(results["db_path"]).expanduser().resolve(), results["db_passwd"]))
        except CredentialsError:
            print("Incorrect credentials")
            
def share_database(ctx: ContextApp) -> None:
    pass

def list_databases(ctx: ContextApp) -> None:
    local_lines = []
    remote_lines = []
    for idx, db in ctx.get_indexes_databases():
        line = [idx, db.get_name(), Path(db.get_filename()).expanduser().resolve()]
        if isinstance(db, DBLocal): 
            local_lines.append(line)
        else:
            remote_lines.append(line)
    table = PrettyTable()
    table.field_names = ["N.", "Name", "Filepath"]
    table.title = "Local databases"
    table.add_rows(local_lines)
    table.set_style(TableStyle.SINGLE_BORDER)
    local_lines = table.get_string().splitlines()

    table.clear_rows()
    table.title = "Remote databases"
    table.add_rows(remote_lines)
    remote_lines = table.get_string().splitlines()
    
    filling = len(local_lines[0]) if len(local_lines) < len(remote_lines) else len(remote_lines[0])
    # Pad lines so both tables have the same number of rows
    for line1, line2 in zip_longest(local_lines,
                                    remote_lines, 
                                    fillvalue=" " * filling):
        print(f"{line1}   {line2}")

def list_entries(ctx: ContextApp) -> None:
    idx = database_selection(ctx)
    db = ctx.get_database(idx)
    if not db:
        return

    table = PrettyTable()
    table.set_style(TableStyle.SINGLE_BORDER)
    table.field_names = ["Title", "Username", "Password", "Path"]
    table.title = "Database entries"

    table.add_rows([
        [entry.title, entry.username, entry.password, "/".join(entry.path)] 
        for entry in db.get_entries()
        ])

    print(table)

def list_groups(ctx: ContextApp) -> None:
    idx = database_selection(ctx)
    db = ctx.get_database(idx)
    if not db:
        return

    table = PrettyTable()
    table.set_style(TableStyle.SINGLE_BORDER)
    table.field_names = ["Name", "Path"]
    table.title = "Database groups"

    table.add_rows([[group.name, "/".join(group.path)] for group in db.get_groups()])

    print(table)
    
def add_group(ctx: ContextApp) -> None:
    idx = database_selection(ctx)
    db = ctx.get_database(idx)
    if not db:
        return
    questions = [
            {
                "type": "text",
                "name": "parent_group",
                "message": "Insert the parent group path (separated by \"/\")\n  For the root group leave an empty input:",
                },
            {
                "type": "text",
                "name": "group_name",
                "message": "Insert the name of the new group:",
                },  
            ]
    results = prompt(questions)
    if not results:
        return

    try:
        db.add_group(results["parent_group"].split("/"), results["group_name"])
    except ValueError as e:
        # TODO check that other errors may be raised, especially by remote dabatases.
        print(e)

def add_entry(ctx: ContextApp) -> None:
    idx = database_selection(ctx)
    db = ctx.get_database(idx)
    if not db:
        return
    questions = [
            {
                "type": "text",
                "name": "parent_group",
                "message": "Insert the parent group path (separated by \"/\")\n  For the root group leave an empty input:",
                },
            {
                "type": "text",
                "name": "entry_title",
                "message": "Insert the title for the new entry:",
                },
            {
                "type": "text",
                "name": "entry_username",
                "message": "Insert the username for the new entry:",
                }, 
            {
                "type": "text",
                "name": "entry_password",
                "message": "Insert the password for the new entry:",
                },  
            ]
    results = prompt(questions)
    if not results:
        return

    try:
        db.add_entry(results["parent_group"].split("/"), results["entry_title"], results["entry_username"], results["entry_password"])
    except KeyError as e:
        # TODO check that other errors may be raised, especially by remote dabatases.
        print(e)

def delete_group(ctx: ContextApp) -> None:
    idx = database_selection(ctx)
    db = ctx.get_database(idx)
    if not db:
        return
    questions = [
            {
                "type": "text",
                "name": "group_path",
                "message": "Insert the group path (separated by \"/\"):",
                },
            ]
    results = prompt(questions)
    if not results:
        return

    try:
        db.delete_group(results["group_path"].split("/"))
        # TODO check that other errors may be raised, especially by remote dabatases.
    except KeyError as e:
        print(e)

def delete_entry(ctx: ContextApp) -> None:
    idx = database_selection(ctx)
    db = ctx.get_database(idx)
    if not db:
        return
    questions = [
            {
                "type": "text",
                "name": "entry_path",
                "message": "Insert the entry path (separated by \"/\"):",
                },
            ]
    results = prompt(questions)
    if not results:
        return

    try:
        db.delete_entry(results["entry_path"].split("/"))
    except KeyError as e:
        # TODO check that other errors may be raised, especially by remote dabatases.
        print(e)

def save_changes(ctx: ContextApp) -> None:
    idx = database_selection(ctx)
    db = ctx.get_database(idx)
    if not db:
        return
    
    db.save_changes()

def close_local_db(ctx: ContextApp):
    # TODO add logic to handle the transition from online to offline database
    idx = database_selection(ctx)
    closed_db = ctx.remove_database(idx)
    if not closed_db:
        print("The chosen database is not open!")
    elif isinstance(closed_db, DBLocal):
        print(f"Closed local database: {closed_db.get_name()}")
    else:
        print(f"Closed remote database: {closed_db.get_name()}")
