import splashSumi from "../assets/splash-sumi.webm";
import splashWashi from "../assets/splash-washi.webm";

interface Props {
  onFim: () => void;
  /** Qual render do kanji usar — a cor esta gravada no video, nao no CSS. */
  tema: "washi" | "sumi";
}

/**
 * Tela de abertura: 将軍 escrito a pincel (WebM com alpha, ~5,6s).
 *
 * Roda uma vez e chama onFim ao terminar; um clique pula. Quem prefere
 * menos movimento (prefers-reduced-motion) nunca chega aqui — o App nem
 * monta o splash.
 */
export function Splash({ onFim, tema }: Props) {
  return (
    <div
      className="splash"
      onClick={onFim}
      role="presentation"
      title="Clique para pular"
    >
      <video
        src={tema === "sumi" ? splashSumi : splashWashi}
        autoPlay
        muted
        playsInline
        onEnded={onFim}
        onError={onFim}
      />
    </div>
  );
}
