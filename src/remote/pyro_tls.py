import Pyro5.api

# ---GENERAL TLS CONFIGURATIONS---
Pyro5.config.SSL = True
Pyro5.config.SSL_CACERTS = "certs/CA/ca.crt"    # to make ssl accept the self-signed server cert

# ---SERVER TLS CONFIGURATIONS---
Pyro5.config.SSL_REQUIRECLIENTCERT = True   # enable 2-way ssl
Pyro5.config.SSL_SERVERCERT = "certs/server/server.crt"
Pyro5.config.SSL_SERVERKEY = "certs/server/server.key"