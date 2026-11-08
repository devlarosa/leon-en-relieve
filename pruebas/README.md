# Pruebas del visor en Firefox

Herramientas para abrir el visor en un Firefox real, controlado por WebDriver BiDi (sin dependencias externas),
leer la consola, medir fotogramas y memoria, ejecutar interacciones y hacer capturas.

```bash
python3 -I pruebas/servidor.py web &                      # sirve web/ en http://127.0.0.1:8765
python3 -I pruebas/bidi.py http://127.0.0.1:8765/index.html captura.png 30 1400 850 "$(cat pruebas/fps.js)"
python3 -I pruebas/bidi.py http://127.0.0.1:8765/index.html captura.png 40 1400 850 "$(cat pruebas/inter.js)"
SOFT=1 python3 -I pruebas/bidi.py ...                     # WebGL por software (si la GPU no está disponible)
```

- `fps.js`: gira la cámara 6 s (tecla Q) y devuelve los fotogramas por segundo.
- `inter.js`: elige una comarca, selecciona un municipio, activa la capa histórica y el relieve de población, y
  devuelve el estado y los errores de JavaScript.

Necesita una sesión gráfica (`DISPLAY=:0`); usa un perfil temporal de Firefox que se borra al terminar.
