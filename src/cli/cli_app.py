import questionary
from sys import exit
from collections import defaultdict
from .context import ContextApp
from . import actions

class CLIApp():

    def __init__(self):
        self.ctx = ContextApp()
        self.menu_actions = defaultdict(lambda: self._forced_exit)
        self.menu_actions.update({
                    "Create database": actions.create_database,
                    "Open local database": actions.open_database,
                    "List databases": actions.list_databases,
                    "List entries": actions.list_entries,
                    "List groups": actions.list_groups,
                    "Add group": actions.add_group,
                    "Add entry": actions.add_entry,
                    "Delete group": actions.delete_group,
                    "Delete entry": actions.delete_entry,
                    "Save changes": actions.save_changes,
                    "Close local database": actions.close_local_db,
                    "Exit": self._exit_loop,
                    })


    def run(self):
        while True:
            action = questionary.select(
                "What do you want to do?",
                choices=self.menu_actions.keys()).ask()

            self.menu_actions[action](self.ctx)

    def _exit_loop(self, ctx: ContextApp) -> None:
        confirmation = questionary.confirm("Are you sure you want to exit?").ask()
        if confirmation:
            exit(0)

    def _forced_exit(self, ctx: ContextApp) -> None:
        exit(1)
