# Clasificación de documentos con IA

Plataforma institucional para ingresar PDF con OCR, procesarlos de forma asíncrona,
generar metadatos configurables y conservar trazabilidad del procesamiento y los fallos.

El backend local dispone de HTTPS, cuentas locales, permisos y auditoría persistida
en PostgreSQL con TLS. RabbitMQ está integrado para pruebas sintéticas. La ingestión,
el procesamiento documental y la interfaz visual siguen pendientes. Docker se ha
diferido a una feature final.

## Desarrollo por features

Cada feature tendrá una ficha en `docs/features/` con alcance, exclusiones, rama,
decisiones, pruebas, evidencia y pendientes. Las recomendaciones se identificarán
como propuestas hasta su aprobación.

Flujo local: rama desde `develop` → implementación y verificación → commit → merge
en `develop`. Las ramas nuevas usarán `feature/nombre-feature` hasta nueva indicación.
No se renombrarán las
ramas existentes. Los releases tendrán versión y tag cuando cumplan criterios
acordados. Las publicaciones remotas requieren autorización expresa.

## Documentación

- [Requisitos y restricciones](docs/requirements.md).
- [Preguntas y decisiones pendientes](docs/open-questions.md).
- [F001: acuerdos de trabajo](docs/features/F001-project-agreements.md).
- [F002: base backend segura](docs/features/F002-secure-foundation.md).
- [F002A: secretos en .env](docs/features/F002A-secrets-env.md).
- [F002B: RabbitMQ con TLS](docs/features/F002B-rabbitmq-tls.md).
- [Publicar y ver mensajes de prueba](docs/rabbitmq-local.md).
- [F003: cuentas locales, permisos y auditoría](docs/features/F003-local-accounts-proposal.md).
- [Arrancar y probar usuarios por HTTPS](docs/identity-local.md).
- [Contrato OpenAPI](docs/api/F003-openapi.json).
- [Desarrollo y verificación local](docs/development.md).
- [Arquitectura y patrones actuales](docs/architecture.md).
- [ADR aprobado: mensajería](docs/decisions/0001-messaging.md).
- [ADR: alcance local y TLS](docs/decisions/0002-secure-foundation.md).

Base aprobada: Python/FastAPI, PostgreSQL, RabbitMQ y Celery con una aplicación
modular y procesos API/workers separados. Docker Compose y el arranque de servicios
Linux se comprobarán en la feature final; no están implementados en F002.

## Protección de la información

Es requisito cifrar las comunicaciones y proteger los datos almacenados, incluidos
PDF, texto, base de datos, registros, respaldos y claves. La red interna de Docker
no sustituye TLS. El responsable confirma cifrado en las ubicaciones actuales; la
cobertura del despliegue y respaldos deberá comprobarse antes de usar datos reales.

La base local usa una CA privada de desarrollo sin instalarla en Windows. Los
certificados y claves TLS se generan en `.local/`; las credenciales operativas se
guardan en el `.env` de la raíz. Ambos están ignorados por Git. No hay contraseñas
predeterminadas. Consulte la guía de desarrollo para arrancar HTTPS.

No incorporar documentos institucionales reales, credenciales, claves privadas ni
volcados de base de datos al repositorio. Las pruebas utilizarán datos sintéticos.
