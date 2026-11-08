# Póster 3D de la provincia de León con rayshader, pensado para equipos con poca RAM (8 GB).
#
# Estrategia: cambiar memoria por tiempo.
#  1. Detalle en la textura y no en la malla: el sombreado se calcula con terra (por bloques y en disco)
#     a RES_TEXTURA metros y se pega sobre una malla de RES_MALLA metros simplificada (triangulate).
#  2. terra trabaja con poca memoria (MEMFRAC) y escribe temporales en TMP.
#  3. Cada paso guarda su resultado en disco y libera memoria antes del siguiente.
#  4. El render final se hace en PASADAS de pocas muestras con semillas distintas y se promedia:
#     misma memoria por pasada, menos ruido cuantas más pasadas. Se puede interrumpir y reanudar.
#
# Memoria medida en un iMac de 2015 con 8 GB: pico ≈3,4 GB (textura a 50 m, malla a 100 m, 2400×1600 px).
# Tiempo: ≈8 s por muestra; con 48 muestras × 4 pasadas, unos 25–30 min (se puede interrumpir y reanudar).
#
# Uso:   Rscript R/20_poster_rayshader.R      (prueba rápida: PRUEBA=1 Rscript R/20_poster_rayshader.R)
# Salida: salida/poster_leon.png (y los intermedios en salida/cache/)
suppressMessages({library(sf); library(terra); library(rayshader); library(jsonlite); library(png)})

# ---------------- parámetros (ajusta aquí) ----------------
RES_MALLA   <- 100      # m por celda de la malla 3D (100 = unos 2,8 M celdas para León)
RES_TEXTURA <- 50       # m por píxel de la textura (50 = unos 11 M píxeles; 25 = cuatro veces más tiempo y disco)
MAX_ERROR   <- 3        # tolerancia (m) de la malla simplificada: más alto = menos triángulos y menos RAM
ZSCALE      <- RES_MALLA / 2.2   # exageración vertical ~2,2
ANCHO       <- 2400; ALTO <- 1600   # píxeles (≈3,8 M px: pico ≈3,4 GB; 3600×2400 sube a ≈4,5 GB)
MUESTRAS    <- 48       # muestras por píxel en cada pasada
PASADAS     <- 4        # pasadas a promediar (MUESTRAS × PASADAS = calidad final)
LUZ         <- 80       # intensidad de la luz principal
HILOS       <- 4        # 1 = un solo núcleo (algo menos de RAM, mucho más lento); >1 = todos
MEMFRAC     <- 0.3      # fracción de RAM que terra puede usar
TMP         <- file.path(path.expand("~"), ".cache", "leon3d_tmp")   # p. ej. "/media/devlarosa/My Book Duo/tmp"
# ------------------------------------------------------------
if (Sys.getenv("PRUEBA") == "1") {     # prueba rápida de todo el flujo: PRUEBA=1 Rscript R/20_poster_rayshader.R
  RES_MALLA <- 400; RES_TEXTURA <- 200; ANCHO <- 400; ALTO <- 500; MUESTRAS <- as.numeric(Sys.getenv("MU", "16")); PASADAS <- 2; LUZ <- as.numeric(Sys.getenv("LUZ", "80"))
}

options(rgl.useNULL = TRUE)            # sin ventana: el render no necesita pantalla
dir.create(TMP, recursive = TRUE, showWarnings = FALSE)
dir.create("salida/cache", recursive = TRUE, showWarnings = FALSE)
terraOptions(memfrac = MEMFRAC, tempdir = TMP, progress = 0)
paso <- function(...) cat(format(Sys.time(), "%H:%M:%S"), "·", ..., "\n")
mem  <- function() {                   # memoria actual y pico del proceso (incluye rgl y rayrender)
  st <- readLines("/proc/self/status"); kb <- function(k) as.numeric(gsub("\\D", "", grep(paste0("^", k), st, value = TRUE)))
  sprintf("%.2f GB ahora, pico %.2f GB", kb("VmRSS") / 1048576, kb("VmHWM") / 1048576)
}
cache <- function(f) file.path("salida/cache", f)

