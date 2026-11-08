# Mapa de escaramuza de la provincia de León para 0 A.D. (0.28), generado con datos oficiales.
#  · Relieve: MDT25 del IGN (más franjas de Asturias y Zamora para hacer el mapa cuadrado)
#  · Cubierta y bosques: Copernicus CLC+ Backbone 2021
#  · Ríos, embalses, poblaciones y monumentos: datos del visor (web/data/leon.json, IGN)
# Uso: Rscript juegos/0ad/generar_mapa_leon.R [2|4|8]  (jugadores; por defecto 8)
# Salida: juegos/0ad/user/maps/skirmishes/leon_<n>p.{pmp,xml} y su vista previa.
# Para jugarlo basta con copiar juegos/0ad/user/ dentro de la carpeta de mods de 0 A.D. (ver instalar.sh).
suppressMessages({library(sf); library(terra); library(jsonlite); library(png)})
set.seed(24089)

N      <- 512                    # casillas por lado (Gigante); 32 parches de 16
X0     <- 164000; X1 <- 360000   # 196 km
Y0     <- 4624500; Y1 <- 4820500
CELL   <- (X1 - X0) / N          # ~383 m por casilla
UNID   <- 4                      # unidades del juego por casilla
AGUA   <- 20                     # altura del agua (unidades)
K      <- 0.035                  # unidades del juego por metro de desnivel sobre el fondo del valle (~3,5× de exageración)
SALIDA <- "juegos/0ad/user"
dir.create(file.path(SALIDA, "maps/skirmishes"), recursive = TRUE, showWarnings = FALSE)
dir.create(file.path(SALIDA, "art/textures/ui/session/icons/mappreview"), recursive = TRUE, showWarnings = FALSE)
paso <- function(...) cat(format(Sys.time(), "%H:%M:%S"), "·", ..., "\n")

# ---------- relieve en los vértices (N+1 × N+1), fila 1 = norte ----------
paso("Relieve")
mdt <- vrt(c(list.files("raw/mdt25", "\\.tif$", full.names = TRUE), list.files("raw/mdt25_extra", "\\.tif$", full.names = TRUE)))
crs(mdt) <- "EPSG:25830"
gv <- rast(xmin = X0 - CELL / 2, xmax = X1 + CELL / 2, ymin = Y0 - CELL / 2, ymax = Y1 + CELL / 2, ncols = N + 1, nrows = N + 1, crs = "EPSG:25830")
dem <- resample(mdt, gv, method = "average")
dem[is.na(dem) | dem < -50] <- NA
dem <- focal(dem, 5, "mean", na.policy = "only", na.rm = TRUE); dem[is.na(dem)] <- 400
H <- as.matrix(dem, wide = TRUE)                      # filas: norte → sur
# fondo de valle local: mínimo en ~12 km suavizado; la altura de juego es el desnivel sobre él
fondo <- focal(dem, 31, "min", na.rm = TRUE)
fondo <- focal(fondo, focalMat(fondo, CELL * 8, "Gauss"), "sum", na.rm = TRUE)
Hrel <- pmax(H - as.matrix(fondo, wide = TRUE), 0)
alt <- AGUA + 0.8 + Hrel * K                          # unidades del juego

# ---------- rejilla de casillas (N × N) ----------
gt <- rast(xmin = X0, xmax = X1, ymin = Y0, ymax = Y1, ncols = N, nrows = N, crs = "EPSG:25830")
prov <- vect(st_read("raw/provincia.gpkg", quiet = TRUE))
enProv <- as.matrix(rasterize(prov, gt, background = 0), wide = TRUE) > 0
Ht <- as.matrix(resample(dem, gt), wide = TRUE)       # altitud real por casilla (m)

# cubierta de Copernicus (dos mitades a 100 m en UTM; se les pone la georreferencia pedida)
cob <- lapply(list(c("s", 4624500, 4722500), c("n", 4722500, 4820500)), function(p) {
  r <- rast(sprintf("raw/copernicus/clcplus_0ad/cuadrado_%s.tif", p[1]))[[1]]
  ext(r) <- ext(X0, X1, as.numeric(p[2]), as.numeric(p[3])); crs(r) <- "EPSG:25830"; r })
cob <- merge(cob[[1]], cob[[2]])
C <- as.matrix(resample(cob, gt, method = "mode"), wide = TRUE); C[is.na(C)] <- 0

