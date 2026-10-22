#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gdrive_bridge.py — acces Google Drive stable, sans reconnexion horaire.

MODE 1 — oauth    : votre compte. Refresh token hors ligne stocke localement,
                    access token d'1 h renouvele en silence, automatiquement.
MODE 2 — service  : compte de service GCP. Aucun OAuth, aucun token d'1 h.

Dependances :
    pip install google-api-python-client google-auth google-auth-oauthlib
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from io import BytesIO
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as SACredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

APP_DIR = Path(os.environ.get("GDRIVE_HOME", Path.home() / ".gdrive-bridge"))
TOKEN_FILE = APP_DIR / "token.json"
CLIENT_FILE = APP_DIR / "credentials.json"
SA_FILE = APP_DIR / "service_account.json"

SCOPES = ["https://www.googleapis.com/auth/drive"]
FILE_FIELDS = "files(id,name,mimeType,size,modifiedTime,webViewLink),nextPageToken"


def _die(msg: str, code: int = 1):
    print(f"\n[ERREUR] {msg}\n", file=sys.stderr)
    sys.exit(code)


def _info(msg: str):
    print(f"  {msg}")


def _resolve(path: Path) -> Path:
    """Cherche le fichier a APP_DIR ou dans le repertoire courant."""
    if path.exists():
        return path
    alt = APP_DIR / path.name
    if alt.exists():
        return alt
    _die(f"Fichier introuvable : {path} (ni {alt}). Voir la section Setup.")


def _user_credentials():
    if not TOKEN_FILE.exists():
        _die(
            "Aucun token local. Lancez d'abord :  python gdrive_bridge.py login --mode oauth"
        )
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            _info("Token expire -> renouvellement silencieux en cours...")
            creds.refresh(Request())
            _save_token(creds)
        else:
            _die("Token invalide et sans refresh token. Relancez : login --mode oauth")
    return creds


def _save_token(creds):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass


def cmd_login(args):
    client = _resolve(CLIENT_FILE)
    flow = InstalledAppFlow.from_client_secrets_file(str(client), SCOPES)
    creds = flow.run_local_server(port=args.port, prompt="consent")
    _save_token(creds)
    _info(f"Token enregistre : {TOKEN_FILE}")
    _info(f"Refresh token present : {'OUI' if creds.refresh_token else 'NON'}")
    if not creds.refresh_token:
        _die(
            "Pas de refresh token -> la connexion expirera dans 1 h. "
            "Refaites le login avec prompt=consent, ou verifiez l'ecran de "
            "consentement OAuth (portee hors ligne).",
            code=2,
        )


def _service_credentials(quota_project):
    key = _resolve(SA_FILE)
    return SACredentials.from_service_account_file(
        str(key), scopes=SCOPES, quota_project_id=quota_project
    )


def build_service(args):
    if args.mode == "service":
        creds = _service_credentials(args.quota_project)
    else:
        creds = _user_credentials()
    options = {}
    if args.quota_project:
        options["quota_project_id"] = args.quota_project
    return build("drive", "v3", credentials=creds, cache_discovery=False,
                 client_options=options or None)


def _sa_email(args) -> str:
    try:
        return json.loads(_resolve(SA_FILE).read_text(encoding="utf-8")).get("client_email", "?")
    except SystemExit:
        return "(mode oauth)"


def cmd_doctor(args):
    svc = build_service(args)
    _info(f"mode            : {args.mode}")
    _info(f"compte de service: {_sa_email(args)}")
    try:
        about = svc.about().get(fields="user,storageQuota,canCreateDrives").execute()
        user = about.get("user", {})
        quota = about.get("storageQuota", {})
        _info(f"utilisateur     : {user.get('emailAddress', '?')}")
        _info(f"quota           : {quota.get('limit', '?')} octets "
              f"(usage {quota.get('usage', '?')})")
        _info(f"creation de Drive partage possible : {about.get('canCreateDrives')}")
    except HttpError as exc:
        _info(f"lecture 'about' impossible : {exc}")
    if args.mode == "oauth" and TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        exp = creds.expiry.isoformat() if creds.expiry else "?"
        _info(f"access token    : expire le {exp}")
        _info(f"refresh token   : {'PRESENT (renouvellement automatique OK)' if creds.refresh_token else 'ABSENT (probleme)'}")
    print("\n[OK] Connexion operationnelle — aucun renouvellement manuel necessaire.\n")


def cmd_list(args):
    svc = build_service(args)
    params = {
        "fields": FILE_FIELDS,
        "pageSize": args.max,
        "supportsAllDrives": True,
        "includeItemsFromAllDrives": True,
    }
    if args.folder:
        params["q"] = f"'{args.folder}' in parents and trashed = false"
    elif args.query:
        params["q"] = args.query
    else:
        params["q"] = "trashed = false"
    if args.drive_id:
        params["corpora"] = "drive"
        params["driveId"] = args.drive_id
    items, token = [], None
    while True:
        if token:
            params["pageToken"] = token
        resp = svc.files().list(**params).execute()
        items += resp.get("files", [])
        token = resp.get("nextPageToken")
        if not token:
            break
    print(f"{len(items)} element(s) :")
    for f in items:
        size = f.get("size", "-")
        print(f"  {f['id']}  {f.get('modifiedTime','')[:19]:19}  {str(size):>10}  {f['name']}")
    return items


