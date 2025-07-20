import getpass
from pykeepass import PyKeePass, create_database
from client.db_local import DBLocal

def main():
    db_name = input("Inserisci il nome del database: ")
    try:
        db_pass = getpass.getpass(prompt="Inserisci la password del database: ")
        db = DBLocal(db_name, db_pass)
        for i in range(1000):
            db.add_group2([""], f"{i}")
        db.save_changes()
    except Exception as error:
        print('ERROR', error)

if __name__ == "__main__":
    main()
