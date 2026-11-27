
import os
import re
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
        if not isinstance(valor, str) or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}", valor
        ):
            raise ValueError("La fecha debe ser YYYY-MM-DD")
        try:
            datetime.strptime(valor, "%Y-%m-%d")
        except ValueError:
            raise ValueError("La fecha debe ser YYYY-MM-DD")
        return valor

    @field_validator("hora_salida")
    @classmethod
    def validar_hora(cls, valor):
        if not isinstance(valor, str) or not re.fullmatch(
            r"[0-9]{2}:[0-9]{2}", valor
        ):
            raise ValueError("La hora debe ser HH:MM")
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

        resultado = resenas.update_one(
            {
                "_id": identificador,
                "doc_pasajero": datos.doc_pasajero,
                "estado": {
                    "$in": ["publicada", "destacada"]
                },
                "eliminado_por": {"$ne": "conductor"}
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

        if resultado.matched_count != 1:
            raise HTTPException(
                status_code=409,
                detail="La resena ya no se puede editar"
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

        resultado = resenas.update_one(
            {
                "_id": identificador,
                "doc_pasajero": datos.doc_pasajero,
                "estado": {
                    "$in": ["publicada", "destacada"]
                },
                "eliminado_por": {"$ne": "conductor"}
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

        if resultado.matched_count != 1:
            raise HTTPException(
                status_code=409,
                detail="La resena ya no se puede eliminar"
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

# =====================================================
# RF6 - CONDUCTOR CALIFICA A PASAJERO
# =====================================================

from datetime import datetime, timezone

from fastapi import Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from pymongo import DESCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError


# Reutilizar la conexion existente a MongoDB
resenas_pasajeros = base_datos["resenas_pasajeros"]


# Datos que recibiremos desde Oracle APEX
class CalificacionPasajeroNueva(BaseModel):

    doc_conductor: str = Field(min_length=1)
    doc_pasajero: str = Field(min_length=1)

    nombre_conductor: str = Field(min_length=1)
    nombre_pasajero: str = Field(min_length=1)

    viaje: DatosViaje

    calificacion: int = Field(ge=1, le=5)

    comentario: str | None = Field(
        default=None,
        max_length=2000
    )

    @field_validator("comentario")
    @classmethod
    def limpiar_comentario_pasajero(cls, valor):

        if valor is None:
            return None

        valor = valor.strip()

        if not valor:
            return None

        return valor


# -----------------------------------------------------
# CREAR UNA CALIFICACION DE CONDUCTOR A PASAJERO
# -----------------------------------------------------

@app.post(
    "/resenas/pasajeros",
    status_code=201
)
def crear_calificacion_pasajero(
    datos: CalificacionPasajeroNueva,
    x_api_key: str | None = Header(
        default=None,
        alias="X-API-Key"
    )
):

    # Solo nuestra aplicacion APEX puede escribir
    verificar_clave(x_api_key)

    documento = {
        "doc_conductor": datos.doc_conductor,
        "doc_pasajero": datos.doc_pasajero,

        "nombre_conductor": datos.nombre_conductor,
        "nombre_pasajero": datos.nombre_pasajero,

        "viaje": {
            "placa": datos.viaje.placa,
            "fecha": datos.viaje.fecha,
            "hora_salida": datos.viaje.hora_salida
        },

        "calificacion": datos.calificacion,

        "estado": "publicada",

        "fecha_creacion": datetime.now(
            timezone.utc
        )
    }

    # El comentario es opcional
    if datos.comentario is not None:
        documento["comentario"] = datos.comentario

    try:

        resultado = resenas_pasajeros.insert_one(
            documento
        )

        return {
            "mensaje": (
                "Calificacion del pasajero publicada"
            ),
            "id": str(resultado.inserted_id),
            "estado": "publicada"
        }

    except DuplicateKeyError:

        raise HTTPException(
            status_code=409,
            detail=(
                "Este conductor ya califico a este "
                "pasajero en ese viaje."
            )
        )

    except PyMongoError:

        raise HTTPException(
            status_code=503,
            detail=(
                "No fue posible guardar la calificacion."
            )
        )



# CONSULTAR CALIFICACIONES PUBLICAS DE UN PASAJERO


@app.get("/pasajeros/calificaciones/publicas")
def consultar_calificaciones_pasajero(
    doc_pasajero: str = Query(..., min_length=1),
    pagina: int = Query(1, ge=1),
    limite: int = Query(20, ge=1, le=100)
):

    filtro = {
        "doc_pasajero": doc_pasajero,
        "estado": "publicada"
    }

    try:

        total = resenas_pasajeros.count_documents(
            filtro
        )

        documentos = list(
            resenas_pasajeros.find(filtro)
            .sort(
                "fecha_creacion",
                DESCENDING
            )
            .skip((pagina - 1) * limite)
            .limit(limite)
        )

        items = []

        for documento in documentos:

            items.append({
                "id": str(documento["_id"]),

                "conductor": documento.get(
                    "nombre_conductor", "Conductor"
                ),

                "pasajero": documento.get(
                    "nombre_pasajero", "Pasajero"
                ),

                "viaje": documento.get(
                    "viaje", {}
                ),

                "calificacion": documento.get(
                    "calificacion"
                ),

                "comentario": documento.get(
                    "comentario", ""
                ),

                "fecha": (
                    documento["fecha_creacion"].isoformat()
                    if documento.get("fecha_creacion")
                    else None
                )
            })

        # Calcular el promedio sobre TODAS las
        # calificaciones, no solo la pagina actual
        promedio_datos = list(
            resenas_pasajeros.aggregate([
                {
                    "$match": filtro
                },
                {
                    "$group": {
                        "_id": None,
                        "promedio": {
                            "$avg": "$calificacion"
                        }
                    }
                }
            ])
        )

        if promedio_datos:
            promedio = round(
                promedio_datos[0]["promedio"],
                2
            )
        else:
            promedio = None

        return {
            "doc_pasajero": doc_pasajero,
            "total": total,
            "promedio": promedio,
            "pagina": pagina,
            "limite": limite,
            "items": items
        }

    except PyMongoError:

        raise HTTPException(
            status_code=503,
            detail=(
                "Error al consultar las calificaciones."
            )
        )

# RF7, RF8 Y RF9 - GESTION DE RESENAS DEL CONDUCTOR


from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId

from fastapi import Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from pymongo.errors import PyMongoError



class RespuestaOficialConductor(BaseModel):
    doc_conductor: str = Field(min_length=1)
    texto: str = Field(min_length=1, max_length=2000)

    @field_validator("texto")
    @classmethod
    def validar_texto_respuesta(cls, valor):
        valor = valor.strip()

        if not valor:
            raise ValueError(
                "La respuesta no puede estar vacia"
            )

        return valor


class EliminacionPorConductor(BaseModel):
    doc_conductor: str = Field(min_length=1)
    motivo: str = Field(min_length=5, max_length=500)

    @field_validator("motivo")
    @classmethod
    def validar_motivo(cls, valor):
        valor = valor.strip()

        if len(valor) < 5:
            raise ValueError(
                "Debes indicar el motivo de eliminacion"
            )

        return valor




def fecha_conductor_iso(valor):
    if isinstance(valor, datetime):
        return valor.isoformat()

    return None


def buscar_resena_del_conductor(
    resena_id,
    doc_conductor
):
    # Validar el formato del identificador de MongoDB
    try:
        identificador = ObjectId(resena_id)

    except (InvalidId, TypeError):
        raise HTTPException(
            status_code=400,
            detail="Identificador de resena invalido"
        )

    try:
        documento = resenas.find_one({
            "_id": identificador
        })

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="No se pudo consultar la resena"
        )

    if documento is None:
        raise HTTPException(
            status_code=404,
            detail="La resena no existe"
        )

    # Comprobar que la resena pertenece al conductor
    if (
        str(documento.get("doc_conductor"))
        != str(doc_conductor)
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Esta resena no pertenece al conductor"
            )
        )

    # Solo se pueden responder o retirar resenas activas
    if documento.get("estado") not in (
        "publicada",
        "destacada"
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "La resena ya fue eliminada"
            )
        )

    return identificador, documento





@app.patch("/resenas/{resena_id}/respuesta")
def responder_resena_conductor(
    resena_id: str,
    datos: RespuestaOficialConductor,
    x_api_key: str | None = Header(
        default=None,
        alias="X-API-Key"
    )
):
    # Comprobar la clave privada de la API
    verificar_clave(x_api_key)

    identificador, documento = buscar_resena_del_conductor(
        resena_id,
        datos.doc_conductor
    )

    ahora = datetime.now(timezone.utc)

    # Conservar la fecha de la primera respuesta,
    # incluso cuando el conductor edite su texto
    respuesta_anterior = documento.get("respuesta")

    if isinstance(respuesta_anterior, dict):
        fecha_inicial = respuesta_anterior.get(
            "fecha_respuesta"
        )
    else:
        fecha_inicial = None

    if not isinstance(fecha_inicial, datetime):
        fecha_inicial = ahora

    try:
        resultado = resenas.update_one(
            {
                "_id": identificador,
                "doc_conductor": datos.doc_conductor,
                "estado": {
                    "$in": ["publicada", "destacada"]
                }
            },
            {
                "$set": {
                    "respuesta": {
                        "texto": datos.texto,
                        "fecha_respuesta": fecha_inicial
                    },
                    "fecha_actualizacion": ahora
                }
            }
        )

        if resultado.matched_count != 1:
            raise HTTPException(
                status_code=409,
                detail=(
                    "La resena ya no esta disponible "
                    "para responder"
                )
            )

        return {
            "mensaje": (
                "Respuesta del conductor guardada"
            ),
            "id": resena_id,
            "respondida": True,
            "respuesta": datos.texto
        }

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail=(
                "No fue posible guardar la respuesta"
            )
        )






@app.post("/resenas/{resena_id}/eliminar-conductor")
def eliminar_resena_por_conductor(
    resena_id: str,
    datos: EliminacionPorConductor,
    x_api_key: str | None = Header(
        default=None,
        alias="X-API-Key"
    )
):
    verificar_clave(x_api_key)

    identificador, documento = buscar_resena_del_conductor(
        resena_id,
        datos.doc_conductor
    )

    ahora = datetime.now(timezone.utc)

    try:
        resultado = resenas.update_one(
            {
                "_id": identificador,
                "doc_conductor": datos.doc_conductor,
                "estado": {
                    "$in": ["publicada", "destacada"]
                }
            },
            {
                "$set": {
                    "estado": "eliminada",
                    "eliminado_por": "conductor",
                    "motivo_eliminacion": datos.motivo,
                    "fecha_eliminacion": ahora
                }
            }
        )

        if resultado.matched_count != 1:
            raise HTTPException(
                status_code=409,
                detail=(
                    "La resena ya fue eliminada "
                    "o no esta disponible"
                )
            )

        return {
            "mensaje": (
                "Resena retirada del perfil publico"
            ),
            "id": resena_id,
            "estado": "eliminada",
            "eliminado_por": "conductor"
        }

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail=(
                "No fue posible retirar la resena"
            )
        )





@app.get("/conductores/resenas/recibidas")
def consultar_resenas_recibidas(
    doc_conductor: str = Query(..., min_length=1),
    ordenar: str = Query("fecha", pattern="^(fecha|calificacion)$"),
    pagina: int = Query(1, ge=1),
    limite: int = Query(20, ge=1, le=100),
    x_api_key: str | None = Header(
        default=None,
        alias="X-API-Key"
    )
):
    verificar_clave(x_api_key)

    filtro = {
        "doc_conductor": doc_conductor
    }

    if ordenar == "calificacion":
        campo_orden = "calificacion"
    else:
        campo_orden = "fecha_creacion"

    try:
        total = resenas.count_documents(filtro)

        documentos = list(
            resenas.find(filtro)
            .sort([
                (campo_orden, -1),
                ("_id", -1)
            ])
            .skip((pagina - 1) * limite)
            .limit(limite)
        )

        items = []

        for documento in documentos:

            respuesta = documento.get("respuesta")

            if isinstance(respuesta, dict):
                texto_respuesta = respuesta.get("texto")
            else:
                texto_respuesta = None

            items.append({
                "id": str(documento["_id"]),

                "pasajero": documento.get(
                    "nombre_pasajero",
                    "Pasajero"
                ),

                "doc_pasajero": documento.get(
                    "doc_pasajero"
                ),

                "conductor": documento.get(
                    "nombre_conductor",
                    "Conductor"
                ),

                "viaje": documento.get(
                    "viaje", {}
                ),

                "calificacion": documento.get(
                    "calificacion"
                ),

                "comentario": documento.get(
                    "comentario", ""
                ),

                "estado": documento.get(
                    "estado", "publicada"
                ),

                "utilidad": documento.get(
                    "utilidad", 0
                ),

                "respondida": bool(texto_respuesta),

                "respuesta_conductor": texto_respuesta,

                "fecha": fecha_conductor_iso(
                    documento.get("fecha_creacion")
                ),

                "fecha_eliminacion": fecha_conductor_iso(
                    documento.get("fecha_eliminacion")
                ),

                "eliminado_por": documento.get(
                    "eliminado_por"
                )
            })

        return {
            "doc_conductor": doc_conductor,
            "total": total,
            "pagina": pagina,
            "limite": limite,
            "ordenar": ordenar,
            "items": items
        }

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail=(
                "No fue posible consultar el historial"
            )
        )



