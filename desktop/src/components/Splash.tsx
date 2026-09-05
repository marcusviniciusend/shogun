import splashUrl from "../assets/splash-shogun.webm";

interface Props {
  onFim: () => void;
}

/**
 * Tela de abertura: 将軍 escrito a pincel (WebM com alpha, ~5,6s).
 *
 * Roda uma vez e chama onFim ao terminar; um clique pula. Quem prefere
 * menos movimento (prefers-reduced-motion) nunca chega aqui — o App nem
 * monta o splash.
 */
export function Splash({ onFim }: Props) {
  return (
    <div
      className="splash"
      onClick={onFim}
      role="presentation"
      title="Clique para pular"
    >
      <video
        src={splashUrl}
        autoPlay
        muted
        playsInline
        onEnded={onFim}
        onError={onFim}
      />
    </div>
  );
}
