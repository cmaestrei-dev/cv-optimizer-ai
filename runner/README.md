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
                                 # --portal linkedin|computrabajo: solo ese portal (también en buscar)
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

## Vacantes desde la bandeja de la app (alertas de LinkedIn por correo)

Antes de buscar en los portales, `buscar` revisa tu bandeja de la app y toma las vacantes de LinkedIn y Computrabajo
que todavía no vio. Llegan ya analizadas, por ejemplo desde las alertas de empleo por correo. Les aplica las mismas
exclusiones, compatibilidad mínima y topes. Lo que excluye o descarta queda «descartado» en la app con el motivo.

Es la forma recomendada de recibir vacantes de LinkedIn: su búsqueda pública frena las peticiones (429) desde una
IP de casa, y las alertas son un uso normal que no arriesga la cuenta. Para activarlo:

1. En LinkedIn, crea alertas de empleo diarias para tus búsquedas.
2. En la app, Bandeja → «Alertas por correo» → activar: te da una dirección de reenvío.
3. En tu Gmail, crea un filtro que reenvíe a esa dirección los correos de `jobalerts-noreply@linkedin.com` (el código
   de confirmación de Gmail aparece en la app).

## Computrabajo

Las búsquedas con `portal = "computrabajo"` usan la búsqueda pública de Computrabajo Colombia (sin sesión):
`lugar` acepta Colombia, Remoto o una ciudad, y `dias` 1, 3, 7, 15 o 30. Tiene su propio tope y una compatibilidad
mínima en la tabla `[computrabajo]` (al final del archivo): debajo del mínimo, la vacante queda **descartada** en la
app, con el motivo, y no se le hace CV. Si Computrabajo frena las peticiones, solo su búsqueda espera 6 horas.

Para postular, `python -m runner postular` usa tu sesión de Computrabajo en el navegador del bot:

1. Sube el CV de la vacante a «Hoja de Vida en Word/PDF» y lo marca **por defecto**: es el que recibe la empresa,
   junto con tu hoja de vida en línea (que siempre se ve en su última versión).
2. Pulsa «Aplicar», que en Computrabajo envía de inmediato. Si la oferta tiene preguntas de filtro, las responde
   con el mismo banco y el mismo perfil que en LinkedIn; si alguna queda sin respuesta, no envía.
3. Comprueba que la oferta quede «Postulado» y deja otra vez por defecto tu CV general (`cv_general` en
   `[computrabajo]`), el que va cuando postulas tú a mano.

Computrabajo guarda como máximo 10 PDF. Para hacer espacio, el bot borra el más viejo que subió él; nunca el
general ni los tuyos (si no hay ninguno suyo, se detiene y te avisa). En modo prueba deja listo el CV y vuelve al
general sin pulsar «Aplicar».

Inicia sesión una vez en el navegador del bot (con el bot detenido):

```bash
python -m runner entrar computrabajo   # entra con tu correo y contraseña; cierra la ventana al terminar
python -m runner entrar magneto        # igual, para Magneto
python -m runner entrar elempleo       # igual, para elempleo
```

## Magneto

Las búsquedas con `portal = "magneto"` usan la búsqueda pública de Magneto, sin sesión. Trae 20 por página con la
oferta completa, así que no se abre cada una. `lugar` acepta Colombia, Remoto o una ciudad: en una ciudad sirven las
vacantes de esa ciudad y las remotas. Tope y compatibilidad mínima van en la tabla `[magneto]`.

Para postular usa tu sesión de Magneto en el navegador del bot:

1. Renueva la sesión abriendo el inicio de sesión de Magneto (vence en más o menos una hora). Si entraste con
   Google, se renueva sola; si no, el bot te pide `python -m runner entrar magneto`.
2. Hace las mismas consultas que la página antes de postular. Si Magneto dice que tu cédula ya se postuló a esa
   oferta (p. ej. con otra cuenta), se detiene: nunca cambia de cuenta.
