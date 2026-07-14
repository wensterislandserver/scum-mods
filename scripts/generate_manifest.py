#!/usr/bin/env python3
"""
Genera/actualiza manifest.json a partir de:
  - mods_config.json: metadata estable de cada mod (id, name, file, mandatory).
  - una carpeta local con los .pak actuales (release_paks/, por ejemplo).
  - el manifest.json anterior, para detectar qué archivos cambiaron de verdad.

Solo sube de versión (y apunta la URL a la nueva release) los mods cuyo
archivo cambió realmente (hash SHA-256 distinto al de la última vez). Los que
no cambiaron mantienen su versión, hash y URL tal cual estaban, así que
siguen sirviéndose desde la release anterior en la que se subieron por
última vez — no hace falta volver a subirlos.

Uso típico:
    python scripts/generate_manifest.py \
        --repo TU_ORG/scum-mods \
        --tag v7 \
        --mods-dir ./release_paks \
        --mods-config mods_config.json \
        --previous manifest.json \
        --output manifest.json

Al final imprime qué archivos hay que subir como assets de la nueva release
(los que cambiaron) y el comando `gh release create` ya armado.
"""
import argparse
import hashlib
import json
import os
import sys


def sha256_of_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path, default):
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", required=True, help="owner/repo de GitHub, p.ej. TU_ORG/scum-mods")
    parser.add_argument("--tag", required=True, help="tag de la release donde se subirán los mods NUEVOS/CAMBIADOS")
    parser.add_argument("--mods-dir", required=True, help="carpeta con los .pak actuales")
    parser.add_argument("--mods-config", required=True, help="mods_config.json con la metadata estable")
    parser.add_argument("--previous", default=None, help="manifest.json anterior (omitir la primera vez)")
    parser.add_argument("--output", default="manifest.json")
    parser.add_argument("--launcher-min-version", default=None)
    args = parser.parse_args()

    mods_config = load_json(args.mods_config, None)
    if mods_config is None:
        print(f"No se encontró {args.mods_config}", file=sys.stderr)
        sys.exit(1)

    previous = load_json(args.previous, {"mods": []})
    previous_by_id = {m["id"]: m for m in previous.get("mods", [])}

    new_mods = []
    to_upload = []

    for entry in mods_config["mods"]:
        mod_id = entry["id"]
        filename = entry["file"]
        local_path = os.path.join(args.mods_dir, filename)
        prev = previous_by_id.get(mod_id)

        if not os.path.exists(local_path):
            if prev:
                print(f"[aviso] no se encontró {filename} en {args.mods_dir}; se mantiene la entrada anterior tal cual.")
                new_mods.append(prev)
                continue
            print(f"[error] {filename} no existe y no hay entrada previa para '{mod_id}'.", file=sys.stderr)
            sys.exit(1)

        new_hash = sha256_of_file(local_path)

        if prev and prev.get("sha256") == new_hash:
            # No cambió: se mantiene versión/url/hash de la release anterior.
            new_mods.append(prev)
            continue

        prev_version = int(prev["version"]) if prev else 0
        new_version = prev_version + 1
        url = f"https://github.com/{args.repo}/releases/download/{args.tag}/{filename}"

        new_mods.append({
            "id": mod_id,
            "name": entry.get("name", mod_id),
            "version": str(new_version),
            "file": filename,
            "url": url,
            "sha256": new_hash,
            "mandatory": entry.get("mandatory", True),
        })
        to_upload.append(local_path)
        action = "actualizado" if prev else "nuevo"
        print(f"[{action}] {mod_id}: v{prev_version} -> v{new_version}")

    manifest = {
        "launcher_min_version": args.launcher_min_version or previous.get("launcher_min_version", "1.0.0"),
        "mods": new_mods,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"\nEscrito {args.output} con {len(new_mods)} mod(s) ({len(to_upload)} cambiado(s)).")

    if to_upload:
        quoted = " ".join(f'"{p}"' for p in to_upload)
        print("\nArchivos a subir en la nueva release:")
        for p in to_upload:
            print(f"  - {p}")
        print("\nComando sugerido:")
        print(f'  gh release create {args.tag} {quoted} --notes "Actualización de mods"')
        print("\nDespués de crear la release, sube también el manifest.json actualizado a main:")
        print(f'  git add {args.output} && git commit -m "manifest: {args.tag}" && git push')
    else:
        print("\nNingún mod cambió respecto al manifest anterior: no hace falta crear una release nueva.")


if __name__ == "__main__":
    main()
