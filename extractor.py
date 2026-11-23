from datetime import datetime
import os
import shutil
import subprocess
from zoneinfo import ZoneInfo
import urllib3
from extractor_canal import extraer_canal
from extractor_ecm import SESSION, extraer_ecm

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ZONA_MADRID = ZoneInfo("Europe/Madrid")
ARCHIVOS_BACKUP = [
    ("datos_canal.json", "datos_canal_backup.json"),
    ("datos_liga.json", "datos_liga_backup.json"),
]


def test_ecm_connection() -> bool:
    """Prueba rápida para ver si ECM nos deja entrar (directo, proxy o Worker)."""
    via = (
        "Worker"
        if os.getenv("ECM_WORKER")
        else ("proxy" if os.getenv("ECM_PROXY") else "directo")
    )
    clave_info = (
        f" · clave definida: {'sí' if os.getenv('ECM_WORKER_KEY') else 'NO'}"
        if via == "Worker"
        else ""
    )
    print(f"   Ruta a ECM: {via}{clave_info}")

    url_test = (
        "https://juegosdeportivos.ecmadrid.org/api/CompeticionesPorDeporte"
        "?action=ObtenerCompeticionesDeporteListado&IdDeporte=1&IdTemporada=12"
        "&elementoTodas=false&soloActivas=true"
    )
    try:
        res = SESSION.get(url_test, timeout=25, verify=False)
        print(
            f"   Respuesta: HTTP {res.status_code} · "
            f"{len(res.content)} bytes · {res.text[:80]!r}"
        )
        return res.status_code == 200
    except Exception as e:
        print(f"   Error de conexión: {type(e).__name__}: {str(e)[:150]}")
        return False


def actualizar_backups_diarios(hora_minima: int = 14) -> None:
    """Actualiza el backup una vez al día si es de un día anterior y ya pasó hora_minima (Madrid)."""
    ahora = datetime.now(ZONA_MADRID)
    print(
        f"🌙 Verificando condición de backup diario "
        f"(desde las {hora_minima:02d}:00 hora Madrid)..."
    )

    for principal, backup in ARCHIVOS_BACKUP:
        if not os.path.exists(principal):
            continue

        if not os.path.exists(backup):
            shutil.copy2(principal, backup)
            print(f"📦 Backup inicial creado para {backup}.")
            continue

        fecha_backup = datetime.fromtimestamp(
            os.path.getmtime(backup), tz=ZONA_MADRID
        ).date()

        if ahora.date() > fecha_backup and ahora.hour >= hora_minima:
            shutil.copy2(principal, backup)
            print(
                f"🌙 Backup actualizado para {backup} "
                f"({ahora.strftime('%Y-%m-%d %H:%M')})."
            )
        else:
            print(f"ℹ️ El backup {backup} se mantiene estable.")


def _run_git(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=check,
    )


def subir_cambios_git() -> None:
    """Añade los JSON, backups y static/, hace commit y sube a origin/main."""
    print("\n🚀 Comprobando cambios para subir a GitHub...")
    en_rebase = False
    try:
        _run_git(["config", "user.email", "bot@ligafutbol.com"])
        _run_git(["config", "user.name", "LigaFutbol Bot"])

        rutas = [
            "datos_canal.json",
            "datos_liga.json",
            "datos_canal_backup.json",
            "datos_liga_backup.json",
            "static/",
        ]
        rutas_existentes = [r for r in rutas if os.path.exists(r)]
        if rutas_existentes:
            _run_git(["add", *rutas_existentes], check=False)

        status = _run_git(["status", "--porcelain"], check=False)
        if not status.stdout.strip():
            print("ℹ️ No hay cambios nuevos en los JSON o backups para subir.")
            return

        _run_git(
            ["commit", "-m", "Actualización automática de datos y horarios"]
        )

        pull_result = _run_git(
            ["pull", "origin", "main", "--rebase", "--autostash"], check=False
        )
        if pull_result.returncode != 0:
            en_rebase = True
            print("⚠️ No se pudo hacer pull --rebase:", pull_result.stderr.strip())
            _run_git(["rebase", "--abort"], check=False)
            return

        push_result = _run_git(["push", "origin", "main"], check=False)
        if push_result.returncode == 0:
            print("✅ ¡Todo actualizado y subido a GitHub con éxito!")
        else:
            print("❌ Error al hacer push:", push_result.stderr.strip())

    except Exception as e:
        print(f"❌ Error inesperado en Git: {e}")
        if en_rebase:
            _run_git(["rebase", "--abort"], check=False)


def ejecutar_todo() -> None:
    print("=== INICIANDO EXTRACCIÓN ===")
    es_github_action = os.environ.get("GITHUB_ACTIONS") == "true"

    if es_github_action:
        print("🤖 Entorno GitHub Actions detectado. Verificando conexión con ECM...")
        if test_ecm_connection():
            print("✅ ¡ECM responde a la nube! Procediendo con la extracción completa.")
            try:
                extraer_ecm()
            except Exception as e:
                print(f"❌ Error crítico en ECM: {e}")
        else:
            print(
                "⚠️ ECM bloquea o no responde desde la nube. "
                "Saltando ECM para no ensuciar el log."
            )
    else:
        print("🏠 Entorno local detectado. Extrayendo ECM...")
        try:
            extraer_ecm()
        except Exception as e:
            print(f"❌ Error crítico en ECM: {e}")

    try:
        extraer_canal()
    except Exception as e:
        print(f"❌ Error crítico en Canal: {e}")

    # 1. Actualiza los backups tras extraer (si son de un día anterior y >= 14:00 hora Madrid)
    actualizar_backups_diarios(hora_minima=14)

    # 2. Sube los JSON, los backups y static/ a GitHub
    subir_cambios_git()


if __name__ == "__main__":
    ejecutar_todo()
