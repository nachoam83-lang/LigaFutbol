import requests
import json
import time
import urllib3
import subprocess
import os

# Ocultar avisos de SSL (vital para saltarse el certificado roto de ECMADRID)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest"
}

# Creamos la carpeta de escudos si no existe
os.makedirs("static/escudos", exist_ok=True)

def descargar_escudo(url_escudo):
    """Descarga el escudo de ECMADRID y lo guarda en local. Devuelve la ruta local."""
    if not url_escudo: return ""
    
    # Si ya empieza por http, es una URL completa, si no, le añadimos el dominio
    url_completa = f"https://juegosdeportivos.ecmadrid.org{url_escudo}" if url_escudo.startswith("/") else url_escudo
    
    # Sacamos el nombre del archivo (ej: Emblema_0039.jpg)
    nombre_archivo = url_completa.split("/")[-1]
    ruta_local = f"/static/escudos/{nombre_archivo}"
    ruta_fisica = f"static/escudos/{nombre_archivo}"
    
    # Si ya lo tenemos descargado, no lo volvemos a descargar
    if not os.path.exists(ruta_fisica):
        try:
            r = requests.get(url_completa, headers=HEADERS, verify=False, timeout=10)
            if r.status_code == 200:
                with open(ruta_fisica, "wb") as f:
                    f.write(r.content)
        except Exception as e:
            print(f"  ⚠️ No se pudo descargar el escudo {nombre_archivo}")
            return url_escudo # Si falla, dejamos la url original
            
    return ruta_local

