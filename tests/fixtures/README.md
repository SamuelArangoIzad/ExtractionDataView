# Lecturas OCR de regresión

`layout_ocr.json` contiene palabras y coordenadas obtenidas con el OCR de Windows
en las páginas 4, 5, 8, 9, 10, 11, 12 y 15 de `data/Revista_Essentials.pdf`,
renderizadas a 180 dpi (máximo 2200 píxeles). Incluye las cuatro orientaciones y
las pasadas de contraste en la orientación elegida. El texto mantiene los errores
del motor; no es una transcripción de referencia ni una medida de precisión OCR.

Los tests usan estas lecturas para reproducir fallos de segmentación sin requerir
Windows ni Tesseract. Cambios de versión, idioma o motor pueden producir otras
lecturas. Los conteos de tarjetas y zonas de evidencia se contrastaron visualmente
con las páginas originales. Las cifras grandes de Glucerna y Bebé y mamá siguen
sin una lectura numérica fiable: solo se comprueba que la evidencia queda visible.