prov <- vect(st_read("raw/provincia.gpkg", quiet = TRUE))
mdt  <- vrt(list.files("raw/mdt25", pattern = "\\.tif$", full.names = TRUE))   # mosaico virtual: no carga nada en RAM
crs(mdt) <- "EPSG:25830"
ext_p <- ext(prov) + 2000

# ---------- 1. textura a RES_TEXTURA: color hipsométrico + sombreado multidireccional (todo en disco) ----------
f_tex <- cache(sprintf("textura_%dm.tif", RES_TEXTURA))
if (!file.exists(f_tex)) {
  paso("Textura a", RES_TEXTURA, "m ·", mem())
  dt <- aggregate(crop(mdt, ext_p), fact = RES_TEXTURA / 25, fun = "mean", filename = file.path(TMP, "dt.tif"), overwrite = TRUE)
  pend <- terrain(dt, "slope", unit = "radians", filename = file.path(TMP, "slope.tif"), overwrite = TRUE)
  asp  <- terrain(dt, "aspect", unit = "radians", filename = file.path(TMP, "aspect.tif"), overwrite = TRUE)
  # cuatro luces suaves (estilo "multidireccional") y una principal del noroeste
  luces <- list(c(315, 40, 0.55), c(270, 45, 0.15), c(0, 45, 0.15), c(225, 50, 0.15))
  hs <- NULL
  for (l in luces) {
    h <- shade(pend, asp, angle = l[2], direction = l[1], normalize = TRUE) * l[3]
    hs <- if (is.null(hs)) h else hs + h
  }
  hs <- writeRaster(hs / 255, file.path(TMP, "hs.tif"), overwrite = TRUE)
  # paleta hipsométrica cálida (valles verdes, páramo dorado, montaña ocre y gris, cumbres claras)
  cortes <- c(200, 600, 800, 950, 1200, 1600, 2000, 2400, 2700)
  cols   <- col2rgb(c("#5f8f4e", "#8fae62", "#c9b77c", "#b9a46e", "#9a8a6a", "#8c8577", "#a9a49c", "#e4e2dc", "#ffffff"))
  rgbr <- lapply(1:3, function(k) {     # cada banda se calcula por bloques y se escribe a disco
    base <- app(dt, function(v) approx(cortes, cols[k, ], v, rule = 2)$y, filename = file.path(TMP, sprintf("b%d.tif", k)), overwrite = TRUE)
    lapp(c(base, hs), function(b, h) pmin(pmax(b * (0.35 + 0.85 * h), 0), 255), filename = file.path(TMP, sprintf("c%d.tif", k)), overwrite = TRUE)
  })
  tex <- mask(rast(rgbr), prov, updatevalue = 0, filename = f_tex, datatype = "INT1U", overwrite = TRUE)
  rm(dt, pend, asp, hs, rgbr, tex); invisible(gc())
}

