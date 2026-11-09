"""ONDA SONIKA · Felicitaciones
Recibe las felicitaciones de la web, hace el autotune, muestra la mini app de Ángel (Sí/No),
programa las aceptadas en AzuraCast y sirve la página para que el oyente escuche/descargue su audio.
"""
import base64, datetime as dt, io, json, os, random, secrets, shutil, string, subprocess, threading, time, urllib.parse, urllib.request
from collections import defaultdict, deque
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np, soundfile as sf
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials

DATA = Path(os.getenv("DATA_DIR", "/data"))
ADMIN_PASS = os.getenv("ADMIN_PASS", "")
AZ_URL = os.getenv("AZ_URL", "").rstrip("/")          # p. ej. https://radio.ondasonika.com
AZ_KEY = os.getenv("AZ_KEY", "")
AZ_STATION = os.getenv("AZ_STATION", "1")
AZ_FOLDER = os.getenv("AZ_FOLDER", "10 Dedicatorias")
PUBLIC_URL = (os.getenv("PUBLIC_URL") or "https://radio.ondasonika.com:9443").rstrip("/")  # p. ej. https://radio.ondasonika.com:8448
ORIGINS = [o for o in os.getenv("ALLOWED_ORIGINS", "https://ondasonika.com,https://www.ondasonika.com").split(",") if o]
DIAS_MIN = int(os.getenv("ANTELACION_DIAS", "5"))
BORRAR_DIAS = int(os.getenv("BORRAR_DIAS", "90"))
TZ = ZoneInfo("Europe/Madrid")
FRANJAS = {"Mañana 10-13": (10, 13), "Tarde 17-20": (17, 20), "Noche 20-23": (20, 23)}
MOTIVOS = {"cumple": "Cumpleaños", "aniversario": "Aniversario", "amor": "Amor"}
MAX_BYTES = 20 * 1024 * 1024

for d in ("pend",):
    (DATA / d).mkdir(parents=True, exist_ok=True)

app = FastAPI(docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["POST", "GET"], allow_headers=["Content-Type", "X-Meta"])
security = HTTPBasic()

# ---------- utilidades ----------
_hits = defaultdict(deque)
def limit(ip: str, n: int, per: int):
    q = _hits[ip]; now = time.time()
    while q and q[0] < now - per: q.popleft()
    if len(q) >= n: raise HTTPException(429, "Demasiados envíos. Prueba más tarde.")
    q.append(now)

def ip_of(r: Request): return r.headers.get("x-forwarded-for", r.client.host if r.client else "?").split(",")[0]

def admin(cred: HTTPBasicCredentials = Depends(security)):
    if not ADMIN_PASS or not secrets.compare_digest(cred.password.encode(), ADMIN_PASS.encode()):
        raise HTTPException(401, "No autorizado", headers={"WWW-Authenticate": "Basic"})

def load_meta(code):
    p = DATA / "pend" / code / "meta.json"
    if not p.exists(): raise HTTPException(404, "No existe")
    return json.loads(p.read_text())

def save_meta(m): (DATA / "pend" / m["code"] / "meta.json").write_text(json.dumps(m, ensure_ascii=False, indent=1))

def fecha_txt(iso):
    d = dt.date.fromisoformat(iso)
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    return f"{dias[d.weekday()]} {d.day} de {meses[d.month-1]}"

def read_audio(body: bytes):
    if not body or len(body) > MAX_BYTES: raise HTTPException(413, "Audio demasiado grande")
    try: y, sr = sf.read(io.BytesIO(body), dtype="float32", always_2d=True)
    except Exception: raise HTTPException(400, "Audio no válido")
    return y.mean(axis=1), sr

# ---------- API pública ----------
@app.post("/api/tune")
async def tune(req: Request):
    limit(ip_of(req), 30, 3600)
    y, sr = read_audio(await req.body())
    if len(y) / sr > 55: raise HTTPException(413, "Máximo 45 segundos")
    from tune import autotune, detect_key
    out = autotune(y, sr, strength=1.0, scale=detect_key(y, sr))
    buf = io.BytesIO(); sf.write(buf, out, sr, format="WAV", subtype="PCM_16")
    return Response(buf.getvalue(), media_type="audio/wav")

