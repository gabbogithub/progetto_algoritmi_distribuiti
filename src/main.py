import sys
from cli.cli_app import CLIApp
from context.context import ContextApp

def main():
    if len(sys.argv) < 3:
        print("You need to pass the client certificate and its key!\n" \
        "Usage: python follower.py <client_cert> <client_key>")
        sys.exit(1)
    ctx = ContextApp(sys.argv[1], sys.argv[2])
    ctx.start_daemon_loop()
    app = CLIApp(ctx)
    app.run()

if __name__ == "__main__":
    main()
