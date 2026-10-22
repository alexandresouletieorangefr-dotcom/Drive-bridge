# Obtenir les credentials Google Drive

Deux voies. Choisissez celle qui colle a votre Drive.

---

## Voie A — OAuth (recommandee : acces total, aucun partage a faire)

Un refresh token personnel : acces a **tout** votre Drive, sans partage manuel
de dossier, et il ne se revoque pas tout seul.

### A1. Recuperer le script

    https://raw.githubusercontent.com/alexandresouletieorangefr-dotcom/Drive-bridge/main/gdrive_bridge.py

### A2. Client OAuth (une seule fois)

1. `console.cloud.google.com` → selectionner le projet **`mydrive-bridge`**
2. **APIs et services → Bibliothèque** → activer **Google Drive API**
3. **APIs et services → Écrans de consentement OAuth**
   - User Type : **Externe** → creer
   - App name / Support email / Developer contact : vos infos
   - ⚠️ **Publier l'application** → statut **Production**
     (en *Testing*, le refresh token expire apres **7 jours**)
4. **APIs et services → Identifiants → + Creer des identifiants → ID client OAuth**
   - Type : **Application de bureau**
   - Nom : `Digen Drive Bridge Desktop`
   - **Telecharger le JSON** → renommer **`credentials.json`**

### A3. Se connecter une fois (sur votre machine)

    pip install google-api-python-client google-auth google-auth-oauthlib
    python gdrive_bridge.py login --mode oauth

1. Un navigateur s'ouvre sur la page Google.
2. Si Google affiche « Cette application n'a pas ete verifiee » →
   **Parametres avances → Acceder a Digen Drive Bridge (non securise)**.
3. Acceptez les autorisations (Drive).
4. Le script ecrit `token.json` dans `~/.gdrive-bridge/`.

La ligne **« Refresh token present : OUI »** est la validation a surveiller.

### A4. Verifier

    python gdrive_bridge.py doctor --mode oauth
    python gdrive_bridge.py list --mode oauth --max 10

### A5. Transmettre

Joindre **`credentials.json`** ET **`token.json`** a la conversation.
Je les depose en secrets GitHub chiffres (sealed-box). Jamais dans le depot.

---

## Voie B — Compte de service (cle JSON qui n'expire jamais)

Aucune dependance a l'ecran de consentement Google, mais le compte de service
ne voit **que** ce qu'on lui partage explicitement.

### B1. Creer le compte de service

1. `console.cloud.google.com` → projet **`mydrive-bridge`**
2. **IAM et administration → Comptes de service → Creer**
3. Nom : **`digen-drive-bot`** → Creer
4. *(facultatif mais recommande)* onglet **Details** → cocher
   **« Activer l'API Google Drive pour ce compte de service »**

### B2. Creer la cle JSON

1. Ouvrir `digen-drive-bot` → onglet **Cles**
2. **Ajouter une cle → Creer une cle**
3. Type : **JSON** → **Creer** → `service_account.json` se telecharge

### B3. PARTAGER LES DOSSIERS (indispensable)

Un compte de service ne voit **rien** tant que vous ne l'avez pas partage.

1. Relevez son adresse e-mail, page du compte de service →
   `digen-drive-bot@<projet>.iam.gserviceaccount.com`
   (le suffixe exact est affiche dans le champ **Adresse e-mail**)
2. Dans Google Drive : ouvrir le **dossier racine** qui contient vos assets
   → **Partager → Ajouter des personnes**
   → coller l'adresse du compte de service
   → role **Lecteur** ou **Gestionnaire** → **Envoyer**
3. L'avertissement « Impossible d'envoyer a des comptes Google » est **normal**
   (le compte de service n'a pas d'interface) — partagez quand meme.

> ✅ **Le partage se propage.** Selon Google : « Les autorisations d'un dossier
> parent sont heritees par tous les fichiers et dossiers qu'il contient. »
> Partager le dossier racine suffit donc : les sous-dossiers et leurs fichiers
> sont couverts automatiquement. Inutile de partager chaque sous-dossier.

### B4. Transmettre

Joindre **`service_account.json`** a la conversation.
Je le depose en secret `GDRIVE_SERVICE_ACCOUNT_JSON` (chiffre).

---

## Verifier apres configuration

Le workflow `Drive Bridge` affiche un diagnostic :

- `utilisateur : <e-mail du compte de service>` → mode service
- `N fichier(s) visible(s) pour ce compte` → **0 = dossiers non partages**

Si 0 fichier : la cle est bonne, c'est le partage qui manque (voie B).
