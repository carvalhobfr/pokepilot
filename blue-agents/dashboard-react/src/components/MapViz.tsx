import React, { useEffect, useRef } from 'react';
import * as PIXI from 'pixi.js';

interface MapVizProps {
  ws: React.MutableRefObject<WebSocket | null>;
  connected: boolean;
  onAgentClick: (agent: any) => void;
}

const MapViz: React.FC<MapVizProps> = ({ ws, connected, onAgentClick }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const appRef = useRef<PIXI.Application | null>(null);
  const mapContainerRef = useRef<PIXI.Container | null>(null);
  // One persistent entry per agent, keyed by trainer name. Sprites are never
  // destroyed when their animation ends: coordinate frames arrive only every
  // `upload_interval` steps (~15s of wall clock at 1x), and during a battle the
  // position does not change at all. Destroying on animation end made both bots
  // blink in and out of the map instead of showing where they actually are.
  const spritesRef = useRef<Map<string, {
    container: PIXI.Container,
    label: PIXI.Text,
    badge: PIXI.Text,
    startTime: number,
    path: number[][],
    animating: boolean,
    duration: number,
    lastUpdateAt: number,
    meta: any,
  }>>(new Map());
  const hasPannedRef = useRef(false);

  // Coordinate Conversion (Simplified for now, needs real map data)
  // We'll use a basic scaling factor if we don't have the full map JSON loaded yet
  // But to match the Python backend, we need the offsets.
  // For this MVP, I'll assume the backend sends correct global coords or we use a simplified scaler.
  // Actually, the backend sends game coords (x, y, map_id). The JS frontend had a complex `coordConversionFunc`.
  // I will try to port a simplified version or fetch the map_data.json.

  const mapDataRef = useRef<any>(null);

  useEffect(() => {
    fetch('/assets/map_data.json')
      .then(res => res.json())
      .then(data => {
        mapDataRef.current = data.regions.reduce((acc: any, e: any) => {
          acc[e.id] = e;
          return acc;
        }, {});
      });
  }, []);

  const coordConversion = (coords: number[]) => {
    if (!mapDataRef.current) return [coords[0], coords[1]]; // Fallback
    const mapId = String(coords[2]); // Ensure string key
    const region = mapDataRef.current[mapId];
    if (region) {
      const mapX = region.coordinates[0];
      const mapY = region.coordinates[1];
      // Magic numbers from original visualizer_live.js
      return [coords[0] + mapX - 217.5, coords[1] + mapY - 221.5];
    }
    // If map ID not found, return raw coords (will be at center)
    return [coords[0], coords[1]];
  };

  // Initialize PixiJS
  useEffect(() => {
    if (!containerRef.current) return;

    const app = new PIXI.Application({
      resizeTo: containerRef.current,
      backgroundAlpha: 0,
      // A full devicePixelRatio canvas is unnecessarily expensive on Retina
      // displays for a pixel-art map. Cap the backing resolution while keeping
      // the CSS output sharp enough for inspection.
      resolution: Math.min(window.devicePixelRatio || 1, 1.5),
      autoDensity: true,
    });

    containerRef.current.appendChild(app.view as unknown as Node);
    appRef.current = app;

    const container = new PIXI.Container();
    app.stage.addChild(container);
    mapContainerRef.current = container;

    // Load Assets
    PIXI.Assets.load([
      "/assets/kanto_big_done1.png",
      "/assets/characters_transparent.png"
    ]).then(() => {
      // Background
      const bgTexture = PIXI.Texture.from("/assets/kanto_big_done1.png");
      const bg = new PIXI.Sprite(bgTexture);
      bg.anchor.set(0.5);

      // Create two layers like original: Smooth and Sharp
      // For simplicity/performance, just one for now
      container.addChild(bg);

      // Center Map (wait for app to be ready)
      if (app && app.screen) {
        container.x = app.screen.width / 2;
        container.y = app.screen.height / 2;
        container.scale.set(0.5);
      } else {
        console.warn('⚠️ App screen not ready yet');
      }
    });

    // Animation Loop
    app.ticker.add(() => {
      const now = Date.now();

      spritesRef.current.forEach((obj) => {
        if (!obj.animating || obj.path.length === 0) return;
        if (!obj.startTime) obj.startTime = now;
        const timeDelta = now - obj.startTime;
        const progress = Math.min(timeDelta / obj.duration, 1);

        const segments = Math.max(obj.path.length - 1, 0);
        const currentIndex = Math.floor(progress * segments);
        const nextIndex = Math.min(currentIndex + 1, segments);
        const pointProgress = (progress * segments) - currentIndex;

        const currentPoint = coordConversion(obj.path[currentIndex]);
        const nextPoint = coordConversion(obj.path[nextIndex]);

        // Interpolate
        const x = 16 * (currentPoint[0] + (nextPoint[0] - currentPoint[0]) * pointProgress);
        const y = 16 * (currentPoint[1] + (nextPoint[1] - currentPoint[1]) * pointProgress);

        obj.container.position.set(x, y);

        // Park at the last known tile instead of disappearing. The next frame
        // of coordinates restarts the animation from here.
        if (progress >= 1) {
          obj.animating = false;
          obj.path = [obj.path[obj.path.length - 1]];
        }
      });
    });

    // Zoom/Pan
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const scaleFactor = 1 - e.deltaY * 0.001;
      container.scale.x *= scaleFactor;
      container.scale.y *= scaleFactor;
    };
    if (app.view) {
      (app.view as HTMLCanvasElement).addEventListener('wheel', onWheel as any);
    }

    // Dragging
    let isDragging = false;
    let lastPos = { x: 0, y: 0 };
    const onMouseDown = (e: MouseEvent) => {
      isDragging = true;
      lastPos = { x: e.clientX, y: e.clientY };
      hasPannedRef.current = true;
    };
    const onMouseMove = (e: MouseEvent) => {
      if (!isDragging) return;
      container.x += e.clientX - lastPos.x;
      container.y += e.clientY - lastPos.y;
      lastPos = { x: e.clientX, y: e.clientY };
    };
    const onMouseUp = () => { isDragging = false; };

    window.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);

    return () => {
      app.destroy(true, { children: true });
      window.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
  }, []);

  // Handle WebSocket Messages for Sprites
  useEffect(() => {
    if (!connected || !ws.current) return;

    const handleMessage = async (event: MessageEvent) => {
      let data;

      // Handle Blob or ArrayBuffer data
      if (event.data instanceof Blob) {
        const text = await event.data.text();
        try {
          data = JSON.parse(text);
        } catch (error) {
          console.error("Failed to parse Blob as JSON:", error);
          return;
        }
      } else if (typeof event.data === 'string') {
        try {
          data = JSON.parse(event.data);
        } catch (error) {
          console.error("Failed to parse string as JSON:", error);
          return;
        }
      } else {
        return;
      }

      // Log first agent update to confirm data flow
      if (data.agents && data.agents.length > 0 && Math.random() < 0.01) {
        console.log("💓 Data Heartbeat: Received agents", data.agents.length);
      }

      if (data.stats) return;

      const { coords: path, metadata: meta } = data;

      if (!meta || !meta.user) return;

      if (mapContainerRef.current && PIXI.Assets.get("/assets/characters_transparent.png")) {
        // One sprite per trainer, reused across updates.
        const key = String(meta.user);
        let entry = spritesRef.current.get(key);

        if (!entry) {
          const baseTex = PIXI.Texture.from("/assets/characters_transparent.png");
          const spriteId = parseInt(meta.sprite_id || "0");
          const sx = 9 + 17 * 1; // Direction offset
          const sy = 34 + 17 * spriteId;
          const tex = new PIXI.Texture(baseTex.baseTexture, new PIXI.Rectangle(sx, sy, 16, 16));

          const sprite = new PIXI.Sprite(tex);
          sprite.anchor.set(0.5);

          const subContainer = new PIXI.Container();
          subContainer.addChild(sprite);

          // Label
          const label = new PIXI.Text(meta.user, {
            fontFamily: 'Arial', fontSize: 14, fill: meta.color || 'white', align: 'center',
            stroke: 'black', strokeThickness: 2
          });
          label.x = 0;
          label.y = -12;
          label.anchor.set(0.5);
          subContainer.addChild(label);

          // Battle marker: the bot keeps its map position while fighting, so
          // the map answers "where is it" and "what is it doing" at once.
          const badge = new PIXI.Text('⚔', {
            fontFamily: 'Arial', fontSize: 13, fill: '#ff4d4d', align: 'center',
            stroke: 'black', strokeThickness: 3
          });
          badge.x = 10;
          badge.y = -10;
          badge.anchor.set(0.5);
          badge.visible = false;
          subContainer.addChild(badge);

          // Interactive
          subContainer.eventMode = 'static';
          subContainer.cursor = 'pointer';
          subContainer.on('pointerdown', (e) => {
            e.stopPropagation();
            onAgentClick(spritesRef.current.get(key)?.meta ?? meta);
          });

          mapContainerRef.current.addChild(subContainer);

          entry = {
            container: subContainer,
            label,
            badge,
            startTime: 0,
            path: [],
            animating: false,
            // Replay each batch of coordinates over the real gap between
            // updates instead of a fixed 1s burst followed by a long freeze.
            duration: 1000,
            lastUpdateAt: 0,
            meta,
          };
          spritesRef.current.set(key, entry);
        }

        entry.meta = meta;
        const inBattle = Boolean(
          meta.status === 'battle' || meta?.battle_info?.is_battle
        );
        entry.badge.visible = inBattle;
        // Dim slightly while fighting so a parked sprite does not read as stuck.
        entry.container.alpha = inBattle ? 0.85 : 1;

        if (path && path.length > 0) {
          const now = Date.now();
          if (entry.lastUpdateAt) {
            entry.duration = Math.min(Math.max(now - entry.lastUpdateAt, 500), 20000);
          }
          entry.lastUpdateAt = now;
          entry.path = path;
          entry.startTime = 0; // ticker stamps it
          entry.animating = true;
        }

        // Auto-center on first agent if user hasn't moved map
        if (!hasPannedRef.current && path && path.length > 0) {
          const firstPoint = coordConversion(path[0]);
          const x = 16 * firstPoint[0];
          const y = 16 * firstPoint[1];

          if (mapContainerRef.current && appRef.current) {
            const scale = mapContainerRef.current.scale.x;
            mapContainerRef.current.x = appRef.current.screen.width / 2 - x * scale;
            mapContainerRef.current.y = appRef.current.screen.height / 2 - y * scale;
            hasPannedRef.current = true;
          }
        }
      }
    };

    ws.current.addEventListener('message', handleMessage);
    return () => ws.current?.removeEventListener('message', handleMessage);
  }, [connected, ws, onAgentClick]);

  return <div ref={containerRef} className="w-full h-full bg-[#1a1a1a]" />;
};

export default MapViz;
