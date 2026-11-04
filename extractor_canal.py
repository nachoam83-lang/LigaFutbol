import requests
import json
import urllib3
import io
import re
import pdfplumber
from bs4 import BeautifulSoup
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def extraer_canal():
    print("\n🚀 Iniciando extracción de Escuela Canal...")
    url_base = "https://www.ocioydeportecanal.es"
    url_evento = f"{url_base}/es/event/view/240702-competicion-escuela-2627"
    url_api = f"{url_base}/es/matches/loadPublicEventMatchesView/240702"
    url_pdf = "https://32760c338621fc279e50-75ecfd1a96ffdf4c500d931ef477c188.ssl.cf3.rackcdn.com/56/6e/4e/43/f4/63/74/f2/f2/a7/f9/c4/6a/3d/56/24/6ae9bd2dec243.pdf"
    
    categorias = {"PB": "Prebenjamín", "B": "Benjamín", "A": "Alevín", "I": "Infantil", "CJ": "Cadete/Juvenil", "C": "Cadete", "J": "Juvenil"}

    def traducir_equipo(codigo):
        if not codigo: return ""
        codigo = str(codigo).replace('\n', ' ').strip()
        match = re.match(r"^([A-Z]{1,2})(\d+)$", codigo)
        if match: return f"{categorias.get(match.group(1), match.group(1))} {match.group(2)}"
        return codigo

    def es_equipo_valido(nombre):
        return any(nombre.startswith(cat) for cat in categorias.values())

    def parsear_fecha_pdf(fecha_str):
        meses = {"ENERO":"01", "FEBRERO":"02", "MARZO":"03", "ABRIL":"04", "MAYO":"05", "JUNIO":"06", "JULIO":"07", "AGOSTO":"08", "SEPTIEMBRE":"09", "OCTUBRE":"10", "NOVIEMBRE":"11", "DICIEMBRE":"12"}
        match = re.search(r"(\d+)\s+DE\s+([A-Z]+)", fecha_str.upper())
        if match:
            dia = match.group(1).zfill(2)
            mes = meses.get(match.group(2), "01")
            anio = "2027" if int(mes) <= 7 else "2026"
            return f"{anio}-{mes}-{dia}"
        return "2026-01-01"

    def obtener_resultado_detalle(url_detalle, session):
        try:
            res = session.get(url_detalle, verify=False, timeout=10)
            if res.status_code == 200:
                soup_detalle = BeautifulSoup(res.text, 'html.parser')
                
                score_div = soup_detalle.select_one('.match-score, .score, .result, .match-result')
                if score_div:
                    match_res = re.findall(r'(?<!\d)(\d{1,2})\s*-\s*(\d{1,2})(?!\d)', score_div.text.strip())
                    if match_res:
                        return int(match_res[0][0]), int(match_res[0][1])
                
                matches = re.findall(r'(?<!\d)(\d{1,2})\s*-\s*(\d{1,2})(?!\d)', soup_detalle.text)
                if matches:
                    return int(matches[0][0]), int(matches[0][1])
        except Exception:
            pass
        
        # PARCHE DE SEGURIDAD: Si es missing-team y no encontramos marcador, forzamos 0-3
        print("       -> No se encontró marcador. Asignando 0-3 por defecto.")
        return 0, 3

    partidos_antiguos = {}
    if os.path.exists("datos_canal.json"):
        try:
            with open("datos_canal.json", "r", encoding="utf-8") as f:
                old_data = json.load(f)
                for p in old_data.get("partidos", []):
                    key_old = "_".join(sorted([p.get("EquipoLocal", ""), p.get("EquipoVisitante", "")]))
                    partidos_antiguos[key_old] = p
        except Exception:
            pass

    diccionario_partidos = {}
    equipos_por_categoria = {}

    # --- 1. WEB ---
    print("  🌐 Extrayendo de la Web...")
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"})
    res_get = session.get(url_evento, verify=False)
    csrf = session.cookies.get('oydci_productioncsrf_cookie_oydci_production') or '1869d5817061e74fb3b93b50329802d5'

    for page in range(1, 25):
        payload = {'csrf_token_oydci_production': csrf, 'date': '', 'idStatus': '-1', 'idCompetition': '0', 'group': '-1', 'day': '-1', 'venuePitch': '0', 'page': str(page)}
        res = session.post(url_api, data=payload, verify=False)
        try:
            soup = BeautifulSoup(res.json().get("page", ""), 'html.parser')
            partidos_html = soup.select('div.match-round')
            if not partidos_html: break

            for p in partidos_html:
                loc_tag = p.select_one('.match-round-team.local .match-round-team-name')
                vis_tag = p.select_one('.match-round-team.away .match-round-team-name')
                if not loc_tag or not vis_tag: continue
                
                loc, vis = traducir_equipo(loc_tag.text), traducir_equipo(vis_tag.text)
                if not es_equipo_valido(loc) or not es_equipo_valido(vis): continue

                jornada_tag = p.select_one('.match-round-matchday')
                num_jornada = 1
                if jornada_tag:
                    match_j = re.search(r'(\d+)', jornada_tag.text)
                    if match_j: num_jornada = int(match_j.group(1))

                fecha_tag = p.find_parent('div', class_='matches-round')
                fecha = fecha_tag.get('data-day', '') if fecha_tag else ""
                if fecha.startswith("2025") or fecha.startswith("2024") or not fecha: continue

                if 'missing-team' in p.get('class', []):
                    enlace_tag = p.select_one('a.link-encapsulated')
                    if enlace_tag and enlace_tag.get('href'):
                        url_detalle = enlace_tag.get('href')
                        rl, rv = obtener_resultado_detalle(url_detalle, session)
                        print(f"    🏳️ Partido no presentado: {loc} vs {vis}. Resultado asignado: {rl}-{rv}")
                    else:
                        rl, rv = 0, 3 # Si no hay enlace, asumimos 0-3
                else:
                    scoreboard = p.select('.match-round-scoreboard span')
                    rl, rv = 0, 0
                    if len(scoreboard) >= 3:
                        try: rl, rv = int(scoreboard[0].text.strip()), int(scoreboard[2].text.strip())
                        except: pass
                
                key = "_".join(sorted([loc, vis]))
                diccionario_partidos[key] = {
                    "NumeroJornada": num_jornada,
                    "FechaHora": f"{fecha}T12:00:00", "Campo": "Campo",
                    "EquipoLocal": loc, "EquipoVisitante": vis,
                    "URLEscudoEquipoLocal": "/static/escudo_canal.png", "URLEscudoEquipoVisitante": "/static/escudo_canal.png",
                    "ResultadoEquipoLocal": rl, "ResultadoEquipoVisitante": rv,
                    "Cambio": False
                }
                
                cat_loc = loc.split(' ')[0]
                if cat_loc not in equipos_por_categoria: equipos_por_categoria[cat_loc] = set()
                equipos_por_categoria[cat_loc].add(loc)
                equipos_por_categoria[cat_loc].add(vis)
        except Exception:
            break

    # --- 2. PDF (Extrae Horas y Campos Futuros) ---
    print("  📄 Procesando PDF...")
    try:
        response_pdf = requests.get(url_pdf, verify=False, timeout=15)
        with pdfplumber.open(io.BytesIO(response_pdf.content)) as pdf:
            for page in pdf.pages[1:]:
                tables = page.extract_tables() or page.extract_tables({"vertical_strategy": "text", "horizontal_strategy": "text"})
                for tabla in tables:
                    if len(tabla) < 5 or not any("LIGA INTERNA" in str(c) for fila in tabla[:4] for c in fila if c): continue
                    
                    fecha_cruda = next((str(c).replace('\n', ' ') for c in tabla[0] if c), "")
                    fecha_iso = parsear_fecha_pdf(fecha_cruda)
                    if fecha_iso == "2026-01-01": continue

                    for fila in tabla:
                        if not fila[0] or "-" not in str(fila[0]): continue
                        hora = str(fila[0]).split('-')[0].strip()
                        equipos_en_fila = [str(c).strip() for c in fila if c and re.match(r"^[A-Z]{1,2}\d+$", str(c).strip())]
                        
                        for i in range(0, len(equipos_en_fila), 2):
                            if i + 1 < len(equipos_en_fila):
                                loc = traducir_equipo(equipos_en_fila[i])
                                vis = traducir_equipo(equipos_en_fila[i+1])
                                if not es_equipo_valido(loc) or not es_equipo_valido(vis): continue
                                
                                campo_num = (i // 2) + 1
                                key = "_".join(sorted([loc, vis]))
                                if key in diccionario_partidos:
                                    diccionario_partidos[key]["FechaHora"] = f"{fecha_iso}T{hora}:00"
                                    diccionario_partidos[key]["Campo"] = f"Campo {campo_num}"
    except Exception as e:
        print(f"    ❌ Error PDF: {e}")

    # --- 3. COMPARACIÓN DE CAMBIOS ---
    print("  🔍 Comparando cambios...")
    for key, p in diccionario_partidos.items():
        if key in partidos_antiguos:
            old_p = partidos_antiguos[key]
            if old_p.get("FechaHora") != p["FechaHora"] or old_p.get("Campo") != p["Campo"]:
                p["Cambio"] = True

    # --- 4. CÁLCULO DE CLASIFICACIONES ---
    print("  📊 Calculando Clasificaciones...")
    clasificaciones = {}
    for cat, eqs in equipos_por_categoria.items():
        tabla = {eq: {"NombreEquipo": eq, "URLEscudo": "/static/escudo_canal.png", "PJ": 0, "PG": 0, "PE": 0, "PP": 0, "GF": 0, "GC": 0, "Puntos": 0} for eq in eqs}
        
        for p in diccionario_partidos.values():
            loc = p["EquipoLocal"]
            vis = p["EquipoVisitante"]
            if loc in tabla and vis in tabla and (p["ResultadoEquipoLocal"] > 0 or p["ResultadoEquipoVisitante"] > 0):
                rl, rv = p["ResultadoEquipoLocal"], p["ResultadoEquipoVisitante"]
                tabla[loc]["PJ"] += 1; tabla[vis]["PJ"] += 1
                tabla[loc]["GF"] += rl; tabla[loc]["GC"] += rv
                tabla[vis]["GF"] += rv; tabla[vis]["GC"] += rl
                
                if rl > rv:
                    tabla[loc]["Puntos"] += 3; tabla[loc]["PG"] += 1; tabla[vis]["PP"] += 1
                elif rv > rl:
                    tabla[vis]["Puntos"] += 3; tabla[vis]["PG"] += 1; tabla[loc]["PP"] += 1
                else:
                    tabla[loc]["Puntos"] += 1; tabla[vis]["Puntos"] += 1
                    tabla[loc]["PE"] += 1; tabla[vis]["PE"] += 1
                    
        lista_tabla = list(tabla.values())
        lista_tabla.sort(key=lambda x: (x["Puntos"], x["GF"] - x["GC"], x["GF"]), reverse=True)
        for i, eq in enumerate(lista_tabla): eq["Posicion"] = i + 1
        clasificaciones[cat] = lista_tabla

    # --- 5. GUARDAR ---
    partidos_finales = sorted(diccionario_partidos.values(), key=lambda x: (x["NumeroJornada"], x["FechaHora"]))
    equipos_finales = {k: sorted(list(v)) for k, v in equipos_por_categoria.items()}
    
    datos_canal = {
        "equipos": equipos_finales,
        "partidos": partidos_finales,
        "clasificacion": clasificaciones
    }
    
    with open("datos_canal.json", "w", encoding="utf-8") as f:
        json.dump(datos_canal, f, ensure_ascii=False, indent=2)
        
    print(f"✅ Escuela Canal finalizada: {len(partidos_finales)} partidos.")
