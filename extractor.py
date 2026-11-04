import os
import subprocess
import shutil
from extractor_ecm import extraer_ecm
from extractor_canal import extraer_canal

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
        print("🤖 Entorno GitHub Actions detectado. Saltando ECM (bloquea IPs de nube).")
    else:
        print("🏠 Entorno local detectado. Generando backups y extrayendo ECM...")
        generar_backups()
        try:
            extraer_ecm()
        except Exception as e:
            print(f"❌ Error crítico en ECM: {e}")
    
    try:
        extraer_canal()
    except Exception as e:
        print(f"❌ Error crítico en Canal: {e}")
    
    print("\n🚀 Comprobando cambios para subir a GitHub...")
    try:
        subprocess.run(["git", "config", "user.email", "bot@ligafutbol.com"], check=True)
        subprocess.run(["git", "config", "user.name", "LigaFutbol Bot"], check=True)
        
        subprocess.run(["git", "add", "."], check=False)
        
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        
        if status.stdout.strip():
            subprocess.run(["git", "commit", "-m", "Actualización automática de datos"], check=True)
            
            pull_result = subprocess.run(["git", "pull", "origin", "main", "--rebase", "--autostash"], capture_output=True, text=True, check=False)
            
            if pull_result.returncode == 0:
                push_result = subprocess.run(["git", "push", "origin", "main"], capture_output=True, text=True, check=False)
                if push_result.returncode == 0:
                    print("✅ ¡Todo subido a GitHub!")
                else:
                    print("❌ Error al hacer push:", push_result.stderr)
            else:
                print("⚠️ No se pudo hacer pull.", pull_result.stderr)
                subprocess.run(["git", "rebase", "--abort"], check=False)
        else:
            print("ℹ️ No hay cambios.")
    except Exception as e:
        print(f"❌ Error inesperado en Git: {e}")
        subprocess.run(["git", "rebase", "--abort"], check=False)

if __name__ == "__main__":
    ejecutar_todo()
