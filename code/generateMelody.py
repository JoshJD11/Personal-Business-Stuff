"""
musicbox30.py
=============
Convierte un archivo MIDI en un arreglo apto para una caja de música
de mecanismo de papel de 30 notas.

El problema NO tiene solución "exacta": el mecanismo tiene un rango de
alturas fijo, sin dinámica, con tiempo cuantizado y polifonía limitada.
Este script implementa el mejor pipeline de APROXIMACIÓN posible:

    1. Extraer notas del MIDI (altura, inicio, duración).
    2. Buscar la transposición óptima (fuerza bruta sobre 24 semitonos)
       que maximiza cuántas notas caen dentro del set de 30 notas real.
    3. Mapear cada nota fuera de rango/escala a la nota disponible más
       cercana (costo = distancia en semitonos).
    4. Cuantizar el tiempo a la resolución mínima del mecanismo.
    5. Reducir la polifonía al máximo de notas simultáneas que el
       mecanismo puede tocar sin atascarse, priorizando la melodía.
    6. Exportar: (a) un MIDI "de vista previa" ya arreglado y
       (b) un CSV con la posición física de cada pin/agujero en la
       tira de papel, listo para fabricar.

IMPORTANTE: NOTE_SET más abajo es un PLACEHOLDER (30 semitonos
cromáticos consecutivos). Las cajas reales varían mucho: algunas son
diatónicas de Do mayor en ~2.5 octavas con 2-3 notas cromáticas
añadidas, otras son cromáticas completas. Reemplaza NOTE_SET por el
diagrama de notas real de tu mecanismo (suele venir impreso en la
caja o en el manual) para que el resultado sea físicamente correcto.
"""

from dataclasses import dataclass
from pathlib import Path
import csv
import pretty_midi
import os


# ----------------------------------------------------------------------
# 1. CONFIGURACIÓN DEL MECANISMO (ajustar a tu caja real)
# ----------------------------------------------------------------------

# Notas reales de la manivela de 30 notas del usuario, en el mismo
# orden en que aparecen en el diagrama (de grave a agudo):
# C, D, G, A, B, C1, D1, E1, F1, F#1, G1, G#1, A1, A#1, B1,
# C2, C#2, D2, D#2, E2, F2, F#2, G2, G#2, A2, A#2, B2, C3, D3, E3
#
# Se asume que "C" (sin número) = C4, "C1" = C5, "C2" = C6, "C3" = C7
# (cada número de octava sube 12 semitonos respecto al anterior).
# Si tu caja suena distinto a lo esperado, es la primera cosa a revisar:
# quizás tu "C" real corresponde a otra octava; en ese caso solo hay
# que sumar/restar un múltiplo de 12 a todos los valores por igual.
NOTE_NAMES = [
    "C", "D", "G", "A", "B",
    "C1", "D1", "E1", "F1", "F#1", "G1", "G#1", "A1", "A#1", "B1",
    "C2", "C#2", "D2", "D#2", "E2", "F2", "F#2", "G2", "G#2", "A2", "A#2", "B2",
    "C3", "D3", "E3",
]

NOTE_SET = [
    60, 62, 67, 69, 71,                                              # C, D, G, A, B
    72, 74, 76, 77, 78, 79, 80, 81, 82, 83,                          # C1..B1
    84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95,                  # C2..B2
    96, 98, 100,                                                     # C3, D3, E3
]
assert len(NOTE_SET) == 30
assert len(NOTE_NAMES) == 30
PITCH_TO_NAME = dict(zip(NOTE_SET, NOTE_NAMES))

MAX_POLYPHONY = 6          # notas simultáneas que el peine puede sonar
TIME_RESOLUTION = 0.12     # segundos entre posiciones válidas en la tira
MIN_REPEAT_GAP = 0.10      # tiempo mínimo entre dos pulsos del mismo pin
STRIP_SPEED_MM_PER_SEC = 20.0  # velocidad de avance del papel (mm/s)


@dataclass
class Note:
    start: float
    end: float
    pitch: int
    velocity: int = 100

# ----------------------------------------------------------------------
# 2. EXTRACCIÓN DE NOTAS DEL MIDI
# ----------------------------------------------------------------------

def load_notes(midi_path: str) -> list[Note]:
    pm = pretty_midi.PrettyMIDI(midi_path)
    notes = []
    for inst in pm.instruments:
        if inst.is_drum:
            continue
        for n in inst.notes:
            notes.append(Note(n.start, n.end, n.pitch, n.velocity))
    notes.sort(key=lambda n: n.start)
    return notes

# ----------------------------------------------------------------------
# 3. BÚSQUEDA DE LA MEJOR TRANSPOSICIÓN
# ----------------------------------------------------------------------

def nearest_in_set(pitch: int, note_set: list[int]) -> tuple[int, int]:
    """Devuelve (nota_disponible_mas_cercana, costo_en_semitonos)."""
    best = min(note_set, key=lambda ns: abs(ns - pitch))
    return best, abs(best - pitch)


def best_transposition(notes: list[Note], note_set: list[int]) -> int:
    """Prueba cada desplazamiento de -12 a +12 semitonos y se queda con
    el que minimiza el costo total de mapear las notas al set real."""
    best_shift, best_cost = 0, float("inf")
    for shift in range(-12, 13):
        cost = 0
        for n in notes:
            _, c = nearest_in_set(n.pitch + shift, note_set)
            cost += c
        if cost < best_cost:
            best_cost, best_shift = cost, shift
    return best_shift

