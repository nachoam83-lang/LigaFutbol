from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from datetime import datetime, timedelta
import json
import os
import urllib.parse

app = FastAPI(title="API Liga Fútbol Sala")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"])

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_index():
    return FileResponse("static/index.html")

def cargar_datos():
    if not os.path.exists("datos_liga.json"):
        return None
    with open("datos_liga.json", "r", encoding="utf-8") as f:
        return json.load(f)

# --- NUEVA FUNCIÓN PARA CARGAR LOS DATOS DE CANAL ---
def cargar_datos_canal():
    if not os.path.exists("datos_canal.json"):
        return {"equipos": [], "partidos": []}
    with open("datos_canal.json", "r", encoding="utf-8") as f:
        return json.load(f)
# ----------------------------------------------------

@app.get("/api/competiciones/{id_deporte}")
def get_competiciones(id_deporte: str):
    if id_deporte == "4": return [] # Canal no usa competiciones
    datos = cargar_datos()
    if not datos: return []
    return datos["competiciones"].get(str(id_deporte), [])

@app.get("/api/grupos/{id_categoria}/{id_competicion}")
def get_grupos(id_categoria: str, id_competicion: str):
    if id_categoria == "99": return [] # Canal no usa grupos
    datos = cargar_datos()
    if not datos: return []
    for id_dep, lista_comps in datos["competiciones"].items():
        for comp in lista_comps:
            if str(comp["Id"]) == id_competicion:
                return comp.get("Grupos", [])
    return []

# --- NUEVO ENDPOINT PARA EL DESPLEGABLE DE CANAL ---
@app.get("/api/equipos_canal")
def get_equipos_canal():
    datos_canal = cargar_datos_canal()
    return datos_canal.get("equipos", [])
# ---------------------------------------------------

@app.get("/api/calendario/{id_deporte}/{id_competicion}/{id_categoria}/{id_grupo}/{id_jornada}")
def get_calendario(id_deporte: str, id_competicion: str, id_categoria: str, id_grupo: str, id_jornada: str):
    if id_deporte == "4":
        datos_canal = cargar_datos_canal()
        partidos = [p for p in datos_canal.get("partidos", []) if p.get("EquipoLocal") == id_grupo or p.get("EquipoVisitante") == id_grupo]
        partidos.sort(key=lambda x: x["FechaHora"])
        
        jornadas_nums = sorted(list(set(p["NumeroJornada"] for p in partidos)))
        lista_jornadas = [{"NumeroJornada": j, "Id": j} for j in jornadas_nums]
        
        if not jornadas_nums:
            return {"jornada": {"Enfrentamientos": []}, "jornadas": []}

        return {
            "jornadas": lista_jornadas,
            "jornada": {
                "NumeroJornada": int(id_jornada) if id_jornada != "0" else jornadas_nums[0],
                "Enfrentamientos": partidos
            }
        }

    datos = cargar_datos()
    if not datos: raise HTTPException(status_code=500, detail="No hay datos")
    
    key = f"{id_deporte}_{id_competicion}_{id_categoria}_{id_grupo}"
    calendario_guardado = datos["calendario"].get(key)
    
    if not calendario_guardado:
        return {"jornada": {"Enfrentamientos": []}, "jornadas": []}
        
    if id_jornada == "0":
        return calendario_guardado
        
    jornadas = calendario_guardado.get("jornadas", [])
    for j in jornadas:
        if str(j.get("Id")) == id_jornada:
            enfrentamientos = []
            for partido in datos["resultados"].get(key, []):
                if str(partido.get("NumeroJornada")) == str(j.get("NumeroJornada")):
                    enfrentamientos.append(partido)
            
            jornada_custom = j.copy()
            jornada_custom["Enfrentamientos"] = enfrentamientos
            return {"jornada": jornada_custom, "jornadas": jornadas}
            
    return calendario_guardado

@app.get("/api/resultados/{id_deporte}/{id_competicion}/{id_categoria}/{id_grupo}")
def get_resultados(id_deporte: str, id_competicion: str, id_categoria: str, id_grupo: str):
    if id_deporte == "4":
        datos_canal = cargar_datos_canal()
        partidos = [p for p in datos_canal.get("partidos", []) if p.get("EquipoLocal") == id_grupo or p.get("EquipoVisitante") == id_grupo]
        partidos.sort(key=lambda x: x["FechaHora"])
        # Añadimos resultados 0-0 para que la app no falle
        for p in partidos:
            if "ResultadoEquipoLocal" not in p:
                p["ResultadoEquipoLocal"] = 0
                p["ResultadoEquipoVisitante"] = 0
        return partidos

    datos = cargar_datos()
    if not datos: return []
    key = f"{id_deporte}_{id_competicion}_{id_categoria}_{id_grupo}"
    return datos["resultados"].get(key, [])

@app.get("/api/clasificacion/{id_deporte}/{id_competicion}/{id_categoria}/{id_grupo}")
def get_clasificacion(id_deporte: str, id_competicion: str, id_categoria: str, id_grupo: str):
    if id_deporte == "4": return [] # Canal no tiene clasificación por ahora
    datos = cargar_datos()
    if not datos: return []
    key = f"{id_deporte}_{id_competicion}_{id_categoria}_{id_grupo}"
    return datos["clasificacion"].get(key, [])

@app.get("/api/ics")
def get_ics(titulo: str, fecha: str, lugar: str, deporte: str = "2"):
    try:
        fecha_dt = datetime.fromisoformat(fecha)
        
        if deporte == "4":
            # Canal: solo 1 hora y sin convocatoria previa
            hora_inicio_evento = fecha_dt
            hora_fin_evento = fecha_dt + timedelta(minutes=60)
            descripcion = "Partido de Liga Interna (Escuela Canal)."
        else:
            # ECM: Convocatoria 30 min antes y duración total 105 min
            hora_inicio_evento = fecha_dt - timedelta(minutes=30)
            hora_fin_evento = hora_inicio_evento + timedelta(minutes=105)
            
            lugar_upper = lugar.upper()
            tipo_campo = "Exterior"
            if "CUBIERTO" in lugar_upper or "CUBIERTA" in lugar_upper or "PABELLON" in lugar_upper:
                tipo_campo = "Pabellón / Cubierto"
                
            descripcion = f"Convocatoria 30 min antes.\\nEl partido comienza a las {fecha_dt.strftime('%H:%M')}h.\\nCampo: {tipo_campo}."

        dtstart = hora_inicio_evento.strftime("%Y%m%dT%H%M%S")
        dtend = hora_fin_evento.strftime("%Y%m%dT%H%M%S")
        
    except Exception as e:
        return Response(status_code=400, content="Fecha inválida")

    lugar_limpio = lugar.replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")
    titulo_limpio = titulo.replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")

    ics_content = f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//LigaFutbol//ES\r\nBEGIN:VEVENT\r\nSUMMARY:{titulo_limpio}\r\nDTSTART:{dtstart}\r\nDTEND:{dtend}\r\nLOCATION:{lugar_limpio}\r\nDESCRIPTION:{descripcion}\r\nEND:VEVENT\r\nEND:VCALENDAR"

    return Response(
        content=ics_content, 
        media_type="text/calendar", 
        headers={"Content-Disposition": "attachment; filename=partido.ics"}
    )