from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException, Query
from pymongo.errors import PyMongoError


@app.get("/reportes/ranking-conductores")
def ranking_conductores(
    fecha_inicio: date | None = Query(default=None),
    fecha_fin: date | None = Query(default=None)
):

    # Validar el rango solicitado
    if (
        fecha_inicio is not None
        and fecha_fin is not None
        and fecha_inicio > fecha_fin
    ):
        raise HTTPException(
            status_code=400,
            detail="La fecha inicial no puede superar la final."
        )

    # Solo usar resenas activas
    filtro = {
        "estado": {
            "$in": ["publicada", "destacada"]
        },
        "calificacion": {
            "$gte": 1,
            "$lte": 5
        },
        "doc_conductor": {
            "$type": "string",
            "$ne": ""
        }
    }

    # Filtrar por fecha de creacion de la resena
    rango_fechas = {}

    if fecha_inicio is not None:
        rango_fechas["$gte"] = datetime.combine(
            fecha_inicio,
            time.min,
            tzinfo=timezone.utc
        )

    if fecha_fin is not None:
        rango_fechas["$lte"] = datetime.combine(
            fecha_fin,
            time.max,
            tzinfo=timezone.utc
        )

    if rango_fechas:
        filtro["fecha_creacion"] = rango_fechas

    # Agrupar las resenas por conductor
    pipeline = [
        {
            "$match": filtro
        },
        {
            "$group": {
                "_id": "$doc_conductor",

                "nombre_conductor": {
                    "$first": "$nombre_conductor"
                },

                "promedio": {
                    "$avg": "$calificacion"
                },

                "total_resenas": {
                    "$sum": 1
                }
            }
        },
        {
            "$sort": {
                "promedio": -1,
                "total_resenas": -1,
                "_id": 1
            }
        }
    ]

    try:
        resultados = list(
            resenas.aggregate(pipeline)
        )

        items = []

        for resultado in resultados:
            items.append({
                "doc_conductor": str(resultado["_id"]),

                "nombre_conductor": (
                    resultado.get("nombre_conductor")
                    or "Conductor"
                ),

                "promedio": round(
                    float(resultado["promedio"]), 2
                ),

                "total_resenas": resultado["total_resenas"]
            })

        # Devolvemos todos los candidatos ordenados.
        # Oracle aplicara el filtro de zona y tomara
        # los primeros 10 que correspondan.
        return {
            "fecha_inicio": (
                fecha_inicio.isoformat()
                if fecha_inicio else None
            ),
            "fecha_fin": (
                fecha_fin.isoformat()
                if fecha_fin else None
            ),
            "total_conductores": len(items),
            "items": items
        }

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="No fue posible calcular el ranking."
        )


