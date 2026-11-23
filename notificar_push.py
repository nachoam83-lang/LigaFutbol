"""Envía avisos push cuando cambia un partido de un equipo que sigue algún móvil.

Uso (lo lanza el workflow tras la extracción):
    python notificar_push.py <carpeta_con_JSON_anteriores> [--prueba]

Variables de entorno: ECM_WORKER, ECM_WORKER_KEY (leer suscripciones), VAPID_PRIVATE, VAPID_SUBJECT (opcional).
Las suscripciones viven en el KV privado del Worker de Cloudflare, no en el repo (que es público).
"""
import json
import os
import sys
import urllib.request
import zlib
from datetime import datetime

DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
MAX_ENVIOS = 400


def cargar(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def parse_fecha(txt):
    try:
        return datetime.fromisoformat(str(txt)[:19])
    except Exception:
        return None


def fecha_txt(txt):
    d = parse_fecha(txt)
    if not d:
        return ""
    s = f"{DIAS[d.weekday()]} {d.day} {MESES[d.month - 1]}"
    return s + (f" {d:%H:%M}" if (d.hour or d.minute) else "")


def es_aplazado(estado):
    e = (estado or "").lower()
    return any(x in e for x in ("aplaz", "suspend", "cancel", "desprogram", "no celebra"))


def es_jugado(estado):
    e = (estado or "").lower()
    return "disputad" in e or "jugad" in e


def cambios_partido(ant, nue):
    """Devuelve lista de (tipo, texto) entre dos versiones del mismo partido."""
    out = []
    fa, fn = parse_fecha(ant.get("FechaHora")), parse_fecha(nue.get("FechaHora"))
    if fa and fn and fa != fn and fn >= datetime.now().replace(hour=0, minute=0):
        if fa.hour == 0 and fa.minute == 0:
            out.append(("hora", f"Ya tiene hora: {fecha_txt(nue['FechaHora'])}"))
        else:
            out.append(("hora", f"Cambio de hora: {fecha_txt(ant['FechaHora'])} → {fecha_txt(nue['FechaHora'])}"))
    ca, cn = (ant.get("Campo") or "").strip(), (nue.get("Campo") or "").strip()
    if cn and ca != cn and fn and fn >= datetime.now().replace(hour=0, minute=0):
        out.append(("campo", f"Cambio de campo: {cn}"))
    ea, en = ant.get("EstadoPartido"), nue.get("EstadoPartido")
    if ea != en:
        reprogramado = "no celebra" in (en or "").lower() and fn and fn > datetime.now()
        if es_aplazado(en) and not es_aplazado(ea) and not reprogramado:
            out.append(("aplazado", "Partido aplazado o desprogramado"))
        elif es_jugado(en) and not es_jugado(ea):
            out.append(("resultado", f"Resultado: {nue.get('ResultadoEquipoLocal')}-{nue.get('ResultadoEquipoVisitante')}"))
    return out


def partidos_ecm(datos):
    """{clave_grupo: {id_partido: partido}}"""
    res = {}
    for clave, lista in ((datos or {}).get("resultados") or {}).items():
        res[clave] = {p.get("Id"): p for p in lista if isinstance(p, dict) and p.get("Id") is not None}
    return res


def partidos_canal(datos):
    """Canal no tiene Id: se identifica por (local, visitante, nº de enfrentamiento)."""
    res, cont = {}, {}
    for p in sorted((datos or {}).get("partidos") or [], key=lambda x: str(x.get("FechaHora"))):
        par = (p.get("EquipoLocal"), p.get("EquipoVisitante"))
        cont[par] = cont.get(par, 0) + 1
        p = dict(p)
        p["EstadoPartido"] = "Disputado" if (p.get("ResultadoEquipoLocal") or p.get("ResultadoEquipoVisitante")) else "Pendiente de Jugar"
        res[(par[0], par[1], cont[par])] = p
    return res


def detectar(ant_liga, nue_liga, ant_canal, nue_canal):
    """Devuelve lista de eventos {grupo|None, deporte, local, visitante, tipo, texto, id}."""
    ev = []
    a, n = partidos_ecm(ant_liga), partidos_ecm(nue_liga)
    for clave, nuevos in n.items():
        viejos = a.get(clave)
        if not viejos:
            continue
        for pid, p in nuevos.items():
            if pid in viejos:
                for tipo, texto in cambios_partido(viejos[pid], p):
                    ev.append({"clave": clave, "canal": False, "local": p.get("EquipoLocal"), "visitante": p.get("EquipoVisitante"),
                               "tipo": tipo, "texto": texto, "id": f"e{pid}"})
    ac, nc = partidos_canal(ant_canal), partidos_canal(nue_canal)
    for k, p in nc.items():
        if k in ac:
            for tipo, texto in cambios_partido(ac[k], p):
                ev.append({"clave": None, "canal": True, "local": p.get("EquipoLocal"), "visitante": p.get("EquipoVisitante"),
                           "tipo": tipo, "texto": texto, "id": f"c{zlib.crc32(repr(k).encode())}"})
    return ev


def mismo(a, b):
    return (a or "").strip().lower() == (b or "").strip().lower()


def clave_equipo(eq):
    return f"{eq.get('d')}_{eq.get('c')}_{eq.get('k')}_{eq.get('g')}"


def avisos_para(sub, eventos):
    """Mensajes {title, body, tag, url} que le tocan a una suscripción según los equipos que sigue."""
    out, vistos = [], set()
    for ev in eventos:
        for eq in sub.get("equipos", []):
            if ev["canal"]:
                if eq.get("d") != "4":
                    continue
            elif clave_equipo(eq) != ev["clave"]:
                continue
            if not (mismo(eq.get("n"), ev["local"]) or mismo(eq.get("n"), ev["visitante"])):
                continue
            if (ev["id"], ev["tipo"]) in vistos:
                continue
            vistos.add((ev["id"], ev["tipo"]))
            rival = ev["visitante"] if mismo(eq.get("n"), ev["local"]) else ev["local"]
            icono = {"hora": "🕒", "campo": "📍", "aplazado": "⚠️", "resultado": "⚽"}.get(ev["tipo"], "ℹ️")
            out.append({"title": f"{icono} {eq.get('n')}", "body": f"{ev['texto']} · vs {rival}", "tag": f"{ev['id']}-{ev['tipo']}", "url": "/"})
    return out


def resumir(msgs, maximo=6):
    """Si hay demasiados cambios a la vez (p. ej. tras una caída), manda un solo aviso resumen."""
    if len(msgs) <= maximo:
        return msgs
    return [{"title": "🔔 Ligas Infantiles", "body": f"Hay {len(msgs)} cambios en tus partidos. Ábrela para verlos.", "tag": "resumen", "url": "/"}]


def pedir(base, clave, ruta, datos=None):
    req = urllib.request.Request(base.rstrip("/") + ruta, method="POST" if datos is not None else "GET",
                                 data=json.dumps(datos).encode() if datos is not None else None,
                                 headers={"X-Key": clave, "Content-Type": "application/json", "User-Agent": "ligafutbol-notificar"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def enviar(webpush, WebPushException, sub, msg, vapid, subject):
    try:
        webpush(subscription_info=sub["sub"], data=json.dumps(msg), vapid_private_key=vapid,
                vapid_claims={"sub": subject}, ttl=6 * 3600)
        return "ok"
    except WebPushException as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        return "caducada" if code in (404, 410) else f"error {code}: {str(e)[:100]}"
    except Exception as e:
        return f"error: {str(e)[:100]}"


def main(argv):
    prueba = "--prueba" in argv
    args = [a for a in argv[1:] if not a.startswith("--")]
    base, clave, vapid = os.getenv("ECM_WORKER"), os.getenv("ECM_WORKER_KEY"), os.getenv("VAPID_PRIVATE")
    if not (base and clave and vapid):
        print("⚠️ Push: faltan ECM_WORKER, ECM_WORKER_KEY o VAPID_PRIVATE. No se envía nada.")
        return 0
    subject = os.getenv("VAPID_SUBJECT") or "https://ligapsj.onrender.com"
    try:
        subs = pedir(base, clave, "/push/subs")
    except Exception as e:
        print(f"⚠️ Push: no se pudo leer la lista de suscripciones: {e}")
        return 0
    print(f"🔔 Suscripciones: {len(subs)}")
    if not subs:
        return 0

    if prueba:
        eventos_por_sub = [(s, [{"title": "🔔 Avisos activados", "body": "Esto es una notificación de prueba de Ligas Infantiles.", "tag": "prueba", "url": "/"}]) for s in subs]
    else:
        carpeta = args[0] if args else "."
        ant_liga, ant_canal = cargar(os.path.join(carpeta, "datos_liga.json")), cargar(os.path.join(carpeta, "datos_canal.json"))
        nue_liga, nue_canal = cargar("datos_liga.json"), cargar("datos_canal.json")
        if not (ant_liga or ant_canal):
            print("ℹ️ Push: no hay copia anterior; no se compara.")
            return 0
        eventos = detectar(ant_liga, nue_liga, ant_canal, nue_canal)
        print(f"🔎 Cambios detectados: {len(eventos)}")
        eventos_por_sub = [(s, resumir(avisos_para(s, eventos))) for s in subs]

    from pywebpush import webpush, WebPushException
    enviados, caducadas = 0, []
    for s, msgs in eventos_por_sub:
        for m in msgs:
            if enviados >= MAX_ENVIOS:
                break
            r = enviar(webpush, WebPushException, s, m, vapid, subject)
            if r == "ok":
                enviados += 1
            elif r == "caducada":
                caducadas.append(s["id"])
                break
            else:
                print("   ", r)
    print(f"✅ Avisos enviados: {enviados} · suscripciones caducadas: {len(set(caducadas))}")
    if caducadas:
        try:
            pedir(base, clave, "/push/del", {"ids": list(set(caducadas))})
        except Exception as e:
            print(f"⚠️ No se pudieron borrar las caducadas: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
