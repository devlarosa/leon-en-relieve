# Zona con la que trabajan los scripts de R: la variable de entorno ZONA (por defecto «leon»).
# Su ficha está en web/zonas.json; sus datos de partida en raw/<zona>/ y los generados en web/data/<zona>/.
#   ZONA=picos Rscript R/10_preparar_web.R
# Uso: source("R/zona.R") desde la raíz del proyecto. Define ZONA, FICHA, RAW, DATA, fr() y fw().
ZONA <- Sys.getenv("ZONA", "leon")
FICHA <- jsonlite::fromJSON("web/zonas.json", simplifyVector = TRUE)[[ZONA]]
if (is.null(FICHA) || startsWith(ZONA, "_")) stop("Zona desconocida: ", ZONA)
RAW <- file.path("raw", ZONA); DATA <- file.path("web", "data", ZONA)
fr <- function(...) file.path(RAW, ...)      # fr("mdt25") = raw/<zona>/mdt25
fw <- function(...) file.path(DATA, ...)     # fw("relieve.png") = web/data/<zona>/relieve.png
dir.create(DATA, recursive = TRUE, showWarnings = FALSE)
