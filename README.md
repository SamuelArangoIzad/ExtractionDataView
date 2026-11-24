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

Verificación actual: 54 pruebas automatizadas aprobadas, incluidas pruebas de
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

## Tarjetas y promociones: detección guiada por OCR local

### Prueba usuario final

Seleccione **PRUEBA USUARIO FINAL** en el menú. Este flujo solo muestra dos cargas
de archivos, **Generar** y la tabla de resultados. Para la prueba actual:

1. Reinicie Streamlit con `.\.venv\Scripts\python.exe -m streamlit run app.py`.
2. Cargue `data/Base_Datos_Demo.xlsx` y `data/Revista_Essentials.pdf` en sus campos.
3. Pulse **Generar** y espere a que termine el recorrido de todas las páginas.
4. Revise primero **Incoherencias encontradas del consenso** y debajo **Revisiones
   pendientes de la revista**. Ambas tablas conservan **Producto, EAN, Página,
   Campo, Descripción de la incoherencia**. Se ocultan los productos por identificar,
   sin nombre o con nombre vacío; sus registros se conservan internamente. Un
   producto puede aparecer en varias filas si tiene varios campos diferentes.
   Las filas sin diferencias no aparecen. Cambiar los archivos elimina el resultado
   anterior; volver a generar ejecuta una lectura nueva.

Internamente se orienta cada página, se obtiene una lectura de página completa,
se detectan tarjetas con EAN/precios y se ejecuta OCR nuevamente sobre cada recorte.
Las dos lecturas usan el mismo motor local, con contextos de imagen distintos:
su acuerdo no equivale a dos motores independientes ni garantiza exactitud.
Los campos solo se comparan con Excel cuando ambas lecturas coinciden y el EAN
es exacto y válido. Excel no se utiliza para rellenar el PDF ni para decidir
qué lectura es correcta. Se mantienen las reglas parametrizadas con sus valores
predeterminados, sin exponer controles técnicos en esta sección.

**Revisión pendiente** identifica desacuerdos, valores sin lectura única, páginas
fallidas o productos sin EAN confirmado. Estas filas no prueban un error en Excel:
hay que comprobar el impreso antes de corregir cualquiera de las fuentes. Los
anuncios sin código no se asocian por parecido de nombre. Precios múltiples,
incluidos «antes» y «ahora», se consideran ambiguos. Los descuentos «hasta» no se
convierten en porcentajes fijos. Marca solo se extrae si aparece identificada como
tal; la vigencia no se extrae en este flujo. Campos sin evidencia no se dan por correctos.

En el libro de prueba se usa **BASE_DATOS_PRUEBA**, nunca **REVISTA_EXTRAIDA** como
lectura del PDF. Para otros libros se requiere una única hoja de catálogo legible
con EAN; si hay varias candidatas se pide un archivo con una sola hoja. Esta
versión se prueba con los archivos incluidos: no descarga revistas de Internet.
La prueba automatizada comprueba desacuerdos, múltiples diferencias por producto,
EAN distinto/ausente, Excel ambiguo, dos llamadas OCR separadas, fallos del motor,
interfaz mínima y regeneración/cambio de archivos.

Verificación local: se ejecutó el flujo real con las 20 páginas y el Excel
incluido. En esa corrida inicial se revisaron 52 regiones y hubo acuerdo en 88
campos; 12 páginas no tuvieron campos confirmados. Esto es cobertura de lectura,
no precisión certificada. Después se corrigieron avisos por prefijos de cantidad
(`x 6 Und`) y nombres parciales, con pruebas específicas. La suite previa de
72 pruebas pasó y las 12 pruebas finales del módulo híbrido también pasaron.

En **TARJETAS: detectar y visualizar**, el modo predeterminado usa texto con
coordenadas para orientar la página y proponer recortes alrededor de EAN y precios.
Revisa cuatro orientaciones, después realiza pasadas de escala y contraste para
texto claro, rojo y amarillo. Las columnas se apoyan en los EAN; los precios
permiten recuperar tarjetas cuyo código no se leyó. El margen amplía el recorte
para incluir precio, descuento y vigencia. No es un detector semántico entrenado.

