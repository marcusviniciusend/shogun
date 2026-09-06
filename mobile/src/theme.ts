/**
 * Paleta e espacamentos compartilhados pelas telas.
 *
 * Espelha a paleta "A1 washi cru" do desktop (`desktop/src/App.css`): tinta
 * sumi sobre papel, quatro tons fechados. O bengara e acento RARO — aparece
 * so em erro e atencao critica, nunca decorativamente.
 *
 * Os nomes dos tokens sao os mesmos de antes de proposito: nenhuma tela
 * precisou mudar. O que mudou foi so o valor de cada um.
 */

/** Tons crus da paleta, na mesma nomenclatura do desktop. */
const papel = "#ede6d4"; // washi cru — fundo
const tinta = "#211e1a"; // sumi — texto e enfase
const hai = "#7a7264"; // cinza-cinza — secundario
const bengara = "#a63d2f"; // SO erro/atencao critica

export const cores = {
  fundo: papel,
  // O desktop nao tem cor de superficie: usa tinta em alpha baixo sobre o
  // papel, em vez de um segundo tom solido.
  superficie: "rgba(33, 30, 26, 0.05)",
  borda: "rgba(33, 30, 26, 0.28)",
  texto: tinta,
  textoFraco: hai,

  // Era um dourado (#c9a227) sem equivalente no desktop, usado como fundo de
  // botao e cor da aba ativa. Vira tinta: a enfase e o peso do traco, nao uma
  // cor a mais. `botaoTexto` e `balaoTextoUsuario` ja usam `fundo`, entao o
  // par fica papel sobre tinta — o mesmo botao escuro do desktop.
  destaque: tinta,

  // O aviso de erro do mobile e uma caixa; o desktop resolve so com cor. Para
  // nao reestruturar o componente, a caixa fica em bengara lavado.
  //
  // 6% e nao 10%: a 10% o bengara em cima cai para 4.41:1, abaixo do minimo
  // AA de 4.5. A 6% sobe para 4.67:1.
  erroFundo: "rgba(166, 61, 47, 0.06)",
  erroBorda: "rgba(166, 61, 47, 0.38)",
  erroTexto: bengara,

  // Status de agente: no desktop o marcador normal e `hai` e SO o estado de
  // erro recebe bengara. O verde some — nao existe na paleta fechada.
  ok: hai,
  falha: bengara,
};

export const espacamento = {
  s: 6,
  m: 12,
  g: 20,
};