from datetime import datetime, timezone

from fastapi import HTTPException, Query
from pymongo.errors import PyMongoError


@app.get("/reportes/evolucion-conductor")
def evolucion_reputacion_conductor(
    doc_conductor: str = Query(..., min_length=1),
    anio: int = Query(..., ge=2000, le=2100)
):

    # 1. Definir el inicio y el final del año
    fecha_inicio = datetime(
        anio, 1, 1,
        tzinfo=timezone.utc
    )

    fecha_fin = datetime(
        anio + 1, 1, 1,
        tzinfo=timezone.utc
    )

    # 2. Consultar solo reseñas activas del conductor
    filtro = {
        "doc_conductor": doc_conductor,

        "estado": {
            "$in": ["publicada", "destacada"]
        },

        "fecha_creacion": {
            "$gte": fecha_inicio,
            "$lt": fecha_fin
        },

        "calificacion": {
            "$gte": 1,
            "$lte": 5
        }
    }

    # 3. Agrupar calificaciones por mes
    pipeline = [
        {
            "$match": filtro
        },
        {
            "$group": {
                "_id": {
                    "$month": {
                        "date": "$fecha_creacion",
                        "timezone": "UTC"
                    }
                },

                "promedio": {
                    "$avg": "$calificacion"
                },

                "total_resenas": {
                    "$sum": 1
                }
            }
        },
        {
            "$sort": {
                "_id": 1
            }
        }
    ]

    nombres_meses = [
        "Enero",
        "Febrero",
        "Marzo",
        "Abril",
        "Mayo",
        "Junio",
        "Julio",
        "Agosto",
        "Septiembre",
        "Octubre",
        "Noviembre",
        "Diciembre"
    ]

    try:
        resultados = list(
            resenas.aggregate(pipeline)
        )

        # 4. Organizar resultados por número de mes
        datos_por_mes = {}

        for resultado in resultados:

            mes = int(resultado["_id"])

            datos_por_mes[mes] = {
                "promedio": round(
                    float(resultado["promedio"]), 2
                ),

                "total_resenas": int(
                    resultado["total_resenas"]
                )
            }

        # 5. Crear siempre los 12 meses del año
        meses = []

        total_resenas_anio = 0

        for mes in range(1, 13):

            datos = datos_por_mes.get(mes)

            if datos is None:
                promedio = None
                cantidad = 0
            else:
                promedio = datos["promedio"]
                cantidad = datos["total_resenas"]

            total_resenas_anio += cantidad

            meses.append({
                "mes": mes,

                "nombre_mes": nombres_meses[mes - 1],

                "promedio": promedio,

                "total_resenas": cantidad
            })

        return {
            "doc_conductor": doc_conductor,
            "anio": anio,
            "total_resenas_anio": total_resenas_anio,
            "meses": meses
        }

    except PyMongoError:

        raise HTTPException(
            status_code=503,
            detail=(
                "No fue posible calcular la "
                "evolucion de reputacion."
            )
        )



