/* PPI decorativo del login: anillos de alcance, radiales de azimut y un campo de
   reflectividad con persistencia de barrido. No representa datos reales; es un fondo.

   El campo se arma en tres capas: una envolvente de lóbulos anchos que define dónde hay
   precipitación, un ruido fractal de crestas con deformación de dominio que le pone la
   estructura filamentosa, y una cuantización en bandas de 5 dBZ sobre una grilla de celdas
   que después se amplía con interpolación. La base del campo se dibuja apagada y el realce
   lo aporta la estela del haz, así el barrido se nota.

   El lienzo se configura por data-attributes:
     data-cx, data-cy        centro del PPI en fracción del lienzo (0–1). Por defecto 0.78 / 0.42.
     data-radius             radio del alcance máximo, en fracción de la diagonal. Por defecto 0.62.
     data-rpm                vueltas por minuto de la barrida. Por defecto 3 (20 s por giro).
     data-seed               semilla del generador, para repetir el mismo campo.
   Con prefers-reduced-motion: reduce dibuja un único cuadro estático y no anima. */

(function () {
    'use strict';

    const canvas = document.getElementById('login-radar');
    if (!canvas || !canvas.getContext) return;

    const ctx = canvas.getContext('2d');
    const ds = canvas.dataset;
    const CX = parseFloat(ds.cx ?? '0.78');
    const CY = parseFloat(ds.cy ?? '0.42');
    const RADIUS_F = parseFloat(ds.radius ?? '0.62');
    const RPM = parseFloat(ds.rpm ?? '3');
    const RINGS = 4;              // anillos a 60, 120, 180 y 240 km
    const SPOKES = 12;            // radiales cada 30° de azimut
    const FIELD_STEP = 3;         // 1 celda de campo cada 3 píxeles de pantalla
    const DBZ_MIN = 13;           // por debajo no se dibuja nada: entre celdas queda vacío
    const DBZ_MAX = 62;

    // Escala de reflectividad, tomada de los productos del OHMC: verde claro (lluvia débil)
    // · verde · amarillo · naranja · rojo · rojo oscuro (granizo). Sin banda azul.
    const SCALE = [
        [10, [167, 221, 158]],
        [20, [76, 184, 86]],
        [30, [186, 212, 62]],
        [35, [242, 231, 59]],
        [42, [240, 160, 48]],
        [50, [217, 59, 43]],
        [60, [142, 26, 18]]
    ];

    function dbzColor(dbz) {
        if (dbz <= SCALE[0][0]) return SCALE[0][1];
        for (let i = 1; i < SCALE.length; i++) {
            if (dbz <= SCALE[i][0]) {
                const [d0, c0] = SCALE[i - 1];
                const [d1, c1] = SCALE[i];
                const t = (dbz - d0) / (d1 - d0);
                return [
                    Math.round(c0[0] + t * (c1[0] - c0[0])),
                    Math.round(c0[1] + t * (c1[1] - c0[1])),
                    Math.round(c0[2] + t * (c1[2] - c0[2]))
                ];
            }
        }
        return SCALE[SCALE.length - 1][1];
    }

    // Tabla de las 13 bandas de 5 dBZ, precalculada.
    const BANDS = [];
    for (let d = 10; d <= 60; d += 5) {
        const [r, g, b] = dbzColor(d);
        // La opacidad crece con la intensidad: el estratiforme queda tenue y el núcleo macizo.
        const a = Math.round(255 * Math.min(0.98, 0.66 + 0.32 * Math.pow((d - 10) / 50, 0.8)));
        BANDS.push([r, g, b, a]);
    }

    // Generador congruencial: mismo campo en cada carga con la misma semilla.
    let seed = parseInt(ds.seed ?? '20251027', 10);
    function rnd() {
        seed = (seed * 1103515245 + 12345) & 0x7fffffff;
        return seed / 0x7fffffff;
    }

    /* ── Ruido ──────────────────────────────────────────────────
       Ruido de valor con interpolación suave, y sobre él dos derivados:
         fbm      suma de octavas, para la textura general;
         ridged   suma de octavas de (1 − |2n − 1|), que produce crestas alargadas y
                  ramificadas en vez de manchas redondas.
       Las crestas, más la deformación de dominio de abajo, son lo que da la estructura
       filamentosa de un eco real: dedos, huecos y bordes dentados. */
    const NW = 128;
    const noiseGrid = new Float32Array(NW * NW);

    function buildNoise() {
        for (let i = 0; i < noiseGrid.length; i++) noiseGrid[i] = rnd();
    }

    function smooth(t) { return t * t * (3 - 2 * t); }

    function noise2(x, y) {
        const xi = Math.floor(x), yi = Math.floor(y);
        const tx = smooth(x - xi), ty = smooth(y - yi);
        const i0 = ((yi % NW) + NW) % NW, i1 = (i0 + 1) % NW;
        const j0 = ((xi % NW) + NW) % NW, j1 = (j0 + 1) % NW;
        const a = noiseGrid[i0 * NW + j0], b = noiseGrid[i0 * NW + j1];
        const c = noiseGrid[i1 * NW + j0], d = noiseGrid[i1 * NW + j1];
        return (a + (b - a) * tx) * (1 - ty) + (c + (d - c) * tx) * ty;
    }

    function fbm(x, y, oct) {
        let v = 0, amp = 0.5, norm = 0;
        for (let i = 0; i < oct; i++) {
            v += amp * noise2(x, y);
            norm += amp;
            amp *= 0.5;
            x *= 2.03; y *= 2.03;
        }
        return v / norm;
    }

    function ridged(x, y, oct) {
        let v = 0, amp = 0.5, norm = 0;
        for (let i = 0; i < oct; i++) {
            v += amp * (1 - Math.abs(2 * noise2(x, y) - 1));
            norm += amp;
            amp *= 0.5;
            x *= 2.11; y *= 2.11;
        }
        return v / norm;
    }

    /* Envolvente del sistema: lóbulos anchos que definen dónde hay precipitación y con
       qué intensidad máxima. La textura queda a cargo del ruido, no de los lóbulos, así
       que acá no hay núcleos puntuales: solo la forma general del sistema. */
    let lobes = [];

    function buildLobes() {
        lobes = [];

        // Sistema principal: lóbulos encadenados sobre un eje, el del lado convectivo más
        // intenso. El azimut se restringe al cuadrante inferior izquierdo del lienzo, que
        // es la zona del panel libre de texto.
        const th0 = Math.PI * (0.58 + rnd() * 0.34);
        const r0 = 0.32 + rnd() * 0.2;
        const axis = th0 + Math.PI / 2 + (rnd() - 0.5) * 0.7;
        const x0 = Math.cos(th0) * r0, y0 = Math.sin(th0) * r0;
        const ux = Math.cos(axis), uy = Math.sin(axis);
        const n = 5;

        for (let i = 0; i < n; i++) {
            const t = (i / (n - 1) - 0.5) * 2;
            lobes.push({
                x: x0 + ux * t * 0.40 + (rnd() - 0.5) * 0.07,
                y: y0 + uy * t * 0.40 + (rnd() - 0.5) * 0.07,
                sx: 0.135 + rnd() * 0.05,
                sy: 0.080 + rnd() * 0.030,
                rot: axis + (rnd() - 0.5) * 0.4,
                w: 1 - 0.32 * Math.abs(t)
            });
        }

        // Dos sistemas desprendidos en otros cuadrantes, más débiles.
        for (let i = 0; i < 2; i++) {
            const th = th0 + Math.PI * (0.5 + rnd() * 0.9);
            const r = 0.35 + rnd() * 0.5;
            lobes.push({
                x: Math.cos(th) * r,
                y: Math.sin(th) * r,
                sx: 0.085 + rnd() * 0.05,
                sy: 0.055 + rnd() * 0.035,
                rot: rnd() * Math.PI,
                w: 0.5 + rnd() * 0.3
            });
        }
    }

    let w = 0, h = 0, cx = 0, cy = 0, R = 0;
    const field = document.createElement('canvas');
    const fctx = field.getContext('2d');
    // Lienzo intermedio donde el campo se enmascara con la estela del haz.
    const layer = document.createElement('canvas');
    const lctx = layer.getContext('2d');

    /* Dibuja el campo cuantizado en el lienzo auxiliar, una sola vez por resize.
       Para cada celda: envolvente por lóbulos, deformación de dominio, crestas de ruido,
       saturación blanda y cuantización en bandas de 5 dBZ. */
    function buildField() {
        const fw = Math.max(1, Math.ceil(w / FIELD_STEP));
        const fh = Math.max(1, Math.ceil(h / FIELD_STEP));
        field.width = fw;
        field.height = fh;

        const img = fctx.createImageData(fw, fh);
        const data = img.data;
        const fcx = cx / FIELD_STEP;
        const fcy = cy / FIELD_STEP;
        const fR = R / FIELD_STEP;

        const L = lobes.map(function (c) {
            return {
                px: fcx + c.x * fR,
                py: fcy + c.y * fR,
                cos: Math.cos(-c.rot),
                sin: Math.sin(-c.rot),
                ix: 1 / (2 * Math.pow(c.sx * fR, 2)),
                iy: 1 / (2 * Math.pow(c.sy * fR, 2)),
                reach: Math.max(c.sx, c.sy) * fR * 3.2,
                w: c.w
            };
        });

        // Escalas de ruido, en celdas de campo.
        const sTex = fR * 0.085;    // textura principal
        const sWarp = fR * 0.22;    // deformación de dominio
        const WARP = fR * 0.075;    // amplitud de la deformación

        for (let y = 0; y < fh; y++) {
            for (let x = 0; x < fw; x++) {
                const dxr = x - fcx, dyr = y - fcy;
                const rr = Math.hypot(dxr, dyr);
                if (rr > fR) continue;                       // fuera del alcance no hay eco

                let env = 0;
                for (let i = 0; i < L.length; i++) {
                    const k = L[i];
                    const dx = x - k.px, dy = y - k.py;
                    if (Math.abs(dx) > k.reach || Math.abs(dy) > k.reach) continue;
                    const u = dx * k.cos - dy * k.sin;
                    const v = dx * k.sin + dy * k.cos;
                    env += k.w * Math.exp(-(u * u * k.ix + v * v * k.iy));
                }
                if (env > 1) env = 1;

                const cover = env;
                if (cover < 0.07) continue;

                // Deformación de dominio: desplaza las coordenadas de la textura con otro
                // ruido. Es lo que curva las crestas y evita que se lean como un patrón.
                const wx = x + WARP * (fbm(x / sWarp, y / sWarp, 3) - 0.5) * 2;
                const wy = y + WARP * (fbm(x / sWarp + 53.7, y / sWarp + 11.3, 3) - 0.5) * 2;

                const tex = ridged(wx / sTex, wy / sTex, 4);

                // El estratiforme ocupa casi toda la superficie y los máximos convectivos
                // salen solo donde coinciden envolvente alta y cresta de ruido alta.
                let dbz = 62 * Math.pow(cover, 0.75) * (0.42 + 0.72 * Math.pow(tex, 1.35));

                dbz = DBZ_MAX * (1 - Math.exp(-dbz / 42));
                if (dbz < DBZ_MIN) continue;

                // Borde del alcance: los últimos kilómetros se desvanecen.
                const edge = Math.min(1, (fR - rr) / (fR * 0.05));

                const band = BANDS[Math.max(0, Math.min(BANDS.length - 1, Math.floor((dbz - 10) / 5)))];
                const o = (y * fw + x) * 4;
                data[o] = band[0];
                data[o + 1] = band[1];
                data[o + 2] = band[2];
                data[o + 3] = Math.round(band[3] * edge);
            }
        }

        fctx.putImageData(img, 0, 0);
    }


    function resize() {
        const rect = canvas.getBoundingClientRect();
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        w = Math.max(1, Math.round(rect.width));
        h = Math.max(1, Math.round(rect.height));
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.imageSmoothingEnabled = true;
        layer.width = canvas.width;
        layer.height = canvas.height;
        lctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        lctx.imageSmoothingEnabled = true;
        cx = w * CX;
        cy = h * CY;
        R = Math.hypot(w, h) * RADIUS_F;
        buildField();
    }

    function drawGrid() {
        ctx.save();
        ctx.lineWidth = 1;

        for (let i = 1; i <= RINGS; i++) {
            const rr = (R * i) / RINGS;
            ctx.beginPath();
            ctx.arc(cx, cy, rr, 0, Math.PI * 2);
            ctx.strokeStyle = i === RINGS ? 'rgba(140, 198, 230, 0.38)' : 'rgba(140, 198, 230, 0.20)';
            ctx.stroke();
        }

        for (let i = 0; i < SPOKES; i++) {
            const a = (i / SPOKES) * Math.PI * 2;
            ctx.beginPath();
            ctx.moveTo(cx, cy);
            ctx.lineTo(cx + Math.cos(a) * R, cy + Math.sin(a) * R);
            ctx.strokeStyle = 'rgba(140, 198, 230, 0.10)';
            ctx.stroke();
        }

        ctx.restore();
    }

    function blitField(alpha) {
        ctx.globalAlpha = alpha;
        ctx.drawImage(field, 0, 0, field.width, field.height, 0, 0, w, h);
        ctx.globalAlpha = 1;
    }

    /* Persistencia del barrido, continua. El campo se copia a un lienzo intermedio y ahí
       se recorta con un degradado cónico cuya opacidad decae de forma exponencial con el
       ángulo detrás del haz: así no quedan sectores con escalones de transparencia, que es
       lo que pasaba al recortar la copia en tres cuñas. */
    const DECAY = 1.0;        // constante del decaimiento angular
    const STOPS = 24;         // puntos del degradado cónico

    function drawPersistence(sweep) {
        if (!lctx.createConicGradient) {
            blitField(0.3);   // sin degradado cónico: realce parejo, sin estela
            return;
        }

        lctx.globalCompositeOperation = 'source-over';
        lctx.clearRect(0, 0, w, h);
        lctx.drawImage(field, 0, 0, field.width, field.height, 0, 0, w, h);

        lctx.globalCompositeOperation = 'destination-in';
        const mask = lctx.createConicGradient(sweep, cx, cy);
        for (let i = 0; i <= STOPS; i++) {
            const t = i / STOPS;
            const a = Math.exp(-t * Math.PI * 2 * DECAY);
            mask.addColorStop(t, 'rgba(0, 0, 0, ' + a.toFixed(4) + ')');
        }
        lctx.fillStyle = mask;
        lctx.fillRect(0, 0, w, h);
        lctx.globalCompositeOperation = 'source-over';

        ctx.globalAlpha = 0.66;
        ctx.drawImage(layer, 0, 0, layer.width, layer.height, 0, 0, w, h);
        ctx.globalAlpha = 1;
    }

    function drawSweep(sweep) {
        const TRAIL = Math.PI * 0.45;
        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(sweep);

        const grad = ctx.createConicGradient ? ctx.createConicGradient(0, 0, 0) : null;
        if (grad) {
            // Estela del haz: cae suave para que no se vea el borde recto del sector.
            const t = TRAIL / (Math.PI * 2);
            grad.addColorStop(0, 'rgba(120, 206, 234, 0.13)');
            grad.addColorStop(t * 0.25, 'rgba(120, 206, 234, 0.075)');
            grad.addColorStop(t * 0.55, 'rgba(120, 206, 234, 0.032)');
            grad.addColorStop(t * 0.8, 'rgba(120, 206, 234, 0.010)');
            grad.addColorStop(t, 'rgba(120, 206, 234, 0)');
            grad.addColorStop(1, 'rgba(120, 206, 234, 0)');
            ctx.fillStyle = grad;
            ctx.beginPath();
            ctx.moveTo(0, 0);
            ctx.arc(0, 0, R, 0, Math.PI * 2);
            ctx.closePath();
            ctx.fill();
        }

        const lineGrad = ctx.createLinearGradient(0, 0, R, 0);
        lineGrad.addColorStop(0, 'rgba(160, 228, 246, 0.70)');
        lineGrad.addColorStop(0.7, 'rgba(160, 228, 246, 0.38)');
        lineGrad.addColorStop(1, 'rgba(160, 228, 246, 0)');
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.lineTo(R, 0);
        ctx.strokeStyle = lineGrad;
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.restore();
    }

    const reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function frame(now) {
        ctx.clearRect(0, 0, w, h);
        const sweep = (now / 1000) * (RPM / 60) * Math.PI * 2;
        drawGrid();
        blitField(0.40);
        drawPersistence(sweep);
        drawSweep(sweep);
        requestAnimationFrame(frame);
    }

    function still() {
        ctx.clearRect(0, 0, w, h);
        drawGrid();
        blitField(0.80);
    }

    buildNoise();
    buildLobes();
    resize();

    let t;
    window.addEventListener('resize', function () {
        clearTimeout(t);
        t = setTimeout(function () { resize(); if (reduced) still(); }, 150);
    });

    if (reduced) still(); else requestAnimationFrame(frame);
})();
