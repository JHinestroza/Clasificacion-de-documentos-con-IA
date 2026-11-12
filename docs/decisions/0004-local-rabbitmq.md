# ADR 0004 — Integración local de RabbitMQ por TLS

- Estado: Aprobado por el responsable el 2026-11-12.
- Feature: F002B, `feature/rabbitmq-integracion-tls`.

## Contexto y alternativas

El responsable instaló RabbitMQ en Windows y autorizó una prueba real de publicación,
consumo y confirmación con TLS antes de Docker. La instalación de contenedores sigue
pospuesta. Celery/Windows no se presenta como ejecución soportada de workers.

Se elige un productor/consumidor técnico con Kombu, ya disponible en el proyecto.
Esperar a Docker impedía probar ahora; usar AMQP sin TLS contradice el requisito.
La prueba no reemplaza Celery ni cambia la arquitectura aprobada.

## Decisión

Listener AMQPS solo en loopback, sin 5672. Certificado de desarrollo firmado por la
CA existente, con localhost/127.0.0.1. Credenciales de `.env`, hash salado en definitions
para provisionar el usuario, sin privilegios administrativos. Recursos limitados a
la cola y exchange `document_platform.integration`; no se transporta texto ni PDF.

Los mensajes sintéticos usan UUID, tipo, versión y fecha UTC; publicación persistente
con publisher confirms, lectura pasiva de conteos y ACK explícito tras validar.
Reencolar permite observar redelivery. No se añade todavía una BD de trabajos.

El usuario exige archivos accesibles bajo su propia cuenta Windows. Se comprueba la
identidad efectiva y se usa `Usuario` para prepararlos. No se crean cuentas Codex.
SYSTEM recibe lectura de los archivos necesarios por ser la cuenta del servicio
existente; no recibe la clave privada de firma de la CA.

## Consecuencias y límites

Prueba real del broker sin PostgreSQL, UI o Docker. No acredita workers Linux,
procesamiento idempotente, auditoría institucional ni TLS del canal de administración
Erlang. No se habilita acceso remoto. Las credenciales o permisos no se rotan
silenciosamente; la configuración previa ajena al proyecto no se sobrescribe.

La carpeta `.local` existente tenía propietario CodexSandboxOffline. Para recuperar
acceso se conservó una copia completa bajo `backups/` y se recreó como Usuario,
verificando contenido; no se borraron los originales. Los permisos privados nuevos
excluyen las cuentas Codex. Los cambios previos del usuario en `.gitignore` y
`bootstrap_local.py` se conservan fuera del commit de esta feature.
