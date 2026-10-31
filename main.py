from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import json
import os

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
