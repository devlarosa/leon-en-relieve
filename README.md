# León en relieve

Mapa 3D interactivo de la provincia de León con su orografía real, pintado con un estilo ilustrado y acogedor. Funciona en el navegador (HTML + [three.js](https://threejs.org/)), sin servidor de mapas ni teselas externas.

**Capas**: relieve (MDT25), límites municipales, comarcas, ríos, embalses y lagos, carreteras, poblaciones, cumbres, sierras, valles y puertos de montaña. Cada municipio tiene una ficha con su población (INE), superficie, altitudes y comarca. Se puede filtrar por comarca, cambiar la exageración vertical y la hora del sol, ver la evolución de la población de 1900 a 2025, transformar el relieve en un relieve de población y usar un mirador que calcula todo lo que se ve desde cualquier punto.

## Fuentes

Todos los datos geográficos proceden de fuentes oficiales; la comarca tradicional que aparece en la ficha de cada municipio es el único dato no oficial:

| Capa | Fuente |
|---|---|
| Relieve | IGN · MDT25, WCS `servicios.idee.es/wcs-inspire/mdt` |
| Provincia, municipios y condominios | IGN · Unidades administrativas INSPIRE, WFS `www.ign.es/wfs-inspire/unidades-administrativas` |
| Ríos | IGN · Hidrografía INSPIRE, WFS `servicios.idee.es/wfs-inspire/hidrografia` |
| Embalses y lagos, carreteras | IGN · OGC API Features `api-features.idee.es` (`standingwater`, `roadlink`) |
| Poblaciones, cumbres, sierras, valles, puertos | IGN · Nomenclátor Geográfico Básico de España, WFS `www.ign.es/wfs-inspire/ngbe` |
| Población | INE · Padrón municipal a 1 de enero (tabla 2877) |
| Densidad de población | INE · Censo 2021, población en celdas de 1 km² de la rejilla europea (`Poblacion_Rejilla_Europea.csv`) |
| Población histórica | INE · Alteraciones de los municipios en los Censos de Población desde 1842 (población de derecho 1900–2021; a cada municipio actual se le suman los que absorbió) |
| El Bierzo | Ley 1/1991 de Castilla y León (38 municipios) |
| Comarcas agrarias | MAPA · `ComarcasAgrarias.shp` de la IDE del Ministerio de Agricultura (copia distribuida por [rOpenSpain/mapSpain](https://github.com/rOpenSpain/mapSpain)). Cada municipio va a la comarca con la que comparte más superficie |
| Comarca tradicional (dato secundario en la ficha) | Ficha de cada municipio en es.wikipedia.org, vía Wikidata (código INE P772). No es oficial |

Los datos del IGN se publican bajo licencia CC BY 4.0 (© Instituto Geográfico Nacional). Los del INE, con cita de la fuente.

Los datos no se guardan en el repositorio: se descargan y se procesan con los scripts.

## Cómo construirlo

Requisitos: `bash`, `curl`, `python3`, R con los paquetes `sf`, `terra`, `dplyr` y `jsonlite`.

```bash
scripts/descargar_datos.sh        # descarga todo en raw/ (unos 300 MB; se puede relanzar)
Rscript R/03_admin.R              # provincia y municipios en ETRS89 / UTM 30N
Rscript R/10_preparar_web.R       # genera web/data/relieve.png y web/data/leon.json
Rscript R/11_rejilla_poblacion.R  # genera web/data/poblacion.png (Censo 2021 en celdas de 1 km²)
cd web && python3 -m http.server  # abrir http://localhost:8000
```

Los servidores del IGN fallan a veces (errores 502 o respuestas cortadas). El script de descarga reintenta y salta lo que ya está completo, así que basta con volver a lanzarlo.

## Lugares destacados (opcional y privado)

Si existe `web/data/destacados.json` con una lista de nombres del Nomenclátor, el visor los marca con un pilar de luz y los añade al panel. Ese fichero no se sube al repositorio. Hay un ejemplo en `web/destacados.ejemplo.json`:

```bash
cp web/destacados.ejemplo.json web/data/destacados.json
```

## Estructura

```
scripts/descargar_datos.sh   descarga de todas las fuentes
scripts/fetch_ogcapi.py      cliente paginado de la OGC API Features de la IDEE
scripts/ine_poblacion.py     padrón del INE
scripts/comarcas_wikipedia.py comarca tradicional de cada municipio
scripts/ine_censos.py        población histórica por municipio (censos del INE)
R/03_admin.R                 límites administrativos
R/10_preparar_web.R          rejilla de alturas, recortes, simplificación y JSON para la web
R/11_rejilla_poblacion.R     población del Censo 2021 por km² en la malla del visor
web/index.html               visor 3D
```

## Pendiente

- Vegetación y usos del suelo con el Mapa Forestal de España (MFE25, MITECO). Su descarga tiene un captcha y hay que bajarla a mano.
- Precipitación media (AEMET).
