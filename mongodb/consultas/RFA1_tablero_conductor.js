// Wheels Alpes - RFA1. Tablero de reputacion de un conductor.
// Lectura solamente; dos agregaciones: resumen y evolucion.
const wa = db.getSiblingDB('ISIS2304C09202620');
const docConductor = '9000000001'; // conductor de prueba; modificar si se requiere
const fechaInicio = null; // ejemplo: ISODate('2026-01-01T00:00:00Z')
const fechaFin = null;    // ejemplo: ISODate('2026-12-31T23:59:59.999Z')
const filtro = {doc_conductor: docConductor};
if (fechaInicio || fechaFin) {
  filtro.fecha_creacion = {};
  if (fechaInicio) filtro.fecha_creacion.$gte = fechaInicio;
  if (fechaFin) filtro.fecha_creacion.$lte = fechaFin;
}
const activos = ['publicada', 'destacada'];
const pipelineResumen = [
  {$match: filtro},
  {$group: {
    _id: null,
    total_recibidas: {$sum: 1},
    total_eliminadas: {$sum: {$cond: [{$eq: ['$estado', 'eliminada']}, 1, 0]}},
    total_activas: {$sum: {$cond: [{$in: ['$estado', activos]}, 1, 0]}},
    total_respondidas: {$sum: {$cond: [{$and: [
      {$in: ['$estado', activos]},
      {$ne: [{$ifNull: ['$respuesta.texto', '']}, '']}
    ]}, 1, 0]}},
    promedio_general: {$avg: {$cond: [{$in: ['$estado', activos]}, '$calificacion', null]}}
  }}
];
const filtroEvolucion = Object.assign({}, filtro, {
  estado: {$in: activos}, calificacion: {$gte: 1, $lte: 5}
});
const pipelineEvolucion = [
  {$match: filtroEvolucion},
  {$group: {
    _id: {$dateToString: {format: '%Y-%m', date: '$fecha_creacion', timezone: 'UTC'}},
    promedio: {$avg: '$calificacion'}, total_resenas: {$sum: 1}
  }},
  {$sort: {_id: 1}}
];
const col = wa.getCollection('resenas_conductores');
const r = col.aggregate(pipelineResumen).toArray()[0] || {};
const activas = r.total_activas || 0;
const evolucion = col.aggregate(pipelineEvolucion).toArray().map(x => ({
  mes: x._id, promedio: Math.round(x.promedio * 100) / 100,
  total_resenas: x.total_resenas
}));
printjson({doc_conductor: docConductor, resumen: {
  promedio_general: r.promedio_general == null ? null : Math.round(r.promedio_general * 100) / 100,
  total_recibidas: r.total_recibidas || 0, total_activas: activas,
  total_respondidas: r.total_respondidas || 0,
  porcentaje_respuestas: activas ? Math.round((r.total_respondidas || 0) / activas * 10000) / 100 : 0,
  total_eliminadas: r.total_eliminadas || 0
}, evolucion});