@app.post("/api/dedica")
async def dedica(req: Request):
    """Recibe la felicitación (multipart: meta, mix, voz), la revisa sola y, si está limpia, la programa en la radio."""
    limit(ip_of(req), 6, 3600)
    form = await req.form()
    try: meta = json.loads(form.get("meta") or "{}")
    except Exception: raise HTTPException(400, "Datos no válidos")
    clean = lambda s, n=40: " ".join(str(s or "").split())[:n]
    m = {"motivo": meta.get("motivo"), "franja": meta.get("franja"), "fecha": meta.get("fecha"),
         "de": clean(meta.get("de")), "para": clean(meta.get("para")),
         "tel": "".join(ch for ch in str(meta.get("tel", "")) if ch.isdigit()), "cancion": clean(meta.get("cancion"), 80),
         "consent": bool(meta.get("consent"))}
    if m["motivo"] not in MOTIVOS or m["franja"] not in FRANJAS or not m["de"] or not m["para"] or not m["consent"]:
        raise HTTPException(400, "Faltan datos")
    if len(m["tel"]) == 9: m["tel"] = "34" + m["tel"]
    if not 10 <= len(m["tel"]) <= 15: raise HTTPException(400, "Teléfono no válido")
    try: f = dt.date.fromisoformat(m["fecha"])
    except Exception: raise HTTPException(400, "Fecha no válida")
    hoy = dt.datetime.now(TZ).date()
    if f < hoy + dt.timedelta(days=DIAS_MIN) or f > hoy + dt.timedelta(days=120): raise HTTPException(400, "Fecha fuera de plazo")
    mix = form.get("mix"); voz = form.get("voz")
    if mix is None or voz is None: raise HTTPException(400, "Falta el audio")
    y, sr = read_audio(await mix.read())
    if len(y) / sr > 70: raise HTTPException(413, "Audio demasiado largo")
    vy, vsr = read_audio(await voz.read())
    code = "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    m.update(code=code, secret=secrets.token_urlsafe(10), creado=dt.datetime.now(TZ).isoformat(timespec="minutes"))
    folder = DATA / "pend" / code; folder.mkdir(parents=True)
    # 1) filtro automático
    from moderar import transcribir, revisar, MSG
    try: texto = transcribir(vy, vsr)
    except Exception as e: texto = ""; m["error"] = f"transcripción: {e}"
    ok, motivo = revisar(texto)
    m["texto"] = texto
    if not ok:
        m.update(estado="rechazada", razon=motivo); save_meta(m)   # solo se guarda el texto, no el audio
        msg = ("No hemos entendido bien tu mensaje. Grábalo otra vez hablando cerca del móvil."
               if motivo.startswith("no se entiende") else MSG)
        raise HTTPException(422, msg)
    # 2) audio final normalizado
    wav = folder / "orig.wav"; sf.write(wav, y, sr)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                    "-ar", "44100", "-ac", "2", "-b:a", "160k", "-metadata", f"title=Felicitación {code}", "-metadata", "artist=ONDA SONIKA",
                    str(folder / "audio.mp3")], check=True)
    wav.unlink()
    # 3) programar en la radio
    try:
        m["azuracast"] = programar(m); m["estado"] = "aceptada"
    except Exception as e:
        m["estado"] = "error"; m["error"] = f"No se pudo programar en la radio: {e}"
    save_meta(m)
    franja = m["franja"].split(" ")
    return {"code": code, "estado": m["estado"], "fecha": fecha_txt(m["fecha"]), "franja": f"{franja[0].lower()} ({franja[1].replace('-', ' a ')} h)",
            "enlace": f"{PUBLIC_URL}/d/{code}/{m['secret']}" if m["estado"] == "aceptada" else ""}

