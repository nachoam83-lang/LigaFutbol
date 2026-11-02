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

@app.get("/api/competiciones/{id_deporte}")
def get_competiciones(id_deporte: int):
    datos = cargar_datos()
    if not datos: return []
    return datos["competiciones"].get(str(id_deporte), [])

@app.get("/api/grupos/{id_categoria}/{id_competicion}")
def get_grupos(id_categoria: int, id_competicion: int):
    datos = cargar_datos()
    if not datos: return []
    for id_dep, lista_comps in datos["competiciones"].items():
        for comp in lista_comps:
            if comp["Id"] == id_competicion:
                return comp.get("Grupos", [])
    return []

@app.get("/api/calendario/{id_deporte}/{id_competicion}/{id_categoria}/{id_grupo}/{id_jornada}")
def get_calendario(id_deporte: int, id_competicion: int, id_categoria: int, id_grupo: int, id_jornada: int):
    datos = cargar_datos()
    if not datos: raise HTTPException(status_code=500, detail="No hay datos")
    
    key = f"{id_deporte}_{id_competicion}_{id_categoria}_{id_grupo}"
    calendario_guardado = datos["calendario"].get(key)
    
    if not calendario_guardado:
        return {"jornada": {"Enfrentamientos": []}, "jornadas": []}
        
    if id_jornada == 0:
        return calendario_guardado
        
    jornadas = calendario_guardado.get("jornadas", [])
    for j in jornadas:
        if j.get("Id") == id_jornada:
            enfrentamientos = []
            for partido in datos["resultados"].get(key, []):
                if partido.get("NumeroJornada") == j.get("NumeroJornada"):
                    enfrentamientos.append(partido)
            
            jornada_custom = j.copy()
            jornada_custom["Enfrentamientos"] = enfrentamientos
            return {"jornada": jornada_custom, "jornadas": jornadas}
            
    return calendario_guardado

@app.get("/api/resultados/{id_deporte}/{id_competicion}/{id_categoria}/{id_grupo}")
def get_resultados(id_deporte: int, id_competicion: int, id_categoria: int, id_grupo: int):
    datos = cargar_datos()
    if not datos: return []
    key = f"{id_deporte}_{id_competicion}_{id_categoria}_{id_grupo}"
    return datos["resultados"].get(key, [])

@app.get("/api/clasificacion/{id_deporte}/{id_competicion}/{id_categoria}/{id_grupo}")
def get_clasificacion(id_deporte: int, id_competicion: int, id_categoria: int, id_grupo: int):
    datos = cargar_datos()
    if not datos: return []
    key = f"{id_deporte}_{id_competicion}_{id_categoria}_{id_grupo}"
    return datos["clasificacion"].get(key, [])

# --- NUEVA RUTA PARA GENERAR EL ARCHIVO DE CALENDARIO ---
@app.get("/api/ics")
def get_ics(titulo: str, fecha: str, lugar: str):
    try:
        # Convertimos la fecha que viene como texto a formato datetime
        fecha_dt = datetime.fromisoformat(fecha)
        fecha_fin = fecha_dt + timedelta(hours=1, minutes=30) # Añadimos 1h y 30m de duración
        
        dtstart = fecha_dt.strftime("%Y%m%dT%H%M%S")
        dtend = fecha_fin.strftime("%Y%m%dT%H%M%S")
    except Exception as e:
        print(f"Error con la fecha: {e}")
        return Response(status_code=400, content="Fecha inválida")

    # Generamos el archivo .ics con el formato estándar
    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//LigaFutbol//ES
BEGIN:VEVENT
SUMMARY:{titulo}
DTSTART:{dtstart}
DTEND:{dtend}
LOCATION:{lugar}
DESCRIPTION:Partido de liga
END:VEVENT
END:VCALENDAR"""

    # Lo devolvemos como archivo descargable
    return Response(
        content=ics_content, 
        media_type="text/calendar", 
        headers={"Content-Disposition": "attachment; filename=partido.ics"}
    )
