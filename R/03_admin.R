# Unidades administrativas de la zona (IGN, unidades administrativas INSPIRE) -> raw/<zona>/provincia.gpkg y municipios.gpkg
# «provincia.gpkg» es el contorno de la zona: la provincia entera (León) o la unión de sus municipios (Picos).
# Para una zona por lista de municipios calcula también la extensión del mapa (la zona más «margen», al kilómetro):
# si no coincide con la de web/zonas.json, la muestra para copiarla allí.
suppressMessages({library(sf); library(dplyr)})
source("R/zona.R")   # ZONA, FICHA, fr() = raw/<zona>/…, fw() = web/data/<zona>/…
sf_use_s2(FALSE)
au <- st_read(fr("au_units.gml"), quiet = TRUE)
if (!is.null(FICHA$municipios$provincia)) {
  # una provincia entera, con sus condominios (códigos 53xxx)
  pr <- FICHA$municipios$provincia
  sel <- au %>% filter(substr(nationalCode,1,2)=="34", substr(nationalCode,5,6)==pr) %>%
    transmute(code = substr(nationalCode,7,11), nombre = text) %>% st_transform(25830)
  prov <- sel %>% filter(code=="00000")
  mun  <- sel %>% filter(code!="00000") %>% mutate(tipo = ifelse(substr(code,1,2)=="53","condominio","municipio"))
} else {
  # una lista de municipios (pueden ser de varias provincias)
  LISTA <- unlist(FICHA$municipios$lista)
  PROVINCIA <- c("24" = "León", "33" = "Asturias", "39" = "Cantabria")
  au <- st_transform(au, 25830); au$code <- substr(au$nationalCode, 7, 11)
  mun <- au %>% filter(nchar(nationalCode) == 11, code %in% names(LISTA)) %>%
    transmute(code, nombre = text, tipo = "municipio", provincia = unname(PROVINCIA[substr(code, 1, 2)]))
  stopifnot(nrow(mun) == length(LISTA))
  prov <- st_sf(code = "00000", nombre = FICHA$corto, geometry = st_union(st_make_valid(mun)))
  m <- if (is.null(FICHA$municipios$margen)) 3000 else FICHA$municipios$margen
  b <- st_bbox(st_buffer(prov, m))
  ext <- unname(c(floor(b["xmin"] / 1000), floor(b["ymin"] / 1000), ceiling(b["xmax"] / 1000), ceiling(b["ymax"] / 1000)) * 1000)
  if (!identical(as.numeric(ext), as.numeric(FICHA$extension)))
    cat("OJO: la extensión calculada (", ext, ") no es la de web/zonas.json (", FICHA$extension, "): cópiala allí\n")
}
st_write(prov, fr("provincia.gpkg"), delete_dsn=TRUE, quiet=TRUE)
st_write(mun, fr("municipios.gpkg"), delete_dsn=TRUE, quiet=TRUE)
b <- st_bbox(prov); print(b); cat("área km²:", round(as.numeric(st_area(prov))/1e6), "·", nrow(mun), "unidades\n")
