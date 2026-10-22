# publish_release.py — publie le miroir ./assets dans une GitHub Release.
#
# Les assets sont nommes <Dossier>__<fichier> (noms uniques, pas de "/").
# Seuls les assets absents de la release precedente sont televerses (incrementiel).
#
# Usage :  python publish_release.py [tag]
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run(args, check=True):
    r = subprocess.run(args, capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.stderr.write(
            f"[publish] CMD FAILED: {' '.join(args)}\n{r.stdout}\n{r.stderr}\n"
        )
        raise SystemExit(1)
    return r


def main():
    tag = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    if not tag:
        stamp = run(["date", "-u", "+%Y%m%d-%H%M"]).stdout.strip()
        tag = f"assets-{stamp}"

    root = Path("assets")
    manifest_path = Path("manifest.json")
    if not manifest_path.exists():
        raise SystemExit("[publish] manifest.json absent — lancez d'abord bridge_sync.py --sync.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    tags = []
    r = run(["gh", "release", "list", "--limit", "50", "--json", "tagName"], check=False)
    if r.returncode == 0 and r.stdout.strip():
        tags = [x["tagName"] for x in json.loads(r.stdout)]

    published = set()
    prev = [t for t in tags if t != tag]
    if prev:
        r = run(["gh", "release", "view", prev[0], "--json", "assets"], check=False)
        if r.returncode == 0 and r.stdout.strip():
            published = {a["name"] for a in json.loads(r.stdout).get("assets", [])}
    print(f"[publish] assets deja publies : {len(published)}")

    if tag in tags:
        print(f"[publish] la release {tag} existe deja")
    else:
        run([
            "gh", "release", "create", tag,
            "--title", f"Drive mirror {tag}",
            "--notes", "Miroir automatique du Drive. Assets : <Dossier>__<fichier>.",
        ])
        print(f"[publish] release {tag} creee")

    stage = Path(tempfile.mkdtemp(prefix="stage-"))
    pending = []
    for asset_name, meta in manifest.get("assets", {}).items():
        if asset_name in published:
            continue
        src = root / meta.get("path", "")
        if not src.exists():
            continue
        link = stage / asset_name
        try:
            link.symlink_to(src.resolve())
        except OSError:
            shutil.copy2(src, link)
        pending.append(link)

    manifest_link = stage / "manifest.json"
    try:
        manifest_link.symlink_to(manifest_path.resolve())
    except OSError:
        shutil.copy2(manifest_path, manifest_link)
    pending.append(manifest_link)

    batch = 20
    for i in range(0, len(pending), batch):
        chunk = [str(p) for p in pending[i:i + batch]]
        run(["gh", "release", "upload", tag, *chunk, "--clobber"])

    print(f"[publish] {len(pending)} asset(s) televerse(s) dans {tag}")
    shutil.rmtree(stage, ignore_errors=True)


if __name__ == "__main__":
    main()