3. Si la oferta tiene cuestionario de filtro, lo responde con el banco y tu perfil. Si una pregunta queda sin
   respuesta, no envía.
4. Envía la misma petición que el botón «Aplicar» y comprueba que la oferta quede postulada.

Magneto le muestra a la empresa **tu perfil de Magneto**, no un PDF por vacante: mantenlo al día (igual a tu
LinkedIn). El CV de la vacante queda en la app como referencia. En modo prueba responde todo y no envía.

## elempleo

Las búsquedas con `portal = "elempleo"` usan la búsqueda pública de elempleo, sin sesión, filtrada por fecha:
`dias` es 1 (hoy y ayer), 7, 15 o 30. `lugar` acepta Colombia, Remoto o una ciudad. elempleo no tiene búsqueda por
ciudad para todos los cargos, así que se busca en todo el país y se dejan las de esa ciudad y las remotas (casi
todas sus ofertas de tecnología son de Bogotá y Medellín). Tope y compatibilidad mínima van en la tabla `[elempleo]`.

Para postular usa tu sesión de elempleo en el navegador del bot (`python -m runner entrar elempleo`). Esa sesión
dura lo que dura el navegador: el bot deja su perfil de Chrome configurado para reabrir la sesión anterior, y así
no hay que entrar cada vez.

1. Abre la oferta y comprueba que tengas sesión y que no te hayas postulado ya.
2. Envía la misma petición que el botón «Postularme a oferta» (elempleo no hace preguntas de filtro) y comprueba
   que la oferta quede postulada.
3. Si la empresa pide seguir en su sitio, o un videocuestionario, no lo abre: te lo manda por Telegram (`/manuales`).
4. Si elempleo dice que tu hoja de vida está incompleta, se detiene.

elempleo le muestra a la empresa **tu hoja de vida de elempleo** (con el CV que tengas adjunto allá), no un PDF por
vacante: mantenla al día. En las ofertas de «postulación rápida», donde se elige qué PDF recibe la empresa, el bot
elige el primero que tengas adjunto (tu CV general) y no sube archivos.

## Analizar solo los cargos que te interesan

Cada vacante que el bot analiza gasta cupo de IA. Con `[incluir]`, las búsquedas en los portales solo analizan los
cargos con alguna de esas palabras; las demás se omiten sin gastar nada. Las palabras cortas («ti», «qa») cuentan
completas, y las largas, al comienzo de una palabra («desarroll» → «desarrollador»). Sin `[incluir]`, se analiza
todo. Las vacantes de la bandeja (alertas por correo) no pasan por este filtro: ya vienen analizadas.

## Vacantes en otros idiomas

Con `solo_idiomas = ["es"]` y `salvo_pais = "Colombia"` en `[excluir]`, el bot omite (antes de hacer el CV) las
vacantes escritas en otro idioma, salvo las de ese país: una oferta en inglés de Estados Unidos o en alemán de
Alemania se descarta en la app con el motivo; una en inglés en Medellín sigue. El idioma y el lugar salen del
análisis de la app.

## El navegador del bot ocupado

Si al empezar una vuelta el navegador del bot está abierto (otra vuelta, o una ventana que abriste con
`entrar`), el bot espera hasta 30 minutos a que se cierre en vez de fallar.

## Portales de empresa en lote (Bancolombia)

Bancolombia usa SAP SuccessFactors: para entrar pide correo, contraseña y captcha, sin «mantener la sesión», y la
sesión dura poco. Por eso se postula en lote: el bot prepara las ofertas que encajan (análisis y CV), te avisa por
Telegram y, cuando corres

```bash
python -m runner lote bancolombia            # --prueba: llena todo sin pulsar «Aplicar»
```

abre su ventana en el acceso. Entras tú (contraseña y captcha) **sin cerrarla**, y el bot postula a cada pendiente:
cambia el currículum por el CV de esa vacante, responde las preguntas del puesto (tu banco, `respuestas` del
`[[vigilar]]` y la regla de experiencia), firma la declaración de conformidad con `firma`, pulsa «Aplicar» y lo
confirma en «Puestos solicitados (N)». Al final deja tu CV general en el perfil y te manda el resumen.

