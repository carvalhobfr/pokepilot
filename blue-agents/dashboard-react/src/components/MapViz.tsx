import React, { useCallback, useEffect, useRef, useState } from 'react';
import * as PIXI from 'pixi.js';
import { Crosshair, Minus, Maximize2, Plus } from 'lucide-react';

interface MapVizProps {
  ws: React.MutableRefObject<WebSocket | null>;
  connected: boolean;
  onAgentClick: (agent: any) => void;
}

const MIN_SCALE = 0.08;
const MAX_SCALE = 6;
const DEFAULT_SCALE = 0.5;
// Following a sprite at the same scale as the whole-region view is useless;
// this is close enough to read the tiles the bot is standing on.
const FOLLOW_SCALE = 2;
// A sprite that stops receiving coordinates is not "standing there" — the
// stream broke, usually because the supervisor rolled over to the next chunk.
// Showing it as if it were live made a healed bot look like a corpse left
// behind in Viridian.
const STALE_AFTER_MS = 25000;
const DROP_AFTER_MS = 150000;

interface SpriteEntry {
  container: PIXI.Container;
  label: PIXI.Text;
  badge: PIXI.Text;
  startTime: number;
  path: number[][];
  animating: boolean;
  duration: number;
  lastUpdateAt: number;
  meta: any;
}

