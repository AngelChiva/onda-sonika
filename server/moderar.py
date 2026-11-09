"""ONDA SONIKA · filtro automático (opción A: transcripción + lista de palabras).
- Pasa la voz a texto con faster-whisper (modelo "base", en el propio servidor, sin coste).
- Rechaza insultos, tacos, contenido sexual o de drogas, amenazas, teléfonos, correos/redes y direcciones.
- Ante la duda, rechaza (mejor pedir que lo graben otra vez que emitir algo malo).
"""
import re, unicodedata

MODEL_NAME = "base"
_model = None

def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8", download_root="/models")
    return _model

def transcribir(y, sr):
    """y: mono float32 a cualquier frecuencia. Devuelve el texto."""
    import numpy as np
    if sr != 16000:
        n = int(len(y) * 16000 / sr)
        y = np.interp(np.linspace(0, len(y) - 1, n), np.arange(len(y)), y).astype("float32")
    segs, _ = _get_model().transcribe(y, language="es", beam_size=1, vad_filter=True, condition_on_previous_text=False)
    return " ".join(s.text.strip() for s in segs).strip()

def norm(t):
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9@ ]+", " ", t)

# Palabras prohibidas (castellano y catalán). Se comparan palabras enteras, sin tildes.
_RAW = """
puta puto putas putos putada putero putilla zorra zorras guarra guarras furcia ramera fulana golfa
cabron cabrona cabrones gilipollas gilipolla gilipuertas imbecil imbeciles idiota idiotas subnormal subnormales
retrasado retrasada mongolo mongola tonto_del_culo capullo capulla mamon mamona pendejo pendeja malparit malparida
maricon maricones marica bollera sudaca sudacas panchito panchitos
polla pollas pollon coño cono conos chocho chumino cojon cojones collons joder jodete jodido jodida follar follando follada
follame foll mamada mamadas paja pajas pajero correrse corrida cachondo cachonda cachondos porno porn tetas tetitas
pene vagina sexo sexual desnudo desnuda desnudos puticlub prostituta prostitutas pute merda mierda mierdas cagar cagate
fotre fotut fotuda gilipolles caca
droga drogas cocaina farlopa porro porros canuto hachis marihuana pastillas speed mdma extasis
matar mato matarte mataros matate suicidate suicidio muere muerete muerta_de_hambre violar violacion pegarte pistola navaja
"""
PROHIBIDAS = {w for w in _RAW.split() if "_" not in w}
_FRASES_EXTRA = [w.replace("_", " ") for w in _RAW.split() if "_" in w]
FRASES = [norm(f) for f in [
    "hijo de puta", "hija de puta", "fill de puta", "me cago en", "me cago", "que te den", "vete a la mierda",
    "te voy a matar", "te voy a pegar", "ojala te mueras", "ves a cagar", "que et fotin", "a la mierda",
    "sigueme en", "seguidme en", "mi instagram", "mi insta", "mi tiktok", "mi numero", "mi telefono", "mi movil",
    "llamame al", "escribeme al", "agregame", "punto com", "arroba",
]] + [norm(f) for f in _FRASES_EXTRA]
REDES = {"instagram", "insta", "tiktok", "facebook", "snapchat", "telegram", "onlyfans", "gmail", "hotmail", "outlook", "whatsapp", "wasap", "guasap"}
NUMEROS = {"cero", "uno", "una", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce",
           "trece", "catorce", "quince", "veinte", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa",
           "cien", "ciento", "zero", "un", "quatre", "sis", "set", "vuit", "nou", "deu", "y", "i"}
VIAS = {"calle", "carrer", "avenida", "avinguda", "plaza", "placa", "paseo", "passeig", "ronda", "camino", "cami", "portal", "piso", "escalera"}

MSG = "Tu mensaje incumple las normas. Prueba a decirlo con otras palabras."

def revisar(texto):
    """Devuelve (ok, motivo_interno). motivo_interno solo se guarda para el historial de Ángel."""
    t = norm(texto)
    pal = t.split()
    if not pal:
        return False, "no se entiende nada (sin palabras)"
    for w in pal:
        if w in PROHIBIDAS:
            return False, f"palabra prohibida: {w}"
        if w.startswith("@") or "@" in w:
            return False, "correo o usuario de red social"
        if w in REDES:
            return False, f"red social o contacto: {w}"
    tt = " " + " ".join(pal) + " "
    for f in FRASES:
        if f" {f} " in tt:
            return False, f"frase prohibida: {f}"
    # teléfonos: 6 o más cifras seguidas (con o sin espacios) o 5+ números dichos con palabras seguidos
    if re.search(r"(\d[\s]*){6,}", t):
        return False, "parece un número de teléfono"
    run = 0
    for w in pal:
        run = run + 1 if (w in NUMEROS and w not in {"y", "i", "un", "una"}) or w.isdigit() else (run if w in {"y", "i"} else 0)
        if run >= 5:
            return False, "parece un número de teléfono dicho en voz alta"
    # direcciones: tipo de vía seguido de nombre y número
    for i, w in enumerate(pal):
        if w in VIAS and any(x.isdigit() or x in NUMEROS for x in pal[i + 1:i + 6]):
            return False, "parece una dirección"
    return True, ""
