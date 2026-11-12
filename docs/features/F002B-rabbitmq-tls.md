# F002B — RabbitMQ local con TLS y cola de prueba

- Estado: Completada para AMQP local; prueba adicional de reinicio pendiente.
- Fecha: 2026-11-12.
- Rama: `feature/rabbitmq-integracion-tls`, desde `develop`.
- Autorización: configuración TLS, usuario/vhost mínimos, prueba real y reinicio del
  servicio aprobados por el responsable; archivos bajo su cuenta Windows.

## Alcance y archivos

`infrastructure/messaging/connection.py` comparte la conexión AMQPS verificada;
`probe.py` y `broker_probe.py` añaden publicación, conteos pasivos y consumo acotado.
`scripts/prepare_rabbitmq_local.py` prepara TLS/definitions sin rotar secretos;
`configure_rabbitmq_windows.ps1` instala y reinicia con consentimiento administrativo;
`verify_rabbitmq_local.py` verifica rechazos reales sin consumir mensajes.
Las pruebas nuevas están en `backend/tests/test_broker_probe.py` y
`test_rabbitmq_setup.py`. Se actualizan README, guía, ADR y acuerdos persistentes.

## Exclusiones

Sin PDF, IA, usuarios del portal, BD de trabajos, UI, worker Celery Windows, Docker
ni exposición remota. No se borran o purgan colas ajenas. Los cambios locales previos
del usuario en `.gitignore` y `scripts/bootstrap_local.py` no pertenecen a esta entrega.

## Criterios

- [x] Conexión AMQPS real con CA/hostname verificados y listener solo local.
- [x] Puerto AMQP sin cifrado desactivado.
- [x] Usuario/vhost de proyecto sin privilegios administrativos y permisos acotados.
- [x] Publicar tres mensajes y observar tres pendientes en la cola dedicada.
- [x] Reencolar sin ACK mantiene el conteo y permite observar redelivery.
- [x] Consumir dos con ACK deja un mensaje sintético para inspección.
- [x] Rechazar contraseña, CA, hostname incorrectos y una cola no autorizada.
- [ ] Comprobación adicional opcional: persistencia tras otro reinicio. No ejecutada
  porque se canceló UAC; no se repitió la solicitud.
- [x] Pruebas de regresión y del preparador, lint, formato y tipos finales correctos.
- [x] Archivos nuevos del proyecto y servicio pertenecen a Usuario, no a cuentas Codex.
- [x] Revisión Git sin secretos; commit/merge local trazable.

## Evidencia

La prueba real de cola produjo
3 mensajes confirmados, reencoló 1 sin reducir el conteo, consumió 2 con ACK y observó
1 redelivery. Quedó 1 mensaje listo. Los seis controles de seguridad reales pasaron.

## Problemas detectados y recuperación

Propiedad y temporales previos de sandbox impedían acceso desde Usuario. Se recuperó
`.local` conservando 11 archivos idénticos y copia en `backups/local-owner-recovery-*`.
Las pruebas usan una base temporal nueva bajo `.local/test-runs`. Se sustituyó
Set-Acl por icacls para aplicar DACL sin exigir privilegios de auditoría del sistema.
El reinicio se realiza con UAC y no crea archivos del proyecto como administrador.

## Próximos pasos

F003 ya tiene aprobación del responsable pero sigue sin implementar. Requiere
PostgreSQL para su verificación real. Docker y los workers Linux permanecen para la
feature final; esta entrega no los declara operativos.

### Verificación final

- Pytest: 89 pruebas pasadas en Windows, sin fallos, warnings u omisiones.
- Lint/formato de backend, pruebas y scripts nuevos: correcto, 30 archivos Python.
- Mypy estricto: sin errores en 21 archivos fuente; pip check correcto.
- Parser PowerShell y ejecución real del instalador: correctos. El servicio arrancó
  por TLS y desactivó 5672; solo escucha AMQP en 127.0.0.1:5671.
- Seis controles de seguridad ejecutados con RabbitMQ real: todos pasaron.
- Prueba adicional de persistencia tras segundo reinicio: pendiente por cancelación
  de UAC. La cola es durable y los mensajes se publican persistentes, pero no se
  declara comprobada su conservación tras reinicio en esta entrega.
- Los archivos previos modificados por el usuario se excluyeron del lint de scripts
  y del commit. No se corrigieron ni descartaron sus cambios.
- Revisión de enlaces, contenidos versionables, propietarios y secretos realizada.

Los primeros intentos de pytest fallaron por permisos del temporal anterior de
sandbox; una base nueva bajo .local/test-runs resolvió el problema y todas las
pruebas volvieron a pasar. No se utiliza el directorio temporal problemático.
