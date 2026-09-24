# Publicar DealScope en internet (100% automático, para cualquiera)

Esta guía conecta tu proyecto a GitHub (donde vive el código y corre la
actualización automática en la nube) y Vercel (donde se publica el
dashboard con un link real). Una vez configurado, **nadie tiene que
tocar nada nunca** — ni tú, ni la persona que lo visite.

## Parte 1 — Sube el proyecto a GitHub (usando GitHub Desktop, sin comandos)

1. Crea una cuenta gratis en [github.com](https://github.com) si no tienes.
2. Descarga e instala [GitHub Desktop](https://desktop.github.com/) —
   es una app con ventanas, no requiere escribir comandos.
3. Abre GitHub Desktop, inicia sesión con tu cuenta de GitHub.
4. Menú **File → Add Local Repository**. Selecciona tu carpeta
   `~/DealScope`.
5. Si te dice que no es un repositorio Git todavía, dale **"create a
   repository"** ahí mismo.
6. Abajo a la izquierda, en "Summary", escribe algo como
   "Primera versión de DealScope" y dale **Commit to main**.
7. Arriba, dale **Publish repository**. Déjalo como **público** (para
   que Vercel lo pueda leer gratis) y dale publicar.

Listo — tu proyecto ya vive en GitHub, en una URL como
`github.com/tu-usuario/DealScope`.

## Parte 2 — Activa la actualización automática en la nube

1. Ve a tu repositorio en github.com (en el navegador).
2. Haz clic en la pestaña **Actions** (arriba).
3. Deberías ver el workflow "Actualizar DealScope" listado. GitHub a
   veces pide confirmar que quieres activarlo — dale que sí.
4. Para probarlo ya, sin esperar 24 horas: haz clic en el workflow,
   luego en el botón **"Run workflow"** (a la derecha), y confirma.
5. Espera 2-4 minutos y recarga la página — debería aparecer con una
   palomita verde ✅ si todo salió bien.

A partir de ahora, esto corre solo **todos los días**, en los
servidores de GitHub — sin importar si tu Mac está prendida, dormida,
o apagada.

## Parte 3 — Publica el dashboard con un link real (Vercel)

1. Crea una cuenta gratis en [vercel.com](https://vercel.com) — puedes
   entrar directo con tu cuenta de GitHub (botón "Continue with GitHub").
2. Dale **"Add New..." → "Project"**.
3. Busca y selecciona tu repositorio `DealScope`, dale **Import**.
4. No cambies ninguna configuración — Vercel detecta solo que es un
   sitio estático. Dale **Deploy**.
5. En unos segundos te da un link real, algo como
   `dealscope.vercel.app` — ¡ese es el que compartes en tu aplicación!

### Lo más importante: que se actualice solo en Vercel también

Por default, Vercel solo re-publica cuando hay un cambio nuevo en
GitHub. Como el robot de GitHub Actions (Parte 2) hace un commit nuevo
cada vez que actualiza los datos, **Vercel se re-publica solo
automáticamente cada vez que eso pasa** — no tienes que hacer nada
adicional. Todo el ciclo queda encadenado:

```
GitHub Actions (corre el modelo, todos los días)
        ↓ (hace commit del dashboard actualizado)
GitHub detecta el cambio
        ↓
Vercel republica el sitio automáticamente
        ↓
Cualquier persona con el link ve la versión más nueva
```

## (Opcional) Activar la IA real en la nube

Si ya pagaste tu API key de Anthropic:

1. En tu repositorio de GitHub, ve a **Settings → Secrets and variables
   → Actions**.
2. Dale **"New repository secret"**.
3. Nombre: `ANTHROPIC_API_KEY`. Valor: tu key completa (`sk-ant-...`).
4. Guarda. El workflow ya está preparado para detectarla sola y activar
   la IA real automáticamente en la próxima corrida — no hay que tocar
   ningún código.

## Notas honestas

- El plan gratis de GitHub Actions te da minutos de sobra para esto
  (corre unos pocos minutos al día).
- El plan gratis de Vercel es más que suficiente para un sitio como este.
- Si algún día quieres pausarlo: ve a Actions en GitHub y desactiva el
  workflow, o simplemente bórralo.