# ríos, embalses y poblaciones del visor (coordenadas locales: x desde 164000, y desde 4790000 hacia el sur)
web <- fromJSON("web/data/leon.json", simplifyVector = FALSE)
a_utm <- function(v) { v <- unlist(v); cbind(web$meta$x0 + v[c(TRUE, FALSE)], web$meta$y1 - v[c(FALSE, TRUE)]) }
lin <- function(lst) st_sf(k = vapply(lst, function(r) r$k, 0), geometry = st_sfc(lapply(lst, function(r) st_multilinestring(lapply(r$g, a_utm))), crs = 25830))
rios <- lin(web$rios); rios <- rios[rios$k >= 12, ]
pol <- function(rings) st_polygon(lapply(rings, function(r) { m <- a_utm(r); rbind(m, m[1, ]) }))
aguas <- st_sf(n = vapply(web$aguas, function(a) if (is.null(a$n)) "" else a$n, ""),
               geometry = st_sfc(lapply(web$aguas, function(a) pol(a$g)), crs = 25830)) |> st_make_valid()
rioM  <- as.matrix(rasterize(vect(st_buffer(rios, ifelse(rios$k > 60, CELL * 0.9, CELL * 0.45))), gt, background = 0), wide = TRUE) > 0
lagoM <- as.matrix(rasterize(vect(aguas), gt, background = 0, touches = FALSE), wide = TRUE) > 0
cat("casillas de río:", sum(rioM), " de embalse:", sum(lagoM), "\n")

# ---------- bases de los jugadores ----------
VARIANTES <- list(`2` = c("León", "Ponferrada"), `4` = c("León", "Ponferrada", "Astorga", "Sahagún"),
                  `8` = c("León", "Ponferrada", "Astorga", "La Bañeza", "Valencia de Don Juan", "Sahagún", "Villablino", "Cistierna"))
NJ <- commandArgs(TRUE)[1]; if (is.na(NJ) || !NJ %in% names(VARIANTES)) NJ <- "8"
bases <- VARIANTES[[NJ]]; ID <- sprintf("leon_%sp", NJ)
cat("Variante:", ID, "·", paste(bases, collapse = ", "), "\n")
caps <- web$capitales
xy_base <- t(vapply(bases, function(b) { c <- Find(function(x) sub(" / .*", "", x$n) == b, caps); a_utm(c$xy) }, c(0, 0)))
a_casilla <- function(xy) cbind(col = (xy[, 1] - X0) / CELL, fila = (Y1 - xy[, 2]) / CELL)   # en casillas, fila desde el norte
bc <- a_casilla(xy_base)
RB <- 9                                                # radio (casillas) que se allana y se deja sin agua
for (i in seq_len(nrow(bc))) {
  cc <- bc[i, ]; ii <- outer(seq_len(N + 1) - 1 - cc["fila"], rep(1, N + 1)); jj <- outer(rep(1, N + 1), seq_len(N + 1) - 1 - cc["col"])
  d <- sqrt(ii^2 + jj^2); dentro <- d <= RB
  nivel <- max(AGUA + 2, mean(alt[dentro]))
  w <- pmin(1, pmax(0, (RB + 4 - d) / 4)); alt <- alt * (1 - w) + nivel * w
  it <- outer(seq_len(N) - 0.5 - cc["fila"], rep(1, N)); jt <- outer(rep(1, N), seq_len(N) - 0.5 - cc["col"])
  sin_agua <- sqrt(it^2 + jt^2) <= RB + 2; rioM[sin_agua] <- FALSE; lagoM[sin_agua] <- FALSE
}

# ---------- agua: ríos vadeables y embalses profundos (sobre los vértices de sus casillas) ----------
marca <- function(M, prof) {
  v <- matrix(FALSE, N + 1, N + 1)
  v[1:N, 1:N] <- v[1:N, 1:N] | M; v[2:(N + 1), 1:N] <- v[2:(N + 1), 1:N] | M
  v[1:N, 2:(N + 1)] <- v[1:N, 2:(N + 1)] | M; v[2:(N + 1), 2:(N + 1)] <- v[2:(N + 1), 2:(N + 1)] | M
  alt[v] <<- pmin(alt[v], AGUA - prof)
}
marca(rioM, 1.1)                       # menos de 2 unidades: se puede vadear
lagoInt <- lagoM & (as.matrix(focal(rast(lagoM * 1), 3, "min", na.rm = TRUE), wide = TRUE) > 0)
marca(lagoM, 1.5); marca(lagoInt, 5)
alt <- pmin(pmax(alt, 0), 700)

