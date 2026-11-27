// Wheels Alpes - Entrega 3
// Prueba de rechazo de documentos invalidos (RF1 y RF2)
// Reproduce la prueba ejecutada en MongoDB Shell el 27-11-2026.
// Uso: ejecutar en mongosh conectado a la base ISIS2304C09202620.
// No se insertan documentos validos ni se modifica informacion existente.

(function () {
    const base = db.getSiblingDB("ISIS2304C09202620");

    function probarRechazo(coleccion, nombre) {
        const identificador = new ObjectId();
        try {
            // Carece de los campos requeridos; debe ser rechazado por $jsonSchema.
            coleccion.insertOne({ _id: identificador });
            // Limpieza preventiva si el esquema estuviera desactivado.
            coleccion.deleteOne({ _id: identificador });
            print("FALLO: " + nombre + " acepto un documento invalido.");
        } catch (error) {
            if (error.code === 121) {
                print("CORRECTO: " + nombre + " rechazo el documento invalido.");
                print("Codigo de error: " + error.code);
            } else {
                print("ERROR DISTINTO A VALIDACION en " + nombre + ": " + error.message);
            }
        }
    }

    probarRechazo(base.getCollection("resenas_conductores"), "resenas_conductores");
    probarRechazo(base.getCollection("resenas_pasajeros"), "resenas_pasajeros");
})();
