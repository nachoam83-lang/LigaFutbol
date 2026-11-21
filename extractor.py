import os
import subprocess
import shutil
import requests
import urllib3
from extractor_ecm import extraer_ecm, SESSION
from extractor_canal import extraer_canal

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def test_ecm_connection():
    """Prueba rápida para ver si ECM nos deja entrar (directo o por el Worker). Imprime el motivo si falla."""
    via = "Worker" if os.getenv("ECM_WORKER") else ("proxy" if os.getenv("ECM_PROXY") else "directo")
    print(f"   Ruta a ECM: {via}" + (f" · clave definida: {'sí' if os.getenv('ECM_WORKER_KEY') else 'NO'}" if via == "Worker" else ""))
    try:
        url_test = "https://juegosdeportivos.ecmadrid.org/api/CompeticionesPorDeporte?action=ObtenerCompeticionesDeporteListado&IdDeporte=1&IdTemporada=12&elementoTodas=false&soloActivas=true"
        res = SESSION.get(url_test, timeout=25, verify=False)
        print(f"   Respuesta: HTTP {res.status_code} · {len(res.content)} bytes · {res.text[:80]!r}")
        return res.status_code == 200
    except Exception as e:
        print(f"   Error de conexión: {type(e).__name__}: {str(e)[:150]}")
        return False

from datetime import datetime

def actualizar_backups_nocturnos():
    archivos = [
        ("datos_canal.json", "datos_canal_backup.json"),
        ("datos_liga.json", "datos_liga_backup.json")
    ]
    
    ahora = datetime.now()
    print("🌙 Verificando condición de backup nocturno (23:59)...")
    
    for principal, backup in archivos:
        if not os.path.exists(principal):
            continue

        # Si el backup no existe, lo creamos directamente
        if not os.path.exists(backup):
            shutil.copy(principal, backup)
            print(f"📦 Backup inicial creado para {principal}.")
            continue

        # Comprobamos la fecha del archivo de backup actual
        tiempo_mod_backup = os.path.getmtime(backup)
        fecha_backup = datetime.fromtimestamp(tiempo_mod_backup)

        # Si ya estamos en un día posterior y son las 23:00 o más tarde, actualizamos el backup
        if ahora.date() > fecha_backup.date() and ahora.hour >= 23:
            shutil.copy(principal, backup)
            print(f"🌙 Backup nocturno actualizado para {principal} ({ahora.strftime('%Y-%m-%d %H:%M')}).")
        else:
            print(f"ℹ️ El backup de {principal} se mantiene estable.")

def generar_backups():
    print("📦 Generando archivos de backup...")
    try:
        if os.path.exists("datos_liga.json"):
            shutil.copy("datos_liga.json", "datos_liga_backup.json")
        if os.path.exists("datos_canal.json"):
            shutil.copy("datos_canal.json", "datos_canal_backup.json")
    except Exception as e:
        print(f"⚠️ Error generando backups: {e}")

def ejecutar_todo():
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
            print("⚠️ ECM sigue bloqueando las IPs de la nube (Timeout). Saltando ECM para no ensuciar el log.")
    else:
        print("🏠 Entorno local detectado. Generando backups y extrayendo ECM...")
        generar_backups()
        try:
            extraer_ecm()
        except Exception as e:
            print(f"❌ Error crítico en ECM: {e}")
    
    # Extraer Canal (ahora con el buscador dinámico de PDF reparado)
    try:
        extraer_canal()
    except Exception as e:
        print(f"❌ Error crítico en Canal: {e}")
    
    # Subir a GitHub
    print("\n🚀 Comprobando cambios para subir a GitHub...")
    try:
        subprocess.run(["git", "config", "user.email", "bot@ligafutbol.com"], check=True)
        subprocess.run(["git", "config", "user.name", "LigaFutbol Bot"], check=True)
        
        # Añadimos específicamente los json generados y la carpeta static por si hay escudos nuevos
        subprocess.run(["git", "add", "datos_canal.json", "datos_liga.json", "static/"], check=False)
        
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        
        if status.stdout.strip():
            subprocess.run(["git", "commit", "-m", "Actualización automática de datos y horarios"], check=True)
            
            pull_result = subprocess.run(["git", "pull", "origin", "main", "--rebase", "--autostash"], capture_output=True, text=True, check=False)
            
            if pull_result.returncode == 0:
                push_result = subprocess.run(["git", "push", "origin", "main"], capture_output=True, text=True, check=False)
                if push_result.returncode == 0:
                    print("✅ ¡Todo actualizado y subido a GitHub con éxito!")
                else:
                    print("❌ Error al hacer push:", push_result.stderr)
            else:
                print("⚠️ No se pudo hacer pull.", pull_result.stderr)
                subprocess.run(["git", "rebase", "--abort"], check=False)
        else:
            print("ℹ️ No hay cambios nuevos en los JSON para subir.")
    except Exception as e:
        print(f"❌ Error inesperado en Git: {e}")
        subprocess.run(["git", "rebase", "--abort"], check=False)

if __name__ == "__main__":
    ejecutar_todo()
