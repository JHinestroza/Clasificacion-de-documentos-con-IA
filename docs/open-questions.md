# Preguntas y decisiones pendientes

Actualizado: 2026-11-18. Cerrar cada decisión antes de implementar la feature afectada.

## Decisiones cerradas

- FastAPI, PostgreSQL, RabbitMQ, Celery y Docker Compose aprobados.
- Nuevas ramas `feature/nombre-feature` hasta nueva indicación.
- `success`: procesamiento de metadatos terminado, sin aprobación humana habitual.
- Los PDF se mueven físicamente a su carpeta de resultado.
- Eliminar un fallido: retirarlo del reencolamiento conservando PDF e historial,
  registrando quién, cuándo y por qué. No es una autorización de borrado físico.
- Docker no está instalado. El responsable difiere esa parte a una feature final.
- El responsable confirma que las ubicaciones actuales están cifradas; no se ha
  comprobado técnicamente la cobertura del host ni la de un futuro servidor.
- Los secretos operativos se guardan en `.env`, excluido del repositorio.
- Las cuentas serán locales y administradas por el superusuario; no se integrará
  inicio de sesión institucional en F003.

## Antes de los usuarios y de utilizar datos reales

- Custodia, recuperación y renovación de claves y certificados institucionales.
  El bootstrap genera una CA de desarrollo sin instalar confianza. En F004A se
  autorizó y verificó su importación únicamente en Usuario CurrentUser\Root.
- El alcance por fondo está implementado en F004B; el de reportes deberá concretarse
  cuando se expongan esos recursos.
  F003 ya implementa cuentas locales, sesiones revocables, permisos y auditoría.
  Recuperación de cuentas y políticas de retención necesitan diseño antes de ampliarlas.
- Acceso solo local o desde otros equipos; API keys para clientes externos si se
  habilita también una API de carga.

## Antes de ingestión, extracción y metadatos

- El primer fondo es UFM; fondos adicionales se administran en el portal.
- Resuelto en F004B: normalización ASCII/mayúsculas, código global único y SHA-256
  como advertencia acotada; entregas completas .part → .pdf.
- Medir páginas habituales/máximas y picos de carga antes de dimensionar producción.
  Límites iniciales de validación aprobados: 5 000 páginas, 30 segundos y 512 MiB.
- Controles por lote confirmados: finalizar la admisión iniciada al pausar/detener;
  conservar pendientes. El efecto sobre la futura ejecución del worker se diseñará en F005.
- Política de reintentos, errores transitorios, documentos sin texto y fallos
  permanentes. Diferenciar cancelar un trabajo de detener el servicio.
- Primeros campos de metadatos, ejemplos sintéticos y esquema de salida esperado.
- Motor inicial: reglas, simulador o IA real; proveedor y autorización de tratamiento
  de datos antes de usar un servicio externo.

## Antes del primer release

- Instalar Docker y definir el despliegue Linux en la feature final; comprobar
  recursos, ubicación de volúmenes y cifrado del almacenamiento y respaldos.
- Revalidar PostgreSQL, RabbitMQ, permisos, reinicios y workers en el despliegue
  Linux; las pruebas locales Windows no sustituyen esa verificación.
- Versión, criterios de aceptación, CI y estrategia de integración de `develop`
  hacia `main`. Publicar el tag, release o imágenes requiere autorización remota.

## Resuelto el 2026-11-12

El alcance detallado de F003 ya fue aprobado; no volver a consultarlo. RabbitMQ está
instalado y se autorizó verificarlo por TLS antes de Docker. PostgreSQL 18.7 está
instalado e integrado por TLS en F003; allí persisten usuarios, sesiones y auditoría.
Docker, los workers Linux y el despliegue completo siguen diferidos a la feature final.

## Respuestas para F004 y entrega inicial F004A

- Se eligió React o Vue; se adopta React/TypeScript/Vite para la interfaz.
- Ejemplos: CAB01.pdf y CAB02.pdf; códigos completos CAB01 y CAB02 conservando ceros.
- Límite por archivo: 100 MB (100 000 000 bytes para la implementación del ingreso).
- Pausa y detención por lote con finalización de la admisión iniciada.
- F004A implementa el portal de cuentas/auditoría; no cambia el esquema documental
  ni permisos del broker. El plan F004 permanece en `feature/ingestion-operacion`.
- Resuelto el 2026-11-13: el responsable autorizó la CA existente en Usuario
  CurrentUser\Root. Confianza y revisión visual del portal verificadas; no se pide
  esa aprobación otra vez. PKI institucional y nuevos equipos conservan sus pendientes.

## F004B — ingreso por carpetas aprobado

El responsable confirmó UFM y aprobó la [propuesta concreta](features/F004B-ingestion-carpetas-proposal.md)
el 2026-11-13. Esquema/ámbito, reglas adicionales, validación/entrega completa y
grants están autorizados; la rama `feature/ingestion-carpetas` entrega implementación y evidencia verificada
antes de integrar en develop. Docker y extracción/metadatos conservan
su alcance posterior. No volver a pedir esa aprobación.
