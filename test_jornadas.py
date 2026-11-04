import json
from datetime import datetime, timedelta

def corregir_anio(fecha_str):
    if not fecha_str or len(fecha_str) < 7: return fecha_str
    try:
        mes = int(fecha_str[5:7])
        if mes <= 7: return "2027" + fecha_str[4:]
        else: return "2026" + fecha_str[4:]
    except: return fecha_str

# --- CARGAR DATOS ---
try:
    with open("datos_canal.json", "r", encoding="utf-8") as f:
        datos = json.load(f)
except Exception as e:
    print(f"Error abriendo datos_canal.json: {e}")
    exit()

categoria = "Benjamín"
partidos = [p for p in datos.get("partidos", []) if p.get("EquipoLocal", "").startswith(categoria) or p.get("EquipoVisitante", "").startswith(categoria)]

# Corregir año y ordenar estrictamente por fecha
for p in partidos:
    p["FechaHora"] = corregir_anio(p.get("FechaHora", ""))
partidos.sort(key=lambda x: x["FechaHora"])

# Obtener todos los equipos
equipos = set()
for p in partidos:
    equipos.add(p["EquipoLocal"])
    equipos.add(p["EquipoVisitante"])

print(f"Analizando {len(partidos)} partidos de la categoría {categoria}...")
print(f"Equipos: {len(equipos)}\n")

# Agrupamos por semanas (lunes a domingo) para no mezclar meses
semanas = {}
for p in partidos:
    fecha_dt = datetime.strptime(p["FechaHora"].split("T")[0], "%Y-%m-%d")
    lunes = fecha_dt - timedelta(days=fecha_dt.weekday())
    clave_semana = lunes.strftime("%Y-%m-%d")
    if clave_semana not in semanas:
        semanas[clave_semana] = []
    semanas[clave_semana].append(p)

# Ahora procesamos cada semana. Si una semana tiene más de 5 partidos, creamos sub-jornadas.
# Si tiene menos, intentamos juntarla con la siguiente.
jornadas_finales = []
semana_actual = []
equipos_semana_actual = set()

for clave_semana in sorted(semanas.keys()):
    partidos_semana = semanas[clave_semana]
    
    for p in partidos_semana:
        loc = p["EquipoLocal"]
        vis = p["EquipoVisitante"]
        
        # Si los equipos ya están en la jornada actual, cerramos la jornada y empezamos una nueva
        if loc in equipos_semana_actual or vis in equipos_semana_actual or len(semana_actual) >= 5:
            if semana_actual:
                jornadas_finales.append(list(semana_actual))
            semana_actual = []
            equipos_semana_actual = set()
            
        semana_actual.append(p)
        equipos_semana_actual.add(loc)
        equipos_semana_actual.add(vis)

# Añadir la última jornada si queda algo
if semana_actual:
    jornadas_finales.append(list(semana_actual))

# Mostrar resultados
print("=" * 60)
for i, partidos_j in enumerate(jornadas_finales, 1):
    equipos_jugando = set()
    for p in partidos_j:
        equipos_jugando.add(p["EquipoLocal"])
        equipos_jugando.add(p["EquipoVisitante"])
    
    equipos_descansan = equipos - equipos_jugando
    descanso_str = ", ".join(sorted(equipos_descansan)) if equipos_descansan else "Ninguno"
    
    print(f"📅 JORNADA {i} ({len(partidos_j)} partidos) - Descansa: {descanso_str}")
    for p in sorted(partidos_j, key=lambda x: x["FechaHora"]):
        fecha = p["FechaHora"].split("T")[0]
        print(f"   - {fecha} | {p['EquipoLocal']} vs {p['EquipoVisitante']}")
    print("-" * 60)
