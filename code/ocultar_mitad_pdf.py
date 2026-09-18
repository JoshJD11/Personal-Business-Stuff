import os
import sys

try:
    import fitz  # PyMuPDF
except ImportError:
    print("Error: Se requiere la biblioteca PyMuPDF.")
    print("Instálala ejecutando: pip install pymupdf")
    sys.exit(1)

def ocultar_mitad_pdf(input_path, output_path, posicion="abajo", color=(1, 1, 1)):
    """
    Oculta la mitad del contenido de un PDF dibujando un rectángulo sólido.
    Mantiene el tamaño de la hoja original intacto.
    
    :param input_path: Ruta del PDF original.
    :param output_path: Ruta donde se guardará el PDF modificado.
    :param posicion: 'arriba', 'abajo', 'izquierda' o 'derecha'.
    :param color: Tupla RGB (0-1) para el color del recuadro. (1, 1, 1) es blanco.
    """
    try:
        # Abrir el documento
        doc = fitz.open(input_path)
        
        for pagina in doc:
            # Obtener las dimensiones de la página (ancho y alto)
            rect = pagina.rect
            ancho = rect.width
            alto = rect.height
            
            # Definir las coordenadas del rectángulo a tapar según la posición
            if posicion == "abajo":
                # Desde la mitad de la altura hasta el fondo
                rect_tapar = fitz.Rect(0, alto / 2, ancho, alto)
            elif posicion == "arriba":
                # Desde el tope hasta la mitad de la altura
                rect_tapar = fitz.Rect(0, 0, ancho, alto / 2)
            elif posicion == "izquierda":
                # Desde el borde izquierdo hasta la mitad del ancho
                rect_tapar = fitz.Rect(0, 0, ancho / 2, alto)
            elif posicion == "derecha":
                # Desde la mitad del ancho hasta el borde derecho
                rect_tapar = fitz.Rect(ancho / 2, 0, ancho, alto)
            else:
                print(f"Posición '{posicion}' no válida. Usa: arriba, abajo, izquierda o derecha.")
                return

            # Dibujar el rectángulo blanco sobre el contenido
            # fill=color llena el rectángulo, keep_proportion=False evita deformaciones
            pagina.draw_rect(rect_tapar, color=color, fill=color, overlay=True)
            
            # OPCIONAL: Eliminar u ocultar texto real en esa zona para que no sea seleccionable
            # pagina.add_redact_annot(rect_tapar)
            # pagina.apply_redactions()

        # Guardar el resultado
        doc.save(output_path)
        doc.close()
        print(f"¡Éxito! Archivo guardado en: {output_path}")
        
    except Exception as e:
        print(f"Ocurrió un error: {e}")

if __name__ == "__main__":
    # Configuración de prueba
    archivo_entrada = "documento_original.pdf"
    archivo_salida = "documento_modificado.pdf"
    
    print("--- CÓDIGO DE EJEMPLO ---")
    print(f"Este script modificará '{archivo_entrada}' ocultando su mitad inferior.")
    print("Asegúrate de cambiar los nombres de los archivos en el código por los tuyos.")
