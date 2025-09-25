from time import time
from pykeepass.exceptions import CredentialsError
from Pyro5.api import URI
from Pyro5.errors import CommunicationError, NamingError
import questionary
from questionary import prompt, ValidationError, Validator, Choice
from prettytable import PrettyTable, TableStyle
from pathlib import Path
from itertools import zip_longest
from database.db_local import DBLocal
from database.db_interface import DBInterface
from remote.db_expose import DBExpose
from remote.db_remote import DBRemote
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
        db_type_str = "Local" if isinstance(db, DBLocal) else "Exposed" if isinstance(db, DBExpose) else "Remote"
        display_name = f"[{db_type_str}] {db.get_name()} ({db_id})"
        choices[display_name] = db_id

    if not choices:
        questionary.print("There are no open databases!", style="bold fg:red")
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
        local_id = ctx.add_database(db)
        db.local_id = local_id

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
            local_db = DBLocal(Path(results["db_path"]).expanduser().resolve(), results["db_passwd"])
            local_id = ctx.add_database(local_db)
            local_db.local_id = local_id
        except CredentialsError:
           questionary.print("Incorrect credentials", style="bold fg:red")

def list_databases(ctx: ContextApp) -> None:
    local_lines = []
    remote_lines = []
    for idx, db in ctx.get_indexes_databases():
        line = [idx, db.get_name(), Path(db.get_filename()).expanduser().resolve()]
        if isinstance(db, DBLocal): 
            local_lines.append(line)
        elif isinstance(db, DBRemote):
            line[1] = "[r] " + line[1] # Stilystic choice to differentiate remote dbs from exposed ones
            remote_lines.append(line)
        else:
            line[1] = "[e] " + line[1] # Stilystic choice to differentiate remote dbs from exposed ones
            remote_lines.append(line)
    table = PrettyTable()
    table.field_names = ["N.", "Name", "Filepath"]
    table.title = "Local databases"
    table.add_rows(local_lines)
    table.set_style(TableStyle.SINGLE_BORDER)
    local_lines = table.get_string().splitlines()

    table.clear_rows()
    table.title = "Remote and exposed databases"
    table.add_rows(remote_lines)
    remote_lines = table.get_string().splitlines()
    
    filling = len(local_lines[0]) if len(local_lines) < len(remote_lines) else len(remote_lines[0])
    # Pad lines so both tables have the same number of rows
    for line1, line2 in zip_longest(local_lines,
                                    remote_lines, 
                                    fillvalue=" " * filling):
        questionary.print(f"{line1}   {line2}")

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

    questionary.print(str(table))

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

    questionary.print(str(table))
    
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
        questionary.print(f"{e}", style="bold fg:red")

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
        questionary.print(f"{e}", style="bold fg:red")

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
        questionary.print(f"{e}", style="bold fg:red")

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
        questionary.print(f"{e}", style="bold fg:red")

def save_changes(ctx: ContextApp) -> None:
    idx = database_selection(ctx)
    db = ctx.get_database(idx)
    if not db:
        return
    
    db.save_changes()

def close_db(ctx: ContextApp) -> None:
    # TODO add logic to handle the transition from online to offline database
    idx = database_selection(ctx)
    closed_db = ctx.remove_database(idx)
    if not closed_db:
        questionary.print("The chosen database is not open!", style="bold fg:red")
    elif isinstance(closed_db, DBLocal):
        questionary.print(f"Closed local database: {closed_db.get_name()}")
    elif isinstance(closed_db, DBExpose):
        # TODO check that the unregistration works
        # TODO add logic to inform the followers
        closed_db.unregister_object(ctx.daemon)
        ctx.unregister_uri(closed_db.get_name())
        ctx.unregister_ignored_service(closed_db.uri)
        questionary.print(f"Closed exposed database: {closed_db.get_name()}")
    else:
        # TODO close the connection
        # Remember to close the connections with the proxies
        ctx.unregister_ignored_service(closed_db.leader_uri)
        ctx.add_service_from_db_name(closed_db.get_name())
        questionary.print(f"Closed remote database: {closed_db.get_name()}")

