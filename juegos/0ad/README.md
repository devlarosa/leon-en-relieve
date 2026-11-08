# La provincia de León en 0 A.D.

Mapas de escaramuza para [0 A.D.](https://play0ad.com) (versión 0.28, gratuito y libre) generados a partir de los
mismos datos oficiales que el visor:

| En el juego | Dato real |
|---|---|
| Relieve | MDT25 del IGN, como desnivel sobre el fondo del valle local (≈3,5× de exageración) para que los ríos discurran a nivel del agua |
| Ríos | Hidrografía del IGN (ríos de más de 12 km): poco profundos, **se pueden vadear** |
| Embalses | IGN (Riaño, Luna, Porma, Bárcena…): profundos |
| Carreteras | Red principal del IGN, con el perfil suavizado para que los puertos (Manzanal, Pajares…) sean transitables |
| Terreno y bosques | Copernicus CLC+ Backbone 2021: pinos en los pinares; robles y hayas en las frondosas caducifolias (hayas en la montaña norte); encinas en las perennifolias; choperas junto a los ríos del llano |
| Recursos | Oro en Las Médulas; metal en la montaña minera; piedra en la montaña y en Maragatería |
| Fauna | Osos pardos y lobos en la Cordillera; ciervos y jabalíes en los bosques; ovejas en el llano; peces en los embalses |

Tamaño Gigante (512 × 512 casillas, ~383 m por casilla) sobre un cuadrado de 196 × 196 km que incluye franjas de
Asturias al norte y de Zamora al sur.

| Mapa | Bases |
|---|---|
| León (2) | León, Ponferrada |
| León (4) | León, Ponferrada, Astorga, Sahagún |
| León (8) | León, Ponferrada, Astorga, La Bañeza, Valencia de Don Juan, Sahagún, Villablino, Cistierna |

## Generar e instalar

Necesita los datos del visor (`scripts/descargar_datos.sh` y `R/10_preparar_web.R`) y, además, las franjas de MDT25
y la cubierta del cuadrado completo en `raw/mdt25_extra/` y `raw/copernicus/clcplus_0ad/`.

```bash
for n in 2 4 8; do Rscript juegos/0ad/generar_mapa_leon.R $n; done
juegos/0ad/instalar.sh          # copia los mapas a la carpeta de usuario de 0 A.D. (se cargan sin activar mods)
```

El generador comprueba que todas las bases quedan conectadas por tierra con las reglas de paso del juego
(agua de menos de 2 de profundidad y pendiente menor de 1).

## Probar sin gráficos

```bash
flatpak run com.play0ad.zeroad -autostart=skirmishes/leon_2p -autostart-nonvisual \
  -autostart-ai=1:petra -autostart-civ=1:iber -autostart-ai=2:petra -autostart-civ=2:rome
```

## Jugar

En el juego: **Un jugador → Partida de escaramuza → Tipo de mapa: Escaramuza → León (2/4/8)**.
O directamente contra la IA:

```bash
flatpak run com.play0ad.zeroad -autostart=skirmishes/leon_2p -autostart-civ=1:iber \
  -autostart-ai=2:petra -autostart-civ=2:rome -autostart-aidiff=2:3
```
