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
4. Seleccionar un producto en **Producto a revisar** y editar precio, nombre o descuento si se desea.
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

En la ficha de revisión del producto, complete `Vigencia texto` (ejemplo: `del 10 al 30 de
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

## Reglas parametrizadas y consulta exacta por EAN

En la barra lateral, **Reglas de comparación** permite seleccionar campos,
tolerancia de descuento (puntos porcentuales), similitud mínima del nombre,
normalización de marca, equivalencias de unidades, alertas de campos vacíos y
exigencia de dígito verificador válido. La tolerancia de precio sigue en COP.
Las tolerancias son inclusivas: una diferencia igual al límite se acepta.

La consulta carga la hoja seleccionada de Excel e indexa sus filas por EAN.
Solo elimina espacios y el sufijo numérico `.0`; conserva los ceros iniciales.
Nunca sustituye el EAN por una coincidencia de nombre. Si no existe, informa
`NO_EN_BASE`; si hay varias filas, `EAN_DUPLICADO_BASE`, sin elegir una arbitrariamente.
Por defecto un GTIN con dígito verificador inválido impide comparar sus campos.
Puede desactivar esa exigencia para revisar transcripciones, manteniendo la alerta
`REVISAR_EAN`. Los códigos de longitud/formato incorrectos siempre se detienen.

Reglas por campo:

- **Nombre:** similitud textual configurable de 0 a 1. Con 1 se exige igualdad del
  texto normalizado. Las cantidades distintas siempre generan diferencia, incluso
  si el texto es muy similar; la semejanza nunca se usa para buscar otro producto.
- **Marca:** comparación normalizada (mayúsculas/tildes) o estricta.
- **Presentación:** equivalencias de una cantidad simple, por ejemplo `100 ml` =
  `100 mililitros` = `0,1 litros`, y `1 kg` = `1000 g`. Unidades, tabletas y cápsulas
  son categorías distintas. No se infieren equivalencias de packs, obsequios ni
  concentraciones; `2 x 50 ml` no equivale automáticamente a `100 ml`.
- **Precio y descuento:** se conservan decimales, se comparan con sus tolerancias
  y se señalan valores inválidos, precios negativos y descuentos fuera de 0–100.
  Los importes en texto usan formato COP (`15.000`, `$ 15.000,50`) o decimal sin
  agrupación (`15000.50`). Un formato ambiguo/no admitido se envía a revisión.
  Descuento siempre en **puntos porcentuales**: `12.5`, `12,5%` o `12,5` = 12.5%.
  Una celda numérica Excel con valor subyacente `0.125` se interpreta como 0.125
  puntos, aunque Excel la muestre como 12.5%; conviértala a 12.5 antes de importar.
- **Vacíos:** `REVISAR_CAMPO_FALTANTE` en los campos seleccionados, incluso si
  faltan en ambas fuentes. Para descuento desconocido no se asume 0; escriba 0
  cuando se confirme que no hay descuento. Desactivar estas alertas no convierte
  un dato ausente en coincidencia, y no oculta datos numéricos inválidos.
- **Vigencia:** conserva la regla temporal documentada arriba y compara inicio/fin
  exactos entre fuentes. Si no hay vigencia en el catálogo, se informa revisión
  cuando están activadas las alertas por vacíos.

Los campos desactivados no generan hallazgos de comparación. EAN siempre se valida.
El reporte incorpora una hoja `REGLAS` con la configuración aplicada. Cambiar datos,
hoja o reglas invalida el resultado anterior: pulse **Comparar** nuevamente.
Cambiar archivo o método requiere volver a cargar/extraer los productos.
El Excel original no se modifica.

### Prueba manual en Windows

1. Desde la raíz del proyecto abra PowerShell y ejecute:

   ```powershell
   .\.venv\Scripts\python.exe -m streamlit run app.py
   ```

2. Abra http://localhost:8501. Mantenga **Utilizar archivos de prueba incluidos**,
   seleccione `BASE_DATOS_PRUEBA`, modo DEMO y pulse **Cargar transcripción para DEMO**.
3. En **Campos a validar**, seleccione solo `PRECIO_COP` para aislar esta prueba.
   Con tolerancia COP `0`, pulse **Comparar contra base de datos**. Para Dolex,
   EAN `7707397791469`, aparecerá diferencia: revista 24700, catálogo 26900.
4. Cambie la tolerancia COP a `2200`. El resultado anterior desaparecerá.
   Compare nuevamente: la diferencia de precio de Dolex ya no debe aparecer.
   Otros EAN pueden conservar alertas propias.
5. Para descuento, seleccione solo `DESCUENTO_PCT`, tolerancia `0`, y cambie el
   descuento de Dolex a `25.5` en su ficha. Compare: debe aparecer diferencia
   contra 25. Cambie la tolerancia a `0.5` y compare: esa diferencia desaparece.
6. Para unidades, seleccione solo `PRESENTACION`. En Dolex cambie `24 tabletas`
   por `24 tableta`. Con equivalencias activadas no debe haber diferencia para
   ese EAN. Desactive **Aceptar unidades equivalentes** y compare: ahora sí aparece.
   También puede probar `75 mililitros` en un Colgate cuya presentación sea `75 ml`.
7. Para marca, seleccione solo `MARCA`. Cambie `Dolex` por `DÓLEX`. Con normalización
   activada se acepta; desactivada genera diferencia. Si deja la marca vacía y
   activa **Alertar campos vacíos**, aparecerá `REVISAR_CAMPO_FALTANTE`.
8. Para EAN exacto, cambie el EAN de Dolex a `5901234123457` (GTIN válido ausente
   de esta base), dejando su nombre intacto. Compare: debe aparecer `NO_EN_BASE`;
   el sistema no lo relaciona con Dolex por su nombre. Para restaurar los datos,
   pulse **Cargar transcripción para DEMO**.
9. Descargue el informe y compruebe que la hoja `REGLAS` refleja los parámetros
   usados. Reactive todos los campos para una auditoría completa.

La prueba de duplicados usa el mismo criterio: si su catálogo tiene dos filas
con el mismo EAN, verá `EAN_DUPLICADO_BASE` y no una comparación contra una fila
seleccionada al azar. Este caso también está cubierto en la suite automatizada.

### Pruebas automatizadas

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

En Kali/Linux: `./scripts/probar.sh`.

Las pruebas incluyen reglas, tolerancias exactas, decimales, valores inválidos,
vacíos, equivalencias, EAN distinto con el mismo nombre, ceros iniciales,
duplicados, dígito verificador, fechas y recorrido Excel → servicio → reporte.
La prueba de integración verifica que el archivo de entrada permanece intacto.

Verificación actual: 46 pruebas automatizadas aprobadas, incluidas pruebas de
interfaz Streamlit para cargar DEMO, editar, navegar, añadir/quitar productos,
comparar y generar el botón de descarga con el reporte. Estas pruebas impiden
importar pandas/pyarrow para comprobar que el flujo DEMO es independiente de ellos.
El ejecutor de pruebas de Streamlit requiere sockets locales.

### Windows: DLL de pandas bloqueada por Control de aplicaciones

El editor tabular anterior (`st.data_editor`) y las tablas de resultados
(`st.dataframe`) cargaban pandas/Arrow. En este equipo Windows bloqueó una de sus
extensiones nativas (`join`), impidiendo mostrar la transcripción.

La interfaz ahora usa una **ficha por producto**, con campos nativos de Streamlit,
y tablas HTML de solo lectura para los resultados. Los textos del catálogo se
escapan antes de mostrarse. El flujo DEMO no necesita cargar pandas/Arrow, y no se
modifican las políticas de seguridad de Windows ni las bibliotecas instaladas.

### Resultados simplificados

La tabla **Incoherencias encontradas** y la hoja **DIFERENCIAS** del informe muestran
solo cinco columnas: **Producto, EAN, Página, Campo y Descripción de la incoherencia**.
Cada fila corresponde a un campo diferente; la descripción indica el valor de la
revista y el de Excel para saber qué revisar antes de publicar. También se muestran
EAN ausentes del catálogo y promociones vencidas con una explicación específica.
No se muestran filas de productos sin diferencias ni campos que coinciden.

Las alertas por datos faltantes, inválidos o identificaciones ambiguas se resumen
en un aviso; no se presentan como discrepancias confirmadas. Los registros que
están solo en Excel se excluyen porque pueden quedar fuera de las páginas procesadas.
Las demás tablas y hojas del informe conservan su contenido. Los datos originales
no se corrigen automáticamente ni se presupone cuál de las dos fuentes es correcta.

Para usar la corrección:
1. Detenga el proceso anterior con Ctrl+C y vuelva a iniciar Streamlit.
2. Recargue el navegador y pulse **Cargar transcripción para DEMO**.
3. En **Producto a revisar**, seleccione el producto. Edite sus campos y confirme
   el cambio con Enter o saliendo del campo. Puede navegar a otro producto sin
   perder los cambios. **Añadir producto** y **Quitar producto seleccionado**
   afectan únicamente la revisión en memoria.
4. Pulse **Comparar contra base de datos** y descargue el informe XLSX.

Esta corrección cubre la edición, comparación y reporte del modo DEMO. El modo OCR
conserva sus dependencias propias y requiere Tesseract; no fue validado en estas pruebas.
