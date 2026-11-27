// Wheels Alpes - RFC2. Promedio mensual de calificaciones de un conductor.
// Lectura solamente. En Python se completan los meses sin reseñas con 0 casos
// y promedio null; aqui tambien se completan para documentar esa salida.
const wa = db.getSiblingDB('ISIS2304C09202620');
const docConductor = '1000000019'; // Juliana Rodriguez Garcia; cambiar segun la prueba
const anio = 2026;
const inicio = ISODate(`${anio}-01-01T00:00:00Z`);
const fin = ISODate(`${anio + 1}-01-01T00:00:00Z`);
const pipeline = [
  {$match: {
    doc_conductor: docConductor,
    estado: {$in: ['publicada', 'destacada']},
    fecha_creacion: {$gte: inicio, $lt: fin},
    calificacion: {$gte: 1, $lte: 5}
  }},
  {$group: {
    _id: {$month: {date: '$fecha_creacion', timezone: 'UTC'}},
    promedio: {$avg: '$calificacion'}, total_resenas: {$sum: 1}
  }},
  {$sort: {_id: 1}}
];
const datos = wa.getCollection('resenas_conductores').aggregate(pipeline).toArray();
const nombres = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];
const meses = nombres.map((nombre_mes, i) => {
  const registro = datos.find(d => d._id === i + 1);
  return {
    mes: i + 1, nombre_mes,
    promedio: registro ? Math.round(registro.promedio * 100) / 100 : null,
    total_resenas: registro ? registro.total_resenas : 0
  };
});
printjson({doc_conductor: docConductor, anio,
  total_resenas_anio: meses.reduce((n, m) => n + m.total_resenas, 0), meses});
