# Evaluación del proyecto de auditoría de revistas

> Actualización: ya se implementaron reglas configurables, validación de vacíos,
> descuentos decimales, equivalencias simples de unidades y un índice de consulta
> exacta por EAN. Consulte el README para la configuración y pruebas manuales.
> Los hallazgos siguientes describen el diagnóstico inicial; los puntos sobre
> truncamiento de descuentos y omisión de campos vacíos quedaron corregidos.
> Por defecto, ahora un dígito verificador inválido bloquea la comparación de campos;
> se puede permitir expresamente la comparación manteniendo su alerta.
> La interfaz DEMO también fue adaptada a fichas de producto y tablas HTML para
> no cargar las DLL de pandas/Arrow bloqueadas por Windows. El flujo de interfaz
> ya pasó las pruebas automatizadas; el bloqueo de la interfaz descrito más abajo
> corresponde al estado anterior a esta corrección. Suite actual: 46 pruebas.

## Alcance revisado

Revisión del código fuente completo, pruebas, README, configuración de empaquetado,
scripts de instalación/ejecución y archivos de demostración. Los `.pyc` son cachés
compiladas y `egg-info` es metadato generado: no constituyen otra implementación.
El repositorio también versiona un archivo de bloqueo de LibreOffice; conviene
retirar estos artefactos generados en una limpieza posterior.

El PDF incluido tiene 20 páginas sin texto extraíble. El libro tiene hojas GUIA,
REVISTA_EXTRAIDA, BASE_DATOS_PRUEBA, COMPARACION, NO_EN_BASE, CASOS_PRUEBA y
ODS_ORIGINAL. La entrada del sistema usa REVISTA_EXTRAIDA en modo DEMO y la hoja
seleccionada como catálogo; no recalcula ni utiliza las fórmulas de COMPARACION
como motor de auditoría. La demostración no contiene columnas de vigencia, pero
cinco registros tienen rangos explícitos en OBSERVACIONES y otros seis mencionan
días específicos sin detallarlos. El lector ahora recupera las notas que comienzan
por `Vigencia `; el año sigue requiriendo confirmación. Las notas imprecisas no se
convierten automáticamente en fechas.

La revisión visual general de las 20 páginas confirma orientaciones mezcladas,
anuncios y tarjetas con varios productos. En la página PDF 15 se ven vigencias
distintas en tarjetas de la misma página (1–15 y 16–30 de noviembre), por lo que
una única fecha por página no sería suficiente. Esta inspección no equivale a
una transcripción exhaustiva ni certifica todos los datos comerciales del PDF.

## Cómo funciona actualmente

1. Streamlit carga PDF y Excel/ODS. El usuario selecciona hoja, páginas y rotación.
2. DEMO lee una transcripción del Excel. OCR rasteriza las páginas a 160 dpi,
   aumenta contraste y ejecuta Tesseract con segmentación dispersa (`--psm 11`).
3. El OCR busca secuencias numéricas y concatena hasta tres palabras próximas
   verticalmente. Produce EAN candidatos y texto vecino en observaciones.
   No construye tarjetas con nombre, marca, presentación, precio y descuento.
4. El usuario revisa/edita los valores. El servicio carga el catálogo completo.
5. El dominio indexa los productos en memoria por EAN normalizado y compara
   coincidencias exactas. Avisa sobre GTIN inválidos, duplicados y ausencias.
6. El reporte exporta diferencias, revista, catálogo y advertencias. No cambia
   la base original ni consulta SQL.

## Hallazgos que afectan la precisión

- La asociación espacial es el problema principal: el texto vecino puede mezclar
  tarjetas de columnas distintas. Concatenar números sin verificar separación
  horizontal también puede generar candidatos falsos.
- La expresión OCR acepta longitudes de 8 a 14; el dominio solo admite 8, 12, 13
  y 14. El dígito de control detecta algunos errores, pero no demuestra que el
  código esté asociado al producto correcto.
