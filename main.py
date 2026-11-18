from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pydantic import BaseModel
import json
import os
import base64
import urllib.request
import urllib.error
import urllib.parse
import threading
import html
import hashlib
import re

app = FastAPI(title="API Liga Fútbol Sala")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")

# 1. Lista global en la memoria del servidor para guardar los pendientes de la PWA
SOLICITUDES_PENDIENTES = []

# ─── MODO ADMINISTRADOR: PENDIENTES TELEGRAM / PWA ───
@app.get("/api/admin/pendientes")
def verificar_pendientes():
    try:
        return {"total": len(SOLICITUDES_PENDIENTES), "avisos": SOLICITUDES_PENDIENTES}
    except Exception as e:
        return {"total": 0, "avisos": []}

# ─── 1. SOLICITAR BORRADO (Unificado: Alimenta la PWA y avisa a Telegram) ───
@app.post("/api/solicitar-borrado")
async def post_solicitar_borrado(request: Request):
    try:
        datos = await request.json()
        equipo_val = datos.get("equipo", "Desconocido")
        motivo_val = datos.get("motivo", "Sin motivo")

        # A. Guardar en la lista global para que aparezca en el banner de la PWA
        nuevo_aviso = {
            "id": len(SOLICITUDES_PENDIENTES) + 1,
            "detalles": {"equipo": equipo_val, "motivo": motivo_val},
            "fecha": str(datetime.now())
        }
        SOLICITUDES_PENDIENTES.append(nuevo_aviso)

        # B. Enviar notificación al chat de Telegram del administrador
        tg_token = os.getenv("TELEGRAM_TOKEN")
        tg_chat = os.getenv("TELEGRAM_CHAT_ID")
        
        if tg_token and tg_chat:
            equipo_seguro = html.escape(equipo_val)
            motivo_seguro = html.escape(motivo_val)
            texto = f"⚠️ <b>SOLICITUD DE BORRADO</b>\n\n<b>Equipo:</b> {equipo_seguro}\n<b>Motivo:</b> {motivo_seguro}"
            
            equipo_hash = hashlib.md5(equipo_val.encode('utf-8')).hexdigest()[:16]
            
            keyboard = {
                "inline_keyboard": [[
                    {"text": "✅ Aprobar borrado", "callback_data": f"del|{equipo_hash}"},
                    {"text": "❌ Ignorar", "callback_data": "ignore"}
                ]]
            }
            
            url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
            data = json.dumps({
                "chat_id": tg_chat,
                "text": texto,
                "parse_mode": "HTML",
                "reply_markup": keyboard
            }).encode('utf-8')
            
            req_tg = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            try:
                urllib.request.urlopen(req_tg)
            except Exception as e:
                print(f"Aviso: No se pudo enviar a Telegram, pero se guardó en la PWA: {e}")

        return {"status": "ok", "mensaje": "Solicitud guardada en pendientes y enviada a Telegram"}
    except Exception as e:
        print(f"Error en solicitar-borrado: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─── 2. RESOLVER O BORRAR UN AVISO PENDIENTE DESDE LA PWA ───
@app.post("/api/admin/resolver/{aviso_id}")
async def resolver_aviso(aviso_id: str, request: Request):
    global SOLICITUDES_PENDIENTES
    try:
        body = await request.json()
        accion = body.get("accion", "rechazar")
    except:
        accion = "rechazar"

    aviso_encontrado = None
    for aviso in SOLICITUDES_PENDIENTES:
        if str(aviso.get("id")) == str(aviso_id):
            aviso_encontrado = aviso
            break

    # Si se aprueba desde la PWA, borramos el grupo de GitHub (grupos.json) igual que en Telegram
    if aviso_encontrado and accion == "aprobar":
        detalles = aviso_encontrado.get("detalles", {})
        nombre_equipo = detalles.get("equipo")
        if nombre_equipo:
            with github_lock:
                grupos, sha = leer_grupos()
                if nombre_equipo in grupos:
                    del grupos[nombre_equipo]
                    guardar_grupos(grupos, sha)

    # Eliminar el aviso de la lista global usando conversión segura a string
    SOLICITUDES_PENDIENTES = [
        aviso for aviso in SOLICITUDES_PENDIENTES 
        if str(aviso.get("id")) != str(aviso_id)
    ]
    
    return {"status": "success", "total_restantes": len(SOLICITUDES_PENDIENTES)}

# ─── 3. LIMPIAR TODOS LOS PENDIENTES ───
@app.post("/api/admin/limpiar")
def limpiar_pendientes():
    global SOLICITUDES_PENDIENTES
    SOLICITUDES_PENDIENTES = []
    return {"status": "success"}

# ─── CONFIGURACIÓN GITHUB ───
GITHUB_REPO = "nachoam83-lang/LigaFutbol"
GITHUB_FILE = "static/grupos.json"
GITHUB_BRANCH = "main"
github_lock = threading.Lock()

_RE_ENLACE_WHATSAPP = re.compile(r"^https://chat\.whatsapp\.com/([A-Za-z0-9_-]{15,40})(?:\?\S*)?$")

def normalizar_enlace_whatsapp(url):
    """Devuelve el enlace canónico https://chat.whatsapp.com/CODIGO o None si no es un enlace de invitación válido.
    Antes bastaba con que el texto contuviera 'chat.whatsapp.com', así que se colaban enlaces a otras webs."""
    m = _RE_ENLACE_WHATSAPP.match((url or "").strip())
    return f"https://chat.whatsapp.com/{m.group(1)}" if m else None

class SolicitudGrupo(BaseModel):
    equipo: str
    url: str

class SolicitudBorrado(BaseModel):
    equipo: str
    motivo: str

def _github_api(method, path, data=None):
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise HTTPException(status_code=500, detail="Falta GITHUB_TOKEN en Render")
    
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "LigaFutbol-App"
    }
    
    req = urllib.request.Request(url, method=method, headers=headers)
    if data:
        req.add_header('Content-Type', 'application/json')
        req.data = json.dumps(data).encode('utf-8')
        
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 404: return None
        if e.code == 409: raise HTTPException(status_code=409, detail="Conflicto de versión en GitHub")
        raise HTTPException(status_code=e.code, detail=f"Error de GitHub: {e.reason}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error de red: {str(e)}")

