// Wheels Alpes - RFC1. Ranking de conductores por reputacion.
// Lectura solamente. MongoDB agrupa y ordena; Oracle APEX filtra por zona,
// calcula viajes completados y elige Top 10 segun el filtro elegido.
// Cambie las fechas por valores ISODate si desea filtrar; null = sin filtro.
const wa = db.getSiblingDB('ISIS2304C09202620');
const fechaInicio = null; // ejemplo: ISODate('2026-01-01T00:00:00Z')
const fechaFin = null;    // ejemplo: ISODate('2026-12-31T00:00:00Z')
const filtro = {
  estado: {$in: ['publicada', 'destacada']},
  calificacion: {$gte: 1, $lte: 5},
  doc_conductor: {$type: 'string', $ne: ''}
};
if (fechaInicio || fechaFin) {
  filtro.fecha_creacion = {};
  if (fechaInicio) filtro.fecha_creacion.$gte = fechaInicio;
  if (fechaFin) filtro.fecha_creacion.$lte = fechaFin;
}
const pipeline = [
  {$match: filtro},
  {$group: {
    _id: '$doc_conductor',
    nombre_conductor: {$first: '$nombre_conductor'},
    promedio: {$avg: '$calificacion'},
    total_resenas: {$sum: 1}
  }},
  {$sort: {promedio: -1, total_resenas: -1, _id: 1}},
  {$project: {
    _id: 0, doc_conductor: '$_id', nombre_conductor: 1,
    promedio: {$round: ['$promedio', 2]}, total_resenas: 1
  }}
];
print('RFC1 - Candidatos ordenados (el top 10 y zona se resuelven en APEX):');
wa.getCollection('resenas_conductores').aggregate(pipeline).forEach(printjson);
