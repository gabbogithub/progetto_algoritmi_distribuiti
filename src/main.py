from cli.cli_app import CLIApp
from context.context import ContextApp

def main():
    ctx = ContextApp()
    ctx.start_daemon_loop()
    app = CLIApp(ctx)
    app.run()

if __name__ == "__main__":
    main()