def list_available_dbs(ctx: ContextApp) -> None:
    lines = [[name.split(".")[0], info[1], info[2]] for name, info in ctx.get_services_information()]
    table = PrettyTable()
    table.set_style(TableStyle.SINGLE_BORDER)
    table.field_names = ["Name", "IP address", "Port"]
    table.title = "Exposed databases"
    table.add_rows(lines)

    questionary.print(str(table))
            
def share_database(ctx: ContextApp) -> None:
    idx = database_selection(ctx)
    db = ctx.get_database(idx)

    if not db:
        return

    if isinstance(db, DBExpose) or isinstance(db, DBRemote):
        questionary.print("The database to share needs to be local!", style="bold fg:red")
        return
    
    if db.get_name() in ctx.get_advertiser().get_services():
        questionary.print("You have already shared a database with that name!", style="bold fg:red")
        return
    
    expose_db = DBExpose.create_and_register(db, ctx)
    ctx.register_ignored_service(expose_db.uri)
    ctx.register_uri(expose_db.get_name(), expose_db.uri)

    try:
        ctx.replace_database(idx, expose_db)
    except KeyError:
        questionary.print("Something went wrong while adding the remote database" \
            "to the list of open databases", style="bold fg:red")

def connect_database(ctx: ContextApp) -> None:
    # Add check for when the user inputs the name of a db that doesn't exist
    choices = {}
    for name, info in ctx.get_services_information():
        display_name = f"{name.split(".")[0]} ({info[1]}) ({info[2]})"
        choices[display_name] = (info[0], name)

    if not choices:
        questionary.print("There are no exposed databases!", style="bold fg:red")
        return
    
    while True:
        selected_display_name = questionary.autocomplete(
            "Start typing to connect to a database:",
            choices=choices.keys(),
            ignore_case=True,
            match_middle=True,
        ).ask()

        if selected_display_name is None:
        # User cancelled the operation
            return
        
        confirmation = questionary.confirm(f"You selected '{selected_display_name}'. Is this correct?").ask()
        if not confirmation:
            continue
        selected_uri = choices[selected_display_name][0]
        
        questions = [
                {
                    "type": "path",
                    "name": "db_path",
                    "message": "Insert a file name for the local copy of the database:",
                    "validate": NameValidator
                    },
                {
                    "type": "password",
                    "name": "db_passwd",
                    "message": "Insert the database password:",
                    },
                ]
        results = prompt(questions)
        if not results:
            return

        path = Path(results["db_path"].strip()).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        db_remote = DBRemote.create_and_register(selected_uri, ctx, results["db_passwd"], path)
        if db_remote:
            # There could be a mismatch between the local name given by the leader of the database and the actual exposed name
            # if the name chosen was already chosen by a mDNS service.
            db_remote.set_name(selected_display_name.split()[0])
            ctx.register_ignored_service(selected_uri)
            ctx.remove_service(choices[selected_display_name][1])
            local_id = ctx.add_database(db_remote)
            db_remote.local_id = local_id
        return
    
def read_notifications(ctx: ContextApp) -> None:
    if ctx.notifications_counter() <= 0:
        questionary.print("There are no notifications to read!", style="bold fg:red")
        return

    for notification in ctx.get_notifications():
        questionary.print(notification.message)
    
    questionary.print("Expired notifications will be deleted", style="bold fg:green")
    ctx.remove_stale_notifications()

def answer_notification(ctx: ContextApp) -> None:
    """Prompts the user to select a notification and answers"""
    notifications = ctx.get_notifications()
    notifications_messages = {notification.message: idx for idx, notification in enumerate(notifications)}

    if not notifications:
        questionary.print("There are no notifications!", style="bold fg:red")
        return
    
    while True:
        selected_notification = questionary.autocomplete(
            "Start typing to select the notification:",
            choices=notifications_messages.keys(),
            ignore_case=True,
            match_middle=True,
        ).ask()

        if selected_notification is None:
            return
        
        choice = questionary.confirm("Do you approve the change").ask()

        if not choice:
            return
        
        notification_id = notifications_messages[selected_notification]
        notification = notifications[notification_id]
        db = ctx.get_database(notification.db_id)
        if db.answer_notification(choice, notification):
            questionary.print("The vote was cast", style="bold")
            ctx.delete_notification(notifications_messages[selected_notification])
        else:
            questionary.print("There was a problem during the voting process", style="boold fg:red")

        return