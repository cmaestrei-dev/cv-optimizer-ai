# Bot de postulación (LinkedIn y Computrabajo)

Corre en **tu computador**, con tu IP de casa y un navegador propio donde inicias sesión una vez. Busca vacantes
en LinkedIn y las pasa por la app: compatibilidad con tu perfil y CV a la medida de cada una. Todo queda en
**Postulaciones**, con el CV exacto.

Postula con la **«Solicitud sencilla»**: sube el CV hecho para esa vacante, responde el formulario y registra el
envío con ese CV. Empieza en **modo prueba** (`modo = "prueba"`): llega a la revisión, guarda una captura y descarta
sin enviar. Cuando las capturas se vean bien, cambia a `modo = "auto"`.

## Una sola vez

```bash
pip install -r requirements-bot.txt
python -m runner configurar      # crea ~/.config/cv-optimizer-bot/config.toml: pon la dirección de la app y tus búsquedas
python -m runner token           # pega el token (app → Perfil → Bot de LinkedIn → Crear token del bot)
python -m runner entrar          # abre un Chrome normal con el perfil del bot: entra a LinkedIn con correo y contraseña
```

Antes, carga tu perfil en la app (Perfil → Importar CV): sin tu experiencia el bot no puede hacer CVs ni responder.

## Cada día

```bash
python -m runner buscar          # busca, analiza y prepara el CV de cada vacante (--sin-cv: solo analizar)
python -m runner postular        # postula a las preparadas (--prueba: hasta la revisión, sin enviar; --max N)
```

Las capturas de cada revisión quedan en `~/.local/share/cv-optimizer-bot/capturas/`.

## Programarlo para que corra solo

```bash
python -m runner programar                      # cada día a las 9:17 y 15:47 (o --horas 8:05 14:40)
python -m runner programar --quitar             # dejar de correrlo solo
```

- Cada vuelta es `python -m runner diario`: busca y luego postula. Nunca corren dos vueltas a la vez, y si la búsqueda falla igual postula a lo ya preparado.
- Usa un temporizador de systemd de tu usuario (sin root), con el código de la carpeta desde donde lo programaste. Prográmalo desde una copia estable del repositorio, no desde una carpeta temporal.
- La ventana del bot se abre en tu sesión: el computador debe estar encendido y con tu sesión iniciada. Si estaba apagado a la hora, la vuelta corre al encenderlo.
- Lo que hace cada vuelta queda en `~/.local/share/cv-optimizer-bot/registro.log`. Al terminar te avisa en el escritorio: cuántas se enviaron, o si LinkedIn pidió una verificación o el bot perdió la sesión.

## Computrabajo

Las búsquedas con `portal = "computrabajo"` usan la búsqueda pública de Computrabajo Colombia (sin sesión):
`lugar` acepta Colombia, Remoto o una ciudad, y `dias` 1, 3, 7, 15 o 30. Tiene su propio tope y una compatibilidad
mínima en la tabla `[computrabajo]` (al final del archivo): debajo del mínimo, la vacante queda **descartada** en la
app, con el motivo, y no se le hace CV. Si Computrabajo frena las peticiones, solo su búsqueda espera 6 horas.

Por ahora el bot prepara las vacantes de Computrabajo; postular allí llega en la siguiente entrega. Para eso, inicia
sesión una vez en el navegador del bot (con el bot detenido):

```bash
python -m runner entrar computrabajo   # entra con tu correo y contraseña; cierra la ventana al terminar
```

## Cómo responde el formulario

1. Lo que LinkedIn ya trae (tu correo, teléfono, respuestas anteriores) se deja.
2. Lo obligatorio que falte se busca primero en tu banco `[respuestas]` de la configuración (salario,
   disponibilidad, inglés…): la clave son partes de la pregunta separadas por `|`, sin tildes.
3. Lo demás lo responde la app con tu perfil, verificado contra él. «¿Cuántos años con X?» usa las fechas de tus
   empleos y se redondea hacia abajo; si tu perfil no muestra X, `sin_evidencia` decide: `"saltar"` la vacante o
   responder `"cero"`.
4. Si una pregunta obligatoria queda sin respuesta, la vacante se salta y el bot te dice cuál era. Nunca responde al azar.

El CV: LinkedIn deja elegido el último que subiste. El bot sube el de la vacante, lo elige y, antes de enviar,
comprueba que sea ese; si no, salta la vacante. Cada CV subido queda en tu lista de currículums de LinkedIn.

## Reglas

- **Contraseña:** nunca se guarda la de LinkedIn. La sesión vive en `~/.local/share/cv-optimizer-bot/navegador`, cifrada con el llavero de tu sistema, y solo tu usuario puede leerla; trátala como un secreto.
- **Inicio de sesión:** se hace en un Chrome normal, porque LinkedIn rechaza iniciar sesión en una ventana automatizada. Luego el bot abre ese mismo perfil con el aislamiento normal de Chrome.
- **Captchas y verificaciones:** el bot nunca los resuelve ni intenta ocultarse. Si LinkedIn pide verificación o avisa su tope de solicitudes, postular se detiene 24 horas; si la búsqueda pública devuelve 429, solo la búsqueda espera 6 horas.
- **Tope y pausas:** el tope diario (`tope_diario`) se cuenta en `~/.local/share/cv-optimizer-bot/estado.json`, junto con las vacantes ya vistas, para no repetirlas. Entre dos envíos espera `pausa_entre_envios_seg` (por defecto de 2 a 4 minutos, al azar).
- **«Seguir a la empresa»** se desmarca siempre.
- **Riesgo:** las condiciones de LinkedIn (§8.2) prohíben los bots. El riesgo es la cuenta (restricción o cierre).
