
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

# ==========================================
# RF2, RF3 y RF5 - Resenas del pasajero
# ==========================================

from bson import ObjectId
from bson.errors import InvalidId


class EditarResena(BaseModel):
    doc_pasajero: str = Field(min_length=1)
    calificacion: int = Field(ge=1, le=5)
    comentario: str = Field(min_length=1, max_length=2000)

    @field_validator("comentario")
    @classmethod
    def limpiar_comentario(cls, valor):
        valor = valor.strip()
        if not valor:
            raise ValueError("El comentario es obligatorio")
        return valor


class EliminarResena(BaseModel):
    doc_pasajero: str = Field(min_length=1)


def convertir_id_resena(resena_id):
    try:
        return ObjectId(resena_id)
    except (InvalidId, TypeError):
        raise HTTPException(
            status_code=400,
            detail="Identificador de resena invalido"
        )


def convertir_fecha(valor):
    if isinstance(valor, datetime):
        return valor.isoformat()
    return None


def verificar_propiedad_y_estado(documento, doc_pasajero):
    if documento is None:
        raise HTTPException(
            status_code=404,
            detail="La resena no existe"
        )

    if documento.get("doc_pasajero") != doc_pasajero:
        raise HTTPException(
            status_code=403,
            detail="Esta resena no pertenece al pasajero"
        )

    if documento.get("eliminado_por") == "conductor":
        raise HTTPException(
            status_code=409,
            detail="El conductor elimino esta resena"
        )

    if documento.get("estado") not in (
        "publicada", "destacada"
    ):
        raise HTTPException(
            status_code=409,
            detail="La resena ya fue eliminada"
        )


# RF5 - Consultar el historial propio
@app.get("/resenas/mias")
def consultar_mis_resenas(
    doc_pasajero: str = Query(..., min_length=1),
    pagina: int = Query(1, ge=1),
    limite: int = Query(20, ge=1, le=100),
    x_api_key: str | None = Header(
        default=None, alias="X-API-Key"
    )
):
    verificar_clave(x_api_key)

    filtro = {"doc_pasajero": doc_pasajero}

    try:
        total = resenas.count_documents(filtro)

        documentos = list(
            resenas.find(filtro)
            .sort("fecha_creacion", DESCENDING)
            .skip((pagina - 1) * limite)
            .limit(limite)
        )

        items = []

        for documento in documentos:
            respuesta = documento.get("respuesta")
            tiene_respuesta = (
                isinstance(respuesta, dict)
                and bool(respuesta.get("texto"))
            )

            items.append({
                "id": str(documento["_id"]),
                "conductor": documento.get(
                    "nombre_conductor", "Conductor"
                ),
                "doc_conductor": documento.get(
                    "doc_conductor"
                ),
                "viaje": documento.get("viaje", {}),
                "calificacion": documento.get(
                    "calificacion"
                ),
                "comentario": documento.get(
                    "comentario"
                ),
                "estado": documento.get("estado"),
                "respondida": tiene_respuesta,
                "respuesta_conductor": (
                    respuesta.get("texto")
                    if tiene_respuesta
                    else None
                ),
                "fecha": convertir_fecha(
                    documento.get("fecha_creacion")
                ),
                "fecha_actualizacion": convertir_fecha(
                    documento.get("fecha_actualizacion")
                ),
                "fecha_eliminacion": convertir_fecha(
                    documento.get("fecha_eliminacion")
                )
            })

        return {
            "total": total,
            "pagina": pagina,
            "limite": limite,
            "items": items
        }

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="Error al consultar el historial"
        )


# RF2 - Editar una resena propia
@app.patch("/resenas/{resena_id}")
def editar_resena(
    resena_id: str,
    datos: EditarResena,
    x_api_key: str | None = Header(
        default=None, alias="X-API-Key"
    )
):
    verificar_clave(x_api_key)
    identificador = convertir_id_resena(resena_id)

    try:
        documento = resenas.find_one(
            {"_id": identificador}
        )

        verificar_propiedad_y_estado(
            documento, datos.doc_pasajero
        )

        resenas.update_one(
            {
                "_id": identificador,
                "doc_pasajero": datos.doc_pasajero,
                "estado": {
                    "$in": ["publicada", "destacada"]
                }
            },
            {
                "$set": {
                    "calificacion": datos.calificacion,
                    "comentario": datos.comentario,
                    "fecha_actualizacion": datetime.now(
                        timezone.utc
                    )
                }
            }
        )

        return {
            "mensaje": "Resena actualizada correctamente",
            "id": resena_id
        }

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="Error al actualizar la resena"
        )


# RF3 - Eliminacion logica por el pasajero
@app.post("/resenas/{resena_id}/eliminar")
def eliminar_resena(
    resena_id: str,
    datos: EliminarResena,
    x_api_key: str | None = Header(
        default=None, alias="X-API-Key"
    )
):
    verificar_clave(x_api_key)
    identificador = convertir_id_resena(resena_id)

    try:
        documento = resenas.find_one(
            {"_id": identificador}
        )

        verificar_propiedad_y_estado(
            documento, datos.doc_pasajero
        )

        resenas.update_one(
            {
                "_id": identificador,
                "doc_pasajero": datos.doc_pasajero,
                "estado": {
                    "$in": ["publicada", "destacada"]
                }
            },
            {
                "$set": {
                    "estado": "eliminada",
                    "eliminado_por": "pasajero",
                    "fecha_eliminacion": datetime.now(
                        timezone.utc
                    )
                }
            }
        )

        return {
            "mensaje": "Resena eliminada correctamente",
            "id": resena_id,
            "estado": "eliminada"
        }

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="Error al eliminar la resena"
        )
