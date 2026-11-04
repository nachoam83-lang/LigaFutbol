import json

def corregir_anio(fecha_str):
    if not fecha_str or len(fecha_str) < 7: return fecha_str
    try:
        mes = int(fecha_str[5:7])
        if mes <= 7: return "2027" + fecha_str[4:]
        else: return "2026" + fecha_str[4:]
    except: return fecha_str

try:
    with open("datos_canal.json", "r", encoding="utf-8") as f:
        datos = json.load(f)
except Exception as e:
    print(f"Error abriendo datos_canal.json: {e}")
    exit()

categoria = "Benjamín"
partidos = [p for p in datos.get("partidos", []) if p.get("EquipoLocal", "").startswith(categoria) or p.get("EquipoVisitante", "").startswith(categoria)]

for p in partidos:
    p["FechaHora"] = corregir_anio(p.get("FechaHora", ""))
    p["Fecha"] = p["FechaHora"].split("T")[0]

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
    p["JornadaBase"] = mapa_fechas.get(p["Fecha"], 99)
    p["Descolgado"] = False

partidos.sort(key=lambda x: (x["JornadaBase"], x["FechaHora"]))

equipos = set()
for p in partidos:
    equipos.add(p["EquipoLocal"])
    equipos.add(p["EquipoVisitante"])

print(f"Analizando {len(partidos)} partidos de la categoría {categoria}...")
print(f"Equipos: {len(equipos)}\n")

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
            jornadas_finales[j].append(p)
        else:
            p["Descolgado"] = True
            descolgados.append(p)
            # Se queda en su jornada base con asterisco
            jornadas_finales[j].append(p)

# Añadir J12 (*) con los descolgados (sin sobrescribir la J11 real)
if descolgados:
    jornadas_finales[12] = descolgados

# Mostrar resultados
print("=" * 60)
for j in sorted(jornadas_finales.keys()):
    partidos_j = jornadas_finales[j]
    equipos_jugando = set()
    for p in partidos_j:
        equipos_jugando.add(p["EquipoLocal"])
        equipos_jugando.add(p["EquipoVisitante"])
    
    equipos_descansan = equipos - equipos_jugando
    descanso_str = ", ".join(sorted(equipos_descansan)) if equipos_descansan else "Ninguno"
    
    sufijo = " (*)" if j == 12 else ""
    print(f"📅 JORNADA {j}{sufijo} ({len(partidos_j)} partidos) - Descansa: {descanso_str}")
    for p in sorted(partidos_j, key=lambda x: x["FechaHora"]):
        asterisco = " *" if p.get("Descolgado") else ""
        print(f"   - {p['Fecha']} | {p['EquipoLocal']} vs {p['EquipoVisitante']}{asterisco}")
    print("-" * 60)
