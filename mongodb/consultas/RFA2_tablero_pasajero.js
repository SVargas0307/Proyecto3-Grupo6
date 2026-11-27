// Wheels Alpes - RFA2. Indicadores de reputacion de un pasajero.
// Lectura solamente; se agregan dos colecciones distintas.
const wa = db.getSiblingDB('ISIS2304C09202620');
// Tomamos un pasajero real de los datos de prueba. Puede reemplazarse por su documento.
const ejemplo = wa.getCollection('resenas_conductores').findOne({}, {projection: {doc_pasajero: 1}});
const docPasajero = ejemplo ? ejemplo.doc_pasajero : 'SIN_DATOS';
const fechaInicio = null; // ejemplo: ISODate('2026-01-01T00:00:00Z')
const fechaFin = null;    // ejemplo: ISODate('2026-12-31T23:59:59.999Z')
function aplicarRango(filtro) {
  if (fechaInicio || fechaFin) {
    filtro.fecha_creacion = {};
    if (fechaInicio) filtro.fecha_creacion.$gte = fechaInicio;
    if (fechaFin) filtro.fecha_creacion.$lte = fechaFin;
  }
  return filtro;
}
const pipelineEscritas = [
  {$match: aplicarRango({doc_pasajero: docPasajero})},
  {$group: {
    _id: null,
    total_escritas: {$sum: 1},
    total_eliminadas: {$sum: {$cond: [{$eq: ['$estado', 'eliminada']}, 1, 0]}},
    total_con_respuesta: {$sum: {$cond: [
      {$ne: [{$ifNull: ['$respuesta.texto', '']}, '']}, 1, 0
    ]}},
    promedio_otorgado: {$avg: {$cond: [
      {$in: ['$estado', ['publicada', 'destacada']]}, '$calificacion', null
    ]}}
  }}
];
const pipelineRecibidas = [
  {$match: aplicarRango({
    doc_pasajero: docPasajero,
    estado: 'publicada', calificacion: {$gte: 1, $lte: 5}
  })},
  {$group: {_id: null, total_recibidas: {$sum: 1}, promedio_recibido: {$avg: '$calificacion'}}}
];
const escritas = wa.getCollection('resenas_conductores').aggregate(pipelineEscritas).toArray()[0] || {};
const recibidas = wa.getCollection('resenas_pasajeros').aggregate(pipelineRecibidas).toArray()[0] || {};
const dosDecimales = x => x == null ? null : Math.round(x * 100) / 100;
printjson({doc_pasajero: docPasajero, resumen: {
  total_escritas: escritas.total_escritas || 0,
  total_eliminadas: escritas.total_eliminadas || 0,
  promedio_otorgado: dosDecimales(escritas.promedio_otorgado),
  total_con_respuesta: escritas.total_con_respuesta || 0,
  total_recibidas: recibidas.total_recibidas || 0,
  promedio_recibido: dosDecimales(recibidas.promedio_recibido)
}});
