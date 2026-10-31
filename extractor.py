import requests
import json
import time
import urllib3
import subprocess

# Ocultar los avisos de SSL de versiones antiguas de Mac
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest"
}

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
    print("🚀 Iniciando extracción masiva de datos. Esto puede tardar unos minutos...")
    datos_finales = {
        "competiciones": {},
        "calendario": {},
        "resultados": {},
        "clasificacion": {}
    }
    
    deportes = {1: "Baloncesto", 2: "Fútbol Sala", 3: "Voleibol"}
    
    for id_deporte, nombre_deporte in deportes.items():
        print(f"\n⚽ Analizando Deporte: {nombre_deporte} (ID: {id_deporte})")
        datos_finales["competiciones"][str(id_deporte)] = []
        
        # 1. Competiciones
        url_comp = f"https://juegosdeportivos.ecmadrid.org/api/CompeticionesPorDeporte?action=ObtenerCompeticionesDeporteListado&IdDeporte={id_deporte}&IdTemporada=12&elementoTodas=false&soloActivas=true&_={int(time.time()*1000)}"
        data_comp = get_json(url_comp)
        
        if not data_comp:
            print("  ❌ Error de conexión.")
            continue
            
        items_comp = data_comp.get("data", data_comp.get("Data", [])) if isinstance(data_comp, dict) else data_comp
        if not isinstance(items_comp, list) or len(items_comp) == 0:
            print("  ❌ No se encontraron competiciones.")
            continue
            
        for comp in items_comp:
            id_comp = comp.get("Id")
            nombre_comp = comp.get("Nombre")
            if not id_comp or id_comp <= 0: continue
            
            print(f"  🏆 Competición: {nombre_comp} (ID: {id_comp})")
            
            # 2. Categorías
            id_cat_real = id_comp
            if comp.get("IdCompeticionPadre") and comp.get("IdCompeticionPadre") > 0:
                id_cat_real = comp.get("IdCompeticionPadre")
            else:
                url_cat = f"https://juegosdeportivos.ecmadrid.org/api/CategoriasPorCompeticion?action=ObtenerCategoriasCompeticionListado&IdCompeticion={id_comp}&_={int(time.time()*1000)}"
                data_cat = get_json(url_cat)
                items_cat = data_cat.get("data", data_cat.get("Data", [])) if isinstance(data_cat, dict) else data_cat
                if items_cat and isinstance(items_cat, list) and len(items_cat) > 0:
                    id_cat_real = items_cat[0].get("Id", id_comp)

            # 3. Grupos
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
                    
                    # 4. Calendario
                    url_cal = f"https://juegosdeportivos.ecmadrid.org/Calendarios/ObtenerDatosJornadaGrupo?IdDeporte={id_deporte}&IdCompeticion={id_comp}&IdCategoria={id_cat_real}&IdGrupo={id_grupo}&IdJornada=0&IdEquipo=0"
                    cal = get_json(url_cal)
                    if cal:
                        datos_finales["calendario"][key_grupo] = cal
                        
                        # 5. Resultados y Clasificación
                        todos_los_partidos = []
                        jornadas = cal.get("jornadas", [])
                        for j in jornadas:
                            url_j = f"https://juegosdeportivos.ecmadrid.org/Calendarios/ObtenerDatosJornadaGrupo?IdDeporte={id_deporte}&IdCompeticion={id_comp}&IdCategoria={id_cat_real}&IdGrupo={id_grupo}&IdJornada={j['Id']}&IdEquipo=0"
                            cal_j = get_json(url_j)
                            if cal_j and "jornada" in cal_j:
                                enf = cal_j["jornada"].get("Enfrentamientos", [])
                                for e in enf:
                                    e["NumeroJornada"] = j["NumeroJornada"]
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
                "Id": id_comp,
                "IdCategoria": id_cat_real,
                "Nombre": nombre_comp,
                "Grupos": lista_grupos
            })

    with open("datos_liga.json", "w", encoding="utf-8") as f:
        json.dump(datos_finales, f, ensure_ascii=False, indent=2)
        
    print("\n✅ ¡Extracción completada! Archivo 'datos_liga.json' creado con éxito.")
    
    # --- SUBIR A GITHUB AUTOMÁTICAMENTE ---
    print("🚀 Comprobando si hay cambios para subir a GitHub...")
    mensaje_alerta = "✅ Proceso finalizado.\n\nLos datos se han extraído correctamente."
    
    try:
        subprocess.run(["git", "add", "datos_liga.json"], check=True)
        
        # Comprobamos si realmente hay cambios en el archivo
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if status.stdout.strip():
            subprocess.run(["git", "commit", "-m", "Actualización automática de datos"], check=True)
            subprocess.run(["git", "push", "origin", "main"], check=True)
            print("✅ ¡Datos subidos a GitHub! Render se actualizará en un minuto.")
            mensaje_alerta = "✅ Actualización realizada con éxito.\n\nLos nuevos datos se han subido a GitHub y la app se actualizará en un minuto."
        else:
            print("ℹ️ Los datos son los mismos que ya estaban en GitHub. No se sube nada.")
            mensaje_alerta = "ℹ️ Los datos ya estaban actualizados.\n\nNo ha habido cambios nuevos que subir."
            
    except Exception as e:
        print(f"❌ Error inesperado al subir a GitHub: {e}")
        mensaje_alerta = f"❌ Hubo un problema al subir a GitHub.\n\n{e}"

    # --- MOSTRAR CUADRO DE DIÁLOGO FINAL ---
    # Usamos AppleScript (osascript) para lanzar una ventana nativa de Mac
    script_osascript = f'display alert "LigaFutbol" message "{mensaje_alerta}" as informational buttons {{"Aceptar"}} default button "Aceptar"'
    subprocess.run(["osascript", "-e", script_osascript])

if __name__ == "__main__":
    extraer_todo()
