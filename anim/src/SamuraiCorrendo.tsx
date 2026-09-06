import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { TINTA } from "./kanji";

/**
 * Samurai correndo — silhueta procedural em pinceladas sumi-e.
 *
 * Cinematica direta: cada membro e um par de segmentos cujo angulo e uma
 * funcao senoidal da fase do passo. O estilo e "dash" de anime (tronco
 * inclinado, passadas longas), que le melhor em silhueta pequena do que
 * uma corrida anatomicamente fiel. Mesma linguagem do kanji: tracos com
 * ponta arredondada, duas passadas (base umida + fio denso) e textura de
 * feTurbulence.
 *
 * O ciclo do passo dura STRIDE frames; a composicao usa um multiplo
 * inteiro disso, entao o loop fecha sem emenda.
 */

const G = Math.PI / 180;

interface Ponto {
  x: number;
  y: number;
}

/** Extremidade de um segmento: angulo 0 = para baixo, positivo = frente (+x). */
function seg(origem: Ponto, anguloDeg: number, comprimento: number): Ponto {
  const a = anguloDeg * G;
  return {
    x: origem.x + comprimento * Math.sin(a),
    y: origem.y + comprimento * Math.cos(a),
  };
}

function caminho(pontos: Ponto[]): string {
  return pontos
    .map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`)
    .join(" ");
}

/** Um traco de pincel: base umida larga + fio central denso. */
const Pincel: React.FC<{ d: string; w: number }> = ({ d, w }) => (
  <>
    <path d={d} stroke={TINTA} strokeWidth={w} strokeOpacity={0.5} fill="none"
      strokeLinecap="round" strokeLinejoin="round" />
    <path d={d} stroke={TINTA} strokeWidth={w * 0.62} fill="none"
      strokeLinecap="round" strokeLinejoin="round" />
  </>
);

/** Frames por passada (ciclo completo de corrida = 2 passadas de perna). */
export const STRIDE = 16;

export const SamuraiCorrendo: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  void fps;

  const p = (frame / STRIDE) * 2 * Math.PI; // fase do ciclo

  // pelve: origem da figura, com trote vertical (2x por ciclo)
  const pelve: Ponto = { x: 0, y: 3.2 * Math.abs(Math.sin(p)) - 1.6 };

  const lean = -20; // tronco lancado a frente
  const ombro = seg(pelve, lean, -40); // -len = para cima
  const pescoco = seg(ombro, lean, -8);
  const cabeca = seg(pescoco, lean, -8);

  // pernas: quadril oscila; joelho flexiona na recuperacao, estende no apoio
  const perna = (fase: number) => {
    const quadril = -14 + 46 * Math.sin(fase);
    const flexao = Math.max(10, 78 * Math.sin(fase - 1.9) + 40);
    const joelho = seg(pelve, quadril, 30);
    const pe = seg(joelho, quadril - flexao, 30);
    return [pelve, joelho, pe];
  };

  // bracos: fase oposta as pernas, cotovelo travado dobrado
  const braco = (fase: number) => {
    const upper = -6 + 40 * Math.sin(fase);
    const cotovelo = seg(ombro, upper, 24);
    const mao = seg(cotovelo, upper - 88, 22);
    return [ombro, cotovelo, mao];
  };

  const pernaFrente = perna(p);
  const pernaTras = perna(p + Math.PI);
  const bracoFrente = braco(p + Math.PI);
  const bracoTras = braco(p);

  // katana embainhada: sai do quadril apontando para tras e para baixo,
  // bem separada das pernas para nao ler como terceiro membro
  const katanaA = seg(pelve, lean, -10);
  const katanaB = seg(katanaA, -118, 34);

  // (sem aba de kimono: nas poses estendidas ela lia como terceira perna)

  // coque (chonmage): atras e acima da cabeca
  const coque = seg(cabeca, lean - 155, 11);

  // linhas de velocidade atras da figura, correndo para tras em loop
  const desloc = ((frame % STRIDE) / STRIDE) * 26;
  const linhas = [
    { y: -46, len: 22, o: 0.35 },
    { y: -24, len: 30, o: 0.28 },
  ];

  return (
    <svg
      viewBox="-112 -104 224 186"
      style={{ width: "100%", height: "100%" }}
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <filter id="tinta-s" x="-20%" y="-20%" width="140%" height="140%">
          <feTurbulence type="fractalNoise" baseFrequency="0.11" numOctaves="2"
            seed="11" result="ruido" />
          <feDisplacementMap in="SourceGraphic" in2="ruido" scale="2" />
        </filter>
      </defs>
      <g filter="url(#tinta-s)">
        {/* linhas de velocidade */}
        {linhas.map((l, i) => (
          <path
            key={i}
            d={`M${-38 - desloc - i * 6},${l.y} h${-l.len}`}
            stroke={TINTA}
            strokeWidth={2.4}
            strokeOpacity={l.o}
            strokeLinecap="round"
            fill="none"
          />
        ))}

        {/* perna e braco do lado de tras, mais claros (profundidade) */}
        <g opacity={0.55}>
          <Pincel d={caminho(pernaTras)} w={7} />
          <Pincel d={caminho(bracoTras)} w={5.5} />
        </g>

        {/* katana atras do corpo */}
        <path d={caminho([katanaA, katanaB])} stroke={TINTA} strokeWidth={2.8}
          strokeLinecap="round" fill="none" />
        <circle cx={katanaA.x} cy={katanaA.y} r={2.2} fill={TINTA} />

        {/* tronco (kimono): traco grosso pelve->ombro, com pescoco */}
        <Pincel d={caminho([{ x: pelve.x, y: pelve.y + 3 }, ombro])} w={15} />
        <path d={caminho([ombro, cabeca])} stroke={TINTA} strokeWidth={5}
          strokeLinecap="round" fill="none" />

        {/* perna e braco da frente */}
        <Pincel d={caminho(pernaFrente)} w={7} />
        <Pincel d={caminho(bracoFrente)} w={5.5} />

        {/* cabeca + coque */}
        <circle cx={cabeca.x} cy={cabeca.y} r={7.5} fill={TINTA} />
        <circle cx={coque.x} cy={coque.y} r={3.2} fill={TINTA} />
        <path d={caminho([cabeca, coque])} stroke={TINTA} strokeWidth={2.6}
          strokeLinecap="round" fill="none" />
      </g>
    </svg>
  );
};
