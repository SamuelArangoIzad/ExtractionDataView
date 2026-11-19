# Auditoría IA local — Revista PDF vs catálogo Excel

Prototipo ejecutable para Kali Linux con **arquitectura de tres capas**:

- **Presentación:** `src/auditoria/presentation/app.py` — Streamlit, interfaz web local.
- **Aplicación/dominio:** `src/auditoria/application/` y `domain/` — casos de uso, normalización, validación de GTIN, reglas de comparación.
- **Infraestructura:** `src/auditoria/infrastructure/` — PDF/OCR con PyMuPDF y Tesseract, lectura Excel/ODS y exportación XLSX.

## Preparación (Kali)

```bash
cd ~/Escritorio/Prueba-001
# Descomprime aquí el proyecto, conservando directorios src/, data/, scripts/
chmod +x scripts/*.sh
./scripts/instalar_kali.sh
./scripts/probar.sh
./scripts/iniciar.sh
```

Abrir en el mismo equipo: **http://127.0.0.1:8501**. Detener con **Ctrl+C**.

La aplicación **no requiere nube, cuentas, Docker ni claves de API**. La instalación requiere Internet para `apt` y `pip`; después funciona sin Internet. `--server.address 127.0.0.1` restringe el servicio a este equipo. No se altera UFW ni systemd.

## Primera demostración de mañana

1. Dejar activado **Utilizar archivos de prueba incluidos**.
2. Seleccionar `BASE_DATOS_PRUEBA` como catálogo.
3. Seleccionar `DEMO: transcripción revisable` y pulsar **Cargar transcripción**.
4. Editar cualquier precio, nombre o descuento de la tabla si se desea.
5. Pulsar **Comparar contra base de datos** y revisar las alertas.
6. Descargar `Reporte_Auditoria.xlsx`.
7. Abrir el modo **OCR: leer PDF real**, elegir página 14 y ajustar rotación hasta que la página quede horizontal y legible; ejecutar OCR. Revisar y completar los registros extraídos antes de compararlos.

## Archivos incluidos

- `data/Revista_Essentials.pdf`: revista escaneada de 20 páginas facilitada por el usuario.
- `data/Base_Datos_Demo.xlsx`: 36 registros transcritos visualmente y una tabla de pruebas con discrepancias deliberadas. **No es una base real ni datos validados comercialmente**.

## Formato de una base real

La primera fila debe tener encabezados. Columnas aceptadas: `EAN_TEXTO` o `EAN`, `PRODUCTO_BASE` o `PRODUCTO`, `MARCA`, `PRESENTACION`, `PRECIO_BASE_COP` o `PRECIO_COP`, `DESCUENTO_BASE_PCT` o `DESCUENTO`, opcional `SKU`. Los EAN deben almacenarse como **texto** (no numérico) para preservar ceros a la izquierda.

Importante: cuando se importe un archivo externo que no incluya `REVISTA_EXTRAIDA`, utiliza el modo OCR para obtener los candidatos desde PDF.

## Límites deliberados del MVP

- El OCR **no extrae de forma confiable automáticamente la asociación precio/descuento/producto** de revistas con varias columnas, fotos y páginas giradas. Obtiene candidatos de códigos visibles que necesitan validación humana.
- No se asume una correspondencia por similitud de nombre cuando el EAN no coincide.
- `SOLO_EN_BASE` puede significar que el producto no fue incluido en las páginas procesadas; no equivale necesariamente a error.
- Algunos códigos transcritos en la demostración pueden tener dígitos incorrectos. Se avisa cuando no pasan validación GTIN.
- La cifra de coincidencias no representa precisión OCR real. La demostración prueba el **motor de reglas**.
- La app no escribe en archivos maestros ni conecta con SQL. SQL puede añadirse mediante un repositorio de infraestructura sin cambiar la lógica de negocio.
- No guardar tokens o contraseñas en hojas del libro ni registrar información sensible en logs.

## Próximas mejoras para uso empresarial

1. Extraer tarjetas de producto mediante detección de regiones y visión multimodal, con evidencia por recorte y coordenadas.
2. Normalización por EAN confirmado, unidad de medida y vigencia promocional.
3. Generación de un reporte clasificado `confirmado / revisión / no localizado` con trazabilidad y validación humana.
4. Sustituir el lector Excel por conexión de **solo lectura** a SQL; nunca corregir la BD automáticamente.
5. Métricas de extracción y falsos positivos con un dataset etiquetado y pruebas de regresión.

## Vigencia promocional

La auditoría evalúa si el descuento **no ha vencido** usando la fecha actual de
Colombia. Devuelve `true` hasta el último día inclusive y `false` desde el día
siguiente. Las promociones futuras tienen booleano `true` y estado `FUTURA`.
Sin fechas fiables, el resultado queda vacío (`null`) con estado `REVISAR`.

En la tabla de revisión, complete `Vigencia texto` (ejemplo: `del 10 al 30 de
noviembre de 2026`) o ambas columnas `Vigencia inicio` y `Vigencia fin`, en formato
`AAAA-MM-DD` o `DD/MM/AAAA`. Las fechas completas prevalecen sobre el texto.
Si el texto no indica año, informe el **año de inicio de la edición** en la barra
lateral. No se presupone el año actual. Puede escribir una vigencia general
confirmada para las filas sin vigencia propia.

Excel admite las columnas opcionales `VIGENCIA`/`VIGENCIA_TEXTO`,
`VIGENCIA_INICIO`/`FECHA_INICIO` y `VIGENCIA_FIN`/`FECHA_FIN`.
El OCR todavía requiere transcribir/revisar la vigencia impresa. La demostración
incluida no contiene estas columnas; se recuperan cinco rangos de las observaciones
que empiezan por `Vigencia `, para los que debe confirmar el año de la edición.
Los demás registros quedan pendientes de revisión. El catálogo original no se modifica.

El informe exporta `VIGENCIA_NO_VENCIDA` como booleano Excel, además de estado,
fechas y fecha de evaluación. Es una instantánea: vuelva a comparar para actualizarla.
Las fechas de revista y base también se comparan cuando ambas están disponibles.

Consulte [el análisis del repositorio y la propuesta de extracción](docs/ANALISIS_Y_PROPUESTA.md)
para los hallazgos, la comparación entre LLM, parametrización y RAG, y el plan de evaluación.