def _resolve_file(svc, args):
    if args.file_id:
        return args.file_id
    resp = svc.files().list(
        q=f"name = '{args.name}' and trashed = false",
        fields="files(id,name,size,modifiedTime)",
        pageSize=5,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    files = resp.get("files", [])
    if not files:
        _die(f"Aucun fichier nomme « {args.name} »")
    files.sort(key=lambda f: f.get("modifiedTime", ""), reverse=True)
    return files[0]["id"]


def cmd_download(args):
    svc = build_service(args)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    fid = _resolve_file(svc, args)
    meta = svc.files().get(fileId=fid, fields="name,size,mimeType",
                           supportsAllDrives=True).execute()
    buf = BytesIO()
    dl = MediaIoBaseDownload(buf, svc.files().get_media(fileId=fid, supportsAllDrives=True))
    done = False
    while not done:
        _, done = dl.next_chunk()
    target = out_dir / meta["name"]
    target.write_bytes(buf.getvalue())
    _info(f"Telecharge : {target} ({target.stat().st_size} octets)")
    print(target)


def cmd_sync(args):
    """Telecharge tous les fichiers d'un dossier vers un repertoire local."""
    svc = build_service(args)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    params = {
        "fields": FILE_FIELDS,
        "pageSize": 200,
        "supportsAllDrives": True,
        "includeItemsFromAllDrives": True,
    }
    if args.drive_id:
        params["corpora"] = "drive"
        params["driveId"] = args.drive_id
    if args.folder:
        params["q"] = f"'{args.folder}' in parents and trashed = false"
    else:
        params["q"] = "trashed = false"
    if args.ext:
        params["q"] += f" and (mimeType contains '{args.ext}' or name contains '{args.ext}')"
    items, token = [], None
    while True:
        if token:
            params["pageToken"] = token
        resp = svc.files().list(**params).execute()
        items += resp.get("files", [])
        token = resp.get("nextPageToken")
        if not token:
            break
    n = 0
    for f in items:
        if f.get("mimeType", "").endswith("google-apps.folder"):
            continue
        target = out_dir / f["name"]
        if target.exists() and not args.force:
            continue
        try:
            buf = BytesIO()
            dl = MediaIoBaseDownload(
                buf, svc.files().get_media(fileId=f["id"], supportsAllDrives=True)
            )
            done = False
            while not done:
                _, done = dl.next_chunk()
            target.write_bytes(buf.getvalue())
            n += 1
            _info(f"+ {f['name']}")
        except HttpError as exc:
            _info(f"! ignore {f['name']} : {exc}")
    print(f"\n{n} fichier(s) synchronise(s) vers {out_dir}")


def cmd_upload(args):
    svc = build_service(args)
    path = Path(args.file)
    if not path.exists():
        _die(f"Fichier absent : {path}")
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = {"name": path.name}
    if args.folder:
        body["parents"] = [args.folder]
    media = MediaIoBaseUpload(path.open("rb"), mimetype=mime, resumable=True)
    resp = svc.files().create(
        body=body, media_body=media, fields="id,name,webViewLink", supportsAllDrives=True
    ).execute()
    _info(f"Envoye : {resp.get('name')} -> {resp.get('webViewLink')}")


def main():
    p = argparse.ArgumentParser(
        description="Pont Google Drive sans coupure horaire.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exemples :\n"
               "  python gdrive_bridge.py login --mode oauth\n"
               "  python gdrive_bridge.py doctor --mode oauth\n"
               "  python gdrive_bridge.py list --mode oauth --folder <ID>\n"
               "  python gdrive_bridge.py sync --mode oauth --folder <ID> --out ./assets\n"
               "  python gdrive_bridge.py upload --mode service ./out.mp4 --folder <ID>\n",
    )
    p.add_argument("command",
                   choices=["login", "doctor", "list", "download", "sync", "upload"])
    p.add_argument("--mode", choices=["oauth", "service"], default="oauth")
    p.add_argument("--quota-project", default=None,
                   help="Projet de quota (ecriture depuis un compte de service sans quota)")
    p.add_argument("--drive-id", default=None, help="ID d'un Drive partage")
    p.add_argument("--folder", default=None, help="ID du dossier")
    p.add_argument("--query", default=None, help="Requete Drive brute")
    p.add_argument("--out", default="./gdrive-assets", help="Repertoire de sortie")
    p.add_argument("--file-id", default=None)
    p.add_argument("--name", default=None, help="Nom exact du fichier a telecharger")
    p.add_argument("--file", default=None, help="Chemin local pour l'upload")
    p.add_argument("--ext", default=None, help="Filtre d'extension pour sync")
    p.add_argument("--max", type=int, default=50)
    p.add_argument("--force", action="store_true", help="Reecrase les fichiers existants")
    p.add_argument("--port", type=int, default=8765, help="Port du callback OAuth")
    args = p.parse_args()

    handlers = {
        "login": cmd_login, "doctor": cmd_doctor, "list": cmd_list,
        "download": cmd_download, "sync": cmd_sync, "upload": cmd_upload,
    }
    try:
        handlers[args.command](args)
    except HttpError as exc:
        _die(f"Erreur Google Drive : {exc}")
    except KeyboardInterrupt:
        print("\n[ANNULE]")


if __name__ == "__main__":
    main()
