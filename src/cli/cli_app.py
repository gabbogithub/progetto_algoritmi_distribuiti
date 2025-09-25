from sys import exit
from collections import defaultdict
from context.context import ContextApp
import questionary
from . import actions
import threading
from time import sleep

class CLIApp():

    def __init__(self, ctx: ContextApp):
        self.ctx = ctx
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
                    "Close database": actions.close_db,
                    "List available exposed databases": actions.list_available_dbs,
                    "Share local database": actions.share_database,
                    "Connect to a remote database": actions.connect_database,
                    "Read notifications": actions.read_notifications,
                    "Answer notification": actions.answer_notification,
                    "Exit": self._exit_loop,
                    })


    def run(self) -> None:
        while True:
            questionary.print(f"\r[Notifications]: {self.ctx.notifications_counter()}", style="bold fg:yellow")
            action = questionary.select(
                "What do you want to do?",
                choices=self.menu_actions.keys()).ask()

            self.menu_actions[action](self.ctx)

    def _exit_loop(self, ctx: ContextApp) -> None:
        confirmation = questionary.confirm("Are you sure you want to exit?").ask()
        if confirmation:
            ctx.close_mdns_service()
            exit(0)

    def _forced_exit(self, ctx: ContextApp) -> None:
        ctx.close_mdns_service()
        exit(1)
