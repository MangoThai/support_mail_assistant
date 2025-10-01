# Incident HTTP 502 (Bad Gateway)

**Symptômes** : Erreur 502 sur la page de connexion.

**Procédure :**
1. Vérifier l'état du **reverse proxy**.
2. Redémarrer le service `auth-gateway`.
3. Contrôler les logs `/var/log/auth-gateway/*.log`.
4. Si persistant, escalader au niveau **INFRA**.

**Notes** : code HTTP **502**, lié à la chaîne proxy.