const MapViz: React.FC<MapVizProps> = ({ ws, connected, onAgentClick }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const appRef = useRef<PIXI.Application | null>(null);
  const mapContainerRef = useRef<PIXI.Container | null>(null);
  // One persistent entry per agent, keyed by trainer name. Sprites are never
  // destroyed when their animation ends: coordinate frames arrive only every
  // `upload_interval` steps, and during a battle the position does not change
  // at all. Destroying on animation end made both bots blink in and out.
  const spritesRef = useRef<Map<string, SpriteEntry>>(new Map());
  const mapDataRef = useRef<any>(null);

  const followRef = useRef<string | null>(null);
  const [followTarget, setFollowTarget] = useState<string | null>(null);
  const [agentNames, setAgentNames] = useState<string[]>([]);
  const [zoom, setZoom] = useState(DEFAULT_SCALE);

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
    if (!mapDataRef.current) return [coords[0], coords[1]];
    const region = mapDataRef.current[String(coords[2])];
    if (region) {
      // Offsets from the original visualizer: region origin minus half the
      // stitched map's tile span.
      return [
        coords[0] + region.coordinates[0] - 217.5,
        coords[1] + region.coordinates[1] - 221.5,
      ];
    }
    return [coords[0], coords[1]];
  };

  /** Scale about a screen point so the tile under the cursor stays put. */
  const zoomAt = useCallback((screenX: number, screenY: number, factor: number) => {
    const container = mapContainerRef.current;
    if (!container) return;
    const current = container.scale.x;
    const next = Math.min(Math.max(current * factor, MIN_SCALE), MAX_SCALE);
    if (next === current) return;
    const worldX = (screenX - container.x) / current;
    const worldY = (screenY - container.y) / current;
    container.scale.set(next);
    container.x = screenX - worldX * next;
    container.y = screenY - worldY * next;
    setZoom(next);
  }, []);

  const zoomByButton = useCallback((factor: number) => {
    const app = appRef.current;
    if (!app) return;
    zoomAt(app.screen.width / 2, app.screen.height / 2, factor);
  }, [zoomAt]);

  const stopFollowing = useCallback(() => {
    followRef.current = null;
    setFollowTarget(null);
  }, []);

  const follow = useCallback((name: string | null) => {
    followRef.current = name;
    setFollowTarget(name);
  }, []);

  const resetView = useCallback(() => {
    const app = appRef.current;
    const container = mapContainerRef.current;
    if (!app || !container) return;
    stopFollowing();
    container.scale.set(DEFAULT_SCALE);
    container.x = app.screen.width / 2;
    container.y = app.screen.height / 2;
    setZoom(DEFAULT_SCALE);
  }, [stopFollowing]);

  useEffect(() => {
    if (!containerRef.current) return;

    const app = new PIXI.Application({
      resizeTo: containerRef.current,
      backgroundAlpha: 0,
      // A full devicePixelRatio canvas is unnecessarily expensive on Retina
      // displays for a pixel-art map.
      resolution: Math.min(window.devicePixelRatio || 1, 1.5),
      autoDensity: true,
    });

    containerRef.current.appendChild(app.view as unknown as Node);
    appRef.current = app;

    const container = new PIXI.Container();
    app.stage.addChild(container);
    mapContainerRef.current = container;

    // The asset promise can resolve before PixiJS has sized its screen, which
    // left the 6976x7104 map anchored at (0,0) with scale 1 — technically on
    // stage, visually off it. Fall back to the element's own size and retry.
    let centered = false;
    const centerMap = () => {
      if (centered) return true;
      const element = containerRef.current;
      const width = app.screen?.width || element?.clientWidth || 0;
      const height = app.screen?.height || element?.clientHeight || 0;
      if (!width || !height) return false;
      container.x = width / 2;
      container.y = height / 2;
      container.scale.set(DEFAULT_SCALE);
      centered = true;
      return true;
    };

    PIXI.Assets.load([
      '/assets/kanto_big_done1.png',
      '/assets/characters_transparent.png',
    ]).then(() => {
      const bg = new PIXI.Sprite(PIXI.Texture.from('/assets/kanto_big_done1.png'));
      bg.anchor.set(0.5);
      container.addChildAt(bg, 0);
      centerMap();
    });

    app.ticker.add(() => {
      const now = Date.now();
      if (!centered) centerMap();

      spritesRef.current.forEach(obj => {
        if (!obj.animating || obj.path.length === 0) return;
        if (!obj.startTime) obj.startTime = now;
        const progress = Math.min((now - obj.startTime) / obj.duration, 1);

        const segments = Math.max(obj.path.length - 1, 0);
        const currentIndex = Math.floor(progress * segments);
        const nextIndex = Math.min(currentIndex + 1, segments);
        const pointProgress = progress * segments - currentIndex;

        const from = coordConversion(obj.path[currentIndex]);
        const to = coordConversion(obj.path[nextIndex]);
        obj.container.position.set(
          16 * (from[0] + (to[0] - from[0]) * pointProgress),
          16 * (from[1] + (to[1] - from[1]) * pointProgress),
        );

        // Park at the last known tile instead of disappearing.
        if (progress >= 1) {
          obj.animating = false;
          obj.path = [obj.path[obj.path.length - 1]];
        }
      });

      // Fade sprites whose stream went quiet, and drop the ones long gone.
      spritesRef.current.forEach((obj, key) => {
        if (!obj.lastUpdateAt) return;
        const silence = now - obj.lastUpdateAt;
        if (silence > DROP_AFTER_MS) {
          mapContainerRef.current?.removeChild(obj.container);
          obj.container.destroy({ children: true });
          spritesRef.current.delete(key);
          setAgentNames(names => names.filter(name => name !== key));
          if (followRef.current === key) {
            followRef.current = null;
            setFollowTarget(null);
          }
          return;
        }
        const stale = silence > STALE_AFTER_MS;
        const inBattle = Boolean(
          obj.meta?.status === 'battle' || obj.meta?.battle_info?.is_battle,
        );
        obj.container.alpha = stale ? 0.35 : inBattle ? 0.85 : 1;
        obj.label.style.fill = stale ? '#8a8a8a' : obj.meta?.color || 'white';
      });

      // Camera lock. Runs after sprite movement so the followed bot never
      // trails the viewport by a frame.
      const target = followRef.current
        ? spritesRef.current.get(followRef.current)
        : null;
      if (target) {
        const scale = container.scale.x;
        container.x = app.screen.width / 2 - target.container.x * scale;
        container.y = app.screen.height / 2 - target.container.y * scale;
      }
    });

    // --- input ------------------------------------------------------------
    // Everything is bound to the canvas, not to window: dragging over the
    // sidebar, the event feed or the control bar used to pan the map.
    const view = app.view as HTMLCanvasElement;
    const pointers = new Map<number, { x: number; y: number }>();
    let dragging = false;
    let last = { x: 0, y: 0 };
    let pinchDistance = 0;

    const localPoint = (event: PointerEvent | WheelEvent) => {
      const rect = view.getBoundingClientRect();
      return { x: event.clientX - rect.left, y: event.clientY - rect.top };
    };

    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const point = localPoint(event);
      // A trackpad pinch arrives as a wheel event with ctrlKey set; a mouse
      // wheel arrives without it. Both zoom, but the pinch needs a gentler
      // constant or it overshoots badly.
      const intensity = event.ctrlKey ? 0.01 : 0.0015;
      zoomAt(point.x, point.y, Math.exp(-event.deltaY * intensity));
    };

    const onPointerDown = (event: PointerEvent) => {
      view.setPointerCapture?.(event.pointerId);
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      if (pointers.size === 1) {
        dragging = true;
        last = { x: event.clientX, y: event.clientY };
      } else if (pointers.size === 2) {
        dragging = false;
        const [a, b] = [...pointers.values()];
        pinchDistance = Math.hypot(a.x - b.x, a.y - b.y);
      }
    };

    const onPointerMove = (event: PointerEvent) => {
      if (!pointers.has(event.pointerId)) return;
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });

      if (pointers.size >= 2) {
        const [a, b] = [...pointers.values()];
        const distance = Math.hypot(a.x - b.x, a.y - b.y);
        if (pinchDistance > 0 && distance > 0) {
          const rect = view.getBoundingClientRect();
          zoomAt(
            (a.x + b.x) / 2 - rect.left,
            (a.y + b.y) / 2 - rect.top,
            distance / pinchDistance,
          );
        }
        pinchDistance = distance;
        return;
      }

      if (!dragging) return;
      const dx = event.clientX - last.x;
      const dy = event.clientY - last.y;
      if (dx || dy) {
        // Panning by hand is an explicit request to look elsewhere.
        if (followRef.current) stopFollowing();
        container.x += dx;
        container.y += dy;
        last = { x: event.clientX, y: event.clientY };
      }
    };

    const onPointerUp = (event: PointerEvent) => {
      pointers.delete(event.pointerId);
      if (pointers.size < 2) pinchDistance = 0;
      if (pointers.size === 0) dragging = false;
      view.releasePointerCapture?.(event.pointerId);
    };

    view.addEventListener('wheel', onWheel, { passive: false });
    view.addEventListener('pointerdown', onPointerDown);
    view.addEventListener('pointermove', onPointerMove);
    view.addEventListener('pointerup', onPointerUp);
    view.addEventListener('pointercancel', onPointerUp);
    view.addEventListener('pointerleave', onPointerUp);
    view.style.touchAction = 'none';
    view.style.cursor = 'grab';

    return () => {
      view.removeEventListener('wheel', onWheel);
      view.removeEventListener('pointerdown', onPointerDown);
      view.removeEventListener('pointermove', onPointerMove);
      view.removeEventListener('pointerup', onPointerUp);
      view.removeEventListener('pointercancel', onPointerUp);
      view.removeEventListener('pointerleave', onPointerUp);
      app.destroy(true, { children: true });
    };
  }, [zoomAt, stopFollowing]);

  // --- agent stream -------------------------------------------------------
  useEffect(() => {
    if (!connected || !ws.current) return;

    const handleMessage = async (event: MessageEvent) => {
      let data: any;
      if (event.data instanceof Blob) {
        try {
          data = JSON.parse(await event.data.text());
        } catch {
          return;
        }
      } else if (typeof event.data === 'string') {
        try {
          data = JSON.parse(event.data);
        } catch {
          return;
        }
      } else {
        return;
      }

      if (data.stats) return;
      const { coords: path, metadata: meta } = data;
      if (!meta || !meta.user) return;
      if (!mapContainerRef.current) return;
      if (!PIXI.Assets.get('/assets/characters_transparent.png')) return;

      const key = String(meta.user);
      let entry = spritesRef.current.get(key);

      if (!entry) {
        const baseTex = PIXI.Texture.from('/assets/characters_transparent.png');
        const spriteId = parseInt(meta.sprite_id || '0');
        const tex = new PIXI.Texture(
          baseTex.baseTexture,
          new PIXI.Rectangle(9 + 17, 34 + 17 * spriteId, 16, 16),
        );

        const sprite = new PIXI.Sprite(tex);
        sprite.anchor.set(0.5);

        const subContainer = new PIXI.Container();
        subContainer.addChild(sprite);

        const label = new PIXI.Text(meta.user, {
          fontFamily: 'Arial', fontSize: 14, fill: meta.color || 'white',
          align: 'center', stroke: 'black', strokeThickness: 2,
        });
        label.y = -12;
        label.anchor.set(0.5);
        subContainer.addChild(label);

        // Battle marker: the bot keeps its map position while fighting, so the
        // map answers "where is it" and "what is it doing" at once.
        const badge = new PIXI.Text('⚔', {
          fontFamily: 'Arial', fontSize: 13, fill: '#ff4d4d',
          align: 'center', stroke: 'black', strokeThickness: 3,
        });
        badge.x = 10;
        badge.y = -10;
        badge.anchor.set(0.5);
        badge.visible = false;
        subContainer.addChild(badge);

        subContainer.eventMode = 'static';
        subContainer.cursor = 'pointer';
        subContainer.on('pointertap', (e: any) => {
          e.stopPropagation();
          const current = spritesRef.current.get(key);
          onAgentClick(current?.meta ?? meta);
          follow(key);
        });

        mapContainerRef.current.addChild(subContainer);
        entry = {
          container: subContainer,
          label,
          badge,
          startTime: 0,
          path: [],
          animating: false,
          duration: 1000,
          lastUpdateAt: 0,
          meta,
        };
        spritesRef.current.set(key, entry);
        setAgentNames(names => (names.includes(key) ? names : [...names, key].sort()));
      }

      entry.meta = meta;
      const inBattle = Boolean(meta.status === 'battle' || meta?.battle_info?.is_battle);
      entry.badge.visible = inBattle;
      entry.container.alpha = inBattle ? 0.85 : 1;
      // Any message counts as a heartbeat, even one without new coordinates.
      entry.lastUpdateAt = Date.now();

      if (path && path.length > 0) {
        const now = Date.now();
        if (entry.lastUpdateAt) {
          // Replay each batch over the real gap between updates instead of a
          // fixed burst followed by a long freeze.
          entry.duration = Math.min(Math.max(now - entry.lastUpdateAt, 500), 20000);
        }
        entry.lastUpdateAt = now;
        entry.path = path;
        entry.startTime = 0;
        entry.animating = true;
      }
    };

    ws.current.addEventListener('message', handleMessage);
    return () => ws.current?.removeEventListener('message', handleMessage);
  }, [connected, ws, onAgentClick, follow]);

  // Snap to a comfortable reading zoom the moment a lock starts.
  useEffect(() => {
    const container = mapContainerRef.current;
    if (!followTarget || !container) return;
    if (container.scale.x < FOLLOW_SCALE) {
      container.scale.set(FOLLOW_SCALE);
      setZoom(FOLLOW_SCALE);
    }
  }, [followTarget]);

  const buttonClass =
    'rounded-lg border border-white/10 bg-black/60 p-2 text-white backdrop-blur-md ' +
    'transition-all hover:bg-white/20 active:scale-95';

  return (
    <div ref={containerRef} className="w-full h-full bg-[#1a1a1a] relative">
      <div className="absolute bottom-4 left-4 z-10 flex flex-col gap-2 items-start">
        {agentNames.length > 0 && (
          <div className="flex flex-wrap gap-1.5 max-w-[260px]">
            {agentNames.map(name => {
              const active = followTarget === name;
              return (
                <button
                  key={name}
                  onClick={() => (active ? stopFollowing() : follow(name))}
                  title={active ? `Parar de seguir ${name}` : `Seguir ${name}`}
                  className={
                    'flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[10px] ' +
                    'font-bold uppercase tracking-wider backdrop-blur-md transition-all ' +
                    'active:scale-95 ' +
                    (active
                      ? 'border-blue-400/60 bg-blue-500/30 text-white'
                      : 'border-white/10 bg-black/60 text-slate-300 hover:bg-white/20')
                  }
                >
                  <Crosshair size={12} className={active ? 'text-blue-300' : 'text-slate-400'} />
                  {name}
                </button>
              );
            })}
          </div>
        )}

        <div className="flex items-center gap-1.5">
          <button onClick={() => zoomByButton(1 / 1.4)} title="Afastar" className={buttonClass}>
            <Minus size={16} />
          </button>
          <span className="min-w-[52px] rounded-lg border border-white/10 bg-black/60 px-2 py-1.5 text-center font-mono text-[10px] text-slate-300 backdrop-blur-md">
            {Math.round(zoom * 100)}%
          </span>
          <button onClick={() => zoomByButton(1.4)} title="Aproximar" className={buttonClass}>
            <Plus size={16} />
          </button>
          <button onClick={resetView} title="Enquadrar Kanto inteiro" className={buttonClass}>
            <Maximize2 size={16} />
          </button>
        </div>

        <p className="rounded-lg border border-white/10 bg-black/50 px-2 py-1 font-mono text-[9px] text-slate-500 backdrop-blur-md">
          arrastar: mover · roda/pinça: zoom · clicar no bot: seguir
        </p>
      </div>
    </div>
  );
};

export default MapViz;