# ---------- 2. ríos y límite provincial pintados sobre la textura ----------
f_tex2 <- cache(sprintf("textura_rios_%dm.tif", RES_TEXTURA))
if (!file.exists(f_tex2)) {
  paso("Ríos y límite sobre la textura ·", mem())
  tex <- rast(f_tex)
  web <- fromJSON("web/data/leon.json", simplifyVector = FALSE)
  a_utm <- function(v) cbind(web$meta$x0 + unlist(v)[c(TRUE, FALSE)], web$meta$y1 - unlist(v)[c(FALSE, TRUE)])
  lineas <- function(lista, ancho) {
    g <- lapply(lista, function(r) st_multilinestring(lapply(r$g, a_utm)))
    st_sf(w = ancho(lista), geometry = st_sfc(g, crs = 25830))
  }
  rios <- lineas(web$rios, function(l) vapply(l, function(r) if (r$k > 60) 3 else if (r$k > 20) 2 else 1, 1))
  rios <- st_buffer(rios, RES_TEXTURA * c(0.4, 0.6, 0.9)[rios$w]); rios$cod <- 1
  rm(web); invisible(gc())
  # una sola máscara (1 = río, 2 = límite) y recoloreado banda a banda, todo por bloques en disco
  m_rio <- rasterize(vect(rios), tex, field = "cod", background = 0, filename = file.path(TMP, "m_rio.tif"), overwrite = TRUE)
  m_lim <- rasterize(as.lines(prov), tex, field = 2, background = 0, filename = file.path(TMP, "m_lim.tif"), overwrite = TRUE)
  codigo <- max(m_rio, m_lim, filename = file.path(TMP, "m.tif"), overwrite = TRUE)
  pal <- rbind(c(70, 150, 190), c(60, 50, 40))
  bandas <- lapply(1:3, function(k) lapp(c(tex[[k]], codigo), function(v, m) ifelse(m == 1, pal[1, k], ifelse(m == 2, pal[2, k], v)),
                                         filename = file.path(TMP, sprintf("t%d.tif", k)), overwrite = TRUE))
  tex <- rast(bandas)
  writeRaster(tex, f_tex2, datatype = "INT1U", overwrite = TRUE)
  rm(tex, rios, m_rio, m_lim, codigo, bandas); invisible(gc())
}

# ---------- 3. malla de elevación a RES_MALLA ----------
f_dem <- cache(sprintf("malla_%dm.rds", RES_MALLA))
if (!file.exists(f_dem)) {
  paso("Malla a", RES_MALLA, "m ·", mem())
  dm <- mask(aggregate(crop(mdt, ext_p), fact = RES_MALLA / 25, fun = "mean"), prov)
  saveRDS(raster_to_matrix(dm), f_dem); rm(dm); invisible(gc())
}
elmat <- readRDS(f_dem)
paso("Malla:", nrow(elmat), "×", ncol(elmat), "=", round(length(elmat) / 1e6, 1), "M celdas ·", mem())

# ---------- 4. escena 3D con malla simplificada ----------
tex <- rast(cache(sprintf("textura_rios_%dm.tif", RES_TEXTURA)))
arr <- as.array(tex) / 255; arr[is.na(arr)] <- 1
rm(tex); invisible(gc())
paso("Textura:", dim(arr)[1], "×", dim(arr)[2], "·", mem())
plot_3d(arr, elmat, zscale = ZSCALE, solid = FALSE, shadow = TRUE, shadowdepth = -50,
        triangulate = TRUE, max_error = MAX_ERROR, verbose = TRUE,
        windowsize = c(1200, 800), theta = 0, phi = 50, zoom = 0.55, fov = 30, background = "#f4f1ea")
rm(arr); invisible(gc())
paso("Escena lista ·", mem())

# ---------- 5. render en pasadas, promediadas (reanudable) ----------
acum <- NULL; hechas <- 0
for (i in seq_len(PASADAS)) {
  f_p <- cache(sprintf("pasada_%02d_%dx%d_%dmu.png", i, ANCHO, ALTO, MUESTRAS))
  if (!file.exists(f_p)) {
    paso("Pasada", i, "de", PASADAS, "·", mem())
    render_highquality(filename = f_p, width = ANCHO, height = ALTO, samples = MUESTRAS, sample_method = "sobol_blue",
                       light = TRUE, lightdirection = 315, lightaltitude = 35, lightintensity = LUZ, lightsize = 600,
                       ambient_light = TRUE, backgroundhigh = "#ffffff", backgroundlow = "#f4f1ea",
                       lightcolor = "#fff1d6", ground_material = rayrender::diffuse(color = "#f4f1ea"),
                       parallel = HILOS > 1, interactive = FALSE, preview = FALSE,
                       clear = FALSE, verbose = FALSE)
    invisible(gc())
  }
  img <- readPNG(f_p)[, , 1:3]
  acum <- if (is.null(acum)) img else acum + img; hechas <- hechas + 1
}
writePNG(acum / hechas, "salida/poster_leon.png")
paso("Listo: salida/poster_leon.png (", hechas, "pasadas ×", MUESTRAS, "muestras ) ·", mem())
rgl::close3d()
