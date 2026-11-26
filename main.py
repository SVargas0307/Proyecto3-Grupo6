
import os
import secrets
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Header
from pydantic import BaseModel, Field, field_validator
from pymongo import MongoClient, DESCENDING
from pymongo.errors import PyMongoError, DuplicateKeyError
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")
API_WRITE_KEY = os.getenv("API_WRITE_KEY")

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
    version="1.1.0"
)


class DatosViaje(BaseModel):
    placa: str = Field(min_length=1, max_length=20)
    fecha: str
    hora_salida: str

    @field_validator("fecha")
    @classmethod
    def validar_fecha(cls, valor):
        try:
            datetime.strptime(valor, "%Y-%m-%d")
        except ValueError:
            raise ValueError("La fecha debe ser YYYY-MM-DD")
        return valor

    @field_validator("hora_salida")
    @classmethod
    def validar_hora(cls, valor):
        try:
            datetime.strptime(valor, "%H:%M")
        except ValueError:
            raise ValueError("La hora debe ser HH:MM")
        return valor


class ResenaNueva(BaseModel):
    doc_pasajero: str = Field(min_length=1)
    doc_conductor: str = Field(min_length=1)
    nombre_pasajero: str = Field(min_length=1)
    nombre_conductor: str = Field(min_length=1)
    viaje: DatosViaje
    calificacion: int = Field(ge=1, le=5)
    comentario: str = Field(min_length=1, max_length=2000)

    @field_validator("comentario")
    @classmethod
    def validar_comentario(cls, valor):
        valor = valor.strip()
        if not valor:
            raise ValueError("El comentario no puede estar vacio")
        return valor


def verificar_clave(clave_recibida):
    if not API_WRITE_KEY:
        raise HTTPException(
            status_code=503,
            detail="No se ha configurado la clave de escritura"
        )

    if not clave_recibida or not secrets.compare_digest(
        clave_recibida, API_WRITE_KEY
    ):
        raise HTTPException(
            status_code=403,
            detail="No autorizado para modificar resenas"
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


@app.post("/resenas", status_code=201)
def crear_resena(
    datos: ResenaNueva,
    x_api_key: str | None = Header(
        default=None,
        alias="X-API-Key"
    )
):
    verificar_clave(x_api_key)

    documento = {
        "doc_pasajero": datos.doc_pasajero,
        "doc_conductor": datos.doc_conductor,
        "nombre_pasajero": datos.nombre_pasajero,
        "nombre_conductor": datos.nombre_conductor,
        "viaje": datos.viaje.model_dump(),
        "calificacion": datos.calificacion,
        "comentario": datos.comentario,
        "estado": "publicada",
        "fecha_creacion": datetime.now(timezone.utc),
        "utilidad": 0
    }

    try:
        resultado = resenas.insert_one(documento)

        return {
            "mensaje": "Resena creada correctamente",
            "id": str(resultado.inserted_id),
            "calificacion": datos.calificacion,
            "estado": "publicada"
        }

    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail="Este pasajero ya reseno este viaje"
        )

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="No fue posible guardar la resena"
        )
