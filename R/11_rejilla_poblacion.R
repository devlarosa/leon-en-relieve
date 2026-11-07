# Población del Censo 2021 en celdas de 1 km² (INE, rejilla europea EPSG:3035) pasada a la malla de 100 m del visor.
# Salida: web/data/poblacion.png  (R,G = habitantes por km² en 16 bits; B = proporción de mayores de 64 años × 255)
suppressMessages({library(sf); library(terra); library(dplyr)})
X0 <- 164000; X1 <- 360000; Y0 <- 4655000; Y1 <- 4790000; CELL <- 100

raw <- read.csv2("raw/rejilla/Poblacion_Rejilla_Europea.csv", skip = 1, fileEncoding = "latin1", check.names = FALSE)
num <- function(x) suppressWarnings(as.numeric(gsub(".", "", as.character(x), fixed = TRUE)))   # el INE usa punto de miles
csv <- data.frame(id = raw[[1]], total = num(raw[[2]]), mayores64 = num(raw[[7]]))
xy <- regmatches(csv$id, regexec("N(\\d+)E(\\d+)", csv$id))
csv$n <- as.numeric(vapply(xy, `[`, "", 2)); csv$e <- as.numeric(vapply(xy, `[`, "", 3))

# recorte aproximado a la zona del visor en EPSG:3035 antes de construir polígonos
caja <- st_transform(st_as_sfc(st_bbox(c(xmin = X0, xmax = X1, ymin = Y0, ymax = Y1), crs = 25830)), 3035)
bb <- st_bbox(caja)
csv <- csv %>% filter(e >= bb["xmin"] - 1000, e <= bb["xmax"], n >= bb["ymin"] - 1000, n <= bb["ymax"])
cat("Celdas con población en la zona:", nrow(csv), " habitantes:", sum(csv$total, na.rm = TRUE), "\n")

celdas <- st_sf(total = csv$total, p65 = ifelse(csv$total > 0, csv$mayores64 / csv$total, NA),
  geometry = st_sfc(lapply(seq_len(nrow(csv)), function(i) {
    e <- csv$e[i]; n <- csv$n[i]
    st_polygon(list(matrix(c(e, n, e + 1000, n, e + 1000, n + 1000, e, n + 1000, e, n), ncol = 2, byrow = TRUE)))
  }), crs = 3035)) %>% st_transform(25830)

prov <- st_read("raw/provincia.gpkg", quiet = TRUE)
dentro <- lengths(st_intersects(celdas, prov)) > 0
cat("Provincia de León (celdas que la tocan):", sum(dentro), "celdas,", sum(celdas$total[dentro], na.rm = TRUE), "hab.\n")
cat("Densidad máxima:", max(celdas$total, na.rm = TRUE), "hab/km²\n")

grid <- rast(xmin = X0, xmax = X1, ymin = Y0, ymax = Y1, res = CELL, crs = "EPSG:25830")
v <- vect(celdas)
dens <- rasterize(v, grid, field = "total", fun = "max", background = 0)
p65 <- rasterize(v, grid, field = "p65", fun = "max", background = 0)
d <- pmin(round(values(dens)[, 1]), 65535); d[is.na(d)] <- 0
a <- round(pmin(pmax(values(p65)[, 1], 0), 1) * 255); a[is.na(a)] <- 0
out <- rast(grid, nlyrs = 3)
values(out) <- cbind(d %/% 256, d %% 256, a)
writeRaster(out, "web/data/poblacion.png", datatype = "INT1U", overwrite = TRUE)
unlink("web/data/poblacion.png.aux.xml")
cat("poblacion.png:", round(file.size("web/data/poblacion.png") / 1e6, 2), "MB\n")