```toml
[[vigilar]]
nombre = "Bancolombia"
sitio = "https://empleo.grupobancolombia.com"
buscar = ["practicante", "software", "junior"]
postular = true
acceso = "https://career8.successfactors.com/career?company=…&loginFlowRequired=true&lang=es_ES"   # con sesión, lleva al perfil
firma = "Tu nombre completo"   # con esto autorizas aceptar la declaración de conformidad
respuestas = { "como te enteraste" = "Portal de empleo de Bancolombia" }
```

## Vigilar portales de empresas

Algunas empresas publican solo en su propio portal, que pide una cuenta por empresa: Bancolombia y Ecopetrol usan
SAP SuccessFactors; Accenture, DXC, Kyndryl y Unisys, Workday; Mercado Libre, Eightfold. El bot vigila su búsqueda
pública en cada vuelta y te avisa (registro y Telegram) de las vacantes nuevas cuyo cargo
encaja. Además, la app analiza cada una (hasta 20 por vuelta): si llega a la compatibilidad mínima (60 por
defecto, `compatibilidad_minima` en cada `[[vigilar]]`), le hace el CV y te la manda por Telegram con el PDF, lista
para postular (`/manuales`). Si no llega, queda descartada en la app con el motivo. Por defecto encajan los cargos con una palabra de
tecnología (software, sistemas, tecnología, desarrollo, ciberseguridad, soporte, QA, datos…), así que «Practicante
en Tecnología» sí y «Practicante de Ciencias Económicas» no. Se descartan senior, líder, lead, arquitecto, gerente,
manager, expert y niveles III o IV.

```toml
[[vigilar]]
nombre = "Bancolombia"
sitio = "https://empleo.grupobancolombia.com"
buscar = ["practicante", "software", "junior", "tecnología"]
# incluir = [...]   # palabras del cargo que sí (opcional)
# excluir = [...]   # palabras del cargo que no (opcional)

[[vigilar]]
nombre = "Accenture"
portal = "workday"
sitio = "https://accenture.wd103.myworkdayjobs.com/AccentureCareers"   # la página de empleos de la empresa
pais = "Colombia"   # todas las del país; «buscar» es opcional

[[vigilar]]
nombre = "Mercado Libre"
portal = "eightfold"
sitio = "https://mercadolibre.eightfold.ai"
dominio = "mercadolibre.com"
pais = "Colombia"

[[vigilar]]
nombre = "Get on Board"   # bolsa de empleos de tecnología: cada oferta va con su empresa
portal = "getonbrd"
sitio = "https://www.getonbrd.com"
pais = "Colombia"   # las abiertas al país (también remotas para quien vive allí), del último mes
```

Muchas empresas publican en sistemas con una lista pública de ofertas; con la `cuenta` de la empresa en ese sistema
basta (sale en la dirección de su página de empleos):

```toml
[[vigilar]]
nombre = "Bold"
portal = "recruitee"          # también: greenhouse, lever, ashby, smartrecruiters, teamtailor, buk, gupy, muevete
sitio = "https://jobs.bold.co"  # Recruitee, Teamtailor, Buk y Gupy: la página de empleos; los demás usan «cuenta»
pais = "Colombia"

[[vigilar]]
nombre = "Addi"
portal = "ashby"
cuenta = "addi"               # jobs.ashbyhq.com/addi · Greenhouse: job-boards.greenhouse.io/<cuenta> ·
pais = "Colombia"             # Lever: jobs.lever.co/<cuenta> · SmartRecruiters: jobs.smartrecruiters.com/<cuenta>
```