from fastapi import HTTPException
from pymongo.errors import PyMongoError


@app.get("/reportes/comparacion-conductores")
def comparacion_conductores():

    # Calculamos las estadisticas de cada conductor.
    # Oracle filtrara posteriormente por universidad.

    pipeline = [
        {
            "$match": {
                "estado": {
                    "$in": ["publicada", "destacada"]
                },
                "doc_conductor": {
                    "$type": "string",
                    "$ne": ""
                },
                "calificacion": {
                    "$gte": 1,
                    "$lte": 5
                }
            }
        },
        {
            "$group": {
                "_id": "$doc_conductor",

                "suma_puntos": {
                    "$sum": "$calificacion"
                },

                "total_resenas": {
                    "$sum": 1
                },

                "respondidas": {
                    "$sum": {
                        "$cond": [
                            {
                                "$ne": [
                                    {
                                        "$ifNull": [
                                            "$respuesta.texto",
                                            ""
                                        ]
                                    },
                                    ""
                                ]
                            },
                            1,
                            0
                        ]
                    }
                }
            }
        },
        {
            "$sort": {
                "_id": 1
            }
        }
    ]

    try:
        resultados = list(
            resenas.aggregate(pipeline)
        )

        items = []

        for documento in resultados:

            total = int(documento["total_resenas"])
            puntos = int(documento["suma_puntos"])
            respondidas = int(documento["respondidas"])

            promedio = (
                round(puntos / total, 2)
                if total > 0
                else None
            )

            porcentaje = (
                round(respondidas * 100 / total, 2)
                if total > 0
                else 0
            )

            items.append({
                "doc_conductor": str(documento["_id"]),
                "suma_puntos": puntos,
                "total_resenas": total,
                "respondidas": respondidas,
                "promedio": promedio,
                "porcentaje_respuestas": porcentaje
            })

        return {
            "total_conductores_calificados": len(items),
            "items": items
        }

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail=(
                "No fue posible calcular la "
                "comparacion de conductores."
            )
        )



