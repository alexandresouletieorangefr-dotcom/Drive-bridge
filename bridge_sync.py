# bridge_sync.py — Miroir Google Drive -> ./assets/<Dossier>/<fichier> + manifest.json
#
# Connexion PERMANENTE (aucun token d'1 h a renouveler a la main) :
#   --mode service : compte de service GCP (cle JSON, n'expire jamais)  <- recommande
#   --mode oauth   : refresh token personnel (renouvele en silence)
#
# Usage :  python bridge_sync.py --doctor
#          python bridge_sync.py --sync
import argparse
import datetime
import json
import os
import re
import sys
from io import BytesIO
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as SACredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError 
from googleapiclient.http import MediaIoBaseDownload

HOME = Path(os.environ.get("GDRIVE_HOME", Path.home() / ".gdrive-bridge"))
SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_MIME = "application/vnd.google-apps.folder"
FILE_FIELDS = "files(id,name,mimeType,size,modifiedTime,parents,md5Checksum)"
MAX_MB = int(os.environ.get("BRIDGE_MAX_MB", "200"))


def log(msg):
    print(f"[bridge] {msg}", flush=True)


def build_service(mode):
    if mode == "service":
        sa = HOME / "service_account.json"
        if not sa.exists():
            sys.exit(f"[ERREUR] {sa} introuvable")
        creds = SACredentials.from_service_account_file(str(sa), scopes=SCOPES)
    else:
        tok = HOME / "token.json"
        if not tok.exists():
            sys.exit(f"[ERREUR] {tok} introuvable")
        creds = Credentials.from_authorized_user_file(tok, SCOPES)
        if not creds.valid and creds.refresh_token:
            log("renouvellement silencieux du token...")
            creds.refresh(Request())
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def list_all(svc, q, fields):
    out, token = [], None
    while True:
        resp = svc.files().list(
            q=q, fields=fields, pageSize=1000,
            supportsAllDrives=True, includeItemsFromAllDrives=True,
            pageToken=token,
        ).execute()
        out.extend(resp.get("files", []))
        token = resp.get("nextPageToken")
        if not token:
            break
    return out


def safe(name):
    """Nom de fichier / d'asset safe (GitHub refuse certains caracteres)."""
    name = re.sub(r"[^\w.\-]+", "_", name, flags=re.UNICODE).strip("_")
    return name or "fichier"


def doctor(svc, mode):
    log(f"mode : {mode}")
    try:
        about = svc.about().get(fields="user,storageQuota").execute()
        user = about.get("user", {})
        quota = about.get("storageQuota", {})
        log(f"utilisateur : {user.get('emailAddress', user.get('displayName', '?'))}")
        log(f"quota : {quota.get('limit', '?')} octets")
    except HttpError as exc:
        log(f"lecture 'about' impossible : {exc}")
    files = list_all(svc, "trashed = false", FILE_FIELDS)
    log(f"{len(files)} fichier(s) visible(s) pour ce compte")
    log("[OK] connexion operative.")


def sync(svc, mode, out_root):
    out_root.mkdir(parents=True, exist_ok=True)

    folders = {
        f["id"]: f.get("name", "dossier")
        for f in list_all(svc, f"mimeType = '{FOLDER_MIME}' and trashed = false",
                          "files(id,name,parents)")
    }
    files = [
        f for f in list_all(svc, "trashed = false", FILE_FIELDS)
        if f.get("mimeType") != FOLDER_MIME
    ]
    log(f"{len(folders)} dossier(s), {len(files)} fichier(s) visibles")

    manifest = {
        "generated_at": "",
        "mode": mode,
        "total_files": len(files),
        "folders": {},
        "assets": {},
    }

    downloaded = skipped = failed = 0
    for f in files:
        parents = f.get("parents") or []
        parent = parents[0] if parents else ""
        fname = f.get("name", "fichier")
        folder = folders.get(parent, parent or "racine")
        fdir = out_root / safe(folder)
        fdir.mkdir(parents=True, exist_ok=True)
        target = fdir / safe(fname)
        asset_name = f"{safe(folder)}__{safe(fname)}"
        size = int(f.get("size") or 0)

        if size > MAX_MB * 1024 * 1024:
            log(f"! ignore (trop gros, {size // 1024 // 1024} Mo) : {fname}")
            failed += 1
            continue

        if target.exists() and (size == 0 or target.stat().st_size == size):
            skipped += 1
        else:
            try:
                buf = BytesIO()
                dl = MediaIoBaseDownload(
                    buf, svc.files().get_media(fileId=f["id"], supportsAllDrives=True)
                )
                done = False
                while not done:
                    _, done = dl.next_chunk()
                target.write_bytes(buf.getvalue())
                downloaded += 1
            except HttpError as exc:
                log(f"! echec {fname} : {exc}")
                failed += 1
                continue

        entry = {
            "asset": asset_name,
            "name": fname,
            "drive_id": f["id"],
            "folder": folder,
            "folder_id": parent,
            "path": f"{safe(folder)}/{safe(fname)}",
            "size": size,
            "modifiedTime": f.get("modifiedTime", ""),
            "mimeType": f.get("mimeType", ""),
        }
        manifest["assets"][asset_name] = entry
        manifest["folders"].setdefault(parent, {"name": folder, "files": []})["files"].append(entry)

    manifest["generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    manifest["stats"] = {"downloaded": downloaded, "skipped": skipped, "failed": failed}
    (out_root.parent / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log(f"telecharges={downloaded} ignores={skipped} echecs={failed}")
    log("manifest.json ecrit")


def main():
    ap = argparse.ArgumentParser(description="Miroir Google Drive -> GitHub Release.")
    ap.add_argument("--mode", choices=["service", "oauth"],
                    default=os.environ.get("GDRIVE_MODE", "service"))
    ap.add_argument("--out", default="./assets")
    ap.add_argument("--doctor", action="store_true")
    ap.add_argument("--sync", action="store_true")
    args = ap.parse_args()

    svc = build_service(args.mode)
    if args.doctor:
        doctor(svc, args.mode)
    if args.sync:
        sync(svc, args.mode, Path(args.out))
    if not args.doctor and not args.sync:
        doctor(svc, args.mode)
        sync(svc, args.mode, Path(args.out))


if __name__ == "__main__":
    main()