# ---------- carreteras principales (IGN): perfil suavizado para que los puertos sean transitables ----------
carr <- Filter(function(c) c$c <= 2, web$carreteras)
caminos <- matrix(FALSE, N, N)
PEND_MAX <- 0.55 * 0.5                                  # unidades de desnivel por media casilla (pendiente 0,55)
for (cr in carr) for (parte in cr$g) {
  m <- a_utm(parte); if (nrow(m) < 2) next
  cs <- a_casilla(m); seg <- sqrt(rowSums(diff(cs)^2)); L <- sum(seg); if (L < 2) next
  t <- c(0, cumsum(seg)); ns <- max(2, ceiling(L * 2))
  cx <- approx(t, cs[, 1], seq(0, L, length.out = ns))$y; cz <- approx(t, cs[, 2], seq(0, L, length.out = ns))$y
  vi <- pmin(N + 1, pmax(1, round(cz) + 1)); vj <- pmin(N + 1, pmax(1, round(cx) + 1))
  pr <- alt[cbind(vi, vj)]
  if (ns >= 9) { pr <- as.numeric(stats::filter(pr, rep(1 / 9, 9), sides = 2)); pr[is.na(pr)] <- alt[cbind(vi, vj)][is.na(pr)] }
  for (it in 1:3) {                                     # limitar la pendiente en ambos sentidos
    for (k in 2:ns) pr[k] <- min(max(pr[k], pr[k - 1] - PEND_MAX), pr[k - 1] + PEND_MAX)
    for (k in (ns - 1):1) pr[k] <- min(max(pr[k], pr[k + 1] - PEND_MAX), pr[k + 1] + PEND_MAX)
  }
  pr <- pmax(pr, AGUA + 0.3)                            # vado: nunca por debajo de 0,3 sobre el agua
  for (k in seq_len(ns)) for (di in -1:1) for (dj in -1:1) {
    i2 <- vi[k] + di; j2 <- vj[k] + dj; if (i2 < 1 || j2 < 1 || i2 > N + 1 || j2 > N + 1) next
    w <- if (di == 0 && dj == 0) 1 else 0.6
    alt[i2, j2] <- alt[i2, j2] * (1 - w) + pr[k] * w
  }
  ti <- pmin(N, pmax(1, ceiling(cz))); tj <- pmin(N, pmax(1, ceiling(cx))); caminos[cbind(ti, tj)] <- TRUE
}
cat("casillas de carretera:", sum(caminos), "\n")

# ---------- texturas por casilla ----------
pend <- matrix(0, N, N)
for (di in 0:1) for (dj in 0:1) pend <- pmax(pend, abs(alt[1:N + di, 1:N + dj] - alt[1:N + 1 - di, 1:N + 1 - dj]))
tex <- matrix("temp_grass", N, N); alta <- Ht > 1400
tex[C == 6] <- "temp_grass_long"; tex[C == 6 & alta] <- "alpine_grass_a"
tex[C == 7] <- "medit_grass_field_b"; tex[C == 7 & Ht < 900 & (runif(N * N) < 0.4)] <- "steppe_grass_a"
tex[C == 5] <- "medit_shrubs"; tex[C == 5 & alta] <- "alpine_grass_rocky"
tex[C == 2] <- "temp_forestfloor_pine"; tex[C == 3] <- "temp_forestfloor_a"; tex[C == 4] <- "medit_forestfloor_a"
tex[C == 1] <- "medit_city_pavement"; tex[C == 8] <- "alpine_grass_rocky"; tex[C == 9] <- "alpine_rock_01"
tex[C == 10] <- "temp_grass_wet"; tex[C == 11 | Ht > 2200] <- "alpine_snow_a"
tex[pend > 4] <- ifelse(Ht[pend > 4] > 1500, "alpine_cliff_a", "temp_cliff_a")
tex[rioM] <- "temp_mud_a"; tex[lagoM] <- "medit_sand_wet"; tex[lagoInt] <- "temp_mud_a"
tex[caminos & !lagoM] <- "temp_road"
texturas <- unique(c("temp_grass", sort(unique(as.vector(tex)))))
cat("texturas:", length(texturas), paste(texturas, collapse = ", "), "\n")

