# Prepara los datos oficiales para el visor web 3D de la provincia de León.
# Fuentes: IGN (MDT25, unidades administrativas, hidrografía, NGBE) e INE (Padrón 2025).
# Salida: web/data/relieve.png (alturas codificadas RGB) y web/data/leon.json
suppressMessages({library(sf); library(terra); library(dplyr); library(jsonlite)})
sf_use_s2(FALSE)
dir.create("web/data", recursive = TRUE, showWarnings = FALSE)

X0 <- 164000; X1 <- 360000; Y0 <- 4655000; Y1 <- 4790000; CELL <- 100
loc <- function(m) cbind(round(m[,1] - X0), round(Y1 - m[,2]))   # metros locales, y hacia el sur

# ---------- Administrativo ----------
prov <- st_read("raw/provincia.gpkg", quiet = TRUE)
mun  <- st_read("raw/municipios.gpkg", quiet = TRUE)
pob  <- read.csv("raw/poblacion_ine_2025.csv", colClasses = c(code = "character"))
mun  <- mun %>% left_join(pob[, c("code", "pob2025")], by = "code")
prov_buf <- st_buffer(prov, 400)

# ---------- Relieve (MDT25 IGN) ----------
cat("Mosaico MDT25...\n")
tiles <- list.files("raw/mdt25", pattern = "\\.tif$", full.names = TRUE)
dem25 <- do.call(mosaic, c(lapply(tiles, rast), fun = "mean"))
crs(dem25) <- "EPSG:25830"
dem25[dem25 < -100 | dem25 > 4000] <- NA
grid <- rast(xmin = X0, xmax = X1, ymin = Y0, ymax = Y1, res = CELL, crs = "EPSG:25830")
dem <- resample(dem25, grid, method = "average")
dem <- focal(dem, w = 3, fun = "mean", na.policy = "only", na.rm = TRUE)  # rellena huecos
dem[is.na(dem)] <- 0
cat("Rejilla:", ncol(dem), "x", nrow(dem), " rango:", unlist(global(dem, "range")), "\n")

v <- round((values(dem)[,1] + 10000) * 10)
rgbr <- rast(dem, nlyrs = 3)
values(rgbr) <- cbind(v %/% 65536, (v %/% 256) %% 256, v %% 256)
writeRaster(rgbr, "web/data/relieve.png", datatype = "INT1U", overwrite = TRUE)
unlink("web/data/relieve.png.aux.xml")

# ---------- Estadísticas municipales ----------
ex <- terra::extract(dem25, vect(mun), fun = function(x, ...) c(min(x, na.rm=TRUE), max(x, na.rm=TRUE), mean(x, na.rm=TRUE)))
mun$alt_min <- round(ex[,2]); mun$alt_max <- round(ex[,3]); mun$alt_med <- round(ex[,4])
mun$area_km2 <- round(as.numeric(st_area(mun)) / 1e6, 2)

# ---------- Nomenclátor (NGBE) ----------
rd_pts <- function(f) {
  p <- st_read(f, quiet = TRUE)
  p$nombre <- vapply(p$text, function(t) paste(unique(unlist(t)), collapse = " / "), "")
  p <- st_transform(p, 25830) %>% select(nombre)
  p[lengths(st_intersects(p, prov_buf)) > 0, ]
}
capprov <- rd_pts("raw/ngbe/Capital_de_provincia.gml")
capmun  <- rd_pts("raw/ngbe/Capital_de_municipio.gml")
# localidades: entidades singulares, núcleos, capitales de junta vecinal (EATIM) y entidades menores del NGBE
tipos_loc <- c("Entidad_singular", "Núcleos_de_población", "Capital_de_EATIM", "Entidad_menor_de_población")
ent <- do.call(rbind, lapply(tipos_loc, function(t) { f <- sprintf("raw/ngbe/%s.gml", t); if (file.exists(f)) rd_pts(f) }))
mont    <- rd_pts("raw/ngbe/Montaña.gml")

capmun <- st_join(capmun, mun[, c("code")], join = st_within) %>% filter(!is.na(code)) %>%
  group_by(code) %>% slice(1) %>% ungroup()