def leer_grupos():
    try:
        res = _github_api("GET", GITHUB_FILE)
        if res and "content" in res:
            contenido = base64.b64decode(res["content"]).decode('utf-8')
            return json.loads(contenido), res["sha"]
    except Exception as e:
        print(f"⚠️ Fallo al leer de GitHub, usando local: {e}")
    
    if os.path.exists(GITHUB_FILE):
        try:
            with open(GITHUB_FILE, "r", encoding="utf-8") as f:
                return json.load(f), None
        except: pass
        
    return {}, None

def guardar_grupos(grupos, sha_actual):
    contenido_str = json.dumps(grupos, ensure_ascii=False, indent=2)
    os.makedirs(os.path.dirname(GITHUB_FILE), exist_ok=True)
    with open(GITHUB_FILE, "w", encoding="utf-8") as f:
        f.write(contenido_str)

    try:
        contenido_b64 = base64.b64encode(contenido_str.encode('utf-8')).decode('utf-8')
        data = {
            "message": "Actualizar grupo de WhatsApp vía App",
            "content": contenido_b64,
            "branch": GITHUB_BRANCH
        }
        if sha_actual:
            data["sha"] = sha_actual
            
        _github_api("PUT", GITHUB_FILE, data)
        return True
    except Exception as e:
        print(f"❌ Error guardando en GitHub: {e}")
        return False