# ---------- conectividad: ¿se puede ir de León a todas las bases? (reglas de paso del juego) ----------
prof <- AGUA - pmin(alt[1:N, 1:N], alt[2:(N + 1), 1:N], alt[1:N, 2:(N + 1)], alt[2:(N + 1), 2:(N + 1)])
pasable <- pend / UNID < 1 & prof < 2
alcanza <- matrix(FALSE, N, N); ini <- round(bc["León", c("fila", "col")]) + 1
cola <- matrix(ini, 1); alcanza[ini[1], ini[2]] <- TRUE
while (nrow(cola)) {
  nb <- rbind(cbind(cola[, 1] - 1, cola[, 2]), cbind(cola[, 1] + 1, cola[, 2]), cbind(cola[, 1], cola[, 2] - 1), cbind(cola[, 1], cola[, 2] + 1))
  nb <- nb[nb[, 1] >= 1 & nb[, 1] <= N & nb[, 2] >= 1 & nb[, 2] <= N, , drop = FALSE]
  nb <- unique(nb[pasable[nb] & !alcanza[nb], , drop = FALSE]); alcanza[nb] <- TRUE; cola <- nb
}
ok <- vapply(seq_len(nrow(bc)), function(i) alcanza[min(N, round(bc[i, "fila"]) + 1), min(N, round(bc[i, "col"]) + 1)], TRUE)
cat("transitable:", round(100 * mean(pasable)), "% · alcanzable desde León:", round(100 * mean(alcanza)), "% · bases conectadas:",
    paste(paste0(rownames(bc), ifelse(ok, " ✓", " ✗")), collapse = ", "), "\n")

# ---------- fichero PMP (versión 7) ----------
paso("PMP")
f <- file(file.path(SALIDA, "maps/skirmishes", paste0(ID, ".pmp")), "wb")
cuerpo <- rawConnection(raw(0), "wb")
writeBin(as.integer(N / 16), cuerpo, size = 4, endian = "little")
hv <- round(alt[(N + 1):1, ] * 92)                    # el juego guarda las filas de sur a norte; altura × 92
writeBin(as.integer(t(hv)), cuerpo, size = 2, endian = "little")
writeBin(length(texturas), cuerpo, size = 4, endian = "little")
for (tx in texturas) { writeBin(nchar(tx, "bytes"), cuerpo, size = 4, endian = "little"); writeBin(charToRaw(tx), cuerpo) }
idx <- matrix(match(tex, texturas) - 1L, N, N)[N:1, ]  # sur → norte
casillas <- as.vector(t(idx))
bloque <- matrix(as.raw(0), 8, length(casillas))
bloque[1, ] <- as.raw(casillas %% 256); bloque[2, ] <- as.raw(casillas %/% 256)
bloque[3, ] <- as.raw(255); bloque[4, ] <- as.raw(255)          # segunda textura: ninguna (0xFFFF)
pri <- casillas                                                     # prioridad de mezcla = orden de textura
bloque[5, ] <- as.raw(pri %% 256); bloque[6, ] <- as.raw(pri %/% 256)
writeBin(as.vector(bloque), cuerpo)
datos <- rawConnectionValue(cuerpo); close(cuerpo)
writeBin(charToRaw("PSMP"), f); writeBin(c(7L, length(datos)), f, size = 4, endian = "little"); writeBin(datos, f); close(f)

# ---------- entidades ----------
paso("Entidades")
ents <- list(); add <- function(tpl, x, z, jug = 0, rot = runif(1, -pi, pi)) ents[[length(ents) + 1]] <<- list(tpl, x, z, jug, rot)
pos <- function(col, fila) c(x = unname(col) * UNID, z = (N - unname(fila)) * UNID)    # casilla → coordenadas del juego (z hacia el norte)
lejos_bases <- function(col, fila, r = RB + 3) all(sqrt((bc[, "col"] - col)^2 + (bc[, "fila"] - fila)^2) > r)
alt_c <- function(col, fila) alt[min(N + 1, max(1, round(fila) + 1)), min(N + 1, max(1, round(col) + 1))]
seco <- function(col, fila) alt_c(col, fila) > AGUA + 0.5

