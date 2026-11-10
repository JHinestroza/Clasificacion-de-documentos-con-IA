# ADR 0002 — Base backend local y comunicaciones seguras

- Estado: Aprobado para F002; despliegue Linux diferido por el responsable.
- Fecha: 2026-11-10.

## Contexto y decisión

El equipo de desarrollo es Windows y no tiene Docker. El responsable aprobó la
base FastAPI/PostgreSQL/RabbitMQ/Celery y pidió dejar Docker para una feature final.
F002 entrega API HTTPS local, configuración centralizada, secretos separados y
pruebas de TLS. No instala software de sistema ni cambia el almacén de confianza.

## Alternativas

- Instalar y probar Docker ahora: descartado por indicación expresa del responsable.
- Implementar transporte HTTP temporal: descartado por el requisito de cifrado.
- Preparar y comprobar localmente el backend HTTPS, dejando integración de servicios
  reales para la feature final: alternativa elegida.

## Límites y responsabilidades

- FastAPI expone únicamente salud/disponibilidad; no admite documentos ni usuarios.
- Un único paquete contiene puntos de entrada API y worker. Configuración, rutas y
  adaptadores están separados; no hay lógica documental en la base.
- La API escucha inicialmente en loopback y exige certificado y clave. Los clientes
  verifican CA y nombre; no hay fallback a HTTP ni modo de aceptar cualquier CA.
- PostgreSQL usa `verify-full`; RabbitMQ requiere CA y verificación del servidor.
  Celery acepta JSON, sin resultados ni control remoto en esta feature.
- La CA de desarrollo y los secretos se generan en `.local/`, fuera de Git. La CA
  privada no se distribuye a clientes ni se instala en Windows. El bootstrap no
  sustituye una política institucional de certificados o de rotación.
- El responsable declara cifrado en las ubicaciones actuales. No se ha auditado el
  host. Los volúmenes, respaldos y servidor futuro necesitan comprobación antes de
  utilizar documentación sensible.
- Celery no tiene soporte oficial de ejecución en Windows: aquí se comprueba su
  configuración, no se presenta un worker Windows como despliegue soportado.

## Riesgos y verificación

Las pruebas locales de TLS verifican conexiones reales a la API: confianza válida,
CA incorrecta, nombre incorrecto y rechazo de HTTP. Pruebas de configuración y
dobles verifican respuestas de disponibilidad sin filtrar errores o secretos.
No sustituyen la integración con PostgreSQL, RabbitMQ y workers Linux, pendiente
de la feature final. No declarar el sistema listo para datos reales por pasar F002.

## Fuentes

- [PostgreSQL: verificación de TLS](https://www.postgresql.org/docs/current/libpq-ssl.html).
- [RabbitMQ: TLS](https://www.rabbitmq.com/docs/ssl).
- [Celery: seguridad](https://docs.celeryq.dev/en/stable/userguide/security.html).
- [Celery: plataformas soportadas](https://docs.celeryq.dev/en/stable/getting-started/introduction.html).
