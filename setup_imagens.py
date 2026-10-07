#!/usr/bin/env python3
"""Script temporário para baixar ícones de classe taxonômica (Wikimedia).

Será deletado após a execução para manter o repositório limpo.
"""

import os
import time
import requests

DEST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "imagens")

# URLs originais verificadas
IMAGES = {
    "default_mammalia.jpg": "https://upload.wikimedia.org/wikipedia/commons/7/73/Lion_waiting_in_Namibia.jpg",
    "default_aves.jpg": "https://upload.wikimedia.org/wikipedia/commons/1/1a/About_to_Launch_%2826075320352%29.jpg",
    "default_actinopterygii.jpg": "https://upload.wikimedia.org/wikipedia/commons/2/23/Georgia_Aquarium_-_Giant_Grouper_edit.jpg",
    "default_reptilia.jpg": "https://upload.wikimedia.org/wikipedia/commons/f/f4/Florida_Box_Turtle_Digon_many_2015.jpg",
    "default_amphibia.jpg": "https://upload.wikimedia.org/wikipedia/commons/4/44/Red-eyed_tree_frog_edit2.jpg",
    "default_insecta.jpg": "https://upload.wikimedia.org/wikipedia/commons/e/e0/Coccinella_septempunctata_-_front_%28aka%29.jpg",
    "default_arachnida.jpg": "https://upload.wikimedia.org/wikipedia/commons/4/4e/Brachypelma_smithi_2009_G03.jpg",
    "default_unknown.png": "https://upload.wikimedia.org/wikipedia/commons/4/46/Question_mark_%28black%29.svg",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"}
DELAY = 3  # segundos entre requests para evitar 429


def download_with_retry(url: str, dest: str, retries: int = 3) -> bool:
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=60)
            if resp.status_code == 429:
                wait = DELAY * (attempt + 2)
                print(f"    429 rate-limited, aguardando {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            with open(dest, "wb") as f:
                f.write(resp.content)
            return True
        except Exception as exc:
            print(f"    Tentativa {attempt+1}: {exc}")
            if attempt < retries - 1:
                time.sleep(DELAY * (attempt + 1))
    return False


def main() -> None:
    os.makedirs(DEST_DIR, exist_ok=True)
    ok = 0
    for filename, url in IMAGES.items():
        dest = os.path.join(DEST_DIR, filename)
        if os.path.isfile(dest):
            print(f"  [skip] {filename} já existe")
            ok += 1
            continue
        print(f"  Baixando {filename} ...")
        if download_with_retry(url, dest):
            size = os.path.getsize(dest)
            print(f"  [ok]   {filename} ({size} bytes)")
            ok += 1
        else:
            print(f"  [ERRO] {filename}: falha após retries")
        time.sleep(DELAY)

    print(f"\nConcluído! {ok}/{len(IMAGES)} imagens salvas em: {DEST_DIR}")


if __name__ == "__main__":
    main()
