
import os
from datetime import datetime
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from pymongo import MongoClient, DESCENDING
from pymongo.errors import PyMongoError
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")

if not MONGO_URI or not MONGO_DB:
    raise RuntimeError("Falta configurar MongoDB en .env")

cliente = MongoClient(
    MONGO_URI,
    serverSelectionTimeoutMS=8000
)

base_datos = cliente[MONGO_DB]
resenas = base_datos["resenas_conductores"]

app = FastAPI(
    title="Wheels Alpes - API de Reputacion",
    version="1.0.0"
)


@app.get("/")
def inicio():
    return {
        "mensaje": "API de Wheels Alpes funcionando correctamente"
    }


@app.get("/salud")
def salud():
    return {
        "estado": "ok",
        "proyecto": "Wheels Alpes"
    }


@app.get("/resenas/conteo")
def contar_resenas():
    try:
        return {
            "coleccion": "resenas_conductores",
            "total": resenas.count_documents({})
        }
    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="No fue posible consultar MongoDB"
        )


@app.get("/resenas/publicas")
def consultar_resenas(
    doc_conductor: str | None = None,
    ordenar: Literal["fecha", "utilidad"] = "fecha",
    pagina: int = Query(1, ge=1),
    limite: int = Query(10, ge=1, le=50)
):
    filtros = {
        "estado": {"$in": ["publicada", "destacada"]}
    }

    if doc_conductor:
        filtros["doc_conductor"] = doc_conductor

    if ordenar == "utilidad":
        orden = [
            ("utilidad", DESCENDING),
            ("fecha_creacion", DESCENDING)
        ]
    else:
        orden = [
            ("fecha_creacion", DESCENDING),
            ("_id", DESCENDING)
        ]

    try:
        total = resenas.count_documents(filtros)

        documentos = list(
            resenas.find(filtros)
            .sort(orden)
            .skip((pagina - 1) * limite)
            .limit(limite)
        )

        resultados = []

        for documento in documentos:
            fecha = documento.get("fecha_creacion")
            respuesta = documento.get("respuesta")

            resultados.append({
                "conductor": documento.get(
                    "nombre_conductor", "Conductor"
                ),
                "pasajero": documento.get(
                    "nombre_pasajero", "Pasajero"
                ),
                "calificacion": documento.get("calificacion"),
                "comentario": documento.get("comentario"),
                "fecha": (
                    fecha.isoformat()
                    if isinstance(fecha, datetime)
                    else None
                ),
                "utilidad": documento.get("utilidad", 0),
                "respuesta_conductor": (
                    respuesta.get("texto")
                    if isinstance(respuesta, dict)
                    else None
                )
            })

        return {
            "total": total,
            "pagina": pagina,
            "limite": limite,
            "items": resultados
        }

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="No fue posible consultar las resenas"
        )
