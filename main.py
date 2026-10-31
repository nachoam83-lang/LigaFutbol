from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import json
import time
import asyncio

app = FastAPI(title="API Liga Fútbol Sala")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"])

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest"
}

@app.get("/api/competiciones/{id_deporte}")
async def get_competiciones(id_deporte: int):
    t = int(time.time() * 1000)
    url = f"https://juegosdeportivos.ecmadrid.org/api/CompeticionesPorDeporte?action=ObtenerCompeticionesDeporteListado&IdDeporte={id_deporte}&IdTemporada=12&elementoTodas=true&soloActivas=true&_={t}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.get(url, headers=HEADERS)
            data = r.json()
            if isinstance(data, str): data = json.loads(data)
            items = data.get("data", data.get("Data", [])) if isinstance(data, dict) else data
            resultado = []
            for item in items:
                if not isinstance(item, dict): continue
                id_comp = item.get("Id")
                nombre = item.get("Nombre")
                if id_comp is None or id_comp <= 0 or not nombre: continue
                if not any(c["Id"] == int(id_comp) for c in resultado):
                    resultado.append({
                        "Id": int(id_comp),
                        "IdCategoria": int(item.get("IdCategoria", id_comp)),
                        "Nombre": str(nombre)
                    })
            resultado.sort(key=lambda x: x["Nombre"])
            return resultado
        except Exception as e:
            return {"error": str(e)}

@app.get("/api/grupos/{id_categoria}/{id_competicion}")
async def get_grupos(id_categoria: int, id_competicion: int):
    t = int(time.time() * 1000)
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            url_cat = f"https://juegosdeportivos.ecmadrid.org/api/CategoriasPorCompeticion?action=ObtenerCategoriasCompeticionListado&IdCompeticion={id_competicion}&_={t}"
            r_cat = await client.get(url_cat, headers=HEADERS)
            data_cat = r_cat.json()
            if isinstance(data_cat, str): data_cat = json.loads(data_cat)

            id_cat_real = id_categoria
            items_cat = data_cat.get("data", data_cat.get("Data", [])) if isinstance(data_cat, dict) else data_cat
            if items_cat and isinstance(items_cat, list) and len(items_cat) > 0:
                id_cat_real = items_cat[0].get("Id", id_categoria)

            url_grupos = f"https://juegosdeportivos.ecmadrid.org/api/GruposPorCategoria?action=ObtenerGruposCategoriaListado&IdCategoria={id_cat_real}&IdCompeticion={id_competicion}&elementoTodas=true&_={t}"
            r_grupos = await client.get(url_grupos, headers=HEADERS)
            data_grupos = r_grupos.json()
            if isinstance(data_grupos, str): data_grupos = json.loads(data_grupos)
            items_grupos = data_grupos.get("data", data_grupos.get("Data", [])) if isinstance(data_grupos, dict) else data_grupos
            
            resultado = []
            for item in items_grupos:
                if not isinstance(item, dict): continue
                id_g = item.get("Id")
                if id_g is None or id_g <= 0: continue
                nombre = item.get("Nombre")
                if nombre:
                    resultado.append({"Id": int(id_g), "Nombre": str(nombre)})
            return resultado
        except Exception as e:
            return {"error": str(e)}

@app.get("/api/calendario/{id_deporte}/{id_competicion}/{id_categoria}/{id_grupo}/{id_jornada}")
async def get_calendario(id_deporte: int, id_competicion: int, id_categoria: int, id_grupo: int, id_jornada: int):
    t = int(time.time() * 1000)
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            url_cat = f"https://juegosdeportivos.ecmadrid.org/api/CategoriasPorCompeticion?action=ObtenerCategoriasCompeticionListado&IdCompeticion={id_competicion}&_={t}"
            r_cat = await client.get(url_cat, headers=HEADERS)
            data_cat = r_cat.json()
            if isinstance(data_cat, str): data_cat = json.loads(data_cat)
            items_cat = data_cat.get("data", data_cat.get("Data", [])) if isinstance(data_cat, dict) else data_cat
            id_cat_real = id_categoria
            if items_cat and isinstance(items_cat, list) and len(items_cat) > 0:
                id_cat_real = items_cat[0].get("Id", id_categoria)

            url = f"https://juegosdeportivos.ecmadrid.org/Calendarios/ObtenerDatosJornadaGrupo?IdDeporte={id_deporte}&IdCompeticion={id_competicion}&IdCategoria={id_cat_real}&IdGrupo={id_grupo}&IdJornada={id_jornada}&IdEquipo=0"
            r = await client.get(url, headers=HEADERS)
            data = json.loads(r.text)
            if isinstance(data, str): data = json.loads(data)
            return data
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

