import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Line, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import type { Graph } from "./types";
import { visibleGraph } from "./graph";

function ResearchStructure() {
  const group = useRef<THREE.Group>(null);
  const { invalidate } = useThree();
  const started = useRef<number | null>(null);
  useFrame(({ clock, pointer }) => {
    if (!group.current || document.hidden) return;
    started.current ??= clock.elapsedTime;
    const elapsed = clock.elapsedTime - started.current;
    group.current.rotation.y =
      -0.42 + pointer.x * 0.12 + Math.sin(Math.min(elapsed, 6) * 0.28) * 0.12;
    group.current.rotation.x = 0.16 + pointer.y * 0.06;
    group.current.position.y = Math.sin(Math.min(elapsed, 6) * 0.65) * 0.07;
    if (elapsed < 6) invalidate();
  });
  const orbit = useMemo(
    () =>
      Array.from({ length: 97 }, (_, i) => {
        const a = (i / 96) * Math.PI * 2;
        return new THREE.Vector3(
          Math.cos(a) * 2.8,
          Math.sin(a) * 0.78,
          Math.sin(a) * 1.05,
        );
      }),
    [],
  );
  return (
    <group ref={group}>
      <Line
        points={orbit}
        color="#70f3c2"
        transparent
        opacity={0.42}
        lineWidth={1}
      />
      <group rotation={[0, 0, -0.14]}>
        {[0, 1, 2].map((i) => (
          <group
            key={i}
            position={[(i - 1) * 0.28, i * 0.11, (i - 1) * 0.38]}
            rotation={[0.05 * i, -0.1 * i, 0.04 * i]}
          >
            <mesh>
              <boxGeometry args={[2.25, 2.9, 0.035]} />
              <meshPhysicalMaterial
                color={i === 2 ? "#1d343d" : "#13232d"}
                metalness={0.35}
                roughness={0.34}
                transparent
                opacity={0.94}
              />
            </mesh>
            <mesh position={[-0.67, 0.98, 0.025]}>
              <planeGeometry args={[0.55, 0.035]} />
              <meshBasicMaterial color="#70f3c2" />
            </mesh>
            {[0, 1, 2, 3, 4, 5, 6].map((j) => (
              <mesh key={j} position={[-0.08, 0.62 - j * 0.2, 0.025]}>
                <planeGeometry
                  args={[j === 0 ? 1.6 : j === 6 ? 0.95 : 1.45, 0.015]}
                />
                <meshBasicMaterial color={j < 2 ? "#89a8b4" : "#3a5663"} />
              </mesh>
            ))}
            <mesh position={[0.37, -0.99, 0.025]}>
              <planeGeometry args={[0.8, 0.24]} />
              <meshBasicMaterial
                color={i === 2 ? "#70f3c2" : "#344f59"}
                transparent
                opacity={0.8}
              />
            </mesh>
          </group>
        ))}
      </group>
      {[
        [2.3, 0.65, 0.1],
        [-2.2, -0.55, 0],
        [1.6, -1.6, 0.6],
        [-1.6, 1.7, -0.2],
      ].map((p, i) => (
        <group key={i} position={p as [number, number, number]}>
          <mesh>
            <octahedronGeometry args={[i === 0 ? 0.15 : 0.09]} />
            <meshStandardMaterial
              color={i === 0 ? "#f2c779" : "#70f3c2"}
              emissive={i === 0 ? "#f2c779" : "#70f3c2"}
              emissiveIntensity={0.7}
            />
          </mesh>
          <Line
            points={[
              [0, 0, 0],
              [-p[0] * 0.55, -p[1] * 0.55, -p[2]],
            ]}
            color={i === 0 ? "#f2c779" : "#70f3c2"}
            transparent
            opacity={0.22}
          />
        </group>
      ))}
    </group>
  );
}
function RenderPolicy() {
  const { invalidate, gl } = useThree();
  useEffect(() => {
    const redraw = () => {
      if (!document.hidden) invalidate();
    };
    gl.domElement.addEventListener("pointermove", redraw);
    document.addEventListener("visibilitychange", redraw);
    return () => {
      gl.domElement.removeEventListener("pointermove", redraw);
      document.removeEventListener("visibilitychange", redraw);
    };
  }, [invalidate, gl]);
  return null;
}
function EvidenceNodes({
  graph,
  onSelect,
}: {
  graph: Graph;
  onSelect: (id: string) => void;
}) {
  const projection = visibleGraph(graph, null, 60),
    nodes = projection.nodes;
  const positions = useMemo(
    () =>
      nodes.map((n, i) => {
        const a = (i / Math.max(nodes.length, 1)) * Math.PI * 2,
          r = n.type === "claim" ? 1.3 : n.type === "finding" ? 2.4 : 3.2;
        return new THREE.Vector3(
          Math.cos(a) * r,
          Math.sin(a) * r * 0.72,
          Math.sin(i * 2.4) * 0.9,
        );
      }),
    [graph],
  );
  const idx = new Map(nodes.map((n, i) => [n.id, i]));
  return (
    <group>
      {projection.edges.slice(0, 120).map((e, i) => {
        const a = idx.get(e.source),
          b = idx.get(e.target);
        return a === undefined || b === undefined ? null : (
          <Line
            key={i}
            points={[positions[a], positions[b]]}
            color={e.type === "conflicts_with" ? "#ff766d" : "#34535e"}
            lineWidth={1}
          />
        );
      })}
      {nodes.map((n, i) => (
        <mesh
          key={n.id}
          position={positions[i]}
          onClick={(e) => {
            e.stopPropagation();
            onSelect(n.finding_id || n.artifact_id || n.id);
          }}
        >
          <sphereGeometry args={[n.type === "claim" ? 0.1 : 0.14, 16, 16]} />
          <meshStandardMaterial
            color={
              n.type === "finding"
                ? "#ff766d"
                : n.type === "decision"
                  ? "#f2c779"
                  : n.type === "claim"
                    ? "#5cc8ff"
                    : "#70f3c2"
            }
            emissive={n.type === "finding" ? "#ff766d" : "#70f3c2"}
            emissiveIntensity={0.25}
          />
        </mesh>
      ))}
    </group>
  );
}
export default function Scene({
  graph,
  onSelect,
  hero = false,
}: {
  graph?: Graph;
  onSelect?: (id: string) => void;
  hero?: boolean;
}) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const c = document.createElement("canvas"),
      gl = c.getContext("webgl2");
    setReady(!!gl);
    gl?.getExtension("WEBGL_lose_context")?.loseContext();
  }, []);
  if (!ready)
    return (
      <div className="scene-fallback" aria-hidden="true">
        <div className="fallback-orbit" />
        <div className="fallback-sheet">
          <span>RESEARCH</span>
          <i />
          <i />
          <i />
          <b>evidence →</b>
        </div>
      </div>
    );
  return (
    <Canvas
      dpr={[1, 1.5]}
      frameloop="demand"
      camera={{ position: [0, 0, hero ? 7.8 : 8.8], fov: 38 }}
      gl={{ antialias: true, alpha: true, powerPreference: "low-power" }}
      aria-hidden={hero}
    >
      <RenderPolicy />
      <ambientLight intensity={1.4} />
      <directionalLight position={[3, 4, 5]} intensity={3} color="#c9f4ea" />
      <pointLight position={[-4, -2, 3]} intensity={20} color="#5cc8ff" />
      {hero ? (
        <ResearchStructure />
      ) : graph ? (
        <EvidenceNodes graph={graph} onSelect={onSelect || (() => {})} />
      ) : null}
      {!hero && (
        <OrbitControls
          enableZoom={false}
          enablePan={false}
          minPolarAngle={0.5}
          maxPolarAngle={2.6}
        />
      )}
    </Canvas>
  );
}