# bosques: solo en manchas continuas, para no sembrar árboles sueltos por todo el mapa
bosque <- (C >= 2 & C <= 4) * 1
mancha <- as.matrix(focal(rast(bosque), 5, "mean", na.rm = TRUE), wide = TRUE)
for (fi in seq_len(N)) for (co in seq_len(N)) {
  cl <- C[fi, co]; if (cl < 2 || cl > 4 || mancha[fi, co] < 0.45 || pend[fi, co] > 4) next
  if (runif(1) > 0.42) next
  col <- co - runif(1); fila <- fi - runif(1)
  if (!lejos_bases(col, fila) || !seco(col, fila)) next
  tpl <- if (cl == 2) sample(c("gaia/tree/pine", "gaia/tree/pine_black"), 1, prob = c(0.7, 0.3))
         else if (cl == 4) "gaia/tree/oak_holly"
         else if (Ht[fi, co] > 1000 && fi < N * 0.45) sample(c("gaia/tree/euro_beech", "gaia/tree/oak"), 1, prob = c(0.6, 0.4))
         else sample(c("gaia/tree/oak", "gaia/tree/temperate", "gaia/tree/euro_birch"), 1, prob = c(0.6, 0.3, 0.1))
  p <- pos(col, fila); add(tpl, p["x"], p["z"])
}
# choperas junto a los ríos del llano
orilla <- as.matrix(focal(rast(rioM * 1), 3, "max", na.rm = TRUE), wide = TRUE) > 0 & !rioM & Ht < 950
for (k in which(orilla & matrix(runif(N * N), N, N) < 0.18)) {
  fi <- (k - 1) %% N + 1; co <- (k - 1) %/% N + 1; col <- co - runif(1); fila <- fi - runif(1)
  if (lejos_bases(col, fila) && seco(col, fila)) { p <- pos(col, fila); add("gaia/tree/poplar_lombardy", p["x"], p["z"]) }
}
cat("árboles:", length(ents), "\n")

# recursos repartidos según el terreno
sorteo <- function(n, cond, tpl, grupo = 1, radio = 2) {
  cand <- which(matrix(cond, N, N), arr.ind = TRUE); if (!nrow(cand)) return(invisible())
  for (s in sample(nrow(cand), min(n, nrow(cand)))) {
    fila <- cand[s, 1] - 0.5; col <- cand[s, 2] - 0.5
    if (!lejos_bases(col, fila, RB + 6) || !seco(col, fila)) next
    for (g in seq_len(grupo)) { cg <- col + runif(1, -radio, radio); fg <- fila + runif(1, -radio, radio)
      if (seco(cg, fg)) { p <- pos(cg, fg); add(tpl, p["x"], p["z"]) } }
  }
}
llano <- pend < 1.5
filaM <- matrix(seq_len(N), N, N)                      # fila (1 = norte)
norte <- filaM < N * 0.45                              # la Cordillera y el Bierzo alto
montana <- Ht > 1100 & pend < 2.6
sorteo(45, montana & norte, "gaia/ore/temperate_large")               # metal: la montaña minera
sorteo(30, montana, "gaia/rock/temperate_large")                       # piedra en la montaña
mar <- matrix(FALSE, N, N)                                             # Maragatería (al oeste y sur de Astorga)
cA <- a_casilla(a_utm(Find(function(x) sub(" / .*", "", x$n) == "Astorga", caps)$xy))[1, ]; mar[abs(filaM - cA["fila"]) < 35 & abs(matrix(seq_len(N), N, N, byrow = TRUE) - (cA["col"] - 25)) < 30] <- TRUE
sorteo(12, mar & llano, "gaia/rock/temperate_large")
sorteo(14, llano & !norte, "gaia/rock/temperate_small")
sorteo(14, llano & !norte, "gaia/ore/temperate_small")
# oro de Las Médulas
med <- a_casilla(matrix(c(164000 + 26002, 4790000 - 82202), 1))
for (g in 1:8) { cg <- med[1] + runif(1, -6, 6); fg <- med[2] + runif(1, -6, 6); if (seco(cg, fg)) { p <- pos(cg, fg); add("gaia/ore/temperate_large", p["x"], p["z"]) } }
# fauna
sorteo(120, C %in% c(2, 3) & mancha > 0.6, "gaia/fauna_deer", grupo = 3)
sorteo(50, C %in% c(3, 4, 5), "gaia/fauna_boar", grupo = 2)
sorteo(18, montana & norte, "gaia/fauna_wolf", grupo = 3)
sorteo(9, montana & norte & C %in% c(3, 5), "gaia/fauna_bear_brown")
sorteo(70, llano & C %in% c(6, 7), "gaia/fauna_sheep", grupo = 4)
sorteo(40, C %in% c(5, 6), "gaia/fruit/berry_01", grupo = 4, radio = 1)
# peces en los embalses
for (k in sample(which(lagoInt), min(60, sum(lagoInt)))) { fi <- (k - 1) %% N + 1; co <- (k - 1) %/% N + 1; p <- pos(co - 0.5, fi - 0.5); add("gaia/fish/generic", p["x"], p["z"]) }