@app.get("/d/{code}/{secret}.mp3")
def audio_pub(code: str, secret: str):
    m = load_meta(code.upper())
    if not secrets.compare_digest(m["secret"], secret) or m["estado"] != "aceptada": raise HTTPException(404)
    return FileResponse(DATA / "pend" / m["code"] / "audio.mp3", media_type="audio/mpeg", filename=f"felicitacion-ONDA-SONIKA-{m['code']}.mp3")

@app.get("/d/{code}/{secret}", response_class=HTMLResponse)
def page_pub(code: str, secret: str):
    m = load_meta(code.upper())
    if not secrets.compare_digest(m["secret"], secret) or m["estado"] != "aceptada": raise HTTPException(404)
    esc = lambda s: str(s).replace("&", "&amp;").replace("<", "&lt;")
    src = f"/d/{m['code']}/{secret}.mp3"
    return PAGE.format(body=f"""<h1>Tu felicitación 🎉</h1>
<p>{MOTIVOS[m['motivo']]} para <b>{esc(m['para'])}</b> · sonará en ONDA SONIKA el {fecha_txt(m['fecha'])} ({m['franja'].split(' ')[0].lower()}).</p>
<audio controls src="{src}"></audio>
<a class="btn" href="{src}" download>⬇ Descargar mi audio</a>
<a class="btn alt" href="https://ondasonika.com">📻 Escuchar ONDA SONIKA</a>""")

