/* bg.js — animated 3D blocky neural network background.
 *
 * Three layers of voxel cubes connected by edge cuboids. A travelling
 * activation wave brightens cubes and edges in sequence. Slow rotation
 * around the Y axis. Respects prefers-reduced-motion.
 */
(() => {
  if (!window.THREE) return;
  const canvas = document.getElementById('bg');
  if (!canvas) return;

  const reduced =
    window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const renderer = new THREE.WebGLRenderer({
    canvas, antialias: false, alpha: true,
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.setClearColor(0x000000, 0);

  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x0d0f14, 18, 45);

  const camera = new THREE.PerspectiveCamera(
    52, window.innerWidth / window.innerHeight, 0.1, 100
  );
  camera.position.set(8, 5, 14);
  camera.lookAt(0, 0, 0);

  // soft ambient + directional for the flat-shaded blocky look
  scene.add(new THREE.AmbientLight(0x404858, 1.0));
  const sun = new THREE.DirectionalLight(0xffffff, 0.9);
  sun.position.set(8, 12, 6);
  scene.add(sun);
  const fill = new THREE.DirectionalLight(0x5cdb95, 0.3);
  fill.position.set(-8, -2, 4);
  scene.add(fill);

  // === Network topology ===
  // 4 layers, each a vertical column of cubes; offsets give a 3D feel
  const LAYERS = [
    { count: 5, x: -6,   z: -2 },
    { count: 7, x: -2,   z:  1 },
    { count: 7, x:  2,   z:  1 },
    { count: 4, x:  6,   z: -2 },
  ];
  const SPACING = 1.6;
  const CUBE = 0.85;

  const nodeGeom = new THREE.BoxGeometry(CUBE, CUBE, CUBE);
  const nodes = [];   // {mesh, base, layer, layerIndex}
  const layerPositions = [];

  LAYERS.forEach((layer, li) => {
    const positions = [];
    const yOffset = -(layer.count - 1) * SPACING * 0.5;
    for (let i = 0; i < layer.count; i++) {
      const baseColor = new THREE.Color(
        // alternate emerald + diamond cyan along the layers
        li % 2 === 0 ? 0x2f8a5a : 0x3a7588
      );
      const mat = new THREE.MeshLambertMaterial({
        color: baseColor.clone(),
        transparent: true,
        opacity: 0.92,
      });
      const m = new THREE.Mesh(nodeGeom, mat);
      const x = layer.x + (Math.random() - 0.5) * 0.15;
      const y = yOffset + i * SPACING + (Math.random() - 0.5) * 0.15;
      const z = layer.z + (Math.random() - 0.5) * 0.4;
      m.position.set(x, y, z);
      scene.add(m);
      positions.push(m.position);
      nodes.push({ mesh: m, baseColor, layerIndex: li, idx: i, x, y });
    }
    layerPositions.push(positions);
  });

  // === Edges between adjacent layers ===
  // Use thin emissive cuboids so they look pixel-y. Subset: each node
  // connects to ~3 random nodes in the next layer (kept sparse for clarity).
  const EDGE_THICKNESS = 0.06;
  const edges = [];
  for (let li = 0; li < LAYERS.length - 1; li++) {
    const here = layerPositions[li];
    const next = layerPositions[li + 1];
    for (const a of here) {
      const indices = [...next.keys()].sort(() => Math.random() - 0.5).slice(0, 3);
      for (const j of indices) {
        const b = next[j];
        const dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z;
        const len = Math.sqrt(dx*dx + dy*dy + dz*dz);
        const geom = new THREE.BoxGeometry(EDGE_THICKNESS, EDGE_THICKNESS, len);
        const mat = new THREE.MeshBasicMaterial({
          color: 0x2a3038,
          transparent: true,
          opacity: 0.45,
        });
        const m = new THREE.Mesh(geom, mat);
        // place midpoint and orient toward target
        m.position.set((a.x + b.x) / 2, (a.y + b.y) / 2, (a.z + b.z) / 2);
        m.lookAt(b.x, b.y, b.z);
        scene.add(m);
        edges.push({
          mesh: m,
          fromLayer: li,
          toLayer: li + 1,
          baseOpacity: 0.45,
        });
      }
    }
  }

  // === Activation wave ===
  // A wave front moves along the X axis through the layers. Each node's
  // brightness is a function of its distance from the wave front.
  const ACCENT = new THREE.Color(0x5cdb95);   // emerald
  const HOT    = new THREE.Color(0xf0c14b);   // glowstone gold
  const EDGE_LIT = new THREE.Color(0x5cdb95);
  const layerXs = LAYERS.map(l => l.x);
  const xRange = layerXs[layerXs.length - 1] - layerXs[0];
  const PULSE_SPEED = 0.6;       // units/sec
  const PULSE_WIDTH = 1.6;       // softness of the bright window

  let lastT = performance.now() * 0.001;
  let running = true;
  let rotationY = 0;

  function frame(now) {
    const t = now * 0.001;
    const dt = Math.min(0.05, t - lastT);
    lastT = t;

    // travel x position of the wave front (loops)
    const wavePos = ((t * PULSE_SPEED) % (xRange + 4)) + layerXs[0] - 2;

    for (const n of nodes) {
      const dx = Math.abs(n.x - wavePos);
      const heat = Math.max(0, 1 - dx / PULSE_WIDTH);
      const c = n.baseColor.clone().lerp(HOT, heat * 0.85);
      n.mesh.material.color.copy(c);
      n.mesh.material.opacity = 0.85 + heat * 0.15;
      // gentle scale pulse on hot nodes
      const s = 1 + heat * 0.18;
      n.mesh.scale.set(s, s, s);
    }

    for (const e of edges) {
      // edge brightens when wave is between fromLayer and toLayer
      const from = layerXs[e.fromLayer];
      const to = layerXs[e.toLayer];
      const lo = Math.min(from, to);
      const hi = Math.max(from, to);
      let lit = 0;
      if (wavePos >= lo - PULSE_WIDTH && wavePos <= hi + PULSE_WIDTH) {
        const center = (lo + hi) / 2;
        const dx = Math.abs(wavePos - center);
        lit = Math.max(0, 1 - dx / ((hi - lo) / 2 + PULSE_WIDTH));
      }
      const c = new THREE.Color(0x2a3038).lerp(EDGE_LIT, lit * 0.9);
      e.mesh.material.color.copy(c);
      e.mesh.material.opacity = e.baseOpacity + lit * 0.4;
    }

    if (!reduced) {
      rotationY += dt * 0.06;
    }
    scene.rotation.y = Math.sin(rotationY) * 0.18;
    scene.rotation.x = Math.sin(rotationY * 0.7) * 0.05;

    renderer.render(scene, camera);
    if (running) requestAnimationFrame(frame);
  }

  function resize() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  resize();
  window.addEventListener('resize', resize);

  // pause when tab is hidden — saves battery
  document.addEventListener('visibilitychange', () => {
    running = !document.hidden;
    if (running) {
      lastT = performance.now() * 0.001;
      requestAnimationFrame(frame);
    }
  });

  requestAnimationFrame(frame);
})();
