# Bot de postulación (LinkedIn)

Corre en **tu computador**, con tu IP de casa y un navegador propio donde inicias sesión una vez. Busca vacantes
en LinkedIn y las pasa por la app: compatibilidad con tu perfil y CV a la medida de cada una. Todo queda en
**Postulaciones**, con el CV exacto.

Hoy (entrega 2) funciona en **modo prueba**: busca, analiza y prepara el CV, pero **no envía**. Postular con la
«Solicitud sencilla» llega en la entrega 3.

## Una sola vez

```bash
pip install -r requirements-bot.txt
python -m runner configurar      # crea ~/.config/cv-optimizer-bot/config.toml: pon la dirección de la app y tus búsquedas
python -m runner token           # pega el token (app → Perfil → Bot de LinkedIn → Crear token del bot)
python -m runner entrar          # abre el navegador del bot: inicia sesión en LinkedIn tú mismo (para la entrega 3)
```

Antes, carga tu perfil en la app (Perfil → Importar CV): sin tu experiencia el bot no puede hacer CVs ni responder.

## Cada día

```bash
python -m runner buscar          # o --sin-cv para solo analizar (gasta menos cupo de IA)
```

## Reglas

- **Contraseña:** nunca se guarda la de LinkedIn. La sesión vive en `~/.local/share/cv-optimizer-bot/navegador` (solo tu usuario puede leerla); trátala como un secreto.
- **Captchas y verificaciones:** el bot nunca los resuelve ni intenta ocultarse. Si LinkedIn frena las peticiones o pide verificación, se detiene 24 horas.
- **Tope:** el tope diario (`tope_diario`) se cuenta en `~/.local/share/cv-optimizer-bot/estado.json`, junto con las vacantes ya vistas, para no repetirlas.
- **Riesgo:** las condiciones de LinkedIn (§8.2) prohíben los bots. El riesgo es la cuenta (restricción o cierre).