# ---------- mini app de Ángel ----------
@app.get("/admin", response_class=HTMLResponse, dependencies=[Depends(admin)])
def admin_page():
    items = []
    for p in sorted((DATA / "pend").glob("*/meta.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        items.append(json.loads(p.read_text()))
    esc = lambda s: str(s).replace("&", "&amp;").replace("<", "&lt;")
    cards = []
    for m in items:
        st = m.get("estado", "pendiente")
        if st == "aceptada":
            az_ = m.get("azuracast", {})
            btns = f'<p class="st aceptada">✅ PROGRAMADA · {fecha_txt(m["fecha"])} a las {az_.get("hora","?")}</p><button class="no" onclick="quitar(\'{m["code"]}\')">Quitar de la radio</button>'
        elif st in ("error", "pendiente"):
            btns = f'<p class="err">{esc(m.get("error",""))}</p><button class="yes" onclick="prog(\'{m["code"]}\')">Programar ahora</button>'
        elif st == "rechazada":
            btns = f'<p class="st rechazada">❌ RECHAZADA AUTOMÁTICAMENTE · {esc(m.get("razon",""))}</p>'
        else:
            btns = f'<p class="st">{st.upper()}</p>'
        audio = f'<audio controls preload="none" src="/admin/audio/{m["code"]}.mp3"></audio>' if (DATA / "pend" / m["code"] / "audio.mp3").exists() else ""
        cards.append(f"""<div class="card {st}" data-st="{st}"><div class="code">{m['code']}</div>
<b>{MOTIVOS.get(m['motivo'], m['motivo'])} para {esc(m['para'])}</b>
<p>{fecha_txt(m['fecha'])} · {m['franja']}<br>De: {esc(m['de'])} · +{m['tel']}<br>Música: {esc(m.get('cancion') or 'sin canción')}<br><small>Recibida {m['creado'].replace('T',' ')}</small></p>
<p style="color:#ddd;font-style:italic">“{esc(m.get('texto','')) or '—'}”</p>{audio}{btns}</div>""")
    n = lambda e: sum(1 for m in items if m.get("estado") == e)
    return PAGE.format(body=f"""<h1>Felicitaciones</h1><p>Se aceptan y programan solas. Aquí ves el historial.</p>
<div class="tabs"><button onclick="f('aceptada')" class="on">Programadas ({n('aceptada')})</button><button onclick="f('rechazada')">Rechazadas ({n('rechazada')})</button><button onclick="f('error')">Con error ({n('error')+n('pendiente')})</button><button onclick="f('retirada')">Quitadas ({n('retirada')})</button></div>
{''.join(cards) or '<p>No hay felicitaciones todavía.</p>'}
<details style="margin-top:30px"><summary>⚙️ Ajustes</summary><p>Clave API de AzuraCast: {'✅ puesta' if az_key() else '❌ falta'}</p><input id="azk" placeholder="Pega aquí la clave API" style="width:100%;padding:12px;border-radius:10px;border:1px solid #333;background:#0f0f11;color:#fff"><button onclick="saveKey()" style="margin-top:8px;padding:10px 16px;border-radius:10px">Guardar</button></details>
<script>
function f(s){{document.querySelectorAll('.card').forEach(c=>c.style.display=(c.dataset.st===s||(s==='error'&&c.dataset.st==='pendiente'))?'':'none');document.querySelectorAll('.tabs button').forEach(b=>b.classList.toggle('on',b.getAttribute('onclick').includes("'"+s+"'")))}}f('aceptada');
async function quitar(code){{if(!confirm('¿Quitar esta felicitación de la radio? Ya no sonará.'))return;const r=await fetch('/admin/quitar/'+code,{{method:'POST'}});const j=await r.json();if(!r.ok)alert(j.detail||'Error');location.reload()}}
async function prog(code){{const r=await fetch('/admin/decide/'+code+'?ok=1',{{method:'POST'}});const j=await r.json();alert(r.ok?(j.aviso||'Programada'):(j.detail||'Error'));location.reload()}}
async function saveKey(){{const v=document.getElementById('azk').value.trim();if(!v)return;await fetch('/admin/config',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{az_key:v}})}});location.reload()}}
</script>""")

@app.post("/admin/quitar/{code}", dependencies=[Depends(admin)])
def quitar(code: str):
    m = load_meta(code.upper())
    if m.get("estado") != "aceptada": raise HTTPException(409, "No está programada")
    a = m.get("azuracast", {})
    try:
        if a.get("playlist_id"): az("DELETE", f"/playlist/{a['playlist_id']}")
        if a.get("file_id"): az("DELETE", f"/file/{a['file_id']}")
    except Exception as e:
        raise HTTPException(502, f"No se pudo quitar de la radio: {e}")
    m["estado"] = "retirada"; m["retirada"] = dt.datetime.now(TZ).isoformat(timespec="minutes"); save_meta(m)
    return {"ok": True}

def az_key(): return cfg().get("az_key") or AZ_KEY

@app.post("/admin/config", dependencies=[Depends(admin)])
async def admin_config(req: Request):
    j = await req.json(); c = cfg()
    if j.get("az_key"): c["az_key"] = j["az_key"].strip()
    (DATA / "config.json").write_text(json.dumps(c)); return {"ok": True}

@app.get("/admin/audio/{code}.mp3", dependencies=[Depends(admin)])
def admin_audio(code: str):
    return FileResponse(DATA / "pend" / load_meta(code.upper())["code"] / "audio.mp3", media_type="audio/mpeg")

def wa_link(m):
    if m["estado"] == "aceptada":
        txt = (f"¡Hola {m['de']}! 🎉 Tu felicitación para {m['para']} ha sido aceptada.\n"
               f"Sonará en ONDA SONIKA el {fecha_txt(m['fecha'])} en la franja de {m['franja'].split(' ')[0].lower()} "
               f"({m['franja'].split(' ')[1].replace('-', ' a ')} h).\n\nEscúchala y descárgala aquí: {PUBLIC_URL}/d/{m['code']}/{m['secret']}\n\n¡Gracias por participar! 📻 ondasonika.com")
    else:
        txt = (f"Hola {m['de']}, gracias por tu felicitación para {m['para']} (código {m['code']}).\n"
               f"Esta vez no hemos aceptado tu propuesta. ¡Puedes intentarlo de nuevo cuando quieras! 📻 ONDA SONIKA")
    return f"https://wa.me/{m['tel']}?text={urllib.parse.quote(txt)}"

@app.get("/admin/wa/{code}", dependencies=[Depends(admin)])
def admin_wa(code: str): return {"wa": wa_link(load_meta(code.upper()))}

@app.post("/admin/decide/{code}", dependencies=[Depends(admin)])
def decide(code: str, ok: int):
    m = load_meta(code.upper())
    if m.get("estado") not in ("pendiente", "error"): raise HTTPException(409, "Ya estaba decidida")
    aviso = None
    if ok:
        try:
            m["azuracast"] = programar(m); m.pop("error", None)
        except Exception as e:
            m["error"] = f"No se pudo programar en la radio: {e}"; save_meta(m)
            raise HTTPException(502, m["error"])
        m["estado"] = "aceptada"
        aviso = f"Programada para el {fecha_txt(m['fecha'])} a las {m['azuracast']['hora']}."
    else:
        m["estado"] = "rechazada"
    m["decidido"] = dt.datetime.now(TZ).isoformat(timespec="minutes"); m["wa"] = True
    save_meta(m)
    return {"wa": wa_link(m), "aviso": aviso}

# ---------- AzuraCast ----------
def az(method, path, data=None):
    req = urllib.request.Request(f"{AZ_URL}/api/station/{AZ_STATION}{path}", method=method,
                                 data=json.dumps(data).encode() if data is not None else None,
                                 headers={"X-API-Key": az_key(), "Content-Type": "application/json", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read().decode() or "{}"
    return json.loads(body)

def cfg():
    p = DATA / "config.json"
    return json.loads(p.read_text()) if p.exists() else {}

def programar(m):
    if not (AZ_URL and az_key()): raise RuntimeError("falta la clave de AzuraCast (pon la clave en Ajustes, abajo del todo)")
    h0, h1 = FRANJAS[m["franja"]]
    hora = random.randint(h0, h1 - 1); minuto = random.choice(range(0, 50, 5))
    start = hora * 100 + minuto
    end = min(h1 * 100, (hora + 1) * 100 + minuto)
    path = f"{AZ_FOLDER}/felicitacion-{m['code']}.mp3"
    mp3 = (DATA / "pend" / m["code"] / "audio.mp3").read_bytes()
    up = az("POST", "/files", {"path": path, "file": base64.b64encode(mp3).decode()})
    f = dt.date.fromisoformat(m["fecha"])
    pl = az("POST", "/playlists", {
        "name": f"Felicitación {m['code']} ({m['fecha']})", "type": "default", "source": "songs", "order": "sequential",
        "is_enabled": True, "weight": 25, "include_in_requests": False, "include_in_on_demand": False,
        "avoid_duplicates": False, "is_jingle": False,
        "schedule_items": [{"start_time": start, "end_time": end, "days": [f.isoweekday()],
                            "start_date": m["fecha"], "end_date": m["fecha"], "loop_once": True}]})
    az("PUT", "/files/batch", {"do": "playlist", "files": [path], "dirs": [], "playlists": [pl["id"]], "currentDirectory": ""})
    return {"playlist_id": pl["id"], "file": path, "file_id": up.get("id"), "hora": f"{start // 100}:{start % 100:02d}"}

# ---------- limpieza ----------
def limpieza():
    while True:
        lim = time.time() - BORRAR_DIAS * 86400
        for d in (DATA / "pend").iterdir():
            if d.is_dir() and d.stat().st_mtime < lim: shutil.rmtree(d, ignore_errors=True)
        time.sleep(86400)
threading.Thread(target=limpieza, daemon=True).start()

# ---------- Pide tu canción: límites ----------
# Cada persona (su móvil) puede pedir 2 canciones al día; cada conexión, 6 al día.
# Un mismo artista no se puede pedir más de una vez cada hora (para que no suene lo mismo 50 veces).
PEDIR_DIA, PEDIR_IP_DIA, ARTISTA_MIN = 2, 6, 60
_ped = {"dia": None, "dev": defaultdict(int), "ip": defaultdict(int), "art": {}}
_ped_lock = threading.Lock()

def _norm(t): return " ".join(str(t or "").lower().split())

@app.post("/api/pedir")
async def pedir(req: Request):
    """Da permiso (o no) para pedir una canción que YA está en la radio. Si lo da, la web la pide a AzuraCast."""
    d = await req.json()
    dev = str(d.get("dev", ""))[:40] or "?"; ip = ip_of(req); art = _norm(d.get("artista"))
    if d.get("cancelar"):
        with _ped_lock:
            _ped["dev"][dev] = max(0, _ped["dev"][dev] - 1); _ped["ip"][ip] = max(0, _ped["ip"][ip] - 1); _ped["art"].pop(art, None)
        return {"ok": True}
    ahora = dt.datetime.now(TZ)
    with _ped_lock:
        if _ped["dia"] != ahora.date():
            _ped.update(dia=ahora.date(), dev=defaultdict(int), ip=defaultdict(int), art={})
        if _ped["dev"][dev] >= PEDIR_DIA or _ped["ip"][ip] >= PEDIR_IP_DIA:
            raise HTTPException(429, f"Ya has pedido {PEDIR_DIA} canciones hoy. ¡Mañana puedes pedir más! 📻")
        ult = _ped["art"].get(art)
        if art and ult and (ahora - ult).total_seconds() < ARTISTA_MIN * 60:
            raise HTTPException(429, "Este artista ya se ha pedido hace poco. Prueba con otro o vuelve en un rato.")
        _ped["dev"][dev] += 1; _ped["ip"][ip] += 1
        if art: _ped["art"][art] = ahora
        quedan = PEDIR_DIA - _ped["dev"][dev]
    return {"ok": True, "quedan": quedan}

@app.get("/health")
def health(): return {"ok": True}

PAGE = """<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>ONDA SONIKA</title>
<style>:root{{--bg:#0b0b0c;--panel:#151517;--line:#26262a;--txt:#f4f1ec;--mut:#a29d96;--or:#ff7a1a;--or2:#ffb347}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--txt);font-family:system-ui,sans-serif}}
.w{{max-width:620px;margin:0 auto;padding:20px 16px 50px}}.top{{color:var(--or2);font-weight:800;letter-spacing:.16em;font-size:13px}}
h1{{font-size:26px;margin:14px 0 6px}}p{{color:var(--mut);line-height:1.45}}audio{{width:100%;margin:12px 0}}
.btn{{display:block;text-align:center;padding:15px;border-radius:14px;background:linear-gradient(145deg,var(--or2),var(--or));color:#111;font-weight:800;text-decoration:none;margin-top:10px}}
.btn.alt{{background:transparent;border:1px solid var(--or);color:var(--or2)}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:16px;margin-top:14px}}
.card b{{font-size:17px}}.code{{float:right;color:var(--or2);font-weight:800;letter-spacing:.1em}}
.row{{display:flex;gap:10px}}.row button{{flex:1;padding:15px;border-radius:14px;border:0;font-size:17px;font-weight:800}}
.yes{{background:#25d366;color:#05290f}}.no{{background:#3a1d1d;color:#ff8a80}}
.tabs{{display:flex;gap:8px;margin-top:10px}}.tabs button{{flex:1;padding:10px;border-radius:99px;border:1px solid var(--line);background:#0f0f11;color:var(--txt)}}
.tabs .on{{border-color:var(--or);color:var(--or2)}}.st.aceptada{{color:#25d366}}.st.rechazada{{color:#ff8a80}}.err{{color:#ff8a80}}a{{color:var(--or2)}}
</style></head><body><div class="w"><div class="top">ONDA SONIKA</div>{body}</div></body></html>"""

# precarga el modelo de voz a texto al arrancar, para que la primera felicitación no tarde
def _precarga():
    try:
        from moderar import transcribir; transcribir(np.zeros(16000, dtype="float32"), 16000)
    except Exception as e: print("precarga whisper:", e)
threading.Thread(target=_precarga, daemon=True).start()
