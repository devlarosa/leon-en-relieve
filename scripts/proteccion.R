#!/usr/bin/env Rscript
# Figuras de protección de la zona -> web/data/<zona>/proteccion.json
# Entrada: raw/<zona>/proteccion/ (scripts/descargar_proteccion.sh). Necesita los paquetes sf y jsonlite.
# Dos juegos de fuentes, según «procesado.proteccion» de la ficha de la zona:
#  «cyl» (León, por defecto): Red de Espacios Naturales y Red Natura 2000 de la Junta de Castilla y León,
#        con sus fichas (patrimonionatural.org), y los Bienes de Interés Cultural inmuebles de la Junta
#  «nacional» (zonas de varias comunidades, como Picos): Espacios Naturales Protegidos y Red Natura 2000 del
#        MITECO (Banco de Datos de la Naturaleza); sin BIC (no hay una capa abierta común a Asturias y Cantabria)
#  En las dos: Reservas de la Biosfera (MITECO-OAPN), con su zonificación (núcleo, tampón, transición)
# Las geometrías se recortan a la provincia, se simplifican y se pasan a las coordenadas del visor
# (metros desde x0 hacia el este y desde y1 hacia el sur, como en leon.json).
suppressMessages({ library(sf); library(jsonlite) })
sf_use_s2(FALSE)
args <- commandArgs(trailingOnly = FALSE)
RAIZ <- normalizePath(file.path(dirname(sub("^--file=", "", args[grep("^--file=", args)])), ".."))
setwd(RAIZ); source("R/zona.R")   # ZONA, FICHA, fr() = raw/<zona>/…, fw() = web/data/<zona>/…
RAW <- file.path(RAIZ, "raw", ZONA, "proteccion")
L <- fromJSON(file.path(RAIZ, "web", "data", ZONA, "zona.json"), simplifyVector = FALSE)
M <- L$meta

# provincia (desde leon.json, en EPSG:25830)
anillos <- lapply(L$provincia, function(r) {
  v <- unlist(r); a <- cbind(v[c(TRUE, FALSE)] + M$x0, M$y1 - v[c(FALSE, TRUE)])
  if (any(a[1, ] != a[nrow(a), ])) a <- rbind(a, a[1, ]); a
})
prov <- st_make_valid(st_sfc(st_multipolygon(lapply(anillos, function(a) list(a))), crs = 25830))

leer <- function(f) st_make_valid(st_zm(st_transform(st_read(file.path(RAW, f), quiet = TRUE), 25830)))
FUENTES <- if (is.null(FICHA$procesado$proteccion)) "cyl" else FICHA$procesado$proteccion
# solo lo que tiene en la provincia al menos 1 km² o el 2 % de su superficie (descarta las vecinas que solo rozan el límite)
en_leon <- function(x) {
  x <- x[lengths(st_intersects(x, prov)) > 0, ]
  dentro <- suppressWarnings(st_intersection(st_geometry(x), prov))
  a_in <- as.numeric(st_area(dentro)); a_tot <- as.numeric(st_area(st_geometry(x)))
  ok <- a_in >= 1e6 | a_in / pmax(a_tot, 1) >= 0.02
  x <- x[ok, ]; st_geometry(x) <- dentro[ok]
  x$ha_tot <- round(a_tot[ok] / 1e4); x$ha_leon <- round(a_in[ok] / 1e4); x
}
# geometría -> lista de anillos [x, y, x, y, ...] en coordenadas del visor (enteros, metros)
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
rotulo <- function(g) { c0 <- st_coordinates(st_point_on_surface(st_sfc(g, crs = 25830)))[1, ]; as.integer(round(c(c0[1] - M$x0, M$y1 - c0[2]))) }
fecha <- function(v) ifelse(is.na(v), NA, format(as.Date(v), "%Y-%m-%d"))
# «IGLESIA DE SANTA MARÍA DEL CAMINO» -> «Iglesia de Santa María del Camino»
MENORES <- c("de", "del", "la", "las", "el", "los", "y", "e", "en", "a", "al", "o", "u", "con", "por", "sobre", "entre")
ROMANOS <- "^(i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv|xv|xvi|xvii|xviii|xix|xx)$"
# tildes que faltan en algunos nombres del registro (solo palabras que nunca se escriben sin ella)
TILDES <- list(Asuncion = "Asunción", Nicolas = "Nicolás", Maria = "María", Martin = "Martín", Tomas = "Tomás", Andres = "Andrés",
               Roman = "Román", Julian = "Julián", Sebastian = "Sebastián", Millan = "Millán", Adrian = "Adrián", Cristobal = "Cristóbal",
               Angel = "Ángel", Ines = "Inés", Jose = "José", Fabian = "Fabián", Basilica = "Basílica", Iglesia_ = "Iglesia",
               Concepcion = "Concepción", Salvacion = "Salvación", Encarnacion = "Encarnación", Transfiguracion = "Transfiguración",
               Purisima = "Purísima", Leon = "León", Ponferrada = "Ponferrada", Lucia = "Lucía", Garcia = "García", Vazquez = "Vázquez",
               Gutierrez = "Gutiérrez", Rodriguez = "Rodríguez", Fernandez = "Fernández", Gonzalez = "González", Sanchez = "Sánchez")
