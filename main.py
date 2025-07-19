import getpass
from pykeepass import PyKeePass, create_database
from client.db_local import DBLocal

def main():
    """
    db_name = input("Inserisci il nome del database: ")
    try:
        db_pass = getpass.getpass(prompt="Inserisci la password del database: ")
    except Exception as error:
        print('ERROR', error)
    else:
    """
    db = DBLocal("prova", "prova")
    print(db._pk_db.find_groups(name="Root"))
        #db.add_group("root", "gruppone")

if __name__ == "__main__":
    main()
