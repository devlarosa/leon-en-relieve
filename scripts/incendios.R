#!/usr/bin/env Rscript
# Grandes incendios de la zona (ZONA=leon por defecto) -> web/data/<zona>/incendios.json
# Entrada: raw/incendios/effis_ba.json (scripts/descargar_incendios.sh). Necesita los paquetes sf y jsonlite.
# EFFIS (Copernicus) cartografía con satélite los incendios de unas 30 ha o más. Para cada uno se guarda:
# fechas, municipio de origen según EFFIS, superficie total y dentro de la zona, cubierta quemada (CORINE),
# porcentaje en Red Natura 2000, los pueblos (Nomenclátor del IGN) que quedan dentro del perímetro y el
# perímetro recortado a la provincia, en las coordenadas del visor. Los pueblos son los que quedan dentro del
# perímetro o a menos de 300 m de él (los cascos que se salvaron quedan como huecos del perímetro).
suppressMessages({ library(sf); library(jsonlite) })
sf_use_s2(FALSE)
args <- commandArgs(trailingOnly = FALSE)
RAIZ <- normalizePath(file.path(dirname(sub("^--file=", "", args[grep("^--file=", args)])), ".."))
setwd(RAIZ); source("R/zona.R")   # ZONA, FICHA, fr() = raw/<zona>/…, fw() = web/data/<zona>/…
L <- fromJSON(file.path(RAIZ, "web", "data", ZONA, "zona.json"), simplifyVector = FALSE)
M <- L$meta
anillos <- lapply(L$provincia, function(r) {
  v <- unlist(r); a <- cbind(v[c(TRUE, FALSE)] + M$x0, M$y1 - v[c(FALSE, TRUE)])
  if (any(a[1, ] != a[nrow(a), ])) a <- rbind(a, a[1, ]); a
})
prov <- st_make_valid(st_sfc(st_multipolygon(lapply(anillos, function(a) list(a))), crs = 25830))

x <- st_make_valid(st_transform(st_read(file.path(RAIZ, "raw", ZONA, "incendios", "effis_ba.json"), quiet = TRUE), 25830))
x <- x[!duplicated(x$id), ]
x <- x[lengths(st_intersects(x, prov)) > 0, ]
dentro <- suppressWarnings(st_intersection(st_geometry(x), prov))
a_in <- as.numeric(st_area(dentro))
ok <- a_in >= 5e4                                     # al menos 5 ha dentro de la provincia
x <- x[ok, ]; dentro <- dentro[ok]; a_in <- a_in[ok]

# pueblos del Nomenclátor (entidades y capitales de municipio) en coordenadas reales
pts <- do.call(rbind, lapply(c(L$entidades, L$capitales), function(e) data.frame(n = sub(" / .*", "", e$n), x = e$xy[[1]] + M$x0, y = M$y1 - e$xy[[2]])))
pts <- pts[!duplicated(paste(pts$n, round(pts$x, -2), round(pts$y, -2))), ]
pts_sf <- st_as_sf(pts, coords = c("x", "y"), crs = 25830)

# cada anillo empieza en su vértice más al suroeste: los cálculos de GEOS no siempre devuelven el mismo punto
# de arranque y, sin esto, el fichero de salida cambiaba de una ejecución a otra (aunque la forma fuera la misma)
normalizar <- function(g) {
  rota <- function(r) { m <- r[-nrow(r), , drop = FALSE]; k <- order(m[, 1], m[, 2])[1]; m <- m[c(k:nrow(m), seq_len(k - 1)), , drop = FALSE]; rbind(m, m[1, ]) }
  st_multipolygon(lapply(st_cast(st_sfc(g, crs = 25830), "MULTIPOLYGON")[[1]], function(p) lapply(p, rota)))
}
anillos_visor <- function(g, tol) {
  g <- st_simplify(st_sfc(normalizar(g), crs = 25830), dTolerance = tol, preserveTopology = TRUE)
  out <- list()
  for (p in st_cast(st_cast(g, "MULTIPOLYGON"), "POLYGON")) for (r in p) {
    if (nrow(r) < 4) next
    out[[length(out) + 1]] <- as.integer(round(c(t(cbind(r[, 1] - M$x0, M$y1 - r[, 2])))))
  }
  out
}
num <- function(v) { v <- suppressWarnings(as.numeric(v)); ifelse(is.na(v), 0, v) }
fuegos <- lapply(seq_len(nrow(x)), function(i) {
  r <- x[i, ]; g <- dentro[[i]]
  # pueblos dentro del perímetro o a menos de 300 m: los núcleos que no ardieron quedan como huecos del perímetro
  cerca <- st_buffer(st_geometry(r), 300)
  dentro_pts <- pts$n[lengths(st_intersects(pts_sf, cerca)) > 0 & lengths(st_intersects(pts_sf, prov)) > 0]
  c0 <- st_coordinates(st_point_on_surface(st_sfc(g, crs = 25830)))[1, ]
  cub <- c(frondosas = num(r$BROADLEA), coniferas = num(r$CONIFER), mixto = num(r$MIXED),
           matorral = num(r$SCLEROPH) + num(r$TRANSIT), pastos_y_roca = num(r$OTHERNATLC),
           agricola = num(r$AGRIAREAS), urbano = num(r$ARTIFSURF), otros = num(r$OTHERLC))
  list(id = r$id, anio = as.integer(substr(r$FIREDATE, 1, 4)), ini = substr(r$FIREDATE, 1, 10), fin = substr(r$FINALDATE, 1, 10),
       mun = r$COMMUNE, prov = r$PROVINCE, ha = round(num(r$AREA_HA)), haLeon = min(round(num(r$AREA_HA)), round(a_in[i] / 1e4)),
       cub = as.list(round(cub[cub >= 0.5])), natura = round(num(r$PERCNA2K)),
       locs = sort(unique(dentro_pts)), c = as.integer(round(c(c0[1] - M$x0, M$y1 - c0[2]))), g = anillos_visor(g, 30))
})
fuegos <- fuegos[order(-vapply(fuegos, function(f) f$haLeon, 0))]
anios <- sort(unique(vapply(fuegos, function(f) f$anio, 0L)))
resumen <- lapply(anios, function(a) { fs <- Filter(function(f) f$anio == a, fuegos)
  list(anio = a, n = length(fs), ha = sum(vapply(fs, function(f) f$haLeon, 0)), gif = sum(vapply(fs, function(f) f$ha >= 500, TRUE))) })
out <- list(fuente = "EFFIS, Sistema Europeo de Información sobre Incendios Forestales (Copernicus, Centro Común de Investigación de la Comisión Europea): superficies quemadas cartografiadas por satélite (modis.ba.poly)",
            actualizado = format(Sys.Date()), anios = resumen, incendios = fuegos)
f <- file.path(RAIZ, "web", "data", ZONA, "incendios.json")
writeLines(toJSON(out, auto_unbox = TRUE, digits = NA), f, useBytes = TRUE)
cat(sprintf("%d incendios (%s) -> %s (%.2f MB)\n", length(fuegos), paste(range(anios), collapse = "–"), f, file.size(f) / 1e6))
for (s in resumen) cat(sprintf("  %d: %3d incendios, %7.0f ha en la zona, %d de más de 500 ha\n", s$anio, s$n, s$ha, s$gif))
for (fu in head(Filter(function(f) f$anio >= 2025, fuegos), 12))
  cat(sprintf("  %s  %-24s %6d ha (%6d en la zona)  %d pueblos: %s\n", fu$ini, fu$mun, fu$ha, fu$haLeon, length(fu$locs), paste(head(fu$locs, 6), collapse = ", ")))
