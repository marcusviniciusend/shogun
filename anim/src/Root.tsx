import React from "react";
import { AbsoluteFill, Composition } from "remotion";
import { SamuraiCorrendo, STRIDE } from "./SamuraiCorrendo";
import { ShogunKanji } from "./ShogunKanji";
import "./index.css";

/**
 * O mesmo desenho, renderizado uma vez por tema do app:
 *
 *   *Washi  — kanji em sumi (#211e1a), para o tema claro
 *   *Sumi   — kanji em bengara (#d4664f), para o tema escuro
 *
 * Os valores vêm do `desktop/src/App.css`: são exatamente a cor que o kanji
 * estático do cabeçalho tem em cada tema, para o vídeo não destoar dele ao
 * entrar no estado "pensando".
 *
 * Duas composições, mesmo desenho:
 *
 * SplashShogun    800x400, 30fps, 168 frames (5,6s)
 *                 escrita 8–104, sustenta até 128, desescreve 128–160
 *
 * IndicadorShogun 320x160, 30fps, 66 frames (2,2s)
 *                 escrita 2–40, sustenta até 48, desescreve 48–63
 *
 * Fundo transparente — o alpha vai no render (WebM/VP9 yuva420p).
 */

/** Cores do kanji, uma por tema do app. Espelham `App.css`. */
const SUMI = "#211e1a";
const BENGARA_ESCURO = "#d4664f";

const Splash =
  (cor: string): React.FC =>
  () => (
    <AbsoluteFill style={{ padding: 24 }}>
      <ShogunKanji
        inicioEscrita={8}
        duracaoEscrita={96}
        inicioApaga={128}
        duracaoApaga={32}
        pincel={5}
        cor={cor}
      />
    </AbsoluteFill>
  );

const Indicador =
  (cor: string): React.FC =>
  () => (
    <AbsoluteFill style={{ padding: 8 }}>
      <ShogunKanji
        inicioEscrita={2}
        duracaoEscrita={38}
        inicioApaga={48}
        duracaoApaga={15}
        pincel={5.6}
        cor={cor}
      />
    </AbsoluteFill>
  );

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="SplashWashi"
        component={Splash(SUMI)}
        durationInFrames={168}
        fps={30}
        width={800}
        height={400}
      />
      <Composition
        id="SplashSumi"
        component={Splash(BENGARA_ESCURO)}
        durationInFrames={168}
        fps={30}
        width={800}
        height={400}
      />
      <Composition
        id="SamuraiCorrendo"
        component={SamuraiCorrendo}
        durationInFrames={STRIDE * 4}
        fps={30}
        width={400}
        height={280}
      />
      <Composition
        id="IndicadorWashi"
        component={Indicador(SUMI)}
        durationInFrames={66}
        fps={30}
        width={320}
        height={160}
      />
      <Composition
        id="IndicadorSumi"
        component={Indicador(BENGARA_ESCURO)}
        durationInFrames={66}
        fps={30}
        width={320}
        height={160}
      />
    </>
  );
};