- Los campos de marca estaban almacenados sin compararse. Se añadió esa comparación.
- Nombre y presentación vacíos en una de las fuentes pueden omitir comprobaciones.
  La similitud textual del nombre no valida equivalencias comerciales de unidades.
- `_number` convierte descuentos a entero; descuentos fraccionarios y formatos
  locales de dinero requieren una normalización separada en una próxima mejora.
- Un EAN con dígito verificador inválido todavía puede compararse por coincidencia
  exacta, acompañado de una alerta. Esos resultados necesitan revisión.
- `SOLO_EN_BASE` mide cobertura de las páginas procesadas, no necesariamente un error.
- La confianza OCR es la etiqueta fija `REVISAR`; no es una probabilidad calibrada.
- No hay dataset independiente etiquetado ni medición de precisión/recobrado del
  OCR. Las pruebas del motor no permiten afirmar una precisión de extracción.

## Elección: visión/OCR por regiones + parametrización + consulta exacta

| Opción | Utilidad | Límite en este proyecto |
| --- | --- | --- |
| LLM multimodal sobre toda la revista | Comprende diseño y textos variables | Puede omitir productos, mezclar precios o inventar campos; una llamada grande dificulta trazabilidad y repetición |
| Parametrización | Reglas de formato, tolerancias, fechas, unidades, esquemas y validación EAN | Coordenadas rígidas fallan cuando cambia la maquetación; regex no resuelve sola la asociación visual |
| RAG | Recuperar documentación o proponer candidatos cuando falta un identificador | No extrae por sí mismo las tarjetas del PDF ni garantiza igualdad de códigos, precios o fechas |

Recomendación técnica, pendiente de validación experimental: recorrer **todas las
páginas**, detectar regiones de producto y procesar cada región con OCR y, cuando
sea necesario, un modelo multimodal. Conservar página, coordenadas, recorte y texto
original para cada campo. Mantener un esquema de salida fijo con valores nulos
cuando no existe evidencia y reglas deterministas para verificar el resultado.
La parametrización se refiere aquí a configuración y reglas, no a entrenar un LLM.
No hay aún datos suficientes para recomendar fine-tuning.

El extractor debe trabajar con la evidencia del PDF de forma independiente del
catálogo: darle el precio esperado antes de leerlo puede ocultar justamente el error
que se quiere detectar. Después, consultar Excel/SQL por EAN exacto. Una búsqueda
semántica puede proponer candidatos para revisión humana si falta EAN, pero no
confirmar automáticamente la identidad. No hace falta una base vectorial para
consultar los EAN del catálogo actual.

Las vigencias generales requieren ámbito explícito (revista/página/producto).
Las excepciones por tarjeta deben prevalecer. No propagar automáticamente una
fecha cercana a todos los productos de una página.

### Cómo comprobar qué alternativa funciona mejor

Etiquetar manualmente revistas representativas, incluyendo páginas rotadas,
varias columnas, ofertas múltiples, EAN ilegibles, vigencias generales y excepciones.
Separar revistas completas para desarrollo y evaluación, evitando repartir páginas
de la misma revista entre ambos conjuntos. Comparar OCR actual, OCR por regiones y
visión multimodal por regiones sobre el mismo conjunto reservado.

Medir: cobertura de productos, exactitud por campo, asociación producto-precio,
EAN exacto, rangos de fecha exactos, precisión y recobrado de alertas reales,
falsos negativos, porcentaje que requiere revisión, costo y tiempo por página.
Publicar resultados por tipo de diseño y dificultad, además del promedio.
Fijar con el negocio los umbrales de aceptación antes de elegir una alternativa.
La transcripción de demostración sirve para probar reglas, no para certificar OCR.

