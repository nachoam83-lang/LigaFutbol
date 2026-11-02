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

@app.get("/api/ics")
def get_ics(titulo: str, fecha: str, lugar: str):
    try:
        fecha_dt = datetime.fromisoformat(fecha)
        
        # El evento empieza 30 mins antes (Convocatoria)
        hora_inicio_evento = fecha_dt - timedelta(minutes=30)
        # Dura 105 mins en total (30 + 75)
        hora_fin_evento = hora_inicio_evento + timedelta(minutes=105)
        
        dtstart = hora_inicio_evento.strftime("%Y%m%dT%H%M%S")
        dtend = hora_fin_evento.strftime("%Y%m%dT%H%M%S")
        hora_partido_str = fecha_dt.strftime("%H:%M")
    except Exception as e:
        return Response(status_code=400, content="Fecha inválida")

    # Detectar si es exterior o pabellón para las notas
    lugar_upper = lugar.upper()
    tipo_campo = "Exterior"
    if "CUBIERTO" in lugar_upper or "CUBIERTA" in lugar_upper or "PABELLON" in lugar_upper:
        tipo_campo = "Pabellón / Cubierto"
        
    lugar_limpio = lugar.replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")
    titulo_limpio = titulo.replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")
    
    # Notas: Aviso de convocatoria y el tipo de campo
    descripcion = f"Convocatoria 30 min antes.\\nEl partido comienza a las {hora_partido_str}h.\\nCampo: {tipo_campo}."

    ics_content = f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//LigaFutbol//ES\r\nBEGIN:VEVENT\r\nSUMMARY:{titulo_limpio}\r\nDTSTART:{dtstart}\r\nDTEND:{dtend}\r\nLOCATION:{lugar_limpio}\r\nDESCRIPTION:{descripcion}\r\nEND:VEVENT\r\nEND:VCALENDAR"

    return Response(
        content=ics_content, 
        media_type="text/calendar", 
        headers={"Content-Disposition": "attachment; filename=partido.ics"}
    )
