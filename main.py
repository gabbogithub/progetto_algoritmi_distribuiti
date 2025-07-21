import getpass
from pykeepass import PyKeePass, create_database
from client.db_local import DBLocal

def main():
    db_name = input("Inserisci il nome del database: ")
    try:
        db_pass = getpass.getpass(prompt="Inserisci la password del database: ")
        db = DBLocal(db_name, db_pass)
        db.add_group([""], "a")
        db.add_entry(["a"], "b", "c", "d")
        db.delete_entry(["a", "b"])
        try:
            db.delete_entry(["a", "b"])
        except:
            print("b")

        db.save_changes()
    except Exception as error:
        print('ERROR', error)

if __name__ == "__main__":
    main()
