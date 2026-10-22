# Drive Bridge

Miroir permanent de Google Drive, sans dependre du connecteur OAuth de l'agent.

## Principe

Le connecteur Google Drive de l'agent se coupe toutes les heures (expiration du
token OAuth). Ce repo delegue le travail a un runner **GitHub Actions** gratuit,
qui lui se connecte a Drive avec une credence qui **n'expire jamais** :

- **compte de service GCP** (secret `GDRIVE_SERVICE_ACCOUNT_JSON`) — cle JSON, jamais d'expiration ;
- **OAuth refresh token** (secrets `GDRIVE_CLIENT_JSON` + `GDRIVE_TOKEN_JSON`) — le token d'1 h est renouvele en silence.

Toutes les 2 h, le runner :

1. liste l'integralite des fichiers visibles par le compte ;
2. les telecharge dans `assets/<Dossier>/<fichier>` ;
3. ecrit `manifest.json` (dossier, nom, `drive_id`, taille, date de modification) ;
4. publie les nouveaux assets dans une **GitHub Release** nommee `<Dossier>__<fichier>`.

L'agent lit ensuite la release via l'API GitHub (fiable) au lieu du connecteur Drive.

## Utilisation

- Declencher manuellement : onglet **Actions** > *Drive Bridge* > *Run workflow*.
- Consulter le resultat : **Releases** > `assets-<AAAAJJJJ-HHMM>`.
- `manifest.json` est publie comme asset de la release : c'est l'index complet
  (dossier -> fichiers -> `drive_id`).

## Secrets attendus

| Secret | Role | Requis |
|---|---|---|
| `GDRIVE_SERVICE_ACCOUNT_JSON` | Cle JSON du compte de service (mode `service`) | au moins un des deux modes |
| `GDRIVE_CLIENT_JSON` | `client_secret_*.json` du client OAuth | mode `oauth` |
| `GDRIVE_TOKEN_JSON` | `token.json` produit par `gdrive_bridge.py login` | mode `oauth` |

Les secrets sont chiffres (sealed box) et ne sont jamais ecrits dans le depot.

## Compte de service

Le compte de service doit avoir acces aux dossiers suivis : les partager avec
son adresse `client_email` (Depuis Google Drive > Partager > Ajouter des
lecteurs > adresse du compte de service).
