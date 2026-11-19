#!/usr/bin/env Rscript
# Todas las cumbres con nombre de la zona -> web/data/<zona>/cumbres.json
# leon.json solo lleva las 150 más altas y separadas (para la vista general); aquí van todas las «Montaña» del
# Nomenclátor Geográfico Básico del IGN (raw/ngbe/Montaña.gml) dentro de la provincia, con la altitud del MDT25
# (máximo en 60 m alrededor, como en R/10_preparar_web.R) y su aislamiento: distancia a la cumbre más alta más
# cercana. El visor las rotula al acercarse, antes las más aisladas.
# Entrada: raw/ngbe/Montaña.gml, raw/mdt25/*.tif, raw/provincia.gpkg (scripts/descargar_datos.sh). Paquetes sf, terra, jsonlite.
suppressMessages({ library(sf); library(terra); library(jsonlite) })
sf_use_s2(FALSE)
args <- commandArgs(trailingOnly = FALSE)
RAIZ <- normalizePath(file.path(dirname(sub("^--file=", "", args[grep("^--file=", args)])), ".."))
setwd(RAIZ); source("R/zona.R")   # ZONA, FICHA, fr() = raw/<zona>/…, fw() = web/data/<zona>/…
X0 <- FICHA$extension[1]; Y1 <- FICHA$extension[4]

prov <- st_read(fr("provincia.gpkg"), quiet = TRUE)
margen <- FICHA$procesado$cumbresMargen; if (is.null(margen)) margen <- 400   # Picos: también las del entorno inmediato
prov_buf <- st_buffer(prov, margen)
cat("Mosaico MDT25...\n")
tiles <- list.files(fr("mdt25"), pattern = "\\.tif$", full.names = TRUE)
dem25 <- do.call(mosaic, c(lapply(tiles, rast), fun = "mean")); crs(dem25) <- "EPSG:25830"
dem25[dem25 < -100 | dem25 > 4000] <- NA

m <- st_read(fr("ngbe/Montaña.gml"), quiet = TRUE)
m$nombre <- vapply(m$text, function(t) paste(unique(unlist(t)), collapse = " / "), "")
m <- st_transform(m, 25830)["nombre"]
m <- m[lengths(st_intersects(m, prov_buf)) > 0, ]
m$elev <- terra::extract(dem25, vect(st_buffer(m, 60)), fun = max, na.rm = TRUE)[, 2]
m <- m[!is.na(m$elev) & is.finite(m$elev), ]
m <- m[order(-m$elev), ]
xy <- st_coordinates(m)

# duplicados: dos nombres a menos de 150 m son la misma cumbre («Teleno» y «Pico Teleno»): se queda el nombre más largo
fuera <- rep(FALSE, nrow(m))
for (i in seq_len(nrow(m))) {
  if (fuera[i]) next
  d <- sqrt((xy[, 1] - xy[i, 1])^2 + (xy[, 2] - xy[i, 2])^2)
  j <- which(d < 150 & !fuera); if (length(j) < 2) next
  mejor <- j[which.max(nchar(sub(" / .*", "", m$nombre[j])))]
  fuera[setdiff(j, mejor)] <- TRUE
}
m <- m[!fuera, ]; xy <- xy[!fuera, , drop = FALSE]

# aislamiento (km): distancia a la cumbre con nombre más alta más cercana (para la más alta, 50 km)
iso <- vapply(seq_len(nrow(m)), function(i) {
  if (i == 1) return(50)
  d <- sqrt((xy[1:(i - 1), 1] - xy[i, 1])^2 + (xy[1:(i - 1), 2] - xy[i, 2])^2)
  min(d) / 1000
}, 0)
out <- lapply(seq_len(nrow(m)), function(i) list(n = m$nombre[i], e = round(m$elev[i]),
  xy = as.integer(round(c(xy[i, 1] - X0, Y1 - xy[i, 2]))), iso = round(iso[i], 1)))
f <- fw("cumbres.json")
writeLines(toJSON(list(fuente = "IGN · Nomenclátor Geográfico Básico de España (montañas con nombre); altitudes del MDT25", cumbres = out),
                  auto_unbox = TRUE, digits = NA), f, useBytes = TRUE)
cat(sprintf("%d cumbres con nombre -> %s (%.2f MB)\n", length(out), f, file.size(f) / 1e6))
print(head(data.frame(n = m$nombre, e = round(m$elev), iso = round(iso, 1)), 12))
