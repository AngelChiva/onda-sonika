"""Autotune ONDA SONIKA: detecta el tono (pYIN) y lo corrige al semitono más cercano (PSOLA)."""
import numpy as np, librosa, psola, scipy.signal as sg, soundfile as sf

def autotune(y, sr, strength=1.0, scale=None):
    """y: mono float32. strength 0..1 (1 = efecto autotune marcado). scale: lista de clases de nota (0=Do) o None = cromática."""
    fmin, fmax = librosa.note_to_hz('C2'), librosa.note_to_hz('C6')
    hop = 256
    f0, voiced, _ = librosa.pyin(y, fmin=fmin, fmax=fmax, sr=sr, frame_length=2048, hop_length=hop)
    midi = librosa.hz_to_midi(f0)
    if scale is None:
        tgt = np.round(midi)
    else:
        tgt = np.copy(midi)
        for i, m in enumerate(midi):
            if np.isnan(m): continue
            cands = [n for n in range(int(m) - 2, int(m) + 3) if n % 12 in scale]
            tgt[i] = min(cands, key=lambda n: abs(n - m))
    # suavizar el objetivo (evita saltos bruscos) y mezclar con la intención original
    tgt = sg.medfilt(np.nan_to_num(tgt, nan=0.0), 9)
    tgt[np.isnan(midi)] = np.nan
    corr = midi + strength * (tgt - midi)
    target_hz = librosa.midi_to_hz(corr)
    target_hz[~voiced] = np.nan
    out = psola.vocode(y, sample_rate=sr, target_pitch=target_hz, fmin=fmin, fmax=fmax)
    return out.astype(np.float32)

def detect_key(y, sr):
    """Escala mayor más probable (clases de nota)."""
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
    major = np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88])
    best = max(range(12), key=lambda k: np.corrcoef(np.roll(major, k), chroma)[0, 1])
    return [(best + s) % 12 for s in (0, 2, 4, 5, 7, 9, 11)]

if __name__ == '__main__':
    import sys
    y, sr = librosa.load(sys.argv[1], sr=22050, mono=True)
    sf.write(sys.argv[2], autotune(y, sr, scale=detect_key(y, sr)), sr)
