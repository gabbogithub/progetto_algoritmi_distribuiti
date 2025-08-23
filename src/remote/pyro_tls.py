import Pyro5.errors
import Pyro5.api

# ---GENERAL TLS CONFIGURATIONS---
Pyro5.config.SSL = True
Pyro5.config.SSL_CACERTS = "certs/combined_certs.pem"    # to make ssl accept the self-signed server cert

# ---CLIENT TLS CONFIGURATIONS---
Pyro5.config.SSL_CLIENTCERT = "certs/client_cert.pem"
Pyro5.config.SSL_CLIENTKEY = "certs/client_key.pem"

# ---SERVER TLS CONFIGURATIONS---
Pyro5.config.SSL_REQUIRECLIENTCERT = True   # enable 2-way ssl
Pyro5.config.SSL_SERVERCERT = "certs/server_cert.pem"
Pyro5.config.SSL_SERVERKEY = "certs/server_key.pem"

class CertCheckingProxy(Pyro5.api.Proxy):
    def verify_cert(self, cert):
        if not cert:
            raise Pyro5.errors.CommunicationError("server cert missing")
        if cert["serialNumber"] != "63814787F3ADE6ECD4B60922D228A90B54B39B7D":
            raise Pyro5.errors.CommunicationError("cert serial number incorrect", cert["serialNumber"])
        issuer = dict(p[0] for p in cert["issuer"])
        subject = dict(p[0] for p in cert["subject"])
        if issuer["organizationName"] != "Algoritmi distribuiti":
            raise Pyro5.errors.CommunicationError("Incorrect issuer")
        if subject["countryName"] != "IT":
            raise Pyro5.errors.CommunicationError("cert not for country IT")
        if subject["organizationName"] != "Algoritmi distribuiti":
            raise Pyro5.errors.CommunicationError("cert not for the expected subject")

    def _pyroValidateHandshake(self, response):
        cert = self._pyroConnection.getpeercert()
        self.verify_cert(cert)


class CertValidatingDaemon(Pyro5.api.Daemon):
    def validateHandshake(self, conn, data):
        cert = conn.getpeercert()
        if not cert:
            raise Pyro5.errors.CommunicationError("client cert missing")
        if cert["serialNumber"] != "0F98326014DE54AA4F3A223739AF1187EEFBEDBA":
            raise Pyro5.errors.CommunicationError("cert serial number incorrect", cert["serialNumber"])
        issuer = dict(p[0] for p in cert["issuer"])
        subject = dict(p[0] for p in cert["subject"])
        if issuer["organizationName"] != "Algoritmi distribuiti":
            raise Pyro5.errors.CommunicationError("cert not issued by the expected issuer")
        if subject["countryName"] != "IT":
            raise Pyro5.errors.CommunicationError("cert not for country IT")
        if subject["organizationName"] != "Algoritmi distribuiti":
            raise Pyro5.errors.CommunicationError("cert not for the expected subject")
        return super(CertValidatingDaemon, self).validateHandshake(conn, data)
