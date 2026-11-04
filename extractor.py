import subprocess
import os
import sys

from extractor_ecm import extraer_ecm
from extractor_canal import extraer_canal

def ejecutar_todo():
    print("=== INICIANDO EXTRACCIÓN ===")
    
    # 1. Extraer ECM
  #  try:
  #      extraer_ecm()
  #  except Exception as e:
  #      print(f"❌ Error crítico en ECM: {e}")
    
    # 2. Extraer Canal
    try:
        extraer_canal()
    except Exception as e:
        print(f"❌ Error crítico en Canal: {e}")
    
    # 3. Subir a GitHub de forma segura y transparente
    print("\n🚀 Comprobando cambios para subir a GitHub...")
    try:
        subprocess.run(["git", "config", "user.email", "bot@ligafutbol.com"], check=True)
        subprocess.run(["git", "config", "user.name", "LigaFutbol Bot"], check=True)
        
        # Añadimos TODO (incluyendo archivos nuevos como extractor_canal.py)
        subprocess.run(["git", "add", "-A"], check=True)
        
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        
        if status.stdout.strip():
            # Intentamos hacer commit y mostramos el error si falla
            commit_result = subprocess.run(
                ["git", "commit", "-m", "Actualización de datos y escudos"],
                capture_output=True, text=True, check=False
            )
            if commit_result.returncode != 0:
                print("❌ El commit ha fallado. Detalle:")
                print(commit_result.stdout)
                print(commit_result.stderr)
                return
            
            print("✅ Commit realizado correctamente.")
            
            # Pull seguro con autostash
            pull_result = subprocess.run(
                ["git", "pull", "origin", "main", "--rebase", "--autostash"],
                capture_output=True, text=True, check=False
            )
            
            if pull_result.returncode == 0:
                push_result = subprocess.run(
                    ["git", "push", "origin", "main"],
                    capture_output=True, text=True, check=False
                )
                if push_result.returncode == 0:
                    print("✅ ¡Todo subido a GitHub! Render se actualizará.")
                else:
                    print("❌ Error al hacer push:")
                    print(push_result.stdout)
                    print(push_result.stderr)
            else:
                print("⚠️ No se pudo hacer pull. Detalle:")
                print(pull_result.stdout)
                print(pull_result.stderr)
                subprocess.run(["git", "rebase", "--abort"], check=False)
        else:
            print("ℹ️ No hay cambios en los datos.")
            
    except Exception as e:
        print(f"❌ Error inesperado al subir a GitHub: {e}")
        subprocess.run(["git", "rebase", "--abort"], check=False)

if __name__ == "__main__":
    ejecutar_todo()