# bases: centro cívico, unidades y recursos cercanos para cada jugador
for (i in seq_len(nrow(bc))) {
  cc <- bc[i, ]; p <- pos(cc["col"], cc["fila"]); jug <- i
  add("skirmish/structures/default_civil_centre", p["x"], p["z"], jug, rot = 2.356)
  uni <- c(rep("skirmish/units/default_support_female_citizen", 4), rep("skirmish/units/default_infantry_melee_b", 2),
           rep("skirmish/units/default_infantry_ranged_b", 2), "skirmish/units/default_cavalry")
  for (u in seq_along(uni)) { a <- u / length(uni) * 2 * pi; add(uni[u], p["x"] + cos(a) * 22, p["z"] + sin(a) * 22, jug) }
  a0 <- runif(1, 0, 2 * pi)
  for (b in 1:5) { a <- a0 + b * 0.12; add("gaia/fruit/berry_01", p["x"] + cos(a) * 34, p["z"] + sin(a) * 34) }
  for (r in 1:2) { a <- a0 + pi * 0.6 + r * pi * 0.5; add(c("gaia/ore/temperate_large", "gaia/rock/temperate_large")[r], p["x"] + cos(a) * 50, p["z"] + sin(a) * 50) }
  for (t in 1:30) { a <- a0 + pi + runif(1, -0.5, 0.5); d <- runif(1, 52, 68); add("gaia/tree/oak", p["x"] + cos(a) * d, p["z"] + sin(a) * d) }
  for (h in 1:4) { a <- a0 + pi * 1.5 + h * 0.15; add("gaia/fauna_deer", p["x"] + cos(a) * 45, p["z"] + sin(a) * 45) }
}
cat("entidades:", length(ents), "\n")

# ---------- XML del escenario ----------
paso("XML")
ent_xml <- vapply(seq_along(ents), function(i) {
  e <- ents[[i]]
  sprintf('\t\t<Entity uid="%d">\n\t\t\t<Template>%s</Template>\n\t\t\t<Player>%d</Player>\n\t\t\t<Position x="%.3f" z="%.3f"/>\n\t\t\t<Orientation y="%.4f"/>\n\t\t</Entity>',
          i + 999, e[[1]], as.integer(e[[4]]), e[[2]], e[[3]], e[[5]])
}, "")
ajustes <- list(CircularMap = FALSE,
  Description = paste("La provincia de León con su relieve real (MDT25 del IGN), bosques de Copernicus, ríos y embalses.",
                      sprintf("Bases en %s.", paste(bases, collapse = ", ")),
                      "Oro en Las Médulas, metal en la montaña minera, osos y lobos en la Cordillera Cantábrica. Los ríos se pueden vadear."),
  Keywords = list(), Name = sprintf("León (%s)", NJ), PlayerData = c(list(NULL), rep(list(setNames(list(), character(0))), length(bases))),
  Preview = paste0(ID, ".png"), VictoryConditions = list("conquest"))