Referencias primarias consultadas:
- [Tesseract: calidad, rotación y segmentación](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html).
- [Microsoft: alcance de RAG y recuperación](https://learn.microsoft.com/en-us/azure/foundry/concepts/retrieval-augmented-generation).

## Cambio implementado: vigencia

`domain/validity.py` concentra el cálculo, independiente de OCR y Streamlit.
El booleano `not_expired`, presentado como `VIGENCIA_NO_VENCIDA`, sigue literalmente
la regla solicitada: `fecha_evaluacion <= fecha_fin`. El último día está incluido.
Una oferta futura devuelve true y estado FUTURA; no significa que el descuento
ya se pueda aplicar. Para esa otra pregunta se necesitaría comprobar también el inicio.

| Información disponible | Booleano | Estado |
| --- | --- | --- |
| Fecha actual posterior al fin | false | VENCIDA |
| Fecha actual dentro del rango | true | VIGENTE |
| Fecha actual anterior al inicio | true | FUTURA |
| Fecha ausente, ambigua, inválida o rango invertido | null | REVISAR |

Se usa la fecha de Colombia (UTC-5) al comparar, con fecha inyectable en pruebas.
No se depende de la zona horaria local del servidor. Un reporte descargado es una
instantánea con su fecha de evaluación; hay que volver a comparar para actualizarlo.
La interfaz impide descargar la comparación del día anterior al volver a ejecutarse.

Entradas: fechas completas ISO o DD/MM/AAAA, fechas nativas de Excel, o texto como
`del 10 al 30 de noviembre de 2026`. El rango sin año requiere el año de inicio de
la edición, informado explícitamente. No se infiere del reloj. Un rango diciembre–enero
sin años usa ese año inicial y el siguiente para el fin. Fechas completas confirmadas
prevalecen sobre el texto original; si se completa solo una, se solicita revisión.

El Excel acepta `VIGENCIA`/`VIGENCIA_TEXTO`, `VIGENCIA_INICIO`/`FECHA_INICIO` y
`VIGENCIA_FIN`/`FECHA_FIN`; también recupera notas que empiezan por `Vigencia `
si no existe columna de texto de vigencia. En la interfaz se puede transcribir una vigencia general
confirmada que solo se aplica a filas sin texto ni fechas. Los valores particulares
de cada producto prevalecen. No se hereda la vigencia desde el catálogo para rellenar
la revista: eso impediría detectar discrepancias entre ambas fuentes.

La auditoría alerta por vigencias vencidas o no interpretables incluso sin EAN válido.
Cuando ambas fuentes tienen rangos interpretables, compara inicio y fin. Si el
catálogo no contiene fechas, no es posible comprobar su igualdad con la revista,
pero sí evaluar el vencimiento del rango publicado. El reporte incluye booleanos
Excel reales, estado, fechas, fecha de evaluación y motivo de revisión.

**Límite conservado:** el OCR actual no extrae/asocia automáticamente vigencias.
Se deben transcribir o importar junto a los registros. No se incorporó un servicio
LLM ni RAG: esta entrega evalúa esas opciones y añade la regla temporal verificable.

## Verificación

La suite de 17 pruebas cubre las reglas originales, el día final inclusivo, ofertas
futuras, vencimiento, cambio de año, años bisiestos, fechas inválidas/incompletas,
año omitido, reloj actualizado, comparación de marca/fechas, notas de la demo y
exportación/relectura de booleanos XLSX. Ejecución: `python -m unittest discover -s
tests -v` con `PYTHONPATH=src` y las dependencias de `requirements.txt` instaladas.

Integración con el libro incluido: 36 productos de revista, 35 de catálogo y
reporte XLSX generado correctamente. Con fecha de evaluación 2026-11-19 y año de
edición 2026 confirmado para la prueba: 2 vigencias vencidas, 3 no vencidas y 31
pendientes de revisión. Esto no confirma por sí mismo el año real impreso.

La comprobación de la interfaz completa en este equipo quedó limitada por un
`ImportError` de pandas: Windows Control de aplicaciones bloqueó una DLL (`fields`).
No se eludió esa política. Tampoco se validó una ejecución OCR integral: el ejecutable
Tesseract no está disponible en PATH. Los resultados anteriores corresponden al
dominio, lector Excel y exportador, no a una certificación de la interfaz o del OCR.