Workday frena si se le pide seguido (HTTP 429), y el límite es por conexión, no por empresa: en cada vuelta el bot
revisa solo 3 portales de Workday (los que llevan más tiempo sin revisarse), con pausas largas, y si uno frena espera
a la próxima vuelta. En casi todos estos portales el bot no postula (piden cuenta o tienen captcha): te llegan por Telegram con su CV.
**Teamtailor sí**: su formulario no pide cuenta ni captcha. Con `postular = true` en su `[[vigilar]]`, en cada vuelta el bot
postula solo a las que llegan a la compatibilidad mínima (hasta 10 por vuelta): responde las preguntas de la empresa con
tu banco y tu perfil, usa tu nombre, correo y teléfono del perfil de la app, sube el CV de esa vacante y marca solo el
consentimiento obligatorio de la política de privacidad (el de «futuras oportunidades» no). Si una pregunta queda sin
respuesta, no envía: te la pregunta por Telegram (`/preguntas`) y la reintenta cuando la respondes. Para probar sin
enviar: `python -m runner lote <empresa> --prueba`.
De Get on Board toma solo las de tecnología (por su categoría), sin experiencia, junior o semi senior, y descarta las
de ventas, las bilingües y las que están en inglés sin sede en el país.

`python -m runner vigilar` lo revisa ya. Para tener la cuenta de Bancolombia en el navegador del bot:
`python -m runner entrar bancolombia`.

## Telegram (avisos y control desde el celular)

Un bot de Telegram tuyo, que corre en tu computador (sin abrir puertos) y solo atiende tu chat:

```bash
python -m runner telegram configurar   # pide el token de @BotFather (oculto) y te da un código para emparejar
python -m runner telegram instalar     # lo deja escuchando siempre (servicio de systemd del usuario)
python -m runner telegram probar       # te envía un mensaje de prueba
```

- **Avisos:** al terminar cada vuelta te llega el resumen. También te avisa de lo que solo tú puedes hacer:
  verificaciones, una sesión perdida y preguntas de filtro sin respuesta.
- **Comandos:** `/estado`, `/hoy`, `/vuelta` (correr una ahora), `/pausar [horas]`, `/reanudar`, `/preguntas`,
  `/responder N texto`, `/manuales` y `/hecha N`.
- **Postulaciones manuales:** las que debes enviar tú (formulario con captcha, que pide cédula o cuenta propia) llegan por Telegram con el enlace, el CV en PDF y lo que pide el formulario. `/manuales` las lista y `/hecha N` marca una como enviada. Se agregan con `python -m runner manual URL --titulo … --empresa … --cv …`.
- **Respuestas:** lo que respondes queda en `respuestas_extra.json`, junto a tu banco. Las vacantes que se habían
  saltado por esa pregunta vuelven solas a la cola.
- **Seguridad:** el token queda en `~/.config/cv-optimizer-bot/telegram` (solo tú puedes leerlo) y nunca se
  imprime. El bot de Telegram no escribe el estado de las vueltas: las pausas van a `control.json`.

## Cómo responde el formulario

1. Lo que LinkedIn ya trae (tu correo, teléfono, respuestas anteriores) se deja.
2. Lo obligatorio que falte se busca primero en tu banco `[respuestas]` de la configuración (salario,
   disponibilidad, inglés…): la clave son partes de la pregunta separadas por `|`, sin tildes.
3. Lo demás lo responde la app con tu perfil, verificado contra él. «¿Cuántos años con X?» usa las fechas de tus
   empleos y se redondea hacia abajo. Si tu perfil no muestra X, en las preguntas de experiencia decide
   `sin_evidencia`:
   - `"saltar"`: salta la vacante;
   - `"cero"`: «No», «0» o «Aún no tengo experiencia con eso»;
   - `"si"`: «Sí» y, en años, lo que muestre tu perfil o al menos `experiencia_por_defecto` (2 por defecto; en
     meses, ×12). Con opciones («1 a 2 años», «3 a 5 años»…) elige la que contiene ese número. Lo afirmas tú: úsalo
     solo si de verdad puedes responder por eso en una entrevista.

   Las demás preguntas (patrocinio de visa, dirección…) no cambian con esto: o las responde tu banco o tu perfil, o
   se salta la vacante.
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