# ----------------------------------------------------------------------
# 4. MAPEO A NOTAS DISPONIBLES + CUANTIZACIÓN DE TIEMPO
# ----------------------------------------------------------------------

def map_and_quantize(notes: list[Note], shift: int) -> list[Note]:
    out = []
    for n in notes:
        mapped_pitch, _ = nearest_in_set(n.pitch + shift, NOTE_SET)
        q_start = round(n.start / TIME_RESOLUTION) * TIME_RESOLUTION
        q_end = max(q_start + TIME_RESOLUTION, round(n.end / TIME_RESOLUTION) * TIME_RESOLUTION)
        out.append(Note(q_start, q_end, mapped_pitch, n.velocity))
    return out

# ----------------------------------------------------------------------
# 5. REDUCCIÓN DE POLIFONÍA Y RESTRICCIÓN MECÁNICA
# ----------------------------------------------------------------------

def reduce_polyphony(notes: list[Note], max_poly: int) -> tuple[list[Note], list[tuple[Note, str]]]:
    """Devuelve (notas_finales, descartadas), donde 'descartadas' es una
    lista de (nota, motivo) para que puedas revisar qué se perdió."""
    from collections import defaultdict
    by_time = defaultdict(list)
    for n in notes:
        by_time[n.start].append(n)

    dropped: list[tuple[Note, str]] = []
    kept = []
    for t in sorted(by_time):
        group = by_time[t]
        if len(group) > max_poly:
            # Prioriza: nota más aguda (melodía) y las de mayor duración.
            group.sort(key=lambda n: (-n.pitch, -(n.end - n.start)))
            for n in group[max_poly:]:
                dropped.append((n, f"polifonía excedida en t={t:.2f}s ({len(group)} notas simultáneas, máx {max_poly})"))
            group = group[:max_poly]
        kept.extend(group)

    # Evita que el mismo pin se dispare dos veces demasiado rápido
    # (el mecanismo necesita tiempo para que la lengüeta vuelva a su sitio).
    kept.sort(key=lambda n: n.start)
    last_hit = {}
    final = []
    for n in kept:
        prev = last_hit.get(n.pitch, -999)
        if n.start - prev < MIN_REPEAT_GAP:
            gap = n.start - prev
            dropped.append((n, f"repique muy rápido: {gap:.3f}s desde el hit anterior de la misma nota (mínimo {MIN_REPEAT_GAP}s)"))
            continue  # se descarta el repique demasiado cercano
        last_hit[n.pitch] = n.start
        final.append(n)
    return final, dropped

# ----------------------------------------------------------------------
# 6. EXPORTACIÓN
# ----------------------------------------------------------------------

def get_downloads_folder() -> Path:
    """Devuelve la carpeta Downloads del usuario, funcionando igual en
    Windows, macOS y Linux. Si no existe (poco común), la crea."""
    downloads = Path.home() / "Downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    return downloads


def export_midi(notes: list[Note], path: str):
    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=0)  # 0 = piano acústico (General MIDI)
    for n in notes:
        inst.notes.append(pretty_midi.Note(n.velocity, n.pitch, n.start, n.end))
    pm.instruments.append(inst)
    pm.write(path)


def export_punch_csv(notes: list[Note], path: str):
    """Genera el listado de perforaciones: posición física en la tira
    (mm) y número de pin/carril (0-29) para cada nota."""
    pitch_to_track = {p: i for i, p in enumerate(NOTE_SET)}
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tiempo_s", "posicion_mm", "carril_0_29", "nota_midi", "nota_nombre"])
        for n in sorted(notes, key=lambda n: n.start):
            pos_mm = n.start * STRIP_SPEED_MM_PER_SEC
            w.writerow([
                f"{n.start:.3f}", f"{pos_mm:.2f}", pitch_to_track[n.pitch],
                n.pitch, PITCH_TO_NAME[n.pitch],
            ])

# ----------------------------------------------------------------------
# 7. PIPELINE COMPLETO
# ----------------------------------------------------------------------

def arrange_for_musicbox(midi_in: str, midi_out: str, csv_out: str):
    notes = load_notes(midi_in)
    shift = best_transposition(notes, NOTE_SET)
    mapped = map_and_quantize(notes, shift)
    final_notes, dropped = reduce_polyphony(mapped, MAX_POLYPHONY)
    export_midi(final_notes, midi_out)
    export_punch_csv(final_notes, csv_out)

    print(f"Transposición elegida: {shift:+d} semitonos")
    print(f"Notas originales: {len(notes)} -> notas en el arreglo final: {len(final_notes)}")
    if dropped:
        print(f"\n{len(dropped)} nota(s) descartada(s):")
        for n, motivo in dropped:
            nombre = PITCH_TO_NAME.get(n.pitch, "?")
            print(f"  - t={n.start:.2f}s, nota {nombre} ({n.pitch}): {motivo}")

    print(f"\nArchivos guardados en: {midi_out}")
    print(f"                        {csv_out}")
    return final_notes

if __name__ == "__main__":
    print("Ingrese el path hacia tu archivo MIDI")
    source = input().strip('"').strip()

    if not os.path.exists(source):
        print(f"Error: no se encontró el archivo '{source}'. Revisa la ruta e intenta de nuevo.")
    else:
        downloads = get_downloads_folder()
        stem = Path(source).stem  # nombre del archivo sin extensión, para nombrar la salida

        arrange_for_musicbox(
            source,
            str(downloads / f"{stem}_arreglo_30notas.mid"),
            str(downloads / f"{stem}_perforaciones.csv"),
        )