from datetime import date, datetime, time, timezone

from fastapi import Header, HTTPException, Query
from pymongo.errors import PyMongoError


@app.get("/reportes/tablero-conductor")
def tablero_reputacion_conductor(
    doc_conductor: str = Query(..., min_length=1),
    fecha_inicio: date | None = Query(default=None),
    fecha_fin: date | None = Query(default=None),
    x_api_key: str | None = Header(
        default=None,
        alias="X-API-Key"
    )
):

    # La consulta privada solo puede realizarla APEX
    verificar_clave(x_api_key)

    # ---------------------------------------------
    # 1. VALIDAR EL PERIODO
    # ---------------------------------------------

    if (
        fecha_inicio is not None
        and fecha_fin is not None
        and fecha_inicio > fecha_fin
    ):
        raise HTTPException(
            status_code=400,
            detail="La fecha inicial supera la fecha final."
        )

    filtro = {
        "doc_conductor": doc_conductor
    }

    rango = {}

    if fecha_inicio is not None:
        rango["$gte"] = datetime.combine(
            fecha_inicio,
            time.min,
            tzinfo=timezone.utc
        )

    if fecha_fin is not None:
        rango["$lte"] = datetime.combine(
            fecha_fin,
            time.max,
            tzinfo=timezone.utc
        )

    if rango:
        filtro["fecha_creacion"] = rango

    estados_activos = ["publicada", "destacada"]

    # ---------------------------------------------
    # 2. ESTADISTICAS GENERALES
    # ---------------------------------------------

    pipeline_resumen = [
        {
            "$match": filtro
        },
        {
            "$group": {
                "_id": None,

                "total_recibidas": {
                    "$sum": 1
                },

                "total_eliminadas": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$estado", "eliminada"]},
                            1,
                            0
                        ]
                    }
                },

                "total_activas": {
                    "$sum": {
                        "$cond": [
                            {
                                "$in": [
                                    "$estado",
                                    estados_activos
                                ]
                            },
                            1,
                            0
                        ]
                    }
                },

                "total_respondidas": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {
                                        "$in": [
                                            "$estado",
                                            estados_activos
                                        ]
                                    },
                                    {
                                        "$ne": [
                                            {
                                                "$ifNull": [
                                                    "$respuesta.texto",
                                                    ""
                                                ]
                                            },
                                            ""
                                        ]
                                    }
                                ]
                            },
                            1,
                            0
                        ]
                    }
                },

                "promedio_general": {
                    "$avg": {
                        "$cond": [
                            {
                                "$in": [
                                    "$estado",
                                    estados_activos
                                ]
                            },
                            "$calificacion",
                            None
                        ]
                    }
                }
            }
        }
    ]

    # ---------------------------------------------
    # 3. EVOLUCION MENSUAL
    # ---------------------------------------------

    filtro_evolucion = {
        **filtro,

        "estado": {
            "$in": estados_activos
        },

        "calificacion": {
            "$gte": 1,
            "$lte": 5
        }
    }

    pipeline_evolucion = [
        {
            "$match": filtro_evolucion
        },
        {
            "$group": {
                "_id": {
                    "$dateToString": {
                        "format": "%Y-%m",
                        "date": "$fecha_creacion",
                        "timezone": "UTC"
                    }
                },

                "promedio": {
                    "$avg": "$calificacion"
                },

                "total_resenas": {
                    "$sum": 1
                }
            }
        },
        {
            "$sort": {
                "_id": 1
            }
        }
    ]

    # ---------------------------------------------
    # 4. EJECUTAR LAS AGREGACIONES
    # ---------------------------------------------

    try:
        resultados_resumen = list(
            resenas.aggregate(pipeline_resumen)
        )

        resultados_evolucion = list(
            resenas.aggregate(pipeline_evolucion)
        )

        if resultados_resumen:
            resumen = resultados_resumen[0]
        else:
            resumen = {}

        total_recibidas = int(
            resumen.get("total_recibidas", 0)
        )

        total_activas = int(
            resumen.get("total_activas", 0)
        )

        total_respondidas = int(
            resumen.get("total_respondidas", 0)
        )

        total_eliminadas = int(
            resumen.get("total_eliminadas", 0)
        )

        promedio = resumen.get("promedio_general")

        if promedio is not None:
            promedio = round(float(promedio), 2)

        # Porcentaje sobre reseñas activas
        porcentaje_respuestas = (
            round(
                total_respondidas * 100 / total_activas,
                2
            )
            if total_activas > 0
            else 0
        )

        evolucion = []

        for registro in resultados_evolucion:
            evolucion.append({
                "mes": registro["_id"],
                "promedio": round(
                    float(registro["promedio"]),
                    2
                ),
                "total_resenas": int(
                    registro["total_resenas"]
                )
            })

        return {
            "doc_conductor": doc_conductor,

            "resumen": {
                "promedio_general": promedio,
                "total_recibidas": total_recibidas,
                "total_activas": total_activas,
                "total_respondidas": total_respondidas,
                "porcentaje_respuestas": porcentaje_respuestas,
                "total_eliminadas": total_eliminadas
            },

            "evolucion": evolucion
        }

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail=(
                "No fue posible calcular el tablero "
                "de reputacion del conductor."
            )
        )



