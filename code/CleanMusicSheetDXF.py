#!/usr/bin/env python3
"""
CleanMusicSheetDXF.py

Procesa TODAS las páginas de un PDF.

Conserva únicamente:
- Los círculos/puntos.
- El rectángulo contenedor.

Genera:
1. Un PDF limpio con todas las páginas.
2. Un archivo DXF independiente por cada página.

Los DXF utilizan milímetros y conservan las posiciones
y dimensiones originales de los elementos.

Uso:

    python3 CleanMusicSheetDXF.py entrada.pdf salida.pdf

Ejemplo:

    python3 CleanMusicSheetDXF.py original.pdf limpio.pdf

Esto generará:

    limpio.pdf

    limpio_dxf/
        pagina_01.dxf
        pagina_02.dxf
        pagina_03.dxf
        ...
"""


import sys
import math
import os

import pymupdf as fitz
import ezdxf


# ======================================================================
# PARÁMETROS
# ======================================================================

MAX_CIRCLE_DIAMETER_RATIO = 0.08

ASPECT_RATIO_TOLERANCE = 0.15

MIN_CURVE_SEGMENTS = 4

# Conversión PDF points -> milímetros
PT_TO_MM = 25.4 / 72.0


# ======================================================================
# DETECTAR CÍRCULOS
# ======================================================================

def is_circle(drawing, page_width):
    items = drawing.get("items", [])

    if not items:
        return False

    if not all(item[0] == "c" for item in items):
        return False

    if len(items) < MIN_CURVE_SEGMENTS:
        return False

    rect = drawing.get("rect")

    if not rect:
        return False

    if rect.width <= 0 or rect.height <= 0:
        return False

    aspect = rect.width / rect.height

    if abs(aspect - 1) > ASPECT_RATIO_TOLERANCE:
        return False

    if rect.width > page_width * MAX_CIRCLE_DIAMETER_RATIO:
        return False

    return True


# ======================================================================
# RECORTAR RECTÁNGULO AL TAMAÑO DE PÁGINA (modo "crop")
# ======================================================================

def clip_container_to_page(container, page_width, page_height):
    """
    Devuelve una copia del rectángulo contenedor recortada a los
    límites de la página (0..page_width, 0..page_height).

    Esto es necesario porque, a diferencia de un PDF (donde el visor
    recorta automáticamente lo que se sale de la página al mostrarla),
    el formato DXF NO tiene concepto de "página": si el rectángulo
    original mide más que la página, en el DXF quedaría dibujado
    completo, inflando el tamaño total del diseño y haciendo que
    Silisouette Studio (u otro software) lo escale hacia abajo para
    que quepa en el área de trabajo -- encogiendo también los círculos.

    Por eso, en modo "crop", el recorte debe aplicarse a los datos
    ANTES de dibujar, tanto para el PDF como para el DXF.
    """
    if not container:
        return None

    rect = container["rect"]

    clipped_rect = fitz.Rect(
        max(rect.x0, 0),
        max(rect.y0, 0),
        min(rect.x1, page_width),
        min(rect.y1, page_height),
    )

    clipped = dict(container)
    clipped["rect"] = clipped_rect
    return clipped


def clip_circles_to_page(circles, page_height):
    """
    Descarta los círculos cuyo centro cae fuera del alto de página.
    (Los círculos de este diseño no suelen quedar cortados a la mitad,
    así que basta con revisar el centro.)
    """
    visibles = []
    for c in circles:
        r = c["rect"]
        cy = (r.y0 + r.y1) / 2.0
        if 0 <= cy <= page_height:
            visibles.append(c)
    return visibles


# ======================================================================
# DETECTAR RECTÁNGULO CONTENEDOR
# ======================================================================

def is_container_rect(drawing):
    if drawing.get("type") != "s":
        return False

    items = drawing.get("items", [])

    return (
        len(items) == 1
        and items[0][0] == "re"
    )


# ======================================================================
# DIBUJAR PÁGINA EN PDF
# ======================================================================

def draw_pdf_page(
    output_pdf,
    page_width,
    page_height,
    container,
    circles
):
    new_page = output_pdf.new_page(
        width=page_width,
        height=page_height
    )

    shape = new_page.new_shape()

    if container:

        rect = container["rect"]

        shape.draw_rect(
            fitz.Rect(
                rect.x0,
                rect.y0,
                rect.x1,
                rect.y1
            )
        )

        shape.finish(
            color=container.get("color") or (0, 0, 0),
            width=container.get("width") or 1,
            fill=None
        )

    for circle in circles:

        rect = circle["rect"]

        radius = rect.width / 2.0

        cx = (
            rect.x0 +
            rect.x1
        ) / 2.0

        cy = (
            rect.y0 +
            rect.y1
        ) / 2.0

        shape.draw_circle(
            (cx, cy),
            radius
        )

        shape.finish(
            color=circle.get("color") or (0, 0, 0),
            fill=circle.get("fill"),
            width=circle.get("width") or 0
        )

    shape.commit()