def get_json(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        data = r.json()
        if isinstance(data, str): data = json.loads(data)
        return data
    except Exception as e:
        print(f"Error en la URL: {e}")
        return None

def extraer_todo():
    print("🚀 Iniciando extracción. Descargando datos y escudos...")
    datos_finales = {"competiciones": {}, "calendario": {}, "resultados": {}, "clasificacion": {}}
    deportes = {1: "Baloncesto", 2: "Fútbol Sala", 3: "Voleibol"}
    
    for id_deporte, nombre_deporte in deportes.items():
        print(f"\n⚽ Analizando Deporte: {nombre_deporte} (ID: {id_deporte})")
        datos_finales["competiciones"][str(id_deporte)] = []
        
        url_comp = f"https://juegosdeportivos.ecmadrid.org/api/CompeticionesPorDeporte?action=ObtenerCompeticionesDeporteListado&IdDeporte={id_deporte}&IdTemporada=12&elementoTodas=false&soloActivas=true&_={int(time.time()*1000)}"
        data_comp = get_json(url_comp)
        
        if not data_comp: continue
            
        items_comp = data_comp.get("data", data_comp.get("Data", [])) if isinstance(data_comp, dict) else data_comp
        if not isinstance(items_comp, list) or len(items_comp) == 0: continue
            
        for comp in items_comp:
            id_comp = comp.get("Id")
            nombre_comp = comp.get("Nombre")
            if not id_comp or id_comp <= 0: continue
            
            print(f"  🏆 Competición: {nombre_comp} (ID: {id_comp})")
            
            id_cat_real = id_comp
            if comp.get("IdCompeticionPadre") and comp.get("IdCompeticionPadre") > 0:
                id_cat_real = comp.get("IdCompeticionPadre")
            else:
                url_cat = f"https://juegosdeportivos.ecmadrid.org/api/CategoriasPorCompeticion?action=ObtenerCategoriasCompeticionListado&IdCompeticion={id_comp}&_={int(time.time()*1000)}"
                data_cat = get_json(url_cat)
                items_cat = data_cat.get("data", data_cat.get("Data", [])) if isinstance(data_cat, dict) else data_cat
                if items_cat and isinstance(items_cat, list) and len(items_cat) > 0:
                    id_cat_real = items_cat[0].get("Id", id_comp)

            url_grupos = f"https://juegosdeportivos.ecmadrid.org/api/GruposPorCategoria?action=ObtenerGruposCategoriaListado&IdCategoria={id_cat_real}&IdCompeticion={id_comp}&elementoTodas=false&_={int(time.time()*1000)}"
            data_grupos = get_json(url_grupos)
            items_grupos = data_grupos.get("data", data_grupos.get("Data", [])) if isinstance(data_grupos, dict) else data_grupos
            
            lista_grupos = []
            if items_grupos and isinstance(items_grupos, list):
                for grupo in items_grupos:
                    id_grupo = grupo.get("Id")
                    nombre_grupo = grupo.get("Nombre")
                    if not id_grupo or id_grupo <= 0: continue
                    
                    print(f"    👥 Grupo: {nombre_grupo}")
                    lista_grupos.append({"Id": id_grupo, "Nombre": nombre_grupo})
                    key_grupo = f"{id_deporte}_{id_comp}_{id_cat_real}_{id_grupo}"
                    
                    url_cal = f"https://juegosdeportivos.ecmadrid.org/Calendarios/ObtenerDatosJornadaGrupo?IdDeporte={id_deporte}&IdCompeticion={id_comp}&IdCategoria={id_cat_real}&IdGrupo={id_grupo}&IdJornada=0&IdEquipo=0"
                    cal = get_json(url_cal)
                    if cal:
                        datos_finales["calendario"][key_grupo] = cal
                        todos_los_partidos = []
                        
                        # Descargamos escudos de los partidos del calendario
                        for e in cal.get("jornada", {}).get("Enfrentamientos", []):
                            e["URLEscudoEquipoLocal"] = descargar_escudo(e.get("URLEscudoEquipoLocal"))
                            e["URLEscudoEquipoVisitante"] = descargar_escudo(e.get("URLEscudoEquipoVisitante"))

                        for j in cal.get("jornadas", []):
                            url_j = f"https://juegosdeportivos.ecmadrid.org/Calendarios/ObtenerDatosJornadaGrupo?IdDeporte={id_deporte}&IdCompeticion={id_comp}&IdCategoria={id_cat_real}&IdGrupo={id_grupo}&IdJornada={j['Id']}&IdEquipo=0"
                            cal_j = get_json(url_j)
                            if cal_j and "jornada" in cal_j:
                                for e in cal_j["jornada"].get("Enfrentamientos", []):
                                    e["NumeroJornada"] = j["NumeroJornada"]
                                    e["URLEscudoEquipoLocal"] = descargar_escudo(e.get("URLEscudoEquipoLocal"))
                                    e["URLEscudoEquipoVisitante"] = descargar_escudo(e.get("URLEscudoEquipoVisitante"))
                                    todos_los_partidos.append(e)
                                    
                        datos_finales["resultados"][key_grupo] = todos_los_partidos
                        
                        tabla = {}
                        for p in todos_los_partidos:
                            local, visitante = p.get("EquipoLocal"), p.get("EquipoVisitante")
                            if not local or not visitante: continue
                            if local not in tabla: tabla[local] = {"NombreEquipo": local, "URLEscudo": p.get("URLEscudoEquipoLocal"), "Puntos": 0, "Jugados": 0, "GF": 0, "GC": 0}
                            if visitante not in tabla: tabla[visitante] = {"NombreEquipo": visitante, "URLEscudo": p.get("URLEscudoEquipoVisitante"), "Puntos": 0, "Jugados": 0, "GF": 0, "GC": 0}
                            
                            estado, rl, rv = p.get("EstadoPartido", ""), p.get("ResultadoEquipoLocal", 0), p.get("ResultadoEquipoVisitante", 0)
                            if "Jugado" in estado or "Finalizado" in estado or rl > 0 or rv > 0:
                                tabla[local]["Jugados"] += 1; tabla[visitante]["Jugados"] += 1
                                tabla[local]["GF"] += rl; tabla[local]["GC"] += rv
                                tabla[visitante]["GF"] += rv; tabla[visitante]["GC"] += rl
                                if rl > rv: tabla[local]["Puntos"] += 3
                                elif rl < rv: tabla[visitante]["Puntos"] += 3
                                else: tabla[local]["Puntos"] += 1; tabla[visitante]["Puntos"] += 1
                                
                        lista_tabla = list(tabla.values())
                        lista_tabla.sort(key=lambda x: (x["Puntos"], x["GF"] - x["GC"], x["GF"]), reverse=True)
                        for i, eq in enumerate(lista_tabla): eq["Posicion"] = i + 1
                        datos_finales["clasificacion"][key_grupo] = lista_tabla

            datos_finales["competiciones"][str(id_deporte)].append({
                "Id": id_comp, "IdCategoria": id_cat_real, "Nombre": nombre_comp, "Grupos": lista_grupos
            })

    with open("datos_liga.json", "w", encoding="utf-8") as f:
        json.dump(datos_finales, f, ensure_ascii=False, indent=2)
        
    print("\n✅ ¡Extracción completada! Archivo 'datos_liga.json' y escudos creados.")
    
    # --- SUBIR A GITHUB ---
    print("🚀 Subiendo datos y escudos a GitHub...")
    mensaje_alerta = "✅ Proceso finalizado.\n\nLos datos y los escudos se han actualizado correctamente."
    
    try:
        subprocess.run(["git", "config", "user.email", "bot@ligafutbol.com"], check=True)
        subprocess.run(["git", "config", "user.name", "LigaFutbol Bot"], check=True)

        subprocess.run(["git", "add", "datos_liga.json"], check=True)
        subprocess.run(["git", "add", "static/escudos"], check=True) # Añadimos la carpeta de escudos
        
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if status.stdout.strip():
            subprocess.run(["git", "commit", "-m", "Actualización de datos y escudos"], check=True)
            subprocess.run(["git", "push", "origin", "main"], check=True)
            print("✅ ¡Todo subido a GitHub! Render se actualizará.")
            mensaje_alerta = "✅ Actualización realizada con éxito.\n\nDatos y escudos subidos a la nube."
        else:
            print("ℹ️ No hay cambios nuevos.")
            mensaje_alerta = "ℹ️ Los datos ya estaban actualizados."
            
    except Exception as e:
        print(f"❌ Error inesperado al subir a GitHub: {e}")
        mensaje_alerta = f"❌ Hubo un problema al subir a GitHub.\n\n{e}"

    # --- MOSTRAR CUADRO DE DIÁLOGO FINAL ---
    script_osascript = f'display alert "LigaFutbol" message "{mensaje_alerta}" as informational buttons {{"Aceptar"}} default button "Aceptar"'
    subprocess.run(["osascript", "-e", script_osascript])

if __name__ == "__main__":
    extraer_todo()
