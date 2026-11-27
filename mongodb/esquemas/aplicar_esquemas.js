// Wheels Alpes - respaldo reproducible de esquemas e indices.
// Reconstruido fielmente de db.getCollectionInfos() y getIndexes() el 27-11-2026.
// NO ejecutar sobre la base de datos activa a menos que se quiera reaplicar la validacion.
// Ejecucion manual en mongosh, si fuera necesaria: load("mongodb/esquemas/aplicar_esquemas.js")

const dbWA = db.getSiblingDB("ISIS2304C09202620");
const configuraciones = [
  { nombre: "resenas_conductores", validator: {
  "$jsonSchema": {
    "bsonType": "object",
    "required": [
      "doc_pasajero",
      "doc_conductor",
      "viaje",
      "calificacion",
      "comentario",
      "estado",
      "fecha_creacion"
    ],
    "properties": {
      "doc_pasajero": {
        "bsonType": "string"
      },
      "doc_conductor": {
        "bsonType": "string"
      },
      "viaje": {
        "bsonType": "object",
        "required": [
          "placa",
          "fecha",
          "hora_salida"
        ],
        "properties": {
          "placa": {
            "bsonType": "string"
          },
          "fecha": {
            "bsonType": "string"
          },
          "hora_salida": {
            "bsonType": "string"
          }
        }
      },
      "calificacion": {
        "bsonType": "int",
        "minimum": 1,
        "maximum": 5
      },
      "comentario": {
        "bsonType": "string",
        "minLength": 1
      },
      "estado": {
        "enum": [
          "publicada",
          "eliminada",
          "destacada"
        ]
      },
      "fecha_creacion": {
        "bsonType": "date"
      },
      "respuesta": {
        "bsonType": "object",
        "required": [
          "texto",
          "fecha_respuesta"
        ],
        "properties": {
          "texto": {
            "bsonType": "string"
          },
          "fecha_respuesta": {
            "bsonType": "date"
          }
        }
      },
      "fecha_actualizacion": {
        "bsonType": "date"
      },
      "fecha_eliminacion": {
        "bsonType": "date"
      },
      "eliminado_por": {
        "enum": [
          "pasajero",
          "conductor"
        ]
      },
      "utilidad": {
        "bsonType": "int",
        "minimum": 0
      }
    }
  }
}, indice: {
    "doc_pasajero": 1,
    "viaje.placa": 1,
    "viaje.fecha": 1,
    "viaje.hora_salida": 1
  }, nombreIndice: "indice_resena_unica" },
  { nombre: "resenas_pasajeros", validator: {
  "$jsonSchema": {
    "bsonType": "object",
    "required": [
      "doc_conductor",
      "doc_pasajero",
      "viaje",
      "calificacion",
      "estado",
      "fecha_creacion"
    ],
    "properties": {
      "doc_conductor": {
        "bsonType": "string"
      },
      "doc_pasajero": {
        "bsonType": "string"
      },
      "nombre_conductor": {
        "bsonType": "string"
      },
      "nombre_pasajero": {
        "bsonType": "string"
      },
      "viaje": {
        "bsonType": "object",
        "required": [
          "placa",
          "fecha",
          "hora_salida"
        ],
        "properties": {
          "placa": {
            "bsonType": "string"
          },
          "fecha": {
            "bsonType": "string"
          },
          "hora_salida": {
            "bsonType": "string"
          }
        }
      },
      "calificacion": {
        "bsonType": "int",
        "minimum": 1,
        "maximum": 5
      },
      "comentario": {
        "bsonType": "string"
      },
      "estado": {
        "enum": [
          "publicada"
        ]
      },
      "fecha_creacion": {
        "bsonType": "date"
      }
    }
  }
}, indice: {
    "doc_conductor": 1,
    "doc_pasajero": 1,
    "viaje.placa": 1,
    "viaje.fecha": 1,
    "viaje.hora_salida": 1
  }, nombreIndice: "indice_calificacion_pasajero_unica" }
];

configuraciones.forEach((c) => {
  const existe = dbWA.getCollectionInfos({name: c.nombre}).length > 0;
  if (existe) {
    dbWA.runCommand({
      collMod: c.nombre,
      validator: c.validator,
      validationLevel: "strict",
      validationAction: "error"
    });
  } else {
    dbWA.createCollection(c.nombre, {
      validator: c.validator,
      validationLevel: "strict",
      validationAction: "error"
    });
  }
  dbWA.getCollection(c.nombre).createIndex(c.indice, {
    unique: true,
    name: c.nombreIndice
  });
  print("Configuracion aplicada: " + c.nombre);
});