capmun$capital_prov <- capmun$code == "24089"
mun <- mun %>% left_join(st_drop_geometry(capmun)[, c("code", "nombre")] %>% rename(capital = nombre), by = "code")
# normalización de nombres para cruzar IGN e INE ("UÑA (LA)" = "La Uña"; sin tildes ni signos)
norm_nom <- function(x) {
  x <- sub("^(.*) \\((EL|LA|LOS|LAS|LO|L')\\)$", "\\2 \\1", toupper(trimws(x)))
  x <- iconv(x, "UTF-8", "ASCII//TRANSLIT"); x <- gsub("[^A-Z0-9 ]", " ", x); gsub("\\s+", " ", trimws(x))
}
primer_nom <- function(x) trimws(sub(" / .*", "", x))
ent$municipio <- st_join(ent, mun[, "code"], join = st_within)$code
ent <- ent[!is.na(ent$municipio), ]
ent$clave <- norm_nom(primer_nom(ent$nombre))
# un mismo pueblo aparece con varios tipos: se queda uno por nombre y municipio (y a menos de 1,5 km)
ent <- ent[order(ent$municipio, ent$clave), ]
dup <- logical(nrow(ent)); xy <- st_coordinates(ent)
for (i in seq_len(nrow(ent))[-1]) {
  j <- which(ent$clave[seq_len(i - 1)] == ent$clave[i] & ent$municipio[seq_len(i - 1)] == ent$municipio[i] & !dup[seq_len(i - 1)])
  if (length(j) && any(sqrt((xy[j, 1] - xy[i, 1])^2 + (xy[j, 2] - xy[i, 2])^2) < 1500)) dup[i] <- TRUE
}
ent <- ent[!dup, ]
# población de cada pueblo: Nomenclátor del INE (entidades singulares), cruzado por municipio y nombre
ine_ent <- read.csv("raw/nomenclator/entidades_ine.csv", colClasses = c(codigo = "character", municipio_ine = "character"))
names(ine_ent)[5] <- "pob"
ine_ent$clave <- norm_nom(ine_ent$nombre_ine)
k_ign <- paste(ent$municipio, ent$clave); k_ine <- paste(ine_ent$municipio_ine, ine_ent$clave)
ent$pob <- ine_ent$pob[match(k_ign, k_ine)]
# segunda pasada: nombres casi iguales dentro del mismo municipio ("San Martín" / "San Martín de la Falamosa")
for (i in which(is.na(ent$pob))) {
  cand <- ine_ent[ine_ent$municipio_ine == ent$municipio[i] & !(k_ine %in% k_ign[!is.na(ent$pob)]), ]
  if (!nrow(cand)) next
  d <- adist(ent$clave[i], cand$clave) / pmax(nchar(ent$clave[i]), nchar(cand$clave))
  pre <- startsWith(paste0(cand$clave, " "), paste0(ent$clave[i], " ")) | startsWith(paste0(ent$clave[i], " "), paste0(cand$clave, " "))
  if (min(d) <= 0.2) ent$pob[i] <- cand$pob[which.min(d)]
  else if (sum(pre) == 1) ent$pob[i] <- cand$pob[pre]      # "Caín" = "Caín de Valdeón"
}
emp <- !is.na(ent$pob)
cat("Localidades IGN:", nrow(ent), " con población INE:", sum(emp), sprintf("(%.0f %%)", 100 * mean(emp)),
    " habitantes asignados:", sum(ent$pob, na.rm = TRUE), " pueblos INE sin punto IGN:",
    sum(!(k_ine %in% k_ign[emp])), "\n")
# las que no tienen población en el INE y no son entidad singular suelen ser barrios o caseríos: se quedan, sin cifra
capmun$pob_nucleo <- ent$pob[match(paste(capmun$code, norm_nom(primer_nom(capmun$nombre))), paste(ent$municipio, ent$clave))]
# quitar de las localidades las que son la capital del municipio
es_cap <- paste(ent$municipio, ent$clave) %in% paste(capmun$code, norm_nom(primer_nom(capmun$nombre)))
ent <- ent[!es_cap, ]
cat("Capitales:", nrow(capmun), " Localidades (sin capitales):", nrow(ent), "\n")