Para anuncios sin EAN se conserva la página completa. Se muestran precios,
porcentajes y números destacados **candidatos**, junto con ampliaciones de zonas
destacadas aunque el OCR no consiga leerlas. Estas zonas pueden contener letras
o fotos. No se inventan dígitos, no se asigna una oferta de categoría a un producto
y no se envían estas lecturas automáticamente a la comparación con Excel.
Un porcentaje «hasta» se diferencia de un descuento fijo. Teléfonos, cantidades
y fechas se conservan como contexto, fuera de la tabla comercial principal.

Windows usa su motor OCR local mediante WinRT. En otros sistemas se usa Tesseract
CLI con idiomas `spa+eng`. No requiere API, LLM, Excel, pandas ni Arrow en este
flujo. El modo **Solo regiones visuales** continúa disponible sin motor OCR.
El método OCR antiguo del menú conserva sus dependencias de Tesseract/pytesseract.

### Cómo probarlo

1. Detenga Streamlit con Ctrl+C. En la carpeta del proyecto ejecute:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe -m streamlit run app.py
   ```

2. Abra http://localhost:8501, elija **TARJETAS: detectar y visualizar** y mantenga
   la revista de prueba. Para otro PDF, desactive la revista incluida y cárguelo.
3. Deje **Detección → Guiada por texto (OCR local)**, **Corregir orientación
   automáticamente** activado y **Tipo de página → Automático**. Pulse
   **Detectar tarjetas de esta página** después de elegir cada página.
4. Use las páginas **8, 11, 12 y 15 del PDF**: se verificaron respectivamente
   **5, 6, 4 y 5** regiones de producto. No son los números impresos al pie de
   la revista. Seleccione cada tarjeta y revise precio, descuento y EAN completos.
   En la 15, la foto de la modelo no debe convertirse en tarjeta.
5. Pruebe las páginas **5, 9 y 10**: se propone la página completa. En la 10 se
   recuperó **$92.600**. En 5 y 9 los descuentos estilizados no se leen de forma
   fiable con el motor de este equipo: abra **Zonas destacadas del anuncio para
   revisar**. Un resultado vacío o un número parcial no confirma ausencia de oferta.
6. Si la clasificación no corresponde, seleccione **Catálogo de varios productos**
   o **Promoción de página completa** y detecte otra vez. Si queda girada, desactive
   la orientación automática y ajuste los grados antihorarios manualmente.
7. Corrija recortes con **Izquierda, Arriba, Derecha, Abajo → Guardar límites**.
   Puede añadir regiones manuales o eliminarlas. Un anuncio mixto, como la página
   4, puede requerir estos ajustes. Los precios «antes» y «ahora» requieren revisión.
8. Descargue el ZIP: contiene recortes, página marcada y `regiones.json` con huella
   del PDF, coordenadas, rotación efectiva, lecturas, fuentes de contraste y zonas
   destacadas. Coordenadas en píxeles de la imagen mostrada, con derecha/abajo
   exclusivos. No hay importación automática del ZIP.

Cambiar de página conserva sus ajustes durante la sesión. Cambiar PDF, rotación,
motor, tipo de página o parámetros reinicia las regiones afectadas. Detectar otra
vez reemplaza las regiones manuales. Descargue antes de cerrar la sesión.

### Pruebas y límites medidos

Se verificó OCR nativo sobre las ocho páginas distintas de las capturas
(4, 5, 8, 9, 10, 11, 12 y 15), y se inspeccionaron los recortes. Las capturas
7–8 y 9–10 eran duplicadas. Las lecturas de esas páginas están guardadas en
`tests/fixtures/layout_ocr.json` para pruebas deterministas sin depender del motor
instalado. Son resultados reales con errores, no transcripciones corregidas.
Las pruebas comprueban orientación, número de tarjetas, inclusión de EAN,
precio de Klim, descuentos de la página 8, límites, exportación, errores de motor
y navegación/rotación del frontend con Streamlit AppTest. No constituyen una
medición general de precisión para revistas distintas.

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Los números estilizados, textos inclinados y escaneos borrosos pueden fallar.
Las pasadas pueden discrepar entre sí: se conservan lecturas contradictorias para
revisión. La vigencia general y los descuentos compartidos todavía no se asignan
automáticamente a tarjetas. La interfaz permite revisar el resultado antes de
usar cualquier dato en una auditoría.

Referencias: [OCR de Windows](https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr.ocrengine),
[PyWinRT](https://pywinrt.readthedocs.io/en/latest/),
[salida TSV de Tesseract](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage).
