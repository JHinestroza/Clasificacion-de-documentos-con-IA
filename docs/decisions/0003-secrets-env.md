# ADR 0003 — Secretos operativos en .env

- Estado: Aprobado por instrucción expresa del responsable.
- Fecha: 2026-11-10.
- Feature: F002A, rama `feature/secrets-env`.

## Contexto y alternativas

F002 almacenaba contraseñas en archivos individuales bajo `.local/secrets`, con
variables `*_PASSWORD_FILE`. El responsable solicita guardarlas en `.env`.
Mantener los archivos individuales o introducir un gestor externo no corresponde
a esta indicación ni al alcance actual de desarrollo local.

## Decisión

- `.env` de la raíz contiene `APP_DB_ADMIN_PASSWORD`, `APP_DB_PASSWORD` y
  `APP_BROKER_PASSWORD`; no contiene contraseñas predeterminadas.
- La aplicación solo recibe las credenciales de servicio necesarias; no utiliza
  `APP_DB_ADMIN_PASSWORD` para sus consultas. Este valor se reserva para la futura
  provisión administrativa del servicio, no para el superusuario del portal.
- Settings lee `APP_DB_PASSWORD` y `APP_BROKER_PASSWORD` directamente como secretos
  requeridos. Las variables `*_PASSWORD_FILE` dejan de ser el contrato admitido.
- Leer valores literalmente, incluidas secuencias como `${VARIABLE}`, sin evaluación
  de shell ni sustitución dentro de contraseñas. Rechazar variables ambiguas o duplicadas.
- La migración conserva las credenciales actuales, los certificados y la
  configuración personalizada. No imprime valores ni rota secretos.
- Los archivos anteriores se conservan como respaldo local; el backend no los usa.
  Su eliminación o una rotación posterior requieren un procedimiento explícito.
- Las claves privadas TLS continúan en archivos protegidos bajo `.local/certs`,
  con sus rutas en `.env`. No se convierten PEM en variables multilínea.

## Consecuencias y riesgos

`.env` concentra credenciales y debe permanecer fuera de Git, logs, imágenes y
respuestas HTTP. `.env.example` contiene únicamente nombres y valores vacíos/ficticios.
La protección depende también de ACL y del almacenamiento que el responsable
declara cifrado; el archivo no es un administrador de secretos ni se cifra por usar
TLS. Los cambios de credenciales no actualizan por sí solos PostgreSQL o RabbitMQ.

## Verificación

Probar carga desde `.env`, precedencia del entorno, valores literales, redacción,
rechazo de vacíos/débiles/duplicados y migración idempotente sin pérdida ni rotación.
Verificar Git y arranque HTTPS sin imprimir credenciales. Mantener integración
Linux/servicios reales diferida a la feature final.
