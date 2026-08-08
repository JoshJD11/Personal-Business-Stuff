#!/usr/bin/env python3
"""
CleanMusicSheet.py

Procesa TODAS las páginas de un PDF.

Deja únicamente:
- Los círculos (puntos) rellenos.
- El rectángulo (borde) que los contiene.

Elimina todo lo demás.

Mantiene el tamaño y posición de los elementos conservados.
Finalmente genera un único PDF con todas las páginas procesadas.

Uso:
    python3 CleanMusicSheet.py entrada.pdf salida.pdf

Ejemplo:
    python3 CleanMusicSheet.py original.pdf limpio.pdf
"""

import sys
import math
import pymupdf as fitz  # PyMuPDF


# ----------------------------------------------------------------------
# Parámetros ajustables
# ----------------------------------------------------------------------

MAX_CIRCLE_DIAMETER_RATIO = 0.08
ASPECT_RATIO_TOLERANCE = 0.15
MIN_CURVE_SEGMENTS = 4


# ----------------------------------------------------------------------
# Detectar círculos
# ----------------------------------------------------------------------

def is_circle(drawing, page_width):
    """True si el objeto vectorial es un círculo/punto relleno."""

    items = drawing.get("items", [])

    if not items:
        return False

    # Un círculo está formado solo por segmentos de curva
    if not all(it[0] == "c" for it in items):
        return False

    if len(items) < MIN_CURVE_SEGMENTS:
        return False

    r = drawing.get("rect")

    if not r or r.width == 0 or r.height == 0:
        return False

    aspect = r.width / r.height

    if abs(aspect - 1) > ASPECT_RATIO_TOLERANCE:
        return False

    if r.width > page_width * MAX_CIRCLE_DIAMETER_RATIO:
        return False

    return True


# ----------------------------------------------------------------------
# Detectar rectángulo contenedor
# ----------------------------------------------------------------------

def is_container_rect(drawing):
    """True si el objeto es un rectángulo dibujado solo con trazo."""

    if drawing.get("type") != "s":
        return False

    items = drawing.get("items", [])

    return len(items) == 1 and items[0][0] == "re"


# ----------------------------------------------------------------------
# Dibujar una página procesada
# ----------------------------------------------------------------------

def _draw_page(
    out,
    page_w,
    page_h,
    container,
    circles
):
    """
    Crea una nueva página y dibuja únicamente:
    - el rectángulo contenedor
    - los círculos

    No escala ni desplaza los elementos.
    """

    new_page = out.new_page(
        width=page_w,
        height=page_h
    )

    shape = new_page.new_shape()

    # --------------------------------------------------------------
    # Dibujar rectángulo
    # --------------------------------------------------------------

    if container:

        r = container["rect"]

        shape.draw_rect(
            fitz.Rect(
                r.x0,
                r.y0,
                r.x1,
                r.y1
            )
        )

        shape.finish(
            color=container.get("color") or (0, 0, 0),
            width=container.get("width") or 1,
            fill=None,
        )

    # --------------------------------------------------------------
    # Dibujar círculos
    # --------------------------------------------------------------

    for c in circles:

        r = c["rect"]

        radius = r.width / 2

        cx = (r.x0 + r.x1) / 2
        cy = (r.y0 + r.y1) / 2

        # No dibujar círculos completamente fuera
        if (
            cy + radius < 0
            or cy - radius > page_h
        ):
            continue

        shape.draw_circle(
            (cx, cy),
            radius
        )

        shape.finish(
            color=c.get("color") or (0, 0, 0),
            fill=c.get("fill"),
            width=c.get("width") or 0,
        )

    shape.commit()


# ----------------------------------------------------------------------
# Procesar PDF COMPLETO
# ----------------------------------------------------------------------

