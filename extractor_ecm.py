import requests
import json
import time
import urllib3
import os
import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json", "X-Requested-With": "XMLHttpRequest"}
os.makedirs("static/escudos", exist_ok=True)
ARCHIVO_METADATA = "metadata_escudos.json"

# Creamos el archivo de metadatos vacío si no existe
if not os.path.exists(ARCHIVO_METADATA):
    with open(ARCHIVO_METADATA, "w", encoding="utf-8") as f:
        json.dump({}, f)

def cargar_metadata():
    with open(ARCHIVO_METADATA, "r", encoding="utf-8") as f:
        return json.load(f)

def guardar_metadata(metadata):
    with open(ARCHIVO_METADATA, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

def descargar_escudo(url_escudo, metadata):
    if not url_escudo: return ""
    url_completa = f"https://juegosdeportivos.ecmadrid.org{url_escudo}" if url_escudo.startswith("/") else url_escudo
    nombre_archivo = url_completa.split("/")[-1]
    ruta_local = f"/static/escudos/{nombre_archivo}"
    ruta_fisica = f"static/escudos/{nombre_archivo}"
    
    hoy = datetime.date.today()
    
    if url_escudo in metadata and os.path.exists(ruta_fisica):
        fecha_descarga = datetime.datetime.strptime(metadata[url_escudo]["fecha"], "%Y-%m-%d").date()
        if (hoy - fecha_descarga).days < 30:
            return ruta_local

    try:
        r = requests.get(url_completa, headers=HEADERS, verify=False, timeout=10)
        if r.status_code == 200:
            with open(ruta_fisica, "wb") as f:
                f.write(r.content)
            metadata[url_escudo] = {"fecha": hoy.strftime("%Y-%m-%d"), "archivo": ruta_local}
    except Exception:
        return url_escudo
        
    return ruta_local

def get_json(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        data = r.json()
        # ARREGLO: Si devuelve un string, intentamos parsearlo a JSON
        if isinstance(data, str): 
            data = json.loads(data)
        return data
    except Exception as e: 
        print(f"  ⚠️ Error parseando JSON: {e}")
        return None

def extraer_ecm():
    print("🚀 Iniciando extracción de ECMADRID...")
    metadata = cargar_metadata()
    datos_finales = {"competiciones": {}, "calendario": {}, "resultados": {}, "clasificacion": {}}
    deportes = {1: "Baloncesto", 2: "Fútbol Sala", 3: "Voleibol"}
    exito = False
    
    for id_deporte, nombre_deporte in deportes.items():
        print(f"\n⚽ Analizando Deporte: {nombre_deporte} (ID: {id_deporte})")
        datos_finales["competiciones"][str(id_deporte)] = []
        
        url_comp = f"https://juegosdeportivos.ecmadrid.org/api/CompeticionesPorDeporte?action=ObtenerCompeticionesDeporteListado&IdDeporte={id_deporte}&IdTemporada=12&elementoTodas=false&soloActivas=true&_={int(time.time()*1000)}"
        data_comp = get_json(url_comp)
        
        if not data_comp: continue
        exito = True 
            
        items_comp = data_comp.get("data", data_comp.get("Data", [])) if isinstance(data_comp, dict) else data_comp
        # ARREGLO: Asegurarnos de que es una lista antes de iterar
        if not isinstance(items_comp, list): continue
            
        for comp in items_comp:
            if not isinstance(comp, dict): continue # Saltamos si no es un diccionario
            id_comp, nombre_comp = comp.get("Id"), comp.get("Nombre")
            if not id_comp or id_comp <= 0: continue
            
            print(f"  🏆 Competición: {nombre_comp} (ID: {id_comp})")
            
            id_cat_real = comp.get("IdCompeticionPadre") if comp.get("IdCompeticionPadre") and comp.get("IdCompeticionPadre") > 0 else id_comp
            if id_cat_real == id_comp:
                url_cat = f"https://juegosdeportivos.ecmadrid.org/api/CategoriasPorCompeticion?action=ObtenerCategoriasCompeticionListado&IdCompeticion={id_comp}&_={int(time.time()*1000)}"
                data_cat = get_json(url_cat)
                items_cat = data_cat.get("data", data_cat.get("Data", [])) if isinstance(data_cat, dict) else data_cat
                if items_cat and isinstance(items_cat, list) and len(items_cat) > 0 and isinstance(items_cat[0], dict):
                    id_cat_real = items_cat[0].get("Id", id_comp)

            url_grupos = f"https://juegosdeportivos.ecmadrid.org/api/GruposPorCategoria?action=ObtenerGruposCategoriaListado&IdCategoria={id_cat_real}&IdCompeticion={id_comp}&elementoTodas=false&_={int(time.time()*1000)}"
            data_grupos = get_json(url_grupos)
            items_grupos = data_grupos.get("data", data_grupos.get("Data", [])) if isinstance(data_grupos, dict) else data_grupos
            
            lista_grupos = []
            if items_grupos and isinstance(items_grupos, list):
                for grupo in items_grupos:
                    if not isinstance(grupo, dict): continue
                    id_grupo, nombre_grupo = grupo.get("Id"), grupo.get("Nombre")
                    if not id_grupo or id_grupo <= 0: continue
                    
                    print(f"    👥 Grupo: {nombre_grupo}")
                    lista_grupos.append({"Id": id_grupo, "Nombre": nombre_grupo})
                    key_grupo = f"{id_deporte}_{id_comp}_{id_cat_real}_{id_grupo}"
                    
                    url_cal = f"https://juegosdeportivos.ecmadrid.org/Calendarios/ObtenerDatosJornadaGrupo?IdDeporte={id_deporte}&IdCompeticion={id_comp}&IdCategoria={id_cat_real}&IdGrupo={id_grupo}&IdJornada=0&IdEquipo=0"
                    cal = get_json(url_cal)
                    if cal:
                        datos_finales["calendario"][key_grupo] = cal
                        todos_los_partidos = []
                        
                        for e in cal.get("jornada", {}).get("Enfrentamientos", []):
                            e["URLEscudoEquipoLocal"] = descargar_escudo(e.get("URLEscudoEquipoLocal"), metadata)
                            e["URLEscudoEquipoVisitante"] = descargar_escudo(e.get("URLEscudoEquipoVisitante"), metadata)

                        for j in cal.get("jornadas", []):
                            url_j = f"https://juegosdeportivos.ecmadrid.org/Calendarios/ObtenerDatosJornadaGrupo?IdDeporte={id_deporte}&IdCompeticion={id_comp}&IdCategoria={id_cat_real}&IdGrupo={id_grupo}&IdJornada={j['Id']}&IdEquipo=0"
                            cal_j = get_json(url_j)
                            if cal_j and "jornada" in cal_j:
                                for e in cal_j["jornada"].get("Enfrentamientos", []):
                                    e["NumeroJornada"] = j["NumeroJornada"]
                                    e["URLEscudoEquipoLocal"] = descargar_escudo(e.get("URLEscudoEquipoLocal"), metadata)
                                    e["URLEscudoEquipoVisitante"] = descargar_escudo(e.get("URLEscudoEquipoVisitante"), metadata)
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

            datos_finales["competiciones"][str(id_deporte)].append({"Id": id_comp, "IdCategoria": id_cat_real, "Nombre": nombre_comp, "Grupos": lista_grupos})

    if exito:
        with open("datos_liga.json", "w", encoding="utf-8") as f:
            json.dump(datos_finales, f, ensure_ascii=False, indent=2)
        guardar_metadata(metadata)
        print("\n✅ ¡Extracción ECM completada!")
    else:
        print("\n❌ ERROR: No se pudo conectar con ECMADRID.")