# Picos: altitud del MDT25 (máximo en 60 m alrededor) y selección espaciada
mont$elev <- terra::extract(dem25, vect(st_buffer(mont, 60)), fun = max, na.rm = TRUE)[,2]
mont <- mont %>% filter(!is.na(elev)) %>% arrange(desc(elev))
keep <- integer(0); xy <- st_coordinates(mont)
for (i in seq_len(nrow(mont))) {
  if (length(keep) >= 150) break
  if (!length(keep) || min(sqrt((xy[keep,1]-xy[i,1])^2 + (xy[keep,2]-xy[i,2])^2)) > 2500) keep <- c(keep, i)
}
picos <- mont[keep, ]
picos <- picos[lengths(st_intersects(picos, prov_buf)) > 0, ]
cat("Picos:", nrow(picos), " máximo:", picos$nombre[1], picos$elev[1], "\n")

# Orografía con nombre (NGBE): sierras, valles y puertos, ordenados por importancia según el relieve
relieve_local <- function(p, r) {           # máximo y mínimo del MDT en un radio r alrededor de cada punto
  b <- vect(st_buffer(p, r))
  cbind(terra::extract(dem25, b, fun = max, na.rm = TRUE)[,2], terra::extract(dem25, b, fun = min, na.rm = TRUE)[,2],
        terra::extract(dem25, vect(p))[,2])
}
prov_in <- function(x) x[lengths(st_intersects(x, prov)) > 0, ]
sierras <- rd_pts("raw/ngbe/Alineación_montañosa.gml"); sierras <- sierras[lengths(st_intersects(sierras, st_buffer(prov, 1000))) > 0, ]
rs <- relieve_local(sierras, 2500); sierras$elev <- rs[,1]; sierras$imp <- rs[,1] - rs[,2]
sierras <- sierras %>% filter(!is.na(imp)) %>% arrange(desc(imp + elev / 4))
valles <- prov_in(rd_pts("raw/ngbe/Depresión.gml"))
rv <- relieve_local(valles, 1500); valles$elev <- rv[,3]; valles$imp <- rv[,1] - rv[,3]
valles <- valles %>% filter(!is.na(imp), grepl("^(Valle|Val|Vega|Hoya|Foz|Garganta|Hoces|Desfiladero|Cañón)", nombre)) %>% arrange(desc(imp)) %>% slice_head(n = 260)
puertos <- rd_pts("raw/ngbe/Paso_de_montaña.gml"); puertos <- puertos[lengths(st_intersects(puertos, st_buffer(prov, 1000))) > 0, ]
puertos$elev <- terra::extract(dem25, vect(puertos))[,2]
puertos <- puertos %>% filter(grepl("^Puerto", nombre), !is.na(elev)) %>% arrange(desc(elev))
cat("Sierras:", nrow(sierras), " Valles:", nrow(valles), " Puertos:", nrow(puertos), "\n")
cat("  sierras principales:", paste(head(sierras$nombre, 10), collapse = ", "), "\n")
cat("  puertos:", paste(paste0(puertos$nombre, " ", round(puertos$elev)), collapse = ", "), "\n")

# ---------- Ríos (IGN hidrografía, cursos con nombre "Río ...") ----------
cat("Ríos...\n")
rf <- list.files("raw/rios", pattern = "\\.gml$", full.names = TRUE)
rios <- do.call(rbind, lapply(rf, function(f) st_read(f, quiet = TRUE)[, c("gml_id", "text", "upper")]))
rios <- rios[!duplicated(rios$gml_id), ]
cat("tramos únicos:", nrow(rios), "\n")
rios <- st_transform(rios, 25830)
rios <- st_zm(rios)
rios <- st_intersection(rios, st_geometry(prov))
rios <- rios[st_geometry_type(rios) %in% c("LINESTRING", "MULTILINESTRING"), ]
rios <- rios %>% group_by(nombre = text) %>% summarise(ancho = max(upper, na.rm = TRUE), .groups = "drop") %>% st_cast("MULTILINESTRING") %>%
  st_line_merge()
rios$long_km <- round(as.numeric(st_length(rios)) / 1000, 1)
rios <- rios %>% filter(long_km >= 4) %>% arrange(desc(long_km))
rios <- st_simplify(rios, dTolerance = 30)
cat("ríos:", nrow(rios), " principales:", paste(head(rios$nombre, 12), collapse = ", "), "\n")

