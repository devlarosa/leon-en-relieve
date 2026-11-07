suppressMessages({library(sf); library(dplyr)})
au <- st_read("raw/au_units.gml", quiet = TRUE)
sel <- au %>% filter(substr(nationalCode,1,4)=="3407", substr(nationalCode,5,6)=="24") %>%
  transmute(code = substr(nationalCode,7,11), nombre = text) %>% st_transform(25830)
prov <- sel %>% filter(code=="00000")
mun  <- sel %>% filter(code!="00000") %>% mutate(tipo = ifelse(substr(code,1,2)=="53","condominio","municipio"))
st_write(prov, "raw/provincia.gpkg", delete_dsn=TRUE, quiet=TRUE)
st_write(mun, "raw/municipios.gpkg", delete_dsn=TRUE, quiet=TRUE)
b <- st_bbox(prov); print(b); cat("area km2:", as.numeric(st_area(prov))/1e6, "\n")