from datetime import date, datetime, time, timedelta, timezone

from fastapi import Header, HTTPException, Query
from pymongo.errors import PyMongoError


@app.get("/reportes/tablero-pasajero")
def tablero_reputacion_pasajero(
    doc_pasajero: str = Query(..., min_length=1),
    fecha_inicio: date | None = Query(default=None),
    fecha_fin: date | None = Query(default=None),
    x_api_key: str | None = Header(
        default=None,
        alias="X-API-Key"
    )
):

    # 1. Proteger el acceso a los datos del pasajero
    verificar_clave(x_api_key)

    # 2. Comprobar las fechas
    if (
        fecha_inicio is not None
        and fecha_fin is not None
        and fecha_inicio > fecha_fin
    ):
        raise HTTPException(
            status_code=400,
            detail="La fecha inicial supera la fecha final."
        )

    rango = {}

    if fecha_inicio is not None:
        rango["$gte"] = datetime.combine(
            fecha_inicio,
            time.min,
            tzinfo=timezone.utc
        )

    if fecha_fin is not None:
        rango["$lte"] = datetime.combine(
            fecha_fin,
            time.max,
            tzinfo=timezone.utc
        )

    # 3. Filtrar las resenas escritas por el pasajero
    filtro_escritas = {
        "doc_pasajero": doc_pasajero
    }

    if rango:
        filtro_escritas["fecha_creacion"] = rango

    # Incluye publicadas y eliminadas en el total.
    # El promedio otorgado usa solamente resenas
    # activas para no incluir calificaciones retiradas.
    pipeline_escritas = [
        {
            "$match": filtro_escritas
        },
        {
            "$group": {
                "_id": None,

                "total_escritas": {
                    "$sum": 1
                },

                "total_eliminadas": {
                    "$sum": {
                        "$cond": [
                            {
                                "$eq": [
                                    "$estado",
                                    "eliminada"
                                ]
                            },
                            1,
                            0
                        ]
                    }
                },

                "total_con_respuesta": {
                    "$sum": {
                        "$cond": [
                            {
                                "$ne": [
                                    {
                                        "$ifNull": [
                                            "$respuesta.texto",
                                            ""
                                        ]
                                    },
                                    ""
                                ]
                            },
                            1,
                            0
                        ]
                    }
                },

                "promedio_otorgado": {
                    "$avg": {
                        "$cond": [
                            {
                                "$in": [
                                    "$estado",
                                    [
                                        "publicada",
                                        "destacada"
                                    ]
                                ]
                            },
                            "$calificacion",
                            None
                        ]
                    }
                }
            }
        }
    ]

    # 4. Buscar calificaciones que otros conductores
    # le han otorgado al pasajero
    filtro_recibidas = {
        "doc_pasajero": doc_pasajero,
        "estado": "publicada",
        "calificacion": {
            "$gte": 1,
            "$lte": 5
        }
    }

    if rango:
        filtro_recibidas["fecha_creacion"] = rango

    pipeline_recibidas = [
        {
            "$match": filtro_recibidas
        },
        {
            "$group": {
                "_id": None,

                "total_recibidas": {
                    "$sum": 1
                },

                "promedio_recibido": {
                    "$avg": "$calificacion"
                }
            }
        }
    ]

    # 5. Ejecutar ambas agregaciones
    try:
        escritas = list(
            resenas.aggregate(pipeline_escritas)
        )

        recibidas = list(
            resenas_pasajeros.aggregate(
                pipeline_recibidas
            )
        )

        datos_escritos = (
            escritas[0] if escritas else {}
        )

        datos_recibidos = (
            recibidas[0] if recibidas else {}
        )

        promedio_otorgado = datos_escritos.get(
            "promedio_otorgado"
        )

        promedio_recibido = datos_recibidos.get(
            "promedio_recibido"
        )

        if promedio_otorgado is not None:
            promedio_otorgado = round(
                float(promedio_otorgado), 2
            )

        if promedio_recibido is not None:
            promedio_recibido = round(
                float(promedio_recibido), 2
            )

        return {
            "doc_pasajero": doc_pasajero,

            "resumen": {
                "total_escritas": int(
                    datos_escritos.get(
                        "total_escritas", 0
                    )
                ),

                "total_eliminadas": int(
                    datos_escritos.get(
                        "total_eliminadas", 0
                    )
                ),

                "promedio_otorgado": promedio_otorgado,

                "total_con_respuesta": int(
                    datos_escritos.get(
                        "total_con_respuesta", 0
                    )
                ),

                "total_recibidas": int(
                    datos_recibidos.get(
                        "total_recibidas", 0
                    )
                ),

                "promedio_recibido": promedio_recibido
            }
        }

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail=(
                "No fue posible calcular el tablero "
                "de reputacion del pasajero."
            )
        )