# Función de ayuda para descargar una sola jornada de forma asíncrona
async def descargar_jornada(client, id_deporte, id_competicion, id_cat_real, id_grupo, id_jornada, num_jornada):
    url = f"https://juegosdeportivos.ecmadrid.org/Calendarios/ObtenerDatosJornadaGrupo?IdDeporte={id_deporte}&IdCompeticion={id_competicion}&IdCategoria={id_cat_real}&IdGrupo={id_grupo}&IdJornada={id_jornada}&IdEquipo=0"
    try:
        r = await client.get(url, headers=HEADERS)
        data = json.loads(r.text)
        if isinstance(data, str): data = json.loads(data)
        enf = data.get("jornada", {}).get("Enfrentamientos", [])
        for e in enf:
            e["NumeroJornada"] = num_jornada
        return enf
    except:
        return []

@app.get("/api/resultados/{id_deporte}/{id_competicion}/{id_categoria}/{id_grupo}")
async def get_resultados(id_deporte: int, id_competicion: int, id_categoria: int, id_grupo: int):
    t = int(time.time() * 1000)
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            url_cat = f"https://juegosdeportivos.ecmadrid.org/api/CategoriasPorCompeticion?action=ObtenerCategoriasCompeticionListado&IdCompeticion={id_competicion}&_={t}"
            r_cat = await client.get(url_cat, headers=HEADERS)
            data_cat = r_cat.json()
            items_cat = data_cat.get("data", data_cat.get("Data", [])) if isinstance(data_cat, dict) else data_cat
            id_cat_real = items_cat[0].get("Id", id_categoria) if items_cat else id_categoria

            url_cal = f"https://juegosdeportivos.ecmadrid.org/Calendarios/ObtenerDatosJornadaGrupo?IdDeporte={id_deporte}&IdCompeticion={id_competicion}&IdCategoria={id_cat_real}&IdGrupo={id_grupo}&IdJornada=0&IdEquipo=0"
            r_cal = await client.get(url_cal, headers=HEADERS)
            data_cal = json.loads(r_cal.text)
            if isinstance(data_cal, str): data_cal = json.loads(data_cal)
            
            jornadas = data_cal.get("jornadas", [])
            
            # Pedimos todas las jornadas a la vez
            tareas = []
            for j in jornadas:
                id_j = j.get("Id")
                num_j = j.get("NumeroJornada")
                tareas.append(descargar_jornada(client, id_deporte, id_competicion, id_cat_real, id_grupo, id_j, num_j))
            
            resultados_por_jornada = await asyncio.gather(*tareas)
            
            todos_los_partidos = []
            for lista_partidos in resultados_por_jornada:
                todos_los_partidos.extend(lista_partidos)
                
            return todos_los_partidos
        except Exception as e:
            print(f"Error resultados: {e}")
            return []

@app.get("/api/clasificacion/{id_deporte}/{id_competicion}/{id_categoria}/{id_grupo}")
async def get_clasificacion(id_deporte: int, id_competicion: int, id_categoria: int, id_grupo: int):
    partidos = await get_resultados(id_deporte, id_competicion, id_categoria, id_grupo)
    
    tabla = {}
    for p in partidos:
        local = p.get("EquipoLocal")
        visitante = p.get("EquipoVisitante")
        if not local or not visitante: continue
        
        if local not in tabla:
            tabla[local] = {"NombreEquipo": local, "URLEscudo": p.get("URLEscudoEquipoLocal"), "Puntos": 0, "Jugados": 0, "GF": 0, "GC": 0}
        if visitante not in tabla:
            tabla[visitante] = {"NombreEquipo": visitante, "URLEscudo": p.get("URLEscudoEquipoVisitante"), "Puntos": 0, "Jugados": 0, "GF": 0, "GC": 0}
            
        estado = p.get("EstadoPartido", "")
        rl = p.get("ResultadoEquipoLocal", 0)
        rv = p.get("ResultadoEquipoVisitante", 0)
        
        if "Jugado" in estado or "Finalizado" in estado or rl > 0 or rv > 0:
            tabla[local]["Jugados"] += 1
            tabla[visitante]["Jugados"] += 1
            tabla[local]["GF"] += rl
            tabla[local]["GC"] += rv
            tabla[visitante]["GF"] += rv
            tabla[visitante]["GC"] += rl
            
            if rl > rv:
                tabla[local]["Puntos"] += 3
            elif rl < rv:
                tabla[visitante]["Puntos"] += 3
            else:
                tabla[local]["Puntos"] += 1
                tabla[visitante]["Puntos"] += 1
                
    lista_tabla = list(tabla.values())
    lista_tabla.sort(key=lambda x: (x["Puntos"], x["GF"] - x["GC"], x["GF"]), reverse=True)
    
    for i, equipo in enumerate(lista_tabla):
        equipo["Posicion"] = i + 1
        
    return lista_tabla