# ---------- Embalses y lagos (IGN, OGC API Features de la IDEE) ----------
aguas <- st_read("raw/aguas_api/standingwater.geojson", quiet = TRUE) %>% st_transform(25830) %>% st_zm() %>% st_make_valid()
aguas <- aguas[lengths(st_intersects(aguas, prov)) > 0, ]
aguas$area <- as.numeric(st_area(aguas))
aguas <- aguas %>% filter(area > 150000 | (tipo_aestd == "Lago" & area > 20000)) %>%
  transmute(nombre, tipo = tipo_aestd) %>% st_simplify(dTolerance = 15)
cat("aguas:", nrow(aguas), " con nombre:", paste(na.omit(aguas$nombre[aguas$tipo == "Embalse"]), collapse = ", "), "\n")

# ---------- Carreteras (IGN, red de transporte, clase funcional) ----------
clases <- c(mainRoad = 1, firstClass = 2, secondClass = 3)
carr <- do.call(rbind, lapply(names(clases), function(cl) {
  x <- st_read(sprintf("raw/carreteras/%s.geojson", cl), quiet = TRUE)[, "functionalclass"]
  x$clase <- clases[[cl]]; x[, "clase"] }))
carr <- st_transform(carr, 25830) %>% st_zm()
carr <- st_intersection(carr, st_geometry(st_buffer(prov, 1500)))
carr <- carr[st_geometry_type(carr) %in% c("LINESTRING", "MULTILINESTRING"), ]
carr <- carr %>% group_by(clase) %>% summarise(.groups = "drop") %>% st_cast("MULTILINESTRING") %>% st_line_merge() %>%
  st_simplify(dTolerance = 20)
cat("carreteras km por clase:", round(as.numeric(st_length(carr)) / 1000), "\n")

# ---------- Comarcas tradicionales (ficha de cada municipio en Wikipedia) y El Bierzo (Ley 1/1991 de CyL) ----------
cw <- jsonlite::fromJSON("raw/comarcas/comarca_wikipedia.json")
mun$comarca <- vapply(mun$code, function(k) if (!is.null(cw[[k]])) cw[[k]]$comarca else NA_character_, "")
mun$comarca[mun$comarca == "Cabrera"] <- "La Cabrera"
bierzo_ley <- c("Arganza","Balboa","Barjas","Bembibre","Benuza","Berlanga del Bierzo","Borrenes","Cabañas Raras","Cacabelos",
  "Camponaraya","Candín","Valle de Ancares","Carracedelo","Carucedo","Castropodame","Congosto","Corullón","Cubillos del Sil","Fabero",
  "Folgoso de la Ribera","Igüeña","Molinaseca","Noceda del Bierzo","Oencia","Palacios del Sil","Páramo del Sil","Peranzanes",
  "Ponferrada","Priaranza del Bierzo","Puente de Domingo Flórez","Sancedo","Sobrado","Toral de los Vados","Toreno",
  "Torre del Bierzo","Trabadelo","Vega de Espinareda","Vega de Valcarce","Villafranca del Bierzo")
mun$bierzo <- mun$nombre %in% bierzo_ley
cat("Bierzo (ley):", sum(mun$bierzo), " no encontrados:", paste(setdiff(bierzo_ley, mun$nombre), collapse = ", "), "\n")
cat("sin comarca:", paste(mun$nombre[is.na(mun$comarca) & mun$tipo == "municipio"], collapse = ", "), "\n")
# Los condominios no son municipios: heredan la comarca más frecuente entre los municipios con los que lindan
for (i in which(mun$tipo == "condominio")) {
  vec <- mun$comarca[setdiff(st_touches(mun[i, ], mun)[[1]], i)]
  vec <- vec[!is.na(vec)]
  if (length(vec)) mun$comarca[i] <- names(sort(table(vec), decreasing = TRUE))[1]
}
sin <- mun$nombre[is.na(mun$comarca)]
cat("Unidades sin comarca:", length(sin), paste(sin, collapse = ", "), "\n")
# Comarcas agrarias oficiales del MAPA (ComarcasAgrarias.shp de la IDE del MAPA, copia distribuida por rOpenSpain/mapSpain).
# Cada municipio va a la comarca con la que comparte más superficie.
NOMBRES_AGR <- c("BIERZO" = "El Bierzo", "LA MONTAÑA DE LUNA" = "La Montaña de Luna", "LA MONTAÑA DE RIAÑO" = "La Montaña de Riaño",
  "LA CABRERA" = "La Cabrera", "ASTORGA" = "Astorga", "TIERRAS DE LEON" = "Tierras de León", "LA BAÑEZA" = "La Bañeza",
  "EL PARAMO" = "El Páramo", "ESLA-CAMPOS" = "Esla-Campos", "SAHAGUN" = "Sahagún")