# ─── FUNCIONES AUXILIARES TELEGRAM ───
def _tg_answer(token, cb_id, text):
    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    data = json.dumps({"callback_query_id": cb_id, "text": text}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try: urllib.request.urlopen(req)
    except: pass

def _tg_edit(token, chat_id, msg_id, text):
    url = f"https://api.telegram.org/bot{token}/editMessageText"
    data = json.dumps({"chat_id": chat_id, "message_id": msg_id, "text": text, "parse_mode": "HTML"}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try: urllib.request.urlopen(req)
    except: pass

# ─── ENDPOINTS GRUPOS Y TELEGRAM ───
@app.get("/api/grupos_whatsapp")
def get_grupos_whatsapp():
    grupos, _ = leer_grupos()
    return grupos

@app.post("/api/solicitar-grupo")
def post_solicitar_grupo(req: SolicitudGrupo):
    url_limpia = normalizar_enlace_whatsapp(req.url)
    if not url_limpia:
        raise HTTPException(status_code=400, detail="Enlace de WhatsApp no válido")
    if not req.equipo.strip() or len(req.equipo) > 200:
        raise HTTPException(status_code=400, detail="Equipo no válido")

    with github_lock:
        grupos, sha = leer_grupos()
        if req.equipo in grupos:
            raise HTTPException(status_code=409, detail="Este equipo ya tiene un grupo asignado")
        grupos[req.equipo] = url_limpia
        exito = guardar_grupos(grupos, sha)
        if not exito:
            return {"status": "warning", "mensaje": "Guardado localmente, pero falló en GitHub"}
        return {"status": "ok", "mensaje": "Grupo guardado correctamente"}

@app.post("/api/telegram-webhook")
async def telegram_webhook(request: Request):
    tg_token = os.getenv("TELEGRAM_TOKEN")
    try:
        data = await request.json()
        if "callback_query" in data:
            cb = data["callback_query"]
            cb_id = cb["id"]
            cb_data = cb["data"]
            msg_id = cb["message"]["message_id"]
            chat_id = cb["message"]["chat"]["id"]

            if cb_data.startswith("del|"):
                equipo_hash = cb_data.split("|", 1)[1]
                equipo_encontrado = None
                
                with github_lock:
                    grupos, sha = leer_grupos()
                    for k in list(grupos.keys()):
                        if hashlib.md5(k.encode('utf-8')).hexdigest()[:16] == equipo_hash:
                            equipo_encontrado = k
                            del grupos[k]
                            guardar_grupos(grupos, sha)
                            break
                
                if equipo_encontrado:
                    _tg_answer(tg_token, cb_id, "✅ Grupo eliminado")
                    _tg_edit(tg_token, chat_id, msg_id, f"✅ <b>BORRADO APROBADO</b>\nEquipo: {html.escape(equipo_encontrado)}")
                else:
                    _tg_answer(tg_token, cb_id, "⚠️ El grupo ya no existía")
                    _tg_edit(tg_token, chat_id, msg_id, "⚠️ <b>El grupo ya había sido eliminado</b>")
                
            elif cb_data == "ignore":
                _tg_answer(tg_token, cb_id, "❌ Operación cancelada")
                _tg_edit(tg_token, chat_id, msg_id, "❌ <b>Borrado ignorado</b>")
                
        return {"ok": True}
    except Exception as e:
        print(f"Error en webhook: {e}")
        return {"ok": False}

@app.get("/api/setup-webhook")
def setup_webhook(request: Request):
    tg_token = os.getenv("TELEGRAM_TOKEN")
    if not tg_token: return {"error": "Falta TELEGRAM_TOKEN"}
    
    host = request.headers.get("host")
    webhook_url = f"https://{host}/api/telegram-webhook"
    
    url = f"https://api.telegram.org/bot{tg_token}/setWebhook?url={webhook_url}"
    try:
        res = urllib.request.urlopen(url)
        return {"status": "ok", "webhook_url": webhook_url, "respuesta": json.loads(res.read().decode('utf-8'))}
    except Exception as e:
        return {"error": str(e)}

# ─── LÓGICA DE DATOS ORIGINAL ───
@app.get("/ping")
def ping():
    return Response(content="OK", media_type="text/plain")

@app.get("/")
def read_index():
    return FileResponse("static/index.html")

@lru_cache(maxsize=1)
def _leer_json_liga():
    if not os.path.exists("datos_liga.json"): return None
    with open("datos_liga.json", "r", encoding="utf-8") as f:
        return json.load(f)

@lru_cache(maxsize=1)
def _leer_json_canal():
    if not os.path.exists("datos_canal.json"): return {"equipos": {}, "partidos": [], "clasificacion": {}}
    with open("datos_canal.json", "r", encoding="utf-8") as f:
        return json.load(f)

def cargar_datos():
    datos = _leer_json_liga()
    if not datos or not datos.get("competiciones"):
        print("⚠️ Usando backup para datos_liga.json")
        if os.path.exists("datos_liga_backup.json"):
            with open("datos_liga_backup.json", "r", encoding="utf-8") as f:
                return json.load(f)
    return datos

def cargar_datos_canal():
    datos = _leer_json_canal()
    if not datos or len(datos.get("partidos", [])) == 0:
        print("⚠️ Usando backup para datos_canal.json")
        if os.path.exists("datos_canal_backup.json"):
            with open("datos_canal_backup.json", "r", encoding="utf-8") as f:
                return json.load(f)
    return datos

def corregir_anio(fecha_str):
    if not fecha_str or len(fecha_str) < 7: return fecha_str
    try:
        mes = int(fecha_str[5:7])
        if mes <= 7: return "2027" + fecha_str[4:]
        else: return "2026" + fecha_str[4:]
    except: return fecha_str

def calcular_jornadas_canal(partidos, categoria):
    mapa_fechas = {
        "2026-09-26": 1, "2026-10-03": 1,
        "2026-10-10": 2, "2026-10-17": 2,
        "2026-10-21": 3, "2026-10-22": 3, "2026-10-23": 3,
        "2026-10-24": 4, "2026-10-31": 4,
        "2026-11-07": 5, "2026-11-14": 5,
        "2026-11-21": 6, "2026-11-28": 6,
        "2026-12-12": 7, "2026-12-19": 7,
        "2027-01-09": 8, "2027-01-16": 8,
        "2027-01-23": 9, "2027-01-30": 9,
        "2027-02-06": 10, "2027-02-13": 10,
        "2027-02-20": 11
    }

    for p in partidos:
        p["FechaHora"] = corregir_anio(p.get("FechaHora", ""))
        p["Fecha"] = p["FechaHora"].split("T")[0]
        p["JornadaBase"] = mapa_fechas.get(p["Fecha"], 99)
        p["Descolgado"] = False
        p["NumeroJornada"] = p["JornadaBase"]
        # El extractor de Canal marca Cambio=True en todo partido que aparece en el PDF
        # de horarios, no solo en los que cambian. Se ignora: la app detecta los cambios
        # reales comparando fecha y campo con lo que vio la última vez (snapshot).
        p["Cambio"] = False

    partidos.sort(key=lambda x: (x["JornadaBase"], x["FechaHora"]))
    equipos = set()
    for p in partidos:
        equipos.add(p["EquipoLocal"])
        equipos.add(p["EquipoVisitante"])

    jornadas_finales = {j: [] for j in range(1, 12)}
    descolgados = []

    for j in range(1, 12):
        partidos_j = [p for p in partidos if p["JornadaBase"] == j]
        partidos_j.sort(key=lambda x: x["FechaHora"])
        equipos_jugando = set()
        
        for p in partidos_j:
            loc = p["EquipoLocal"]
            vis = p["EquipoVisitante"]
            if loc not in equipos_jugando and vis not in equipos_jugando:
                equipos_jugando.add(loc)
                equipos_jugando.add(vis)
                p["NumeroJornada"] = j
                jornadas_finales[j].append(p)
            else:
                p["Descolgado"] = True
                p["NumeroJornada"] = j
                descolgados.append(p)
                jornadas_finales[j].append(p)

    if descolgados:
        jornadas_finales[12] = []
        for p in descolgados:
            p_copia = p.copy()
            p_copia["NumeroJornada"] = 12
            jornadas_finales[12].append(p_copia)

    partidos_finales = []
    for j in sorted(jornadas_finales.keys()):
        partidos_finales.extend(jornadas_finales[j])
    return partidos_finales, jornadas_finales

@app.get("/api/competiciones/{id_deporte}")
def get_competiciones(id_deporte: str):
    if id_deporte == "4": return []
    datos = cargar_datos()
    if not datos: return []
    return datos["competiciones"].get(str(id_deporte), [])

@app.get("/api/grupos/{id_categoria}/{id_competicion}")
def get_grupos(id_categoria: str, id_competicion: str):
    if id_categoria == "99": return []
    datos = cargar_datos()
    if not datos: return []
    for id_dep, lista_comps in datos["competiciones"].items():
        for comp in lista_comps:
            if str(comp["Id"]) == id_competicion:
                return comp.get("Grupos", [])
    return []

@app.get("/api/equipos_canal")
def get_equipos_canal():
    datos_canal = cargar_datos_canal()
    return datos_canal.get("equipos", {})

@app.get("/api/calendario/{id_deporte}/{id_competicion}/{id_categoria}/{id_grupo}/{id_jornada}")
def get_calendario(id_deporte: str, id_competicion: str, id_categoria: str, id_grupo: str, id_jornada: str):
    if id_deporte == "4":
        datos_canal = cargar_datos_canal()
        partidos = [p for p in datos_canal.get("partidos", []) if p.get("EquipoLocal", "").startswith(id_categoria) or p.get("EquipoVisitante", "").startswith(id_categoria)]
        partidos_finales, jornadas_dict = calcular_jornadas_canal(partidos, id_categoria)
        jornadas_nums = sorted(list(jornadas_dict.keys()))
        lista_jornadas = [{"NumeroJornada": j, "Id": j} for j in jornadas_nums]
        return {
            "jornadas": lista_jornadas,
            "jornada": {
                "NumeroJornada": int(id_jornada) if id_jornada != "0" and jornadas_nums else (jornadas_nums[0] if jornadas_nums else 0),
                "Enfrentamientos": partidos_finales
            }
        }

    datos = cargar_datos()
    if not datos: raise HTTPException(status_code=500, detail="No hay datos")
    key = f"{id_deporte}_{id_competicion}_{id_categoria}_{id_grupo}"
    calendario_guardado = datos["calendario"].get(key)
    if not calendario_guardado: return {"jornada": {"Enfrentamientos": []}, "jornadas": []}
    if id_jornada == "0": return calendario_guardado
    jornadas = calendario_guardado.get("jornadas", [])
    for j in jornadas:
        if str(j.get("Id")) == id_jornada:
            enfrentamientos = [p for p in datos["resultados"].get(key, []) if str(p.get("NumeroJornada")) == str(j.get("NumeroJornada"))]
            j_custom = j.copy()
            j_custom["Enfrentamientos"] = enfrentamientos
            return {"jornada": j_custom, "jornadas": jornadas}
    return calendario_guardado

@app.get("/api/resultados/{id_deporte}/{id_competicion}/{id_categoria}/{id_grupo}")
def get_resultados(id_deporte: str, id_competicion: str, id_categoria: str, id_grupo: str):
    if id_deporte == "4":
        datos_canal = cargar_datos_canal()
        partidos = [p for p in datos_canal.get("partidos", []) if p.get("EquipoLocal", "").startswith(id_categoria) or p.get("EquipoVisitante", "").startswith(id_categoria)]
        partidos_finales, _ = calcular_jornadas_canal(partidos, id_categoria)
        partidos_finales.sort(key=lambda x: (x["NumeroJornada"], x["FechaHora"]))
        return partidos_finales

    datos = cargar_datos()
    if not datos: return []
    key = f"{id_deporte}_{id_competicion}_{id_categoria}_{id_grupo}"
    return datos["resultados"].get(key, [])

@app.get("/api/clasificacion/{id_deporte}/{id_competicion}/{id_categoria}/{id_grupo}")
def get_clasificacion(id_deporte: str, id_competicion: str, id_categoria: str, id_grupo: str):
    if id_deporte == "4":
        datos_canal = cargar_datos_canal()
        return datos_canal.get("clasificacion", {}).get(id_categoria, [])
    datos = cargar_datos()
    if not datos: return []
    key = f"{id_deporte}_{id_competicion}_{id_categoria}_{id_grupo}"
    return datos["clasificacion"].get(key, [])

def _ics_escape(texto):
    """Escapa texto para iCalendar (RFC 5545). También evita que un valor con saltos de línea inyecte campos."""
    return (str(texto).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", ""))

def _ics_fold(linea):
    """Líneas de máximo 75 octetos; las continuaciones empiezan con un espacio."""
    partes = []
    while len(linea.encode("utf-8")) > 75:
        corte = 75
        while len(linea[:corte].encode("utf-8")) > 75:
            corte -= 1
        partes.append(linea[:corte])
        linea = " " + linea[corte:]
    partes.append(linea)
    return "\r\n".join(partes)

@app.get("/api/ics")
def get_ics(titulo: str, fecha: str, lugar: str, deporte: str = "2"):
    try:
        fecha_dt = datetime.fromisoformat(fecha)
        if deporte == "4":
            hora_inicio_evento = fecha_dt
            hora_fin_evento = fecha_dt + timedelta(minutes=60)
            descripcion = "Partido de Liga Interna (Escuela Canal)."
        else:
            hora_inicio_evento = fecha_dt - timedelta(minutes=30)
            hora_fin_evento = hora_inicio_evento + timedelta(minutes=105)
            tipo_campo = "Exterior" if ("EXTERIOR" in lugar.upper() or "AIRE LIBRE" in lugar.upper()) else "Pabellón"
            descripcion = f"Convocatoria 30 min antes.\nEl partido comienza a las {fecha_dt.strftime('%H:%M')}h.\nCampo: {tipo_campo}."
        dtstart = hora_inicio_evento.strftime("%Y%m%dT%H%M%S")
        dtend = hora_fin_evento.strftime("%Y%m%dT%H%M%S")
    except Exception:
        return Response(status_code=400, content="Fecha inválida")
    # UID estable: si se vuelve a descargar el mismo partido, el calendario lo actualiza en vez de duplicarlo
    uid = hashlib.md5(f"{titulo}|{fecha}|{lugar}|{deporte}".encode("utf-8")).hexdigest() + "@ligafutbol"
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lineas = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//LigaFutbol//ES", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        f"SUMMARY:{_ics_escape(titulo)}",
        f"DTSTART:{dtstart}",
        f"DTEND:{dtend}",
        f"LOCATION:{_ics_escape(lugar)}",
        f"DESCRIPTION:{_ics_escape(descripcion)}",
        "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Partido mañana", "TRIGGER:-P1D", "END:VALARM",
        "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Partido en 1 hora", "TRIGGER:-PT1H", "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    ics_content = "\r\n".join(_ics_fold(l) for l in lineas) + "\r\n"
    return Response(content=ics_content, media_type="text/calendar", headers={"Content-Disposition": "attachment; filename=partido.ics"})
