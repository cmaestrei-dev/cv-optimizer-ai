"""Trabajos en segundo plano (bandeja por lotes, generación de CV): cola en la base de datos.

Persistente: si el proceso se reinicia, lo pendiente sigue en la cola y lo que quedó a medias se
reintenta. Funciona igual en SQLite (desarrollo) y Postgres (`FOR UPDATE SKIP LOCKED`).
"""
