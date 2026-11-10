# F001 — Acuerdos de trabajo y requisitos

- Estado: Documentación verificada; integración local prevista en `develop`.
- Fecha: 2026-11-10.
- Rama: `codex/feature-project-agreements`, creada desde `develop`.
- Tipo: documentación; no implementa aplicación ni infraestructura.

## Problema y objetivo

Conservar las decisiones del responsable al pasar a trabajo por features, evitando
confundir requisitos, recomendaciones y funcionalidades implementadas.

## Alcance y archivos

- `README.md`: estado del proyecto, flujo local de trabajo y acceso a documentación.
- `docs/requirements.md`: requisitos, restricciones y secuencia propuesta de features.
- `docs/open-questions.md`: decisiones aún necesarias y momento en que deben cerrarse.
- `docs/decisions/0001-messaging.md`: comparación y recomendación pendiente de aprobación.
- Esta ficha: alcance, comprobaciones y pendientes de F001.

## Exclusiones

Sin código de aplicación, dependencias, contenedores, credenciales, certificados,
usuarios, documentos institucionales ni integración de IA. No se implementa cifrado
ni se afirma que el equipo está protegido. No se publican cambios remotamente.
`AGENTS.md` se incorporará al aprobar el inicio de implementación, conforme a la
instrucción inicial del responsable.

## Decisiones

Se registran la metodología por features, estados e historial, Windows con ejecución
Linux, carpetas, control operativo, configuración de metadatos, permisos, fallidos
y protección de datos. RabbitMQ + Celery y la base técnica permanecen propuestos.

## Riesgos

- Interpretar `success` como aprobación humana sin aclararlo.
- Interpretar eliminación como permiso para destruir la única copia de un PDF.
- Dar por cifrados los volúmenes por usar TLS o Docker.
- Tratar preferencia por A como aprobación definitiva de arquitectura.

## Criterios de aceptación

- [x] Los requisitos aceptados están separados de recomendaciones y pendientes.
- [x] Existe una ficha trazable y una comparación de mensajería sin selección ficticia.
- [x] Los enlaces Markdown locales resuelven a archivos existentes.
- [x] `git diff --cached --check` no reporta errores.
- [x] Se revisó el diff y solo contiene documentación, sin secretos ni datos reales.
- [x] El flujo de rama y destino de integración local está documentado.

## Verificación y evidencia

- Inspección inicial: solo README, un commit y árbol limpio.
- Validación de enlaces con Python: 5 archivos Markdown, 4 enlaces locales, ninguno
  roto. La comprobación no depende de servicios ni documentos externos.
- `git diff --cached --check`: sin errores de espacios o formato del diff.
- Revisión del diff completo y revisión independiente de requisitos: corregida la
  ubicación de TLS como obligación y registrado el objetivo de imágenes descargables.
- No aplican pruebas de aplicación: todavía no hay código ejecutable.

La integración se comprobará mediante el historial Git local de `develop`, conservando
la rama y un merge explícito para que pueda identificarse la entrega de F001.

## Pendientes

Confirmar broker y base técnica; aclarar success/revisión, política de carpetas y
eliminación. Después, acordar F002 antes de implementar infraestructura o seguridad.

Para siguientes features, esta ficha sirve como formato inicial: problema, alcance,
exclusiones, archivos, decisiones, riesgos, criterios, comprobaciones y pendientes.
