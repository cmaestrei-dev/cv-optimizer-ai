"""Bot de postulación que corre en el computador del dueño (Fase 7).

Busca vacantes en LinkedIn y las pasa por el motor de la app (compatibilidad y CV a la medida) usando
la API con un token del bot. Reglas que no se rompen:
- Nunca guarda la contraseña de LinkedIn: la persona inicia sesión en el navegador del bot.
- Nunca resuelve captchas ni usa herramientas para ocultarse: ante una verificación se detiene.
- Nunca inventa: si una respuesta no sale del perfil o del banco de respuestas, salta la vacante.
"""
