# Clasificación de documentos con IA

Plataforma institucional para ingresar PDF con OCR, procesarlos de forma asíncrona,
generar propuestas de metadatos configurables y conservar trazabilidad para su revisión.

El proyecto se encuentra en descubrimiento. Todavía no existen aplicación, servicios,
contenedores ni controles de seguridad implementados.

## Desarrollo por features

Cada feature tendrá una ficha en `docs/features/` con alcance, exclusiones, rama,
decisiones, pruebas, evidencia y pendientes. Las recomendaciones se identificarán
como propuestas hasta su aprobación.

Flujo local: rama desde `develop` → implementación y verificación → commit → merge
en `develop`. Las ramas nuevas usarán `codex/feature-<nombre>`. No se renombrarán las
ramas existentes. Los releases tendrán versión y tag cuando cumplan criterios
acordados. Las publicaciones remotas requieren autorización expresa.

## Documentación

- [Requisitos y restricciones](docs/requirements.md).
- [Preguntas y decisiones pendientes](docs/open-questions.md).
- [F001: acuerdos de trabajo](docs/features/F001-project-agreements.md).
- [ADR propuesto: mensajería](docs/decisions/0001-messaging.md).

La alternativa recomendada es RabbitMQ + Celery con una aplicación modular y
procesos API/workers separados. Esta selección aún no está aprobada.

## Protección de la información

Es requisito cifrar las comunicaciones y proteger los datos almacenados, incluidos
PDF, texto, base de datos, registros, respaldos y claves. La red interna de Docker
no sustituye TLS. Los mecanismos de cifrado en reposo están pendientes de diseño y
verificación del equipo y del almacenamiento.

No incorporar documentos institucionales reales, credenciales, claves privadas ni
volcados de base de datos al repositorio. Las pruebas utilizarán datos sintéticos.
