import React from "react";
import { Easing, interpolate, useCurrentFrame } from "remotion";
import { TINTA, TRACOS, VIEWBOX } from "./kanji";

/**
 * 将軍 escrito a pincel, traço a traço, na ordem caligráfica — depois
 * sustentado e desescrito na ordem inversa.
 *
 * Pincelada: cada path usa pathLength=1 + stroke-dashoffset animado.
 * A textura de tinta vem de um filtro feTurbulence + feDisplacementMap
 * (borda irregular, não vetor perfeito) e de duas passadas por traço —
 * uma base larga e úmida, um fio central mais denso — com larguras que
 * variam por tipo de traço (pontos levam mais tinta).
 */

export interface FasesProps {
  /** Frame em que a escrita começa. */
  inicioEscrita: number;
  /** Duração total da escrita (todos os traços). */
  duracaoEscrita: number;
  /** Frame em que a desescrita começa. */
  inicioApaga: number;
  /** Duração total da desescrita. */
  duracaoApaga: number;
  /** Largura-base do pincel, em unidades do viewBox. */
  pincel?: number;
  /**
   * Cor da tinta. Existe porque o mesmo desenho e renderizado uma vez por
   * tema do app: no washi o kanji e sumi, no sumi ele e bengara.
   */
  cor?: string;
}

const n = TRACOS.length;

/** Progresso 0→1 de um traço dentro de uma janela sequencial com leve sobreposição. */
function progresso(
  frame: number,
  indice: number,
  inicio: number,
  duracao: number,
): number {
  const fatia = duracao / (n * 0.88); // 12% de sobreposição entre traços
  const comeca = inicio + indice * fatia * 0.88;
  return interpolate(frame, [comeca, comeca + fatia], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    // pincel acelera no meio do gesto e assenta no fim
    easing: Easing.bezier(0.35, 0, 0.35, 1),
  });
}

export const ShogunKanji: React.FC<FasesProps> = ({
  inicioEscrita,
  duracaoEscrita,
  inicioApaga,
  duracaoApaga,
  pincel = 5,
  cor = TINTA,
}) => {
  const frame = useCurrentFrame();

  return (
    <svg
      viewBox={VIEWBOX}
      style={{ width: "100%", height: "100%" }}
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <filter id="tinta" x="-15%" y="-15%" width="130%" height="130%">
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.09"
            numOctaves="2"
            seed="7"
            result="ruido"
          />
          <feDisplacementMap in="SourceGraphic" in2="ruido" scale="2.6" />
        </filter>
      </defs>
      <g filter="url(#tinta)">
        {TRACOS.map((t, i) => {
          const escreve = progresso(frame, i, inicioEscrita, duracaoEscrita);
          // desescreve na ordem inversa: o último traço some primeiro
          const apaga = progresso(frame, n - 1 - i, inicioApaga, duracaoApaga);
          const visivel = Math.max(0, escreve - apaga);
          if (visivel === 0) return null;
          const comum = {
            d: t.d,
            transform: t.dx ? `translate(${t.dx},0)` : undefined,
            pathLength: 1,
            fill: "none",
            stroke: cor,
            strokeLinecap: "round" as const,
            strokeLinejoin: "round" as const,
            strokeDasharray: 1,
            // mesma direcao nas duas fases: ao apagar, a ponta retrai de
            // volta ao inicio do traco — o pincel "desescrevendo"
            strokeDashoffset: 1 - visivel,
          };
          return (
            <g key={i}>
              {/* base úmida, mais larga e translúcida */}
              <path
                {...comum}
                strokeWidth={pincel * t.peso}
                strokeOpacity={0.55}
              />
              {/* fio central denso */}
              <path {...comum} strokeWidth={pincel * t.peso * 0.62} />
            </g>
          );
        })}
      </g>
    </svg>
  );
};
