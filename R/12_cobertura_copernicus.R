# Cubierta del suelo de Copernicus (CLMS) para el visor.
#  · CLC+ Backbone 2021, 10 m, 11 clases (servidor de imágenes de la Agencia Europea de Medio Ambiente, sin registro)
# Se descarga a 10 m en mosaicos (EPSG:3035), se une y se reduce a la malla del visor por clase mayoritaria.
# Salida: web/data/cobertura.png  (un canal: código de clase 0–11 a 50 m, alineado con relieve.png pero al doble de resolución)
suppressMessages({library(sf); library(terra)})
X0 <- 164000; X1 <- 360000; Y0 <- 4655000; Y1 <- 4790000
RES <- 50                      # m por píxel en el visor (3920 × 2700)
SVC <- "https://image.discomap.eea.europa.eu/arcgis/rest/services/CLC_plus/CLMS_CLCplus_RASTER_2021_010m_eu/ImageServer/exportImage"
dir.create("raw/copernicus/clcplus", recursive = TRUE, showWarnings = FALSE)

caja <- st_bbox(st_transform(st_as_sfc(st_bbox(c(xmin = X0, xmax = X1, ymin = Y0, ymax = Y1), crs = 25830)), 3035))
caja <- c(floor(caja[c("xmin", "ymin")] / 1000) * 1000 - 2000, ceiling(caja[c("xmax", "ymax")] / 1000) * 1000 + 2000)
names(caja) <- c("xmin", "ymin", "xmax", "ymax")
TAM <- 40000                    # 40 km = 4000 px a 10 m por mosaico
xs <- seq(caja["xmin"], caja["xmax"] - 1, by = TAM); ys <- seq(caja["ymin"], caja["ymax"] - 1, by = TAM)
cat("Mosaicos:", length(xs) * length(ys), "\n")
op <- options(HTTPUserAgent = "Mozilla/5.0 (compatible; leon3d-datos/1.0)", timeout = 600)
ficheros <- character(0)
for (x in xs) for (y in ys) {
  f <- sprintf("raw/copernicus/clcplus/t_%d_%d.tif", x, y); ficheros <- c(ficheros, f)
  if (file.exists(f) && file.size(f) > 10000) next
  url <- sprintf("%s?bbox=%d,%d,%d,%d&bboxSR=3035&imageSR=3035&size=4000,4000&format=tiff&pixelType=U8&interpolation=RSP_NearestNeighbor&noData=0&f=image",
                 SVC, x, y, x + TAM, y + TAM)
  for (i in 1:5) {
    ok <- tryCatch({ download.file(url, f, mode = "wb", quiet = TRUE); file.size(f) > 10000 }, error = function(e) FALSE)
    if (ok) break
    cat("  reintento", i, basename(f), "\n"); Sys.sleep(5 * i)
  }
  cat("  ", basename(f), round(file.size(f) / 1e6, 1), "MB\n")
}
options(op)

# el servidor devuelve TIFF sin georreferencia completa: se la ponemos a partir de la caja pedida
capas <- lapply(ficheros, function(f) {
  xy <- as.numeric(regmatches(f, regexec("t_(\\d+)_(\\d+)", f))[[1]][2:3])
  r <- rast(f)[[1]]; ext(r) <- ext(xy[1], xy[1] + TAM, xy[2], xy[2] + TAM); crs(r) <- "EPSG:3035"; r
})
mos <- do.call(mosaic, c(capas, fun = "max"))
grid <- rast(xmin = X0, xmax = X1, ymin = Y0, ymax = Y1, res = RES, crs = "EPSG:25830")
cob <- project(mos, grid, method = "mode")
cob[is.na(cob) | cob > 11] <- 0
writeRaster(cob, "web/data/cobertura.png", datatype = "INT1U", overwrite = TRUE)
unlink("web/data/cobertura.png.aux.xml")

prov <- vect(st_read("raw/provincia.gpkg", quiet = TRUE))
fr <- freq(mask(cob, prov)); fr <- fr[fr$value > 0, ]
nombres <- c("Construido", "Coníferas", "Frondosas caducifolias", "Frondosas perennifolias", "Matorral", "Prados y pastos",
             "Cultivos", "Líquenes y musgos", "Roca y suelo desnudo", "Agua", "Nieve y hielo")
fr$clase <- nombres[fr$value]; fr$pct <- round(100 * fr$count / sum(fr$count), 1)
print(fr[, c("value", "clase", "pct")])
cat("cobertura.png:", round(file.size("web/data/cobertura.png") / 1e6, 2), "MB\n")