cag <- st_read("raw/comarcas_agrarias/comarcas_agrarias.gpkg", quiet = TRUE) %>% filter(cpro == "24") %>%
  st_transform(25830) %>% select(CO_COMARCA, DS_COMARCA)
ixa <- suppressWarnings(st_intersection(mun[, "code"], cag)); ixa$a <- as.numeric(st_area(ixa))
best <- ixa %>% st_drop_geometry() %>% group_by(code) %>% slice_max(a, n = 1, with_ties = FALSE) %>% ungroup()
mun$tradicional <- mun$comarca
mun$comarca <- unname(NOMBRES_AGR[best$DS_COMARCA[match(mun$code, best$code)]])
cat("Comarcas agrarias: sin asignar", sum(is.na(mun$comarca)), "\n"); print(table(mun$comarca))
grp <- mun %>% filter(!is.na(comarca)) %>% group_by(nombre = comarca) %>%
  summarise(n = n(), pob = sum(pob2025, na.rm = TRUE), bierzo = all(bierzo), .groups = "drop")
grp <- rbind(grp, mun %>% filter(bierzo) %>% summarise(nombre = "El Bierzo (comarca oficial)", n = n(), pob = sum(pob2025, na.rm = TRUE), bierzo = TRUE))
grp <- st_simplify(grp, dTolerance = 25)
cat("comarcas:", nrow(grp), "\n")

# ---------- Serialización compacta ----------
poly_coords <- function(g) {           # lista de polígonos -> lista de anillos (int planos)
  g <- st_cast(st_geometry(g), "MULTIPOLYGON")
  lapply(g, function(mp) lapply(unlist(unclass(mp), recursive = FALSE), function(r) as.vector(t(loc(r)))))
}
line_coords <- function(g) {
  lapply(st_geometry(g), function(l) {
    parts <- if (inherits(l, "MULTILINESTRING")) unclass(l) else list(unclass(l))
    lapply(parts, function(p) as.vector(t(loc(p))))
  })
}
pt <- function(p) { xy <- loc(st_coordinates(p)); lapply(seq_len(nrow(xy)), function(i) xy[i,]) }