# ======================================================================
# CREAR DXF DE UNA PÁGINA
# ======================================================================

def create_dxf(
    dxf_path,
    page_width,
    page_height,
    container,
    circles
):
    doc = ezdxf.new("R2010")

    doc.units = ezdxf.units.MM

    msp = doc.modelspace()

    page_width_mm = page_width * PT_TO_MM
    page_height_mm = page_height * PT_TO_MM

    if container:

        rect = container["rect"]

        x0 = rect.x0 * PT_TO_MM
        x1 = rect.x1 * PT_TO_MM

        y0 = page_height_mm - rect.y1 * PT_TO_MM
        y1 = page_height_mm - rect.y0 * PT_TO_MM

        msp.add_line(
            (x0, y0),
            (x1, y0)
        )

        msp.add_line(
            (x1, y0),
            (x1, y1)
        )

        msp.add_line(
            (x1, y1),
            (x0, y1)
        )

        msp.add_line(
            (x0, y1),
            (x0, y0)
        )

    for circle in circles:

        rect = circle["rect"]

        cx_pt = (
            rect.x0 +
            rect.x1
        ) / 2.0

        cy_pt = (
            rect.y0 +
            rect.y1
        ) / 2.0

        cx = cx_pt * PT_TO_MM

        cy = (
            page_height_mm -
            cy_pt * PT_TO_MM
        )

        radius = (
            rect.width / 2.0
        ) * PT_TO_MM

        msp.add_circle(
            (cx, cy),
            radius
        )

    doc.saveas(dxf_path)


# ======================================================================
# PROCESAR PDF
# ======================================================================

def limpiar_pdf(
    input_path,
    output_path,
    mode="crop"
):

    src = fitz.open(input_path)

    if len(src) == 0:
        print("Error: el PDF no contiene páginas.")
        src.close()
        return

    output_pdf = fitz.open()

    base_name = os.path.splitext(output_path)[0]
    dxf_directory = base_name + "_dxf"
    os.makedirs(dxf_directory, exist_ok=True)

    total_circles = 0
    total_rectangles = 0
    original_pages = len(src)

    for page_index, page in enumerate(src, start=1):

        drawings = page.get_drawings()
        page_width = page.rect.width
        page_height = page.rect.height

        circles = [d for d in drawings if is_circle(d, page_width)]
        rectangles = [d for d in drawings if is_container_rect(d)]
        container = max(rectangles, key=lambda d: d["rect"].width * d["rect"].height) if rectangles else None

        x0 = float("inf"); y0 = float("inf")
        x1 = float("-inf"); y1 = float("-inf")
        for drawing in drawings:
            rect = drawing["rect"]
            x0 = min(x0, rect.x0); y0 = min(y0, rect.y0)
            x1 = max(x1, rect.x1); y1 = max(y1, rect.y1)

        if mode == "crop":
            # Recortar el rectángulo y descartar círculos fuera de
            # la página ANTES de dibujar, para que el PDF y el DXF
            # queden consistentes (ver clip_container_to_page).
            container_crop = clip_container_to_page(container, page_width, page_height)
            circles_crop = clip_circles_to_page(circles, page_height)

            descartados = len(circles) - len(circles_crop)
            if descartados:
                print(f"  Aviso: {descartados} circulo(s) fuera de la pagina, descartados.")

            draw_pdf_page(output_pdf, page_width, page_height, container_crop, circles_crop)
            dxf_path = os.path.join(dxf_directory, f"pagina_{page_index:02d}.dxf")
            create_dxf(dxf_path, page_width, page_height, container_crop, circles_crop)
            total_circles += len(circles_crop)
            if container_crop:
                total_rectangles += 1
        else:
            raise ValueError(f"Modo desconocido para esta prueba: {mode!r}")

    output_pdf.save(output_path, garbage=4, deflate=True)
    output_pdf.close()
    src.close()

    print(f"Circulos: {total_circles}, Rectangulos: {total_rectangles}, dxf dir: {dxf_directory}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python3 CleanMusicSheetDXF.py entrada.pdf salida.pdf")
        sys.exit(1)
    limpiar_pdf(sys.argv[1], sys.argv[2], mode="crop")