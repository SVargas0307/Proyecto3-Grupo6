// Wheels Alpes - RFC3. Agregacion NoSQL de indicadores por conductor.
// Lectura solamente. Oracle APEX cruza estos datos con ESTUDIANTES.UNIVERSIDAD,
// VEHICULOS y CONDUCTOR_ZONA_TARIFARIA, calcula promedio zonal y marca
// conductores bajo dicho promedio. NO hay universidad o zona en esta coleccion.
const wa = db.getSiblingDB('ISIS2304C09202620');
const pipeline = [
  {$match: {
    estado: {$in: ['publicada', 'destacada']},
    doc_conductor: {$type: 'string', $ne: ''},
    calificacion: {$gte: 1, $lte: 5}
  }},
  {$group: {
    _id: '$doc_conductor',
    suma_puntos: {$sum: '$calificacion'},
    total_resenas: {$sum: 1},
    respondidas: {$sum: {$cond: [
      {$ne: [{$ifNull: ['$respuesta.texto', '']}, '']}, 1, 0
    ]}}
  }},
  {$sort: {_id: 1}},
  {$project: {
    _id: 0, doc_conductor: '$_id', suma_puntos: 1,
    total_resenas: 1, respondidas: 1,
    promedio: {$round: [{$divide: ['$suma_puntos', '$total_resenas']}, 2]},
    porcentaje_respuestas: {$round: [
      {$multiply: [{$divide: ['$respondidas', '$total_resenas']}, 100]}, 2
    ]}
  }}
];
print('RFC3 - Estadisticas base para unir con Oracle por documento:');
wa.getCollection('resenas_conductores').aggregate(pipeline).forEach(printjson);