bonito <- function(s) {
  s <- gsub("\\s+", " ", trimws(s)); if (is.na(s) || !nzchar(s)) return(s)
  p <- strsplit(tolower(s), " ", fixed = TRUE)[[1]]
  p <- vapply(seq_along(p), function(i) {
    w <- p[i]
    if (grepl(ROMANOS, w)) return(toupper(w))
    if (i > 1 && w %in% MENORES) return(w)
    paste0(toupper(substr(w, 1, 1)), substr(w, 2, nchar(w)))
  }, "")
  s <- gsub(" - ?$", "", gsub("\\( ", "(", paste(p, collapse = " ")))
  for (k in names(TILDES)) s <- gsub(paste0("\\b", k, "\\b"), TILDES[[k]], s, perl = TRUE)
  sub("_0*([0-9]+)$", " (n.º \\1)", s)                   # «Hórreo Caldevilla_05» -> «Hórreo Caldevilla (n.º 5)»
}

if (FUENTES == "cyl") {
# ---- espacios naturales (REN)
ren <- en_leon(leer("en_cyl_ren_limites_gpkg/en_cyl_ren_limites.gpkg"))
espacios <- lapply(seq_len(nrow(ren)), function(i) { r <- ren[i, ]; list(
  id = r$c_sitecode, n = if (r$c_figura == "ZPP") paste0(sub("^.*MNAT ", "", r$n_espacio), " (zona periférica)") else r$n_espacio, fig = r$c_figura, figN = r$n_figura, estado = r$d_estado,
  fecha = fecha(r$f_declarac), norma = r$n_norm_reg, porn = r$d_porn, ha = r$ha_tot, haLeon = r$ha_leon,
  url = r$url_info, c = rotulo(st_geometry(r)[[1]]), g = anillos_visor(st_geometry(r)[[1]], 25)) })

# ---- Red Natura 2000
natura <- list()
for (tipo in c("ZEC", "ZEPA")) {
  f <- if (tipo == "ZEC") "en_cyl_rednatura2000_zec_gpkg/en_cyl_rednatura2000_zec.gpkg" else "en_cyl_rednatura2000_zepa_gpkg/en_cyl_rednatura2000_zepa.gpkg"
  x <- en_leon(leer(f)); nom <- if (tipo == "ZEC") x$n_zec else x$n_zepa
  for (i in seq_len(nrow(x))) natura[[length(natura) + 1]] <- list(
    id = x$c_sitecode[i], tipo = tipo, n = sub(" - ZEPA$", "", nom[i]), fecha = fecha(x$f_declarac[i]),
    ha = x$ha_tot[i], haLeon = x$ha_leon[i], url = x$url_ficha[i],
    c = rotulo(st_geometry(x)[[i]]), g = anillos_visor(st_geometry(x)[[i]], 40))
}

} else {
# ---- espacios naturales y Red Natura 2000 (MITECO): para zonas de varias comunidades
FIG <- c("Parque Nacional" = "PNAC", "Parque Natural" = "PNAT", "Parque Regional" = "PREG", "Monumento Natural" = "MNAT",
         "Reserva Natural" = "RNAT", "Paisaje Protegido" = "PPRT", "Reserva Natural Parcial" = "RNAT", "Paraje Natural" = "PPRT")
enp <- leer("enp2025/Enp2025_p.json")
enp <- enp[!grepl("Natura 2000", enp$ODESIGNATE), ]           # la Red Natura va aparte, con sus propios límites
enp <- en_leon(enp)
espacios <- lapply(seq_len(nrow(enp)), function(i) { r <- enp[i, ]; fig <- unname(FIG[r$ODESIGNATE]); if (is.na(fig)) fig <- "OTRO"
  list(id = r$SITE_CODE_, n = r$SITE_NAME, fig = fig, figN = paste0(substr(r$ODESIGNATE, 1, 1), tolower(substring(r$ODESIGNATE, 2))),
       ha = round(r$Sup_ha), haLeon = r$ha_leon, c = rotulo(st_geometry(r)[[1]]), g = anillos_visor(st_geometry(r)[[1]], 25)) })
n2k <- en_leon(leer("n2000_2025/n2000_spatial_es_pibal_proy_end25.geojson"))   # TIPO: A = ZEPA, B = ZEC, C = las dos
natura <- list()
for (tipo in c("ZEC", "ZEPA")) {
  x <- n2k[n2k$TIPO %in% if (tipo == "ZEC") c("B", "C") else c("A", "C"), ]
  for (i in seq_len(nrow(x))) natura[[length(natura) + 1]] <- list(
    id = x$site_code[i], tipo = tipo, n = x$SITE_NAME[i], ha = round(x$HECTAREAS[i]), haLeon = x$ha_leon[i],
    url = paste0("https://natura2000.eea.europa.eu/Natura2000/SDF.aspx?site=", x$site_code[i]),
    c = rotulo(st_geometry(x)[[i]]), g = anillos_visor(st_geometry(x)[[i]], 40))
}

}

