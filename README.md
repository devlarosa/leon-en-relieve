# León en relieve

Mapa 3D interactivo de la provincia de León con su orografía real, pintado con un estilo ilustrado y acogedor. Funciona en el navegador (HTML + [three.js](https://threejs.org/)), sin servidor de mapas ni teselas externas.

**Capas**: relieve (MDT25), límites municipales, comarcas, ríos, embalses y lagos, carreteras, poblaciones, cumbres, sierras, valles y puertos de montaña. Cada municipio tiene una ficha con su población (INE), superficie, altitudes y comarca. Se puede filtrar por comarca, cambiar la exageración vertical y la hora del sol, ver la evolución de la población de 1900 a 2025, transformar el relieve en un relieve de población y usar un mirador que calcula todo lo que se ve desde cualquier punto.

## Fuentes

Todos los datos proceden de fuentes oficiales españolas o europeas (Copernicus); la comarca tradicional que aparece en la ficha de cada municipio es el único dato no oficial:

| Capa | Fuente |
|---|---|
| Relieve | IGN · MDT25, WCS `servicios.idee.es/wcs-inspire/mdt` |
| Provincia, municipios y condominios | IGN · Unidades administrativas INSPIRE, WFS `www.ign.es/wfs-inspire/unidades-administrativas` |
| Ríos | IGN · Hidrografía INSPIRE, WFS `servicios.idee.es/wfs-inspire/hidrografia` |
| Embalses y lagos, carreteras | IGN · OGC API Features `api-features.idee.es` (`standingwater`, `roadlink`) |
| Localidades (incluidas las que no son municipio), cumbres, sierras, valles, puertos | IGN · Nomenclátor Geográfico Básico de España, WFS `www.ign.es/wfs-inspire/ngbe` (entidades singulares, núcleos, capitales de EATIM y entidades menores) |
| Población de cada pueblo | INE · Nomenclátor a 1 de enero de 2025 (entidades singulares), cruzado con el IGN por municipio y nombre |
| Población | INE · Padrón municipal a 1 de enero (tabla 2877) |
| Cubierta del suelo y bosques | Copernicus · CLC+ Backbone 2021 (10 m, 11 clases), servidor de imágenes de la Agencia Europea de Medio Ambiente (`image.discomap.eea.europa.eu`), reducido a 50 m por clase mayoritaria |
| Densidad de población | INE · Censo 2021, población en celdas de 1 km² de la rejilla europea (`Poblacion_Rejilla_Europea.csv`) |
| Población histórica | INE · Alteraciones de los municipios en los Censos de Población desde 1842 (población de derecho 1900–2021; a cada municipio actual se le suman los que absorbió) |
| El Bierzo | Ley 1/1991 de Castilla y León (38 municipios) |
| Comarcas agrarias | MAPA · `ComarcasAgrarias.shp` de la IDE del Ministerio de Agricultura (copia distribuida por [rOpenSpain/mapSpain](https://github.com/rOpenSpain/mapSpain)). Cada municipio va a la comarca con la que comparte más superficie |
| Comarca tradicional (dato secundario en la ficha) | Ficha de cada municipio en es.wikipedia.org, vía Wikidata (código INE P772). No es oficial |
| Clima (normales 1991-2020) | AEMET · rejilla diaria de 5 km ROCIO_IBEB (precipitación v2, temperaturas máxima y mínima v1); normales y ajuste con la altitud calculados por `scripts/clima_aemet.py` |
| Red de ríos y afluentes | IGN · red hidrográfica INSPIRE (HY-N) en la OGC API Features de la IDEE (`api-features.idee.es`) |
| Cuencas | Dirección General del Agua · cuencas de captación con orden Pfafstetter (superficie oficial); la sombra del visor es una aproximación sobre la red del IGN |
| Caudales y embalses | MITECO · Anuario de Aforos 2021-22 (Red Oficial de Estaciones de Aforo, datos de las confederaciones del Duero, Miño-Sil y Cantábrico); el caudal por tramo es una estimación calibrada con las estaciones |
| Geología | IGME-CSIC · MAGNA 1:50.000 (descripción y tipo de roca), Mapa Geológico de España 1:1.000.000 (edad, con los colores de la Comisión Internacional de Estratigrafía), Mapa Hidrogeológico 1:200.000 (permeabilidad) e Inventario Español de Lugares de Interés Geológico |

## Como app en el móvil

`servidor/servidor.py` sirve `web/` como aplicación instalable (icono en la pantalla de inicio, pantalla completa) y añade el botón ↻ para cargar cambios y el guardado de lugares destacados. `servidor/leon3d-visor.service` lo deja como servicio de usuario de systemd (puerto 8800). La ubicación del dispositivo solo funciona si la app se abre por https.

## Licencias

El código de este repositorio se publica con licencia [MIT](LICENSE). Es un proyecto educativo y divulgativo.

Los datos no se guardan en el repositorio: se descargan de sus fuentes oficiales y se procesan con los scripts. Cada fuente conserva su licencia, y todas permiten reutilizar citando el origen:

- **IGN / CNIG** (relieve, límites, hidrografía, toponimia, carreteras): CC BY 4.0, © Instituto Geográfico Nacional.
- **INE** (población, censos, nomenclátor): reutilización libre citando la fuente (Ley 37/2007).
- **AEMET** (clima): reutilización libre, también comercial, citando a AEMET como fuente según su nota legal.
- **MITECO y Dirección General del Agua** (anuario de aforos, embalses, cuencas): reutilización libre citando la fuente (aviso legal del MITECO, Ley 37/2007 y Real Decreto 1495/2011).
- **MAPA** (comarcas agrarias): reutilización libre citando la fuente.
- **IGME-CSIC** (geología): reutilización libre citando la fuente.
- **Copernicus** (cubierta del suelo): acceso libre y gratuito, © Unión Europea, Copernicus Land Monitoring Service, Agencia Europea de Medio Ambiente.
- **Wikipedia / Wikidata** (comarca tradicional y posición de algunos lugares de interés): CC BY-SA 4.0 y CC0.

Quien publique los datos procesados (por ejemplo, el visor con `web/data/`) debe mantener estas atribuciones; el visor las muestra en «Fuentes oficiales».

## Cómo construirlo

Requisitos: `bash`, `curl`, `python3` con `numpy`, `scipy` y `Pillow`, y R con los paquetes `sf`, `terra`, `dplyr` y `jsonlite`. Todas las fuentes se descargan sin registro.

```bash
scripts/descargar_datos.sh        # descarga todo en raw/ (unos 300 MB; se puede relanzar)
Rscript R/03_admin.R              # provincia y municipios en ETRS89 / UTM 30N
Rscript R/10_preparar_web.R       # genera web/data/relieve.png y web/data/leon.json
Rscript R/11_rejilla_poblacion.R  # genera web/data/poblacion.png (Censo 2021 en celdas de 1 km²)
Rscript R/12_cobertura_copernicus.R  # descarga CLC+ Backbone y genera web/data/cobertura.png
scripts/descargar_clima_aemet.sh   # rejilla diaria de 5 km de AEMET, 1991-2020 (unos 800 MB)
python3 scripts/clima_aemet.py    # normales climáticas -> web/data/clima.png y clima.json
python3 scripts/rios_red_descargar.py  # red del IGN (HY-N), cuencas de la DGA y Anuario de Aforos (unos 200 MB)
python3 scripts/rios_red.py        # afluentes, caudales, estaciones, embalses -> web/data/rios.json y cuencas.png
python3 scripts/geologia_descargar.py  # geología del IGME-CSIC (MAGNA 50, mapa 1:1M, hidrogeológico, LIG) -> raw/geologia/
python3 scripts/geologia.py        # tipo de roca, edad, permeabilidad y lugares de interés -> web/data/geologia.*
python3 scripts/lugares.py         # lugares de interés de recursos/lugares.json, situados con el Nomenclátor del IGN o Wikidata
./abrir_visor.sh                  # sirve web/ en http://127.0.0.1:8800 y abre el navegador (--parar para detenerlo)
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
scripts/ine_nomenclator.py   población de cada pueblo (Nomenclátor del INE)
R/03_admin.R                 límites administrativos
R/10_preparar_web.R          rejilla de alturas, recortes, simplificación y JSON para la web
R/11_rejilla_poblacion.R     población del Censo 2021 por km² en la malla del visor
R/12_cobertura_copernicus.R  cubierta del suelo de Copernicus (CLC+ Backbone 2021)
scripts/clima_aemet.py       normales 1991-2020 de AEMET (temperaturas, precipitación, heladas, días de calor) ajustadas a la altitud
scripts/lugares.py           sitúa los lugares de interés (recursos/lugares.json): Nomenclátor del IGN, Wikidata o su pueblo
scripts/geologia.py          tipo de roca, edad de las rocas, permeabilidad y lugares de interés geológico (IGME-CSIC)
scripts/rios_red.py          árbol de afluentes, caudal medio estimado por tramo, estaciones de aforo, embalses y cuencas aproximadas
servidor/servidor.py         servidor de la app (iPhone): cabecera PWA, version.json y guardado de destacados
web/index.html               visor 3D
abrir_visor.sh               abre el visor en local (para un acceso directo del escritorio; icono en recursos/icono.svg)
pruebas/                     pruebas automáticas en Firefox (WebDriver BiDi)
```

## Mapas para juegos

`juegos/0ad/` genera mapas de escaramuza de León para 0 A.D. (gratuito y libre) con el relieve, los ríos, los bosques y las ciudades reales. Ver [juegos/0ad/README.md](juegos/0ad/README.md).

## Pendiente

- Especies arbóreas con el Mapa Forestal de España (MFE25, MITECO): Copernicus distingue coníferas, caducifolias y perennifolias, pero no especies. Su descarga tiene un captcha y hay que bajarla a mano.
- Datos de ríos y embalses en tiempo real (SAIH del Duero y del Miño-Sil): sus servidores usan la raíz de certificados de la FNMT.
