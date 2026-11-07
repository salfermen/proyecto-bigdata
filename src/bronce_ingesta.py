"""Capa BRONCE: ingesta cruda e inmutable de los datasets oficiales de AMLSim.

- Descarga los .tgz del repositorio IBM/AMLSim (si no existen localmente).
- Los extrae sin modificar ningún archivo.
- Genera un manifiesto con linaje: URL, SHA-256, tamaño, conteo de filas y metadatos.

Uso:  python src/bronce_ingesta.py
"""
import hashlib
import json
import tarfile
import urllib.request
from datetime import datetime, timezone

from config import DIR_BRONCE, DIR_FUENTE, ESCENARIOS, URL_BASE


def sha256(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def contar_filas(ruta):
    with open(ruta, "rb") as f:
        return sum(1 for _ in f) - 1  # sin encabezado


def descargar(escenario):
    DIR_FUENTE.mkdir(parents=True, exist_ok=True)
    destino = DIR_FUENTE / f"{escenario}.tgz"
    url = f"{URL_BASE}/{escenario}.tgz"
    if not destino.exists():
        print(f"  descargando {url}")
        urllib.request.urlretrieve(url, destino)
    else:
        print(f"  ya existe {destino.name}, se reutiliza")
    return destino, url


def extraer(archivo_tgz):
    with tarfile.open(archivo_tgz, "r:gz") as tar:
        # filter="data" bloquea rutas absolutas, '..' y enlaces peligrosos
        tar.extractall(DIR_BRONCE, filter="data")


def leer_metadata(ruta):
    if not ruta.exists():
        return None
    return [l.strip() for l in ruta.read_text(encoding="utf-8").splitlines() if l.strip()]


def main():
    manifiesto = {
        "capa": "bronce",
        "fuente": "IBM/AMLSim (https://github.com/IBM/AMLSim), carpeta sample/",
        "fecha_ingesta_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "escenarios": {},
    }
    for esc, descripcion in ESCENARIOS.items():
        print(f"[bronce] {esc}")
        tgz, url = descargar(esc)
        extraer(tgz)
        carpeta = DIR_BRONCE / esc
        archivos = {}
        for f in sorted(carpeta.iterdir()):
            info = {"bytes": f.stat().st_size, "sha256": sha256(f)}
            if f.suffix == ".csv":
                info["filas"] = contar_filas(f)
            archivos[f.name] = info
        manifiesto["escenarios"][esc] = {
            "descripcion": descripcion,
            "url": url,
            "archivo_fuente": {"nombre": tgz.name, "bytes": tgz.stat().st_size, "sha256": sha256(tgz)},
            "metadata_simulador": leer_metadata(carpeta / "metadata.txt"),
            "archivos": archivos,
        }
        print(f"  cuentas={archivos['nodes.csv']['filas']:,}  transacciones={archivos['transactions.csv']['filas']:,}")

    salida = DIR_BRONCE / "_manifiesto_bronce.json"
    salida.write_text(json.dumps(manifiesto, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[bronce] manifiesto -> {salida}")


if __name__ == "__main__":
    main()