# ---- Reservas de la Biosfera (límites y zonificación)
mab <- en_leon(leer("mab_limites/MAB_LIMITE_PyB_EPSG25830.geojson"))
zon <- leer("mab_zonif/MAB_ZONIFICACION_PyB_EPSG25830.geojson")
ZONA_MAB <- c(NU = "Núcleo", TA = "Tampón", TR = "Transición")
biosfera <- lapply(seq_len(nrow(mab)), function(i) { r <- mab[i, ]
  z <- zon[zon$reserva == r$MAB_NAME, ]
  zonas <- list()
  if (nrow(z)) {
    gz <- suppressWarnings(st_intersection(st_geometry(z), prov))
    for (k in seq_len(nrow(z))) if (!st_is_empty(gz[[k]]) && as.numeric(st_area(gz[k])) > 1e4)
      zonas[[length(zonas) + 1]] <- list(z = unname(ZONA_MAB[z$zona[k]]), ha = round(as.numeric(st_area(gz[k])) / 1e4), g = anillos_visor(gz[[k]], 40))
  }
  list(id = r$SITE_MAB, n = r$MAB_NAME, fecha = fecha(r$MAB_DECLAR), ampl = if (is.na(r$MAB_AMPLIA)) NULL else as.character(r$MAB_AMPLIA),
       gestor = r$MAB_EG, ha = r$ha_tot, haLeon = r$ha_leon, c = rotulo(st_geometry(r)[[1]]), g = anillos_visor(st_geometry(r)[[1]], 40), zonas = zonas) })

# ---- Bienes de Interés Cultural (inmuebles; solo con las fuentes de Castilla y León)
bic <- list()
if (FUENTES == "cyl") {
b <- leer("pacu_cyl_bic_inmu_gpkg/pacu_cyl_bic_inmu.gpkg")
b <- b[lengths(st_intersects(b, prov)) > 0, ]
AREA <- c("CONJUNTO HISTÓRICO", "ZONA ARQUEOLÓGICA", "SITIO HISTÓRICO", "PAISAJE CULTURAL", "CONJUNTO ETNOLÓGICO", "CONJUNTO INDUSTRIAL", "JARDÍN HISTÓRICO")
bic <- lapply(seq_len(nrow(b)), function(i) { g <- st_geometry(b)[[i]]; cat_ <- b$d_categ_prot[i]
  x <- list(id = b$c_bien_id[i], n = bonito(b$d_bien_denom[i]), cat = bonito(cat_), fecha = fecha(b$f_proteccion[i]),
            url = b$l_url_pweb[i], xy = rotulo(g))
  a <- as.numeric(st_area(st_sfc(g, crs = 25830)))
  if (cat_ %in% AREA && a > 2e4) { x$ha <- round(a / 1e4, 1); x$g <- anillos_visor(g, 10) }
  x })
bic <- bic[order(vapply(bic, function(x) x$n, ""))]
}

out <- list(
  fuente = if (FUENTES == "cyl") paste("Junta de Castilla y León: Red de Espacios Naturales, Red Natura 2000 (ZEC y ZEPA) y Bienes de Interés Cultural inmuebles",
                 "(datos abiertos, IDECyL); MITECO-OAPN: Reservas de la Biosfera (límites y zonificación)")
           else "MITECO, Banco de Datos de la Naturaleza: Espacios Naturales Protegidos 2025, Red Natura 2000 (diciembre de 2025) y Reservas de la Biosfera (OAPN, límites y zonificación)",
  notaEspacios = if (FUENTES == "cyl") "Red de Espacios Naturales de Castilla y León: parques, monumentos naturales y su zona periférica. Incluye el Parque Nacional de Picos de Europa."
                 else "Espacios Naturales Protegidos del inventario nacional (MITECO): el Parque Nacional y los parques, reservas y monumentos naturales de cada comunidad.",
  espacios = espacios, natura = natura, biosfera = biosfera, bic = bic)
f <- file.path(RAIZ, "web", "data", ZONA, "proteccion.json")
writeLines(toJSON(out, auto_unbox = TRUE, digits = NA, null = "null", na = "null"), f, useBytes = TRUE)
cat(sprintf("%d espacios naturales, %d de Red Natura (%d ZEC, %d ZEPA), %d reservas de la biosfera, %d BIC -> %s (%.2f MB)\n",
            length(espacios), length(natura), sum(vapply(natura, function(x) x$tipo == "ZEC", TRUE)), sum(vapply(natura, function(x) x$tipo == "ZEPA", TRUE)),
            length(biosfera), length(bic), f, file.size(f) / 1e6))
for (e in espacios) cat(sprintf("  %-22s %-45s %7s ha en la zona\n", e$figN, e$n, format(e$haLeon, big.mark = ".", decimal.mark = ",")))
for (r in biosfera) cat(sprintf("  Reserva de la Biosfera %-36s %7s ha en la zona (%d zonas)\n", r$n, format(r$haLeon, big.mark = ".", decimal.mark = ","), length(r$zonas)))
print(table(vapply(bic, function(x) x$cat, "")))
