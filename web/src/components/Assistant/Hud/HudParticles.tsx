import { useState } from 'react';

interface Particle {
  left: string;
  top: string;
  duration: string;
  delay: string;
  opacity: number;
}

const PARTICLE_COUNT = 18;

export const HudParticles = () => {
  const [particles] = useState<Particle[]>(() =>
    Array.from({ length: PARTICLE_COUNT }, () => ({
      left: `${Math.random() * 100}vw`,
      top: `${100 + Math.random() * 30}vh`,
      duration: `${18 + Math.random() * 22}s`,
      delay: `${-Math.random() * 30}s`,
      opacity: 0.3 + Math.random() * 0.5,
    })),
  );

  return (
    <div className="hud-particles" aria-hidden="true">
      {particles.map((p, i) => (
        <span
          key={i}
          className="hud-particles__dot"
          style={{
            left: p.left,
            top: p.top,
            animationDuration: p.duration,
            animationDelay: p.delay,
            opacity: p.opacity,
          }}
        />
      ))}
    </div>
  );
};