leon <- pos(bc["León", "col"], bc["León", "fila"])
xml <- c('<?xml version="1.0" encoding="UTF-8"?>', '', '<Scenario version="7">', '\t<Environment>',
  '\t\t<SkySet>cumulus</SkySet>', '\t\t<SunColor r="1.15" g="1.07" b="0.93"/>', '\t\t<SunElevation angle="0.68"/>', '\t\t<SunRotation angle="-0.9"/>',
  '\t\t<AmbientColor r="0.36" g="0.40" b="0.48"/>',
  '\t\t<Fog>', '\t\t\t<FogFactor>0.0004</FogFactor>', '\t\t\t<FogThickness>0.2</FogThickness>', '\t\t\t<FogColor r="0.80" g="0.85" b="0.90"/>', '\t\t</Fog>',
  '\t\t<Water>', '\t\t\t<WaterBody>', '\t\t\t\t<Type>lake</Type>', '\t\t\t\t<Color r="0.22" g="0.38" b="0.42"/>', '\t\t\t\t<Tint r="0.28" g="0.42" b="0.45"/>',
  sprintf('\t\t\t\t<Height>%.1f</Height>', AGUA), '\t\t\t\t<Waviness>2</Waviness>', '\t\t\t\t<Murkiness>0.6</Murkiness>', '\t\t\t\t<WindAngle>0.5</WindAngle>',
  '\t\t\t</WaterBody>', '\t\t</Water>',
  '\t\t<Postproc>', '\t\t\t<Brightness>0.0</Brightness>', '\t\t\t<Contrast>1.03</Contrast>', '\t\t\t<Saturation>1.05</Saturation>', '\t\t\t<Bloom>0.15</Bloom>', '\t\t\t<PostEffect>hdr</PostEffect>', '\t\t</Postproc>',
  '\t</Environment>', '\t<Camera>', sprintf('\t\t<Position x="%.1f" y="%.1f" z="%.1f"/>', leon["x"], AGUA + 120, leon["z"] - 110),
  '\t\t<Rotation angle="0"/>', '\t\t<Declination angle="0.61"/>', '\t</Camera>',
  '\t<ScriptSettings><![CDATA[', toJSON(ajustes, auto_unbox = TRUE, pretty = TRUE, null = "null"), ']]></ScriptSettings>',
  '\t<Entities>', ent_xml, '\t</Entities>', '\t<Paths/>', '</Scenario>')
writeLines(xml, file.path(SALIDA, "maps/skirmishes", paste0(ID, ".xml")), useBytes = TRUE)

# ---------- vista previa (512 × 512) ----------
paso("Vista previa")
paleta <- c(temp_grass = "#8db35a", temp_grass_long = "#7ea84f", alpine_grass_a = "#a7b56e", medit_grass_field_b = "#d8c27a", steppe_grass_a = "#cbb56f",
  medit_shrubs = "#9b9a62", alpine_grass_rocky = "#a4a184", temp_forestfloor_pine = "#3e6a45", temp_forestfloor_a = "#4f8a3c", medit_forestfloor_a = "#6b7a45",
  medit_city_pavement = "#b9ab98", alpine_rock_01 = "#9a9aa2", temp_grass_wet = "#7fae7a", alpine_snow_a = "#f4f6fb", temp_cliff_a = "#7d7464",
  alpine_cliff_a = "#8c8a90", temp_mud_a = "#4f9fbd", medit_sand_wet = "#7fc6cf", temp_road = "#c8b48a")
rgbm <- col2rgb(ifelse(is.na(paleta[tex]), "#8db35a", paleta[tex])) / 255
img <- array(0, c(N, N, 3)); for (k in 1:3) img[, , k] <- matrix(rgbm[k, ], N, N)
sombra <- 0.75 + 0.25 * pmin(1, pmax(-1, (alt[1:N, 1:N] - alt[2:(N + 1), 2:(N + 1)]) / 3))
for (k in 1:3) img[, , k] <- pmin(1, img[, , k] * sombra)
for (i in seq_len(nrow(bc))) { r <- round(bc[i, "fila"]) + (-4:4); c <- round(bc[i, "col"]) + (-4:4); img[r, c, 1] <- 0.95; img[r, c, 2] <- 0.75; img[r, c, 3] <- 0.2 }
writePNG(img, file.path(SALIDA, "art/textures/ui/session/icons/mappreview", paste0(ID, ".png")))
paso("Listo:", ID, round(file.size(file.path(SALIDA, "maps/skirmishes", paste0(ID, ".pmp"))) / 1e6, 1), "MB ·",
     round(file.size(file.path(SALIDA, "maps/skirmishes", paste0(ID, ".xml"))) / 1e6, 1), "MB de XML")
