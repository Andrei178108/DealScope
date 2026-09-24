# Automatización — DealScope se actualiza solo

Este proyecto usa **launchd**, el sistema nativo de macOS para tareas
programadas (más confiable que `cron` en versiones recientes de macOS,
que a veces requiere permisos especiales de "Acceso Total al Disco").

Una vez configurado, **nunca vuelves a abrir la terminal** para actualizar
DealScope — se actualiza solo cada 3 días, y te avisa con una notificación
nativa de Mac cuando termina.

## Instalación (una sola vez)

1. Confirma la ruta completa de tu carpeta del proyecto:
   ```bash
   pwd
   ```
   Copia esa ruta completa (ej. `/Users/tuusuario/DealScope`).

2. Abre el archivo `com.dealscope.refresh.plist` con un editor de texto
   (TextEdit sirve) y reemplaza **las 4 apariciones** de
   `REPLACE_WITH_FULL_PATH` por la ruta que copiaste en el paso 1.
   Guarda el archivo.

3. Copia el archivo a la carpeta de LaunchAgents de tu usuario:
   ```bash
   cp com.dealscope.refresh.plist ~/Library/LaunchAgents/
   ```

4. Carga el agente:
   ```bash
   launchctl load ~/Library/LaunchAgents/com.dealscope.refresh.plist
   ```

5. Listo. Va a correr inmediatamente una vez (por `RunAtLoad`), y después
   cada 3 días automáticamente.

## Cómo saber que está funcionando

- Vas a recibir una **notificación nativa de macOS** cada vez que termine
  una actualización (éxito o fallo).
- Abre `dashboard.html` en cualquier momento: arriba, en la franja de
  "última actualización", vas a ver un punto verde ("Automatización
  activa") o rojo ("última corrida falló") con la fecha exacta.
- El archivo `refresh_log.txt` en la carpeta del proyecto tiene el
  detalle completo de cada corrida, por si algo falla y quieres ver por qué.

## Importante: tu Mac tiene que estar encendida

launchd (igual que cron) solo puede correr tareas si tu Mac está
**encendida y despierta** en ese momento. Si tu Mac está dormida o
apagada cuando le tocaba correr, simplemente se salta esa vez — no pasa
nada grave, corre en el siguiente intento en que la computadora esté
disponible. Si quieres máxima confiabilidad, considera dejar tu Mac
conectada a corriente y sin que se duerma durante la noche, o ajustar
`StartInterval` para que corra en un horario en que sepas que sí vas a
tener la laptop prendida.

## Cómo desactivarlo (si algún día quieres pausarlo)

```bash
launchctl unload ~/Library/LaunchAgents/com.dealscope.refresh.plist
```

## Cómo reactivarlo después

```bash
launchctl load ~/Library/LaunchAgents/com.dealscope.refresh.plist
```