# ---------- Población histórica (INE, censos 1900-2021 + Padrón 2025, sumando municipios absorbidos) ----------
ANIOS <- c(1900, 1910, 1920, 1930, 1940, 1950, 1960, 1970, 1981, 1991, 2001, 2011, 2021, 2025)
hist <- if (file.exists("raw/historico/censos.json")) jsonlite::fromJSON("raw/historico/censos.json", simplifyVector = FALSE) else list()
serie <- function(k) if (is.null(hist[[k]])) NULL else vapply(as.character(ANIOS), function(a) as.numeric(hist[[k]]$pob[[a]]), 0)
absorbidos <- function(k) if (is.null(hist[[k]])) character(0) else vapply(hist[[k]]$absorbidos, function(x) sub("^\\d+ ", "", x), "")
cat("Series históricas:", sum(vapply(mun$code, function(k) !is.null(hist[[k]]), TRUE)), "\n")
munS <- st_simplify(mun, dTolerance = 18, preserveTopology = TRUE)
provS <- st_simplify(prov, dTolerance = 18)
out <- list(
  meta = list(x0 = X0, y1 = Y1, ancho = X1 - X0, alto = Y1 - Y0, celda = CELL,
              cols = ncol(dem), filas = nrow(dem), crs = "EPSG:25830",
              anios = ANIOS,
              poblacion_total = sum(mun$pob2025, na.rm = TRUE), area_km2 = round(as.numeric(st_area(prov))/1e6),
              fuentes = list(
                relieve = "IGN · MDT25 (WCS servicios.idee.es/wcs-inspire/mdt)",
                limites = "IGN · Unidades administrativas INSPIRE (www.ign.es/wfs-inspire/unidades-administrativas)",
                hidrografia = "IGN · Hidrografía INSPIRE (servicios.idee.es/wfs-inspire/hidrografia)",
                toponimia = "IGN · Nomenclátor Geográfico Básico de España (www.ign.es/wfs-inspire/ngbe)",
                poblacion = "INE · Padrón municipal a 1 de enero de 2025 (tabla 2877)",
                carreteras = "IGN · Red de transporte, clase funcional (api-features.idee.es, roadlink)",
                historico = "INE · Alteraciones de los municipios en los Censos de Población desde 1842 (población de derecho; se suman los municipios absorbidos)",
                localidades = "IGN · NGBE (entidades singulares, núcleos, capitales de EATIM y entidades menores); población: INE · Nomenclátor a 1 de enero de 2025",
                orografia = "IGN · Nomenclátor Geográfico Básico (cumbres, alineaciones montañosas, depresiones y pasos); altitudes del MDT25",
                comarcas = "MAPA · Comarcas agrarias (ComarcasAgrarias.shp de la IDE del MAPA, vía rOpenSpain/mapSpain); El Bierzo oficial: Ley 1/1991 de Castilla y León",
                comarcas_tradicionales = "Comarca tradicional de cada municipio según su ficha en es.wikipedia.org (no oficial)")),
  provincia = poly_coords(provS)[[1]],
  municipios = lapply(seq_len(nrow(munS)), function(i) list(
    c = munS$code[i], n = munS$nombre[i], t = munS$tipo[i], p = munS$pob2025[i], a = munS$area_km2[i],
    cap = munS$capital[i], cm = munS$comarca[i], ct = munS$tradicional[i], bz = munS$bierzo[i], ph = serie(munS$code[i]), abs = absorbidos(munS$code[i]), amin = munS$alt_min[i], amax = munS$alt_max[i], amed = munS$alt_med[i],
    g = poly_coords(munS[i, ])[[1]])),
  rios = lapply(seq_len(nrow(rios)), function(i) list(n = rios$nombre[i], k = rios$long_km[i],
    w = rios$ancho[i], g = line_coords(rios[i, ])[[1]])),
  aguas = lapply(seq_len(nrow(aguas)), function(i) list(n = aguas$nombre[i], t = aguas$tipo[i],
    g = poly_coords(aguas[i, ])[[1]])),
  capitales = lapply(seq_len(nrow(capmun)), function(i) list(n = capmun$nombre[i], c = capmun$code[i],
    p = if (is.na(capmun$pob_nucleo[i])) NULL else capmun$pob_nucleo[i], xy = pt(capmun[i, ])[[1]])),
  entidades = lapply(seq_len(nrow(ent)), function(i) list(n = ent$nombre[i], c = ent$municipio[i],
    p = if (is.na(ent$pob[i])) NULL else ent$pob[i], xy = pt(ent[i, ])[[1]])),
  carreteras = lapply(seq_len(nrow(carr)), function(i) list(c = carr$clase[i], g = line_coords(carr[i, ])[[1]])),
  comarcas = lapply(seq_len(nrow(grp)), function(i) list(n = grp$nombre[i], m = grp$n[i], p = grp$pob[i], bz = grp$bierzo[i],
    g = poly_coords(grp[i, ])[[1]])),
  orografia = list(
    sierras = lapply(seq_len(nrow(sierras)), function(i) list(n = sierras$nombre[i], e = round(sierras$elev[i]), xy = pt(sierras[i, ])[[1]])),
    valles  = lapply(seq_len(nrow(valles)),  function(i) list(n = valles$nombre[i],  e = round(valles$elev[i]),  xy = pt(valles[i, ])[[1]])),
    puertos = lapply(seq_len(nrow(puertos)), function(i) list(n = puertos$nombre[i], e = round(puertos$elev[i]), xy = pt(puertos[i, ])[[1]]))),
  picos = lapply(seq_len(nrow(picos)), function(i) list(n = picos$nombre[i], e = round(picos$elev[i]),
    xy = pt(picos[i, ])[[1]]))
)
write_json(out, "web/data/leon.json", auto_unbox = TRUE, digits = NA)
cat("JSON:", round(file.size("web/data/leon.json")/1e6, 2), "MB\n")