def limpiar_pdf(input_path, output_path, mode="crop"):

    """
    Procesa TODAS las páginas del PDF.

    mode="crop":
        Mantiene exactamente el tamaño de cada página original.
        Todo lo que esté fuera de los límites de la página se ignora.

    mode="split":
        Si una página tiene contenido que se extiende verticalmente
        más allá de su tamaño declarado, genera varias hojas.

    mode="fit_all":
        Genera una página suficientemente grande para contener
        todo el contenido de cada página.
    """

    src = fitz.open(input_path)

    if len(src) == 0:
        print("Error: el PDF no contiene páginas.")
        src.close()
        return

    out = fitz.open()

    total_circles = 0
    total_rects = 0

    # ==============================================================
    # PROCESAR CADA PÁGINA
    # ==============================================================

    for page_number, page in enumerate(src, start=1):

        print()
        print("=" * 60)
        print(f"Procesando página {page_number} de {len(src)}")
        print("=" * 60)

        drawings = page.get_drawings()

        # ----------------------------------------------------------
        # Buscar círculos
        # ----------------------------------------------------------

        circles = [
            d
            for d in drawings
            if is_circle(
                d,
                page.rect.width
            )
        ]

        # ----------------------------------------------------------
        # Buscar rectángulos
        # ----------------------------------------------------------

        rects = [
            d
            for d in drawings
            if is_container_rect(d)
        ]

        # Tomamos el rectángulo más grande
        container = (
            max(
                rects,
                key=lambda d:
                    d["rect"].width *
                    d["rect"].height
            )
            if rects
            else None
        )

        # ----------------------------------------------------------
        # Avisos
        # ----------------------------------------------------------

        if not circles:

            print(
                "Aviso: no se detectaron círculos "
                "en esta página."
            )

        if not container:

            print(
                "Aviso: no se detectó un rectángulo "
                "contenedor en esta página."
            )

        print(
            f"Círculos detectados: {len(circles)}"
        )

        print(
            f"Rectángulos detectados: {len(rects)}"
        )

        # ----------------------------------------------------------
        # Tamaño original
        # ----------------------------------------------------------

        page_w = page.rect.width
        page_h = page.rect.height

        print(
            f"Tamaño de página: "
            f"{page_w / 72:.2f} x "
            f"{page_h / 72:.2f} pulgadas"
        )

        # ----------------------------------------------------------
        # Detectar contenido que sobresale
        # ----------------------------------------------------------

        x0 = float("inf")
        y0 = float("inf")

        x1 = float("-inf")
        y1 = float("-inf")

        for d in drawings:

            r = d["rect"]

            x0 = min(x0, r.x0)
            y0 = min(y0, r.y0)

            x1 = max(x1, r.x1)
            y1 = max(y1, r.y1)

        if y1 > page_h + 1:

            print(
                f"Aviso: el contenido real de esta página "
                f"llega hasta {y1 / 72:.2f} pulgadas."
            )

            print(
                f"La página declarada tiene "
                f"{page_h / 72:.2f} pulgadas de alto."
            )

        # ==========================================================
        # MODE CROP
        # ==========================================================

        if mode == "crop":

            descartados = [
                c
                for c in circles
                if (
                    c["rect"].y0 +
                    c["rect"].y1
                ) / 2 > page_h
            ]

            circles_visibles = [
                c
                for c in circles
                if c not in descartados
            ]

            print(
                f"Creando página "
                f"{page_number} con tamaño original."
            )

            if descartados:

                print(
                    f"Círculos fuera de la página: "
                    f"{len(descartados)}"
                )

            _draw_page(
                out,
                page_w,
                page_h,
                container,
                circles_visibles
            )

            total_circles += len(circles_visibles)

        # ==========================================================
        # MODE SPLIT
        # ==========================================================

        elif mode == "split":

            n_pages = max(
                1,
                math.ceil(y1 / page_h)
            )

            print(
                f"Esta página necesita "
                f"{n_pages} hoja(s)."
            )

            for i in range(n_pages):

                y_offset = i * page_h

                # Crear una página temporal
                new_page = out.new_page(
                    width=page_w,
                    height=page_h
                )

                shape = new_page.new_shape()

                # --------------------------------------------------
                # Rectángulo
                # --------------------------------------------------

                if container:

                    r = container["rect"]

                    shifted = fitz.Rect(
                        r.x0,
                        r.y0 - y_offset,
                        r.x1,
                        r.y1 - y_offset
                    )

                    shape.draw_rect(shifted)

                    shape.finish(
                        color=container.get("color")
                        or (0, 0, 0),
                        width=container.get("width")
                        or 1,
                        fill=None,
                    )

                # --------------------------------------------------
                # Círculos
                # --------------------------------------------------

                for c in circles:

                    r = c["rect"]

                    radius = r.width / 2

                    cx = (
                        r.x0 +
                        r.x1
                    ) / 2

                    cy = (
                        r.y0 +
                        r.y1
                    ) / 2 - y_offset

                    if (
                        cy + radius < 0
                        or cy - radius > page_h
                    ):
                        continue

                    shape.draw_circle(
                        (cx, cy),
                        radius
                    )

                    shape.finish(
                        color=c.get("color")
                        or (0, 0, 0),
                        fill=c.get("fill"),
                        width=c.get("width") or 0,
                    )

                shape.commit()

            total_circles += len(circles)

        # ==========================================================
        # MODE FIT_ALL
        # ==========================================================

        elif mode == "fit_all":

            full_h = max(
                page_h,
                y1
            )

            print(
                f"Creando página larga de "
                f"{page_w / 72:.2f} x "
                f"{full_h / 72:.2f} pulgadas."
            )

            _draw_page(
                out,
                page_w,
                full_h,
                container,
                circles
            )

            total_circles += len(circles)

        else:

            src.close()
            out.close()

            raise ValueError(
                f"mode desconocido: {mode!r}. "
                f"Usa 'crop', 'split' o 'fit_all'."
            )

        if container:
            total_rects += 1

    # ==============================================================
    # GUARDAR PDF FINAL
    # ==============================================================

    out.save(
        output_path,
        garbage=4,
        deflate=True
    )

    out.close()
    src.close()

    print()
    print("=" * 60)
    print("PROCESO TERMINADO")
    print("=" * 60)

    print(
        f"Páginas originales: {len(src) if False else 'procesadas'}"
    )

    print(
        f"Círculos conservados: {total_circles}"
    )

    print(
        f"Rectángulos encontrados: {total_rects}"
    )

    print(
        f"PDF final: {output_path}"
    )


# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------

if __name__ == "__main__":

    if len(sys.argv) < 3:

        print(
            "Uso:"
        )

        print(
            "python3 CleanMusicSheet.py "
            "entrada.pdf salida.pdf"
        )

        sys.exit(1)

    input_pdf = sys.argv[1]
    output_pdf = sys.argv[2]

    limpiar_pdf(
        input_pdf,
        output_pdf,
        mode="crop"
    )