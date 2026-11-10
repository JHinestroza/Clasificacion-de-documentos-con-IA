# ADR 0001 — Mensajería y ejecución de tareas

- Estado: **Propuesto; pendiente de aprobación**.
- Fecha: 2026-11-10.
- Feature de registro: F001.

## Contexto

Procesaremos PDF desde una carpeta mediante trabajos independientes de la interfaz.
Se necesitan estados persistentes, recuperación, fallidos y reencolado. El volumen
potencial supera 10 000 documentos mensuales, pero faltan picos, páginas, tamaños y
duraciones para dimensionar. El responsable expresa preferencia provisional por A.

## Alternativas

| Alternativa | Encaje | Coste o limitación para este proyecto |
| --- | --- | --- |
| A. RabbitMQ + Celery | Broker y framework Python para distribuir trabajos, ejecutar tareas y organizar reintentos. | Requiere configurar durabilidad, confirmaciones, límites y recuperación; no los resuelve automáticamente. |
| B. Kafka + consumidores propios | Eventos retenidos, relectura y consumidores independientes; aprendizaje de Kafka con un caso real. | Mayor trabajo inicial de contratos, consumo, reintentos y operación para el flujo actual. |
| C. PostgreSQL como cola de trabajos | Menos servicios iniciales. | Hay que construir y probar reclamación, concurrencia, reintentos y recuperación. |

Celery es un framework de tareas que utiliza un transporte; no es un broker que
reemplace RabbitMQ. Ninguna alternativa elimina la necesidad de idempotencia.
No se atribuyen cifras de rendimiento sin mediciones.

## Recomendación

Elegir A si prima construir el flujo documental recuperable. Elegir B si aprender
Kafka en la V1 justifica el trabajo adicional. Mantener reglas y casos de uso fuera
del adaptador de mensajería; API y workers pueden compartir una base modular.

No existe todavía una decisión aprobada ni una implementación de esta propuesta.

## Consecuencias y riesgos de A

- Ejecutar workers Celery en Linux: Windows no está soportado oficialmente.
- Utilizar TLS verificado, credenciales de servicio restringidas y mensajes JSON
  con identificadores; no incluir PDF, texto documental ni secretos en las tareas.
- Diseñar publicación recuperable mediante outbox y consumidores idempotentes.
  Confirmar el consumo después de guardar el resultado según el cliente elegido.
- Mantener estados e intentos en PostgreSQL. La cola de fallidos no sustituye el
  historial persistente ni debe producir reintentos infinitos.
- Separar reintento del mismo documento de nueva ingestión de un código duplicado.
- Probar caídas antes/después de guardar resultados, reconexiones y reentregas.
- El almacenamiento de archivos requiere recuperación propia; outbox cubre la
  coordinación de base de datos y publicación, no una transacción con los PDF.

## Fuentes primarias consultadas

- [RabbitMQ: fiabilidad](https://www.rabbitmq.com/docs/reliability).
- [RabbitMQ: confirmaciones](https://www.rabbitmq.com/docs/confirms).
- [Celery: introducción y soporte](https://docs.celeryq.dev/en/stable/getting-started/introduction.html).
- [Celery: tareas, reintentos e idempotencia](https://docs.celeryq.dev/en/stable/userguide/tasks.html).
- [Celery: seguridad](https://docs.celeryq.dev/en/stable/userguide/security.html).
- [Kafka: diseño y garantías](https://kafka.apache.org/44/design/design/).
- [Transactional Outbox: referencia](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html